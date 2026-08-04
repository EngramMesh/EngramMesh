# RFC: Execution HTTP API

- **Status**: Approved
- **Date**: 2026-08-04
- **Type**: Public API / implementation design summary
- **Authority**: `docs/superpowers/specs/2026-08-04-execution-http-api-design.md` (spec is source of truth)
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Temporal runtime adapter, OIDC tenant context, Episode HTTP APIs

## 1. Background

Runtime handlers exist and are wired through `AppRuntime`, but external integrators
cannot start or observe executions over HTTP. Runtime authorization still denies
staging/production traffic until OIDC is extended to runtime actions.

## 2. Goals

1. `POST /v1/tenants/{tenant_id}/executions` — start execution with idempotency
2. `GET /v1/tenants/{tenant_id}/executions/{execution_id}` — read snapshot
3. `POST /v1/tenants/{tenant_id}/executions/{execution_id}/cancel` — cancel execution
4. `TenantScopedRuntimeAuthorization` when `oidc.enabled=true`
5. JSON Schema contracts, structured errors, tests, bilingual documentation

## 3. Non-goals

Execution list API, PostgreSQL execution store (Slice 4), SSE streaming, runtime
Outbox events, handler semantic changes.

## 4. API summary

See spec §5. Key points:

- Start returns `201`/`200` with `created` flag (mirrors episode ingest)
- Snapshot responses share one envelope across start/get/cancel
- `404 execution_not_found` for all scope/id mismatches (no existence leaks)
- `409` for idempotency conflict and invalid cancel transitions
- `503` for `runtime_disabled` and `orchestration_unavailable`

## 5. Architecture

```text
HTTP → bootstrap/http (schemas, mappers, errors)
     → execution_auth_context (OIDC)
     → StartExecution / GetExecutionSnapshot / CancelExecution handlers
     → OrchestratorPort
```

`create_runtime_authorization` selects `TenantScopedRuntimeAuthorization` when OIDC
is enabled.

## 6. JSON Schema

| File | Purpose |
|------|---------|
| `start-execution-request.schema.json` | Start body |
| `cancel-execution-request.schema.json` | Cancel body |
| `execution-snapshot-response.schema.json` | Snapshot body |
| `start-execution-response.schema.json` | Snapshot + `created` |

## 7. Testing

Unit (mappers, auth), HTTP integration (in-memory orchestrator), OIDC integration,
contract tests, composed start→get→cancel E2E. See spec §9.

## 8. Acceptance

See spec §10.

## 9. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅
③ OIDC tenant context                            ✅
④ Temporal runtime adapter                       ✅
   ④a Execution HTTP API + OIDC runtime auth      ← this slice
   ④b Execution snapshot store (PostgreSQL)      ← Slice 4
⑤ Claim extraction processor                     ← Phase 2 entry
```
