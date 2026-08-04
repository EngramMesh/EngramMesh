# Execution HTTP API — Design Spec

- **Status**: Approved
- **Date**: 2026-08-04
- **Type**: Public API / implementation design
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Temporal runtime adapter (Slice 2), OIDC tenant context, Episode HTTP APIs

## 1. Background

EngramMesh exposes durable execution through three application handlers
(`StartExecutionHandler`, `GetExecutionSnapshotHandler`, `CancelExecutionHandler`)
wired by `AppRuntime`, but external integrators cannot start or observe executions
over HTTP. Runtime authorization still uses `EnvironmentGatedRuntimeAuthorization`,
which denies all staging/production traffic.

This slice closes Phase 1 item **④a**: expose the existing runtime handlers via REST
on the same Control API, and wire **OIDC-backed runtime authorization** so
non-development environments can call execution endpoints with the same tenant-bound
Bearer JWT model as Episode APIs.

Application handlers and `OrchestratorPort` semantics are **unchanged**. HTTP is a
thin transport adapter.

## 2. Goals

1. `POST /v1/tenants/{tenant_id}/executions` — start or idempotently replay an execution
2. `GET /v1/tenants/{tenant_id}/executions/{execution_id}` — read one execution snapshot
3. `POST /v1/tenants/{tenant_id}/executions/{execution_id}/cancel` — cancel an execution
4. `TenantScopedRuntimeAuthorization` when `oidc.enabled=true`; environment gate when `false`
5. JSON Schema contracts under `packages/contracts/jsonschema/runtime/v1/`
6. Structured HTTP error mapping for all runtime domain/application errors used by handlers
7. Unit, HTTP integration, OIDC integration, contract, and composed in-memory E2E tests
8. Bilingual `services/README.md` and `services/README.zh-CN.md` updates
9. RFC summary at `docs/rfcs/2026-08-04-execution-http-api.md`

## 3. Non-goals

- Execution list, search, or cursor pagination (requires Slice 4 PostgreSQL store)
- SSE, WebSocket, or long-polling status streams
- PostgreSQL execution snapshot store or runtime Outbox events (Slice 4)
- LangGraph, PlannerPort, AgentEnginePort, full Plan DAG execution
- Claim extraction (Phase 2)
- OpenAPI publish governance, OpenTelemetry, PostgreSQL RLS
- Changing handler semantics, `OrchestratorPort` contract, or workflow behavior
- `/ready` gating on `runtime_enabled` (execution routes return `503 runtime_disabled` instead)

## 4. Architecture

### 4.1 Dependency direction

```text
HTTP Request (FastAPI, existing create_app)
  → bootstrap/http/schemas.py              # Pydantic DTOs
  → bootstrap/http/mappers.py              # DTO → application commands/queries
  → bootstrap/auth/dependencies.py         # execution_auth_context (OIDC)
  → StartExecutionHandler /
    GetExecutionSnapshotHandler /
    CancelExecutionHandler
  → OrchestratorPort (InMemory | Temporal)
```

- FastAPI and uvicorn remain in `bootstrap/http/` and `bootstrap/server.py`.
- HTTP accesses handlers only through `AppRuntime.start_execution_handler()`,
  `get_execution_snapshot_handler()`, and `cancel_execution_handler()`.
- No direct imports from `modules/runtime/adapters/`.
- `create_app(runtime, *, lifespan, token_verifier=...)` remains the single factory.

### 4.2 Authorization wiring

Update `create_runtime_authorization(settings)` in `bootstrap/infrastructure.py`:

| `oidc.enabled` | Implementation | Behavior |
|----------------|----------------|----------|
| `false` | `EnvironmentGatedRuntimeAuthorization` | Allow dev/test only (unchanged) |
| `true` | `TenantScopedRuntimeAuthorization` | `actor_id == principal.actor_id` and `scope.tenant_id == principal.tenant_id` |

`TenantScopedRuntimeAuthorization` mirrors `TenantScopedMemoryAuthorization` and
uses `current_principal()` from `bootstrap/auth/context.py`. It applies to all three
runtime actions: `start_execution`, `get_execution`, `cancel_execution`.

`AppRuntime` continues to call `create_runtime_authorization(settings)` at startup;
no handler signature changes.

### 4.3 HTTP auth context

Add `execution_auth_context` to `bootstrap/auth/dependencies.py` with the same
semantics as `episode_auth_context`:

- `oidc.enabled=false` → yield `None`; caller supplies `actor_id` in body/query
- `oidc.enabled=true` → require Bearer JWT, bind principal for request duration

Reuse `_resolve_actor_id` / `resolve_query_actor_id` from `bootstrap/http/mappers.py`.

### 4.4 Scope and tenant validation

Follow Episode HTTP conventions:

1. Path `tenant_id` must match body `scope.tenant_id` on mutating requests.
2. `GET` uses query parameters for scope narrowing (`subject_id` required;
   `workspace_id`, `agent_id` optional).
3. Mapper assembles domain `MemoryScope` including path `tenant_id`.

## 5. API specification

### 5.1 Start execution

```http
POST /v1/tenants/{tenant_id}/executions
X-Correlation-Id: {uuid}              # optional; generated if absent
Authorization: Bearer {jwt}           # required when oidc.enabled=true
Content-Type: application/json
```

**Request body** (`StartExecutionRequest`):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `actor_id` | uuid | conditional | Required when OIDC off; forbidden when OIDC on |
| `scope` | object | yes | `tenant_id`, `subject_id`, optional `workspace_id`, `agent_id` |
| `objective_ref` | uuid | yes | Artifact reference for execution objective |
| `root_agent_id` | uuid | yes | Root agent definition id |
| `memory_query` | object \| null | yes | Optional cognitive-memory evidence query |
| `budget` | object | yes | Token/cost/deadline limits |
| `idempotency_key` | string | yes | Non-blank; start-scoped idempotency |

**`memory_query` object** (when not null):

| Field | Type | Required |
|-------|------|----------|
| `query_id` | string | yes |
| `scope` | object | yes | Must match execution `scope` (mapper validates) |
| `text` | string | yes |
| `valid_at` | datetime \| null | no |
| `recorded_at` | datetime \| null | no |
| `limit` | int | no | default 10; must be positive |

**`budget` object**:

| Field | Type | Required |
|-------|------|----------|
| `max_input_tokens` | int | yes | ≥ 0 |
| `max_output_tokens` | int | yes | ≥ 0 |
| `max_cost_micros` | int | yes | ≥ 0 |
| `deadline` | datetime | yes | timezone-aware |

**Response** (`StartExecutionResponse` = snapshot + `created` flag):

| Status | Condition |
|--------|-----------|
| `201` | `created=true` (first start for idempotency key) |
| `200` | `created=false` (idempotent replay) |
| `401` | Missing/invalid Bearer token (OIDC on) |
| `403` | `execution_authorization_denied` or `tenant_access_denied` |
| `409` | `execution_idempotency_conflict` |
| `422` | Validation error, tenant mismatch, actor_id rules |
| `503` | `runtime_disabled`, `orchestration_unavailable`, OIDC misconfiguration |

### 5.2 Get execution snapshot

```http
GET /v1/tenants/{tenant_id}/executions/{execution_id}
    ?subject_id={uuid}
    &workspace_id={string}           # optional
    &agent_id={uuid}                  # optional
    &actor_id={uuid}                  # required when oidc.enabled=false
Authorization: Bearer {jwt}           # required when oidc.enabled=true
```

**Response** (`ExecutionSnapshotResponse`):

| Status | Condition |
|--------|-----------|
| `200` | Snapshot found in exact scope |
| `401` | OIDC auth failure |
| `403` | `execution_authorization_denied` |
| `404` | `execution_not_found` |
| `422` | Invalid UUIDs or scope parameters |
| `503` | `runtime_disabled`, `orchestration_unavailable` |

**404 policy**: unknown `execution_id`, wrong tenant, wrong `subject_id`, or optional
scope narrowing mismatch all return `404 execution_not_found`. Never `403` for
cross-tenant or cross-scope existence leaks.

### 5.3 Cancel execution

```http
POST /v1/tenants/{tenant_id}/executions/{execution_id}/cancel
X-Correlation-Id: {uuid}              # optional
Authorization: Bearer {jwt}           # required when oidc.enabled=true
Content-Type: application/json
```

**Request body** (`CancelExecutionRequest`):

| Field | Type | Required |
|-------|------|----------|
| `actor_id` | uuid | conditional |
| `scope` | object | yes |
| `idempotency_key` | string | yes | Cancel-scoped idempotency (handler contract) |

Path `execution_id` is authoritative; body does not repeat it.

**Response** (`ExecutionSnapshotResponse` without `created`):

| Status | Condition |
|--------|-----------|
| `200` | Cancel accepted or execution already terminal (`cancelled`/`failed`) |
| `401` | OIDC auth failure |
| `403` | `execution_authorization_denied` |
| `404` | `execution_not_found` |
| `409` | `invalid_execution_transition` (e.g. already `succeeded`) |
| `422` | Validation error |
| `503` | `runtime_disabled`, `orchestration_unavailable` |

### 5.4 Snapshot response shape

All successful execution responses return the same snapshot envelope:

```json
{
  "execution_id": "uuid",
  "scope": {
    "tenant_id": "uuid",
    "subject_id": "uuid",
    "workspace_id": "string | null",
    "agent_id": "uuid | null"
  },
  "revision": 1,
  "status": "pending",
  "plan_revision": null,
  "node_statuses": { "node-uuid": "pending" },
  "suspension": null,
  "result_ref": null,
  "failure": null,
  "updated_at": "2026-08-04T05:00:00Z"
}
```

`StartExecutionResponse` adds `"created": true | false`.

**`suspension`** (when not null):

| Field | Type |
|-------|------|
| `request_id` | string |
| `idempotency_key` | string |
| `execution_id` | uuid |
| `node_id` | uuid \| null |
| `kind` | `approval` \| `input` \| `external_event` |
| `request_ref` | uuid |
| `requested_at` | datetime |
| `expires_at` | datetime |

**`failure`** (when not null):

| Field | Type |
|-------|------|
| `category` | failure category enum |
| `code` | string |
| `message` | string |
| `details_ref` | uuid \| null |

**`status` and `node_statuses` values** match `ExecutionStatus` / `NodeStatus` enums in
`modules/runtime/domain/model.py` (lowercase snake strings).

## 6. Error mapping

Register handlers in `bootstrap/http/errors.py`:

| Application / domain error | HTTP | `error.code` | Message |
|----------------------------|------|--------------|---------|
| `ExecutionAuthorizationDenied` | 403 | `execution_authorization_denied` | execution is not authorized |
| `ExecutionNotFound` | 404 | `execution_not_found` | execution not found |
| `ExecutionIdempotencyConflict` | 409 | `execution_idempotency_conflict` | idempotency key conflicts with an existing execution |
| `InvalidExecutionTransition` | 409 | `invalid_execution_transition` | execution transition is not allowed |
| `OrchestrationUnavailable` | 503 | `orchestration_unavailable` | orchestration backend is unavailable |
| `ConfigurationError` (`runtime_disabled`) | 503 | `service_unavailable` | service is unavailable |
| `TenantMismatchError` | 422 | `validation_error` | (details on `scope.tenant_id`) |
| `ActorIdRequiredError` | 422 | `actor_id_required` | |
| `ActorIdNotAllowedError` | 422 | `actor_id_not_allowed` | |

Reuse existing OIDC handlers (`authentication_required`, `invalid_token`,
`tenant_access_denied`) and generic handlers (`validation_error`, `internal_error`).

`ConfigurationError` details must surface `runtime_disabled` in the `details` array
(same pattern as `memory_disabled`).

## 7. JSON Schema contracts

Publish under `packages/contracts/jsonschema/runtime/v1/`:

| File | Purpose |
|------|---------|
| `start-execution-request.schema.json` | `POST .../executions` body |
| `cancel-execution-request.schema.json` | `POST .../cancel` body |
| `execution-snapshot-response.schema.json` | Snapshot response (GET, cancel, start without `created`) |
| `start-execution-response.schema.json` | Snapshot + required `created` boolean |

Reuse a shared `$defs/httpMemoryScope` (include `tenant_id`) consistent with memory
HTTP schemas. `memory_query.scope` uses the same scope def.

Contract tests validate Pydantic serialization against these schemas (mirror episode
read contract test style).

## 8. File changes (implementation scope)

| Area | Files |
|------|-------|
| Auth | `bootstrap/infrastructure.py`, `bootstrap/auth/dependencies.py` |
| HTTP | `bootstrap/http/app.py`, `schemas.py`, `mappers.py`, `errors.py` |
| Contracts | `packages/contracts/jsonschema/runtime/v1/*.schema.json` |
| Tests | `tests/unit/bootstrap/`, `tests/unit/bootstrap/http/`, `tests/integration/http/` |
| Docs | `services/README.md`, `services/README.zh-CN.md`, `docs/rfcs/2026-08-04-execution-http-api.md` |

No changes to `modules/runtime/application/*` handler logic unless a test-only gap
is discovered during implementation.

## 9. Testing

### 9.1 Unit

- Mappers: start/get/cancel command construction; tenant mismatch; actor_id rules;
  memory_query scope match validation
- `TenantScopedRuntimeAuthorization`: allow matching principal; deny mismatch
- Pydantic schemas: reject extra fields, invalid enums

### 9.2 HTTP integration (in-memory orchestrator, `runtime_enabled=true`)

| Scenario | Expected |
|----------|----------|
| POST start → 201 + `created=true` | Happy path |
| POST start replay same idempotency key → 200 + `created=false` | Idempotency |
| POST start conflicting fingerprint → 409 | Idempotency conflict |
| GET snapshot after start → 200 | Read path |
| GET unknown id → 404 | Not found |
| GET wrong subject → 404 | Scope isolation |
| POST cancel running execution → 200 `cancelled` | Cancel path |
| POST cancel succeeded execution → 409 | Invalid transition |
| `runtime_enabled=false` → 503 | Configuration gate |
| staging + `oidc.enabled=false` → 403 | Environment gate regression |

### 9.3 OIDC integration

- Bearer JWT on start/get/cancel when `oidc.enabled=true`
- `actor_id` in body/query rejected when principal present
- Path tenant mismatch with JWT tenant → 403 `tenant_access_denied`
- Missing Bearer → 401

### 9.4 Composed E2E

Single HTTP test flow: start → poll/get snapshot until terminal or `running` → cancel
(using in-memory orchestrator; no Temporal required for default CI).

### 9.5 Contract

- Response bodies validate against JSON Schema fixtures
- Request schema files have contract tests with golden examples

## 10. Acceptance criteria

1. `uv run --python 3.14 --project services pytest services/tests -q` passes (temporal excluded by default).
2. `uv run --python 3.14 --project services ruff check services/src services/tests` passes.
3. `uv run --python 3.14 --project services mypy services/src` passes.
4. Local curl (dev, OIDC off): start → get → cancel succeeds against in-memory runtime.
5. OIDC integration tests pass with injected `token_verifier`.
6. No adapter imports in `bootstrap/http/`.
7. Bilingual services README documents endpoints, errors, OIDC behavior, and `runtime_disabled`.
8. RFC summary committed and references this spec as authority.

## 11. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅
③ OIDC tenant context                            ✅
④ Temporal runtime adapter                       ✅
   ④a Execution HTTP API + OIDC runtime auth      ← this slice
   ④b Execution snapshot store (PostgreSQL)      ← Slice 4
⑤ Claim extraction processor                     ← Phase 2 entry
```

## 12. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Large snapshot payloads over HTTP | v1 returns full domain snapshot; large refs stay artifact UUIDs only |
| Cross-tenant execution existence leak | Uniform `404` for scope/id mismatches |
| OIDC/runtime auth drift from memory | Shared `TenantScoped*` pattern and mapper helpers |
| Temporal unavailable in production | Map `OrchestrationUnavailable` → 503 with stable code |
| `app.py` growth | Optional `execution_routes` module; same factory contract |
