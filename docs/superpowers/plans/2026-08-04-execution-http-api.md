# Execution HTTP API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `StartExecution`, `GetExecutionSnapshot`, and `CancelExecution` handlers via REST on the existing Control API, with OIDC-backed runtime authorization when `oidc.enabled=true`.

**Architecture:** Thin HTTP adapter in `bootstrap/http/` maps Pydantic DTOs to existing application commands/queries. `TenantScopedRuntimeAuthorization` mirrors memory OIDC wiring. No changes to runtime application handlers or orchestrator adapters.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, httpx (ASGI tests), jsonschema Draft 2020-12, existing `AppRuntime` composition.

## Global Constraints

- Python **3.14**; run all commands from repo root with `uv run --python 3.14 --project services ...`
- Domain/application layers must **not** import FastAPI or adapters
- HTTP accesses runtime only via `AppRuntime.start_execution_handler()`, `get_execution_snapshot_handler()`, `cancel_execution_handler()`
- Commit messages in **English** with DCO: `git commit -s`
- Verification before claiming done: `pytest services/tests -q`, `ruff check services/src services/tests`, `mypy services/src`
- Default CI excludes `@pytest.mark.temporal`; do not add temporal-marked tests to default suite
- Match existing Episode HTTP patterns: path/body tenant double-check, `error_envelope`, `201`/`200` idempotency for start

---

## File map

| File | Responsibility |
|------|----------------|
| `services/src/engrammesh/bootstrap/infrastructure.py` | `TenantScopedRuntimeAuthorization`, `create_runtime_authorization` |
| `services/src/engrammesh/bootstrap/auth/dependencies.py` | `execution_auth_context` |
| `services/src/engrammesh/bootstrap/http/schemas.py` | Execution request/response Pydantic models |
| `services/src/engrammesh/bootstrap/http/mappers.py` | DTO ↔ application command/query mapping, snapshot serialization |
| `services/src/engrammesh/bootstrap/http/errors.py` | Runtime exception → HTTP status mapping |
| `services/src/engrammesh/bootstrap/http/app.py` | Three execution routes |
| `packages/contracts/jsonschema/runtime/v1/*.schema.json` | Public HTTP contracts |
| `services/tests/integration/http/execution_http_helpers.py` | Shared fixtures and payload builders |
| `services/tests/integration/http/test_execution_http.py` | Non-OIDC HTTP integration |
| `services/tests/integration/http/test_oidc_execution_http.py` | OIDC HTTP integration |
| `services/tests/unit/bootstrap/http/test_execution_http_mappers.py` | Mapper unit tests |
| `services/tests/contract/test_execution_http_schemas.py` | JSON Schema contract tests |
| `services/README.md`, `services/README.zh-CN.md` | Bilingual API docs |

---

### Task 1: TenantScopedRuntimeAuthorization

**Files:**
- Modify: `services/src/engrammesh/bootstrap/infrastructure.py`
- Modify: `services/tests/unit/bootstrap/test_runtime_infrastructure.py`
- Create: `services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py`

**Interfaces:**
- Consumes: `current_principal()`, `RuntimeAuthorizationRequest`, `MemoryScope` (existing)
- Produces: `TenantScopedRuntimeAuthorization.authorize(request) -> bool`; `create_runtime_authorization(settings)` returns `TenantScopedRuntimeAuthorization` when `settings.oidc.enabled` is true

- [ ] **Step 1: Write failing tests**

Create `services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py`:

```python
from __future__ import annotations

from uuid import UUID

import pytest

from engrammesh.bootstrap.auth.context import bind_principal, reset_principal
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedRuntimeAuthorization,
    TenantScopedRuntimeAuthorization,
    create_runtime_authorization,
)
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
TENANT_ID = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
OTHER_TENANT_ID = TenantId(UUID("e63173e8-8f03-4f34-beac-2020676684c0"))


def _runtime_auth_request(
    *,
    actor_id: SubjectId = ACTOR_ID,
    tenant_id: TenantId = TENANT_ID,
    action: str = "start_execution",
) -> RuntimeAuthorizationRequest:
    return RuntimeAuthorizationRequest(
        actor_id=actor_id,
        scope=MemoryScope(tenant_id=tenant_id, subject_id=SubjectId(UUID(int=1))),
        action=action,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_tenant_scoped_runtime_authorization_allows_matching_principal() -> None:
    authorization = TenantScopedRuntimeAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(_runtime_auth_request())
    finally:
        reset_principal(token)
    assert allowed is True


@pytest.mark.asyncio
async def test_tenant_scoped_runtime_authorization_denies_other_tenant() -> None:
    authorization = TenantScopedRuntimeAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(
            _runtime_auth_request(tenant_id=OTHER_TENANT_ID)
        )
    finally:
        reset_principal(token)
    assert allowed is False


def test_create_runtime_authorization_selects_tenant_scoped_when_oidc_enabled() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
            "oidc": {"enabled": True},
        }
    )
    authorization = create_runtime_authorization(settings)
    assert isinstance(authorization, TenantScopedRuntimeAuthorization)


def test_create_runtime_authorization_selects_environment_gate_when_oidc_disabled() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
        }
    )
    authorization = create_runtime_authorization(settings)
    assert isinstance(authorization, EnvironmentGatedRuntimeAuthorization)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py -v`

Expected: FAIL — `TenantScopedRuntimeAuthorization` import error

- [ ] **Step 3: Implement authorization**

In `services/src/engrammesh/bootstrap/infrastructure.py`, add after `TenantScopedMemoryAuthorization`:

```python
@final
class TenantScopedRuntimeAuthorization:
    async def authorize(self, request: RuntimeAuthorizationRequest) -> bool:
        principal = current_principal()
        return (
            request.actor_id == principal.actor_id
            and request.scope.tenant_id == principal.tenant_id
        )
```

Update `create_runtime_authorization`:

```python
def create_runtime_authorization(settings: AppSettings) -> RuntimeAuthorizationPort:
    if settings.oidc.enabled:
        return TenantScopedRuntimeAuthorization()
    return EnvironmentGatedRuntimeAuthorization(settings.environment)
```

Add `from engrammesh.bootstrap.auth.context import current_principal` if not already imported.

Update `test_create_runtime_authorization_uses_environment_gate` in `test_runtime_infrastructure.py` — it remains valid when OIDC is off.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py services/tests/unit/bootstrap/test_runtime_infrastructure.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/src/engrammesh/bootstrap/infrastructure.py \
  services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py
git commit -s -m "feat: add tenant-scoped runtime authorization for OIDC"
```

---

### Task 2: Execution HTTP Pydantic schemas

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/schemas.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_schemas.py`

**Interfaces:**
- Produces: `BudgetRequest`, `MemoryQueryRequest`, `StartExecutionRequest`, `CancelExecutionRequest`, `ScopeResponse` (reuse), `FailureResponse`, `SuspensionResponse`, `ExecutionSnapshotResponse`, `StartExecutionResponse`

- [ ] **Step 1: Write failing schema tests**

Create `services/tests/unit/bootstrap/http/test_execution_http_schemas.py`:

```python
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.http.schemas import (
    BudgetRequest,
    StartExecutionRequest,
    ScopeRequest,
)

TENANT = UUID("53dad495-7915-439a-b03a-379452a1aa86")
SUBJECT = UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45")
OBJECTIVE = UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")
ROOT_AGENT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ACTOR = UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6")
DEADLINE = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _scope() -> ScopeRequest:
    return ScopeRequest(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
    )


def test_start_execution_request_accepts_valid_body() -> None:
    body = StartExecutionRequest(
        actor_id=ACTOR,
        scope=_scope(),
        objective_ref=OBJECTIVE,
        root_agent_id=ROOT_AGENT,
        memory_query=None,
        budget=BudgetRequest(
            max_input_tokens=1000,
            max_output_tokens=500,
            max_cost_micros=100_000,
            deadline=DEADLINE,
        ),
        idempotency_key="exec-1",
    )
    assert body.idempotency_key == "exec-1"


def test_start_execution_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StartExecutionRequest.model_validate(
            {
                "actor_id": str(ACTOR),
                "scope": {
                    "tenant_id": str(TENANT),
                    "subject_id": str(SUBJECT),
                },
                "objective_ref": str(OBJECTIVE),
                "root_agent_id": str(ROOT_AGENT),
                "memory_query": None,
                "budget": {
                    "max_input_tokens": 1,
                    "max_output_tokens": 1,
                    "max_cost_micros": 1,
                    "deadline": DEADLINE.isoformat(),
                },
                "idempotency_key": "exec-1",
                "unexpected": True,
            }
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/http/test_execution_http_schemas.py -v`

Expected: FAIL — import error for `StartExecutionRequest`

- [ ] **Step 3: Add schemas to `schemas.py`**

Append models (use `ExecutionStatus` / `NodeStatus` / `FailureCategory` / `SuspensionKind` from domain as `StrEnum` values in response models):

```python
from engrammesh.modules.runtime.domain.model import (
    ExecutionStatus,
    FailureCategory,
    NodeStatus,
    SuspensionKind,
)

class BudgetRequest(_HttpSchemaModel):
    max_input_tokens: int
    max_output_tokens: int
    max_cost_micros: int
    deadline: datetime

class MemoryQueryRequest(_HttpSchemaModel):
    query_id: str
    scope: ScopeRequest
    text: str
    valid_at: datetime | None = None
    recorded_at: datetime | None = None
    limit: int = 10

class StartExecutionRequest(_HttpSchemaModel):
    actor_id: UUID | None = None
    scope: ScopeRequest
    objective_ref: UUID
    root_agent_id: UUID
    memory_query: MemoryQueryRequest | None
    budget: BudgetRequest
    idempotency_key: str

class CancelExecutionRequest(_HttpSchemaModel):
    actor_id: UUID | None = None
    scope: ScopeRequest
    idempotency_key: str

class FailureResponse(_HttpSchemaModel):
    category: FailureCategory
    code: str
    message: str
    details_ref: UUID | None

class SuspensionResponse(_HttpSchemaModel):
    request_id: str
    idempotency_key: str
    execution_id: UUID
    node_id: UUID | None
    kind: SuspensionKind
    request_ref: UUID
    requested_at: datetime
    expires_at: datetime

class ExecutionSnapshotResponse(_HttpSchemaModel):
    execution_id: UUID
    scope: ScopeResponse
    revision: int
    status: ExecutionStatus
    plan_revision: int | None
    node_statuses: dict[str, NodeStatus]
    suspension: SuspensionResponse | None
    result_ref: UUID | None
    failure: FailureResponse | None
    updated_at: datetime

class StartExecutionResponse(ExecutionSnapshotResponse):
    created: bool
```

- [ ] **Step 4: Run tests**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/http/test_execution_http_schemas.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/src/engrammesh/bootstrap/http/schemas.py \
  services/tests/unit/bootstrap/http/test_execution_http_schemas.py
git commit -s -m "feat: add execution HTTP pydantic schemas"
```

---

### Task 3: Execution HTTP mappers

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/mappers.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_mappers.py`

**Interfaces:**
- Consumes: `StartExecutionRequest`, `CancelExecutionRequest`, `ExecutionSnapshot`, `StartExecutionResult`, `GetExecutionSnapshotResult`, `CancelExecutionResult`, `AuthenticatedPrincipal | None`
- Produces:
  - `to_start_execution_command(...) -> StartExecutionCommand`
  - `to_get_execution_snapshot_query(...) -> GetExecutionSnapshotQuery`
  - `to_cancel_execution_command(...) -> CancelExecutionCommand`
  - `snapshot_to_response(snapshot: ExecutionSnapshot) -> ExecutionSnapshotResponse`
  - `start_result_to_response(result: StartExecutionResult) -> StartExecutionResponse`
  - `MemoryQueryScopeMismatchError` (new, raised when `memory_query.scope != body.scope`)

- [ ] **Step 1: Write failing mapper tests**

Create `services/tests/unit/bootstrap/http/test_execution_http_mappers.py` with tests for:
- `to_start_execution_command` happy path (assert `StartExecutionCommand` fields)
- tenant mismatch raises `TenantMismatchError`
- `actor_id` required when `principal is None`
- `actor_id` forbidden when principal present (`ActorIdNotAllowedError`)
- `memory_query` scope mismatch raises `MemoryQueryScopeMismatchError`
- `snapshot_to_response` maps `node_statuses` keys to strings

Use constants aligned with `test_http_mappers.py` UUID style.

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/http/test_execution_http_mappers.py -v`

- [ ] **Step 3: Implement mappers**

Key implementation notes:
- `_scope_from_request(path_tenant_id, scope: ScopeRequest) -> MemoryScope` — shared helper
- `_memory_query_from_request(mq: MemoryQueryRequest, execution_scope: MemoryScope) -> MemoryQuery` — validate `mq.scope` fields match `execution_scope`
- `_budget_from_request(budget: BudgetRequest) -> Budget`
- `snapshot_to_response` converts `NodeId` keys via `str(node_id.value)`

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP mappers"
```

---

### Task 4: Runtime HTTP error handlers

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/errors.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_errors.py`

**Interfaces:**
- Maps: `ExecutionAuthorizationDenied`→403, `ExecutionNotFound`→404, `ExecutionIdempotencyConflict`→409, `InvalidExecutionTransition`→409, `OrchestrationUnavailable`→503

- [ ] **Step 1: Write failing handler tests**

```python
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from engrammesh.bootstrap.http.errors import error_envelope, register_exception_handlers
from engrammesh.modules.runtime.application.errors import ExecutionAuthorizationDenied
from engrammesh.modules.runtime.domain.errors import ExecutionNotFound

@pytest.mark.asyncio
async def test_execution_not_found_maps_to_404() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def probe() -> None:
        raise ExecutionNotFound()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/probe")
    assert response.status_code == 404
    assert response.json() == error_envelope("execution_not_found", "execution not found")
```

Add parallel tests for `ExecutionAuthorizationDenied`, `ExecutionIdempotencyConflict`, `InvalidExecutionTransition`, `OrchestrationUnavailable`.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Register handlers in `errors.py`**

Import runtime errors and add handlers mirroring episode handlers (same `error_envelope` pattern, stable messages from spec §6).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: map runtime errors to HTTP envelopes"
```

---

### Task 5: JSON Schema contracts

**Files:**
- Create: `packages/contracts/jsonschema/runtime/v1/start-execution-request.schema.json`
- Create: `packages/contracts/jsonschema/runtime/v1/cancel-execution-request.schema.json`
- Create: `packages/contracts/jsonschema/runtime/v1/execution-snapshot-response.schema.json`
- Create: `packages/contracts/jsonschema/runtime/v1/start-execution-response.schema.json`
- Create: `services/tests/contract/test_execution_http_schemas.py`

**Interfaces:**
- Produces: Draft 2020-12 schemas version `1.0.0` with `$id` under `https://engrammesh.org/contracts/runtime/v1/`
- Reuse `$defs/httpMemoryScope` pattern from `record-episode-request.schema.json`

- [ ] **Step 1: Write failing contract test**

Create `services/tests/contract/test_execution_http_schemas.py` with `sample_start_execution_request_dict()`, `sample_execution_snapshot_response_dict()`, and tests:
- `test_start_execution_request_matches_schema`
- `test_execution_snapshot_response_matches_schema`
- `test_start_execution_response_requires_created`

- [ ] **Step 2: Run — expect FAIL** (schema files missing)

- [ ] **Step 3: Add schema JSON files**

Mirror Pydantic field names and enum strings from domain. `start-execution-response.schema.json` should `allOf` ref snapshot schema + `created: boolean`.

- [ ] **Step 4: Run — expect PASS**

Run: `uv run --python 3.14 --project services pytest services/tests/contract/test_execution_http_schemas.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP JSON Schema contracts"
```

---

### Task 6: execution_auth_context

**Files:**
- Modify: `services/src/engrammesh/bootstrap/auth/dependencies.py`
- Create: `services/tests/unit/bootstrap/auth/test_execution_auth_context.py`

**Interfaces:**
- Produces: `execution_auth_context(...)` — identical semantics to `episode_auth_context`

- [ ] **Step 1: Write test** (copy `episode_auth_context` test pattern if exists, or minimal async context manager test)

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** — duplicate `episode_auth_context` as `execution_auth_context` (same body; can factor shared `_tenant_auth_context` private helper to avoid duplication)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution_auth_context dependency"
```

---

### Task 7: HTTP routes

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/app.py`

**Interfaces:**
- Consumes: all mappers and schemas from Tasks 2–3, `execution_auth_context`, runtime handlers from `AppRuntime`

- [ ] **Step 1: Write failing route smoke test**

Add to `services/tests/integration/http/test_execution_http.py` (create file) one test:

```python
@pytest.mark.asyncio
async def test_post_start_returns_201(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    assert response.status_code == 201
    assert response.json()["created"] is True
```

(Create `execution_http_helpers.py` with `make_start_execution_payload()` in same step.)

- [ ] **Step 2: Run — expect FAIL** (404 route)

- [ ] **Step 3: Add routes to `app.py`**

```python
@app.post("/v1/tenants/{tenant_id}/executions")
async def start_execution(...) -> JSONResponse:
    async with execution_auth_context(...) as principal:
        command = to_start_execution_command(...)
        result = await runtime.start_execution_handler().handle(command)
        response = start_result_to_response(result)
        return JSONResponse(
            status_code=201 if result.created else 200,
            content=response.model_dump(mode="json"),
        )

@app.get("/v1/tenants/{tenant_id}/executions/{execution_id}")
async def get_execution_snapshot(...) -> JSONResponse:
    ...

@app.post("/v1/tenants/{tenant_id}/executions/{execution_id}/cancel")
async def cancel_execution(...) -> JSONResponse:
    ...
```

- [ ] **Step 4: Run smoke test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP routes to control API"
```

---

### Task 8: HTTP integration test suite (non-OIDC)

**Files:**
- Create: `services/tests/integration/http/execution_http_helpers.py`
- Create: `services/tests/integration/http/test_execution_http.py`

**Interfaces:**
- Reuse `start_runtime_with_in_memory` from `episode_http_helpers.py`
- Add `OBJECTIVE_REF`, `ROOT_AGENT_ID`, `make_start_execution_payload()`, `make_cancel_execution_payload()`, `seed_succeeded_execution(client, ...)` helper using `InMemoryOrchestratorPort.database.write` to set `ExecutionStatus.SUCCEEDED` for 409 cancel test

- [ ] **Step 1: Implement helpers and full test matrix**

Required tests (spec §9.2):

| Test | Assertion |
|------|-----------|
| `test_post_start_returns_201` | `created=true` |
| `test_post_start_idempotent_replay_returns_200` | same key → `created=false` |
| `test_post_start_idempotency_conflict_returns_409` | same key, different `objective_ref` |
| `test_get_execution_after_start_returns_200` | snapshot fields present |
| `test_get_unknown_execution_returns_404` | `execution_not_found` |
| `test_get_wrong_subject_returns_404` | scope isolation |
| `test_post_cancel_returns_200_cancelled` | status `cancelled` |
| `test_post_cancel_succeeded_execution_returns_409` | use seed helper |
| `test_post_staging_environment_returns_403` | `environment=STAGING`, `execution_authorization_denied` |
| `test_runtime_disabled_returns_503` | `modules.runtime_enabled=false` |

- [ ] **Step 2: Run integration tests**

Run: `uv run --python 3.14 --project services pytest services/tests/integration/http/test_execution_http.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git commit -s -m "test: add execution HTTP integration coverage"
```

---

### Task 9: OIDC execution HTTP integration

**Files:**
- Create: `services/tests/integration/http/test_oidc_execution_http.py`

**Interfaces:**
- Reuse `make_oidc_test_settings`, `auth_headers`, `make_static_dev_verifier` from `episode_http_helpers.py`
- Pass `token_verifier=make_static_dev_verifier()` to `create_app` where needed (mirror `test_oidc_episode_http.py`)

- [ ] **Step 1: Write tests**

| Test | Assertion |
|------|-----------|
| `test_post_start_without_bearer_returns_401` | |
| `test_post_start_with_valid_bearer_returns_201` | no `actor_id` in body |
| `test_post_start_wrong_path_tenant_returns_403` | |
| `test_post_start_actor_id_in_body_returns_422` | `actor_id_not_allowed` |
| `test_get_without_bearer_returns_401` | |
| `test_cancel_without_bearer_returns_401` | |

- [ ] **Step 2: Run tests**

Run: `uv run --python 3.14 --project services pytest services/tests/integration/http/test_oidc_execution_http.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git commit -s -m "test: add OIDC execution HTTP integration coverage"
```

---

### Task 10: Documentation and RFC follow-up

**Files:**
- Modify: `services/README.md`
- Modify: `services/README.zh-CN.md`
- Modify: `docs/rfcs/2026-08-04-execution-http-api.md` (mark slice in progress → complete at end)
- Modify: `docs/rfcs/2026-07-31-temporal-runtime-adapter.md` (④a ✅ when done)

- [ ] **Step 1: Add "Execution HTTP API" section**

Mirror `## Episode read HTTP API` structure:
- Endpoints table with methods, paths, status codes
- Error code table
- OIDC behavior (`actor_id` rules)
- `runtime_disabled` / `orchestration_unavailable` notes
- `curl` example: start → get → cancel (in-memory, OIDC off)
- Remove "Execution HTTP API" from runtime non-goals list

- [ ] **Step 2: Update Chinese README** (same content)

- [ ] **Step 3: Run full verification**

```bash
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git commit -s -m "docs: document execution HTTP API and OIDC runtime auth"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| §4.2 OIDC runtime authorization | Task 1 |
| §5.1 POST start | Tasks 2, 3, 7, 8 |
| §5.2 GET snapshot | Tasks 2, 3, 7, 8 |
| §5.3 POST cancel | Tasks 2, 3, 7, 8 |
| §5.4 Snapshot response shape | Tasks 2, 3, 5 |
| §6 Error mapping | Task 4 |
| §7 JSON Schema | Task 5 |
| §9.2 HTTP integration matrix | Task 8 |
| §9.3 OIDC integration | Task 9 |
| §9.4 Composed E2E (start→get→cancel) | Task 8 |
| §10 Acceptance (pytest/ruff/mypy) | Task 10 |
| §8 Bilingual README | Task 10 |

## Self-review notes

- No placeholders or "similar to Task N" without code in mapper/error tasks — implementers have full test signatures above; expand mapper test file using `test_http_mappers.py` as template during Task 3.
- `RuntimeAction` literal type for `action` in tests uses `# type: ignore` only in test helper; production uses valid literals.
- Cancel 409 test uses database seed helper — not available via public HTTP alone; documented in Task 8.
- `docs/superpowers/plans/` is gitignored; force-add this plan file on commit: `git add -f docs/superpowers/plans/2026-08-04-execution-http-api.md`
