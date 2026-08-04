# Execution HTTP API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `StartExecution`, `GetExecutionSnapshot`, and `CancelExecution` handlers via REST on the existing Control API, with OIDC-backed runtime authorization when `oidc.enabled=true`.

**Architecture:** Thin HTTP adapter in `bootstrap/http/` maps Pydantic DTOs to existing application commands/queries. `TenantScopedRuntimeAuthorization` mirrors memory OIDC wiring. No changes to runtime application handlers or orchestrator adapters.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, httpx (ASGI tests), jsonschema Draft 2020-12, existing `AppRuntime` composition.

**Revision:** 2 — incorporates plan review (2026-08-04): expanded tests, merged route/integration task, `MemoryQueryScopeMismatchError`, contract round-trip, docs/CHANGELOG.

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
| `services/src/engrammesh/bootstrap/auth/dependencies.py` | `_tenant_auth_context`, `execution_auth_context`, refactor `episode_auth_context` |
| `services/src/engrammesh/bootstrap/http/schemas.py` | Execution request/response Pydantic models |
| `services/src/engrammesh/bootstrap/http/mappers.py` | DTO ↔ commands/queries; `MemoryQueryScopeMismatchError` |
| `services/src/engrammesh/bootstrap/http/errors.py` | Runtime + mapper exception → HTTP mapping |
| `services/src/engrammesh/bootstrap/http/app.py` | Three execution routes |
| `packages/contracts/jsonschema/runtime/v1/*.schema.json` | Public HTTP contracts |
| `services/tests/integration/http/execution_http_helpers.py` | Payload builders + `seed_succeeded_execution` |
| `services/tests/integration/http/test_execution_http.py` | Non-OIDC routes + integration matrix |
| `services/tests/integration/http/test_oidc_execution_http.py` | OIDC integration |
| `services/tests/unit/bootstrap/http/test_execution_http_mappers.py` | Mapper unit tests |
| `services/tests/contract/test_execution_http_schemas.py` | JSON Schema + mapper round-trip |
| `CHANGELOG.md`, `services/README.md`, `services/README.zh-CN.md` | Docs |

---

### Task 1: TenantScopedRuntimeAuthorization

**Files:**
- Modify: `services/src/engrammesh/bootstrap/infrastructure.py`
- Modify: `services/tests/unit/bootstrap/test_runtime_infrastructure.py`
- Create: `services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py`

**Interfaces:**
- Produces: `TenantScopedRuntimeAuthorization.authorize(request) -> bool`
- Produces: `create_runtime_authorization(settings)` → `TenantScopedRuntimeAuthorization` when `settings.oidc.enabled`

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
from engrammesh.bootstrap.settings import AppSettings
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
TENANT_ID = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
OTHER_TENANT_ID = TenantId(UUID("e63173e8-8f03-4f34-beac-2020676684c0"))


def _runtime_auth_request(
    *,
    tenant_id: TenantId = TENANT_ID,
    action: str = "start_execution",
) -> RuntimeAuthorizationRequest:
    return RuntimeAuthorizationRequest(
        actor_id=ACTOR_ID,
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
            "oidc": {
                "enabled": True,
                "issuer": "https://dev.engrammesh.test",
                "dev_signing_key": "dev-only-signing-key-not-for-production",
            },
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

Append to `services/tests/unit/bootstrap/test_runtime_infrastructure.py`:

```python
def test_create_runtime_authorization_uses_tenant_scoped_when_oidc_enabled() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
            "oidc": {
                "enabled": True,
                "issuer": "https://dev.engrammesh.test",
                "dev_signing_key": "dev-only-signing-key-not-for-production",
            },
        }
    )
    from engrammesh.bootstrap.infrastructure import TenantScopedRuntimeAuthorization

    auth = create_runtime_authorization(settings)
    assert isinstance(auth, TenantScopedRuntimeAuthorization)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/auth/test_tenant_scoped_runtime_authorization.py services/tests/unit/bootstrap/test_runtime_infrastructure.py -v`

- [ ] **Step 3: Implement**

Add `TenantScopedRuntimeAuthorization` and update `create_runtime_authorization` in `infrastructure.py` (mirror `TenantScopedMemoryAuthorization`; import `current_principal`).

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add tenant-scoped runtime authorization for OIDC"
```

---

### Task 2: Execution HTTP Pydantic schemas

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/schemas.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_schemas.py`

- [ ] **Step 1: Write failing tests** (include extra-fields, blank idempotency_key, negative budget)

```python
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.http.schemas import (
    BudgetRequest,
    CancelExecutionRequest,
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
    return ScopeRequest(tenant_id=TENANT, subject_id=SUBJECT, workspace_id="ws-1")


def _budget() -> BudgetRequest:
    return BudgetRequest(
        max_input_tokens=1000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=DEADLINE,
    )


def test_start_execution_request_accepts_valid_body() -> None:
    body = StartExecutionRequest(
        actor_id=ACTOR,
        scope=_scope(),
        objective_ref=OBJECTIVE,
        root_agent_id=ROOT_AGENT,
        memory_query=None,
        budget=_budget(),
        idempotency_key="exec-1",
    )
    assert body.idempotency_key == "exec-1"


def test_start_execution_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StartExecutionRequest.model_validate(
            {
                "actor_id": str(ACTOR),
                "scope": {"tenant_id": str(TENANT), "subject_id": str(SUBJECT)},
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


def test_cancel_execution_request_accepts_valid_body() -> None:
    body = CancelExecutionRequest(
        actor_id=ACTOR,
        scope=_scope(),
        idempotency_key="cancel-1",
    )
    assert body.idempotency_key == "cancel-1"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Add schema models** (see spec §5.4; import domain enums for response types)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP pydantic schemas"
```

---

### Task 3: Execution HTTP mappers

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/mappers.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_mappers.py`

**Interfaces:**
- Produces: `MemoryQueryScopeMismatchError(ValueError)`
- Produces: `to_start_execution_command`, `to_get_execution_snapshot_query`, `to_cancel_execution_command`, `snapshot_to_response`, `start_result_to_response`

- [ ] **Step 1: Write failing mapper tests**

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.bootstrap.http.mappers import (
    ActorIdNotAllowedError,
    ActorIdRequiredError,
    MemoryQueryScopeMismatchError,
    TenantMismatchError,
    snapshot_to_response,
    to_cancel_execution_command,
    to_get_execution_snapshot_query,
    to_start_execution_command,
)
from engrammesh.bootstrap.http.schemas import (
    BudgetRequest,
    CancelExecutionRequest,
    MemoryQueryRequest,
    ScopeRequest,
    StartExecutionRequest,
)
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.domain.model import Budget, ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    ExecutionId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-000000000002"))
SUBJECT = SubjectId(UUID("436b95a8-df23-4d6e-8200-d2058ad62d86"))
ACTOR = SubjectId(UUID("29ee5d4a-8988-48b9-bd24-e65ba7eb3de5"))
OBJECTIVE = ArtifactId(UUID("a49f42ec-453a-46ba-98d7-32dda8d6ad7e"))
ROOT_AGENT = AgentDefinitionId(UUID("b93676a1-4671-47da-a32e-cd4615588188"))
CORRELATION = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
DEADLINE = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _scope_request(*, tenant: UUID = TENANT_A.value) -> ScopeRequest:
    return ScopeRequest(tenant_id=tenant, subject_id=SUBJECT.value, workspace_id="ws-1")


def _start_body(**overrides: object) -> StartExecutionRequest:
    values: dict[str, object] = {
        "actor_id": ACTOR.value,
        "scope": _scope_request(),
        "objective_ref": OBJECTIVE.value,
        "root_agent_id": ROOT_AGENT.value,
        "memory_query": None,
        "budget": BudgetRequest(
            max_input_tokens=1000,
            max_output_tokens=500,
            max_cost_micros=100_000,
            deadline=DEADLINE,
        ),
        "idempotency_key": "exec-1",
    }
    values.update(overrides)
    return StartExecutionRequest(**values)  # type: ignore[arg-type]


def test_to_start_execution_command_maps_fields() -> None:
    command = to_start_execution_command(
        path_tenant_id=TENANT_A,
        correlation_id=CORRELATION,
        body=_start_body(),
        principal=None,
    )
    assert command.actor_id == ACTOR
    assert command.scope.tenant_id == TENANT_A
    assert command.objective_ref == OBJECTIVE
    assert command.idempotency_key == "exec-1"


def test_to_start_execution_command_raises_tenant_mismatch() -> None:
    with pytest.raises(TenantMismatchError):
        to_start_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            body=_start_body(scope=_scope_request(tenant=TENANT_B.value)),
            principal=None,
        )


def test_to_start_execution_command_requires_actor_when_unauthenticated() -> None:
    with pytest.raises(ActorIdRequiredError):
        to_start_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            body=_start_body(actor_id=None),
            principal=None,
        )


def test_to_start_execution_command_rejects_actor_when_principal_present() -> None:
    from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal

    principal = AuthenticatedPrincipal(actor_id=ACTOR, tenant_id=TENANT_A)
    with pytest.raises(ActorIdNotAllowedError):
        to_start_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            body=_start_body(),
            principal=principal,
        )


def test_to_start_execution_command_rejects_memory_query_scope_mismatch() -> None:
    with pytest.raises(MemoryQueryScopeMismatchError):
        to_start_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            body=_start_body(
                memory_query=MemoryQueryRequest(
                    query_id="q-1",
                    scope=_scope_request(tenant=TENANT_B.value),
                    text="find context",
                )
            ),
            principal=None,
        )


def test_snapshot_to_response_maps_node_status_keys_to_strings() -> None:
    execution_id = ExecutionId.new()
    snapshot = ExecutionSnapshot(
        execution_id=execution_id,
        scope=MemoryScope(TENANT_A, SUBJECT, workspace_id="ws-1"),
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses={},
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=DEADLINE,
    )
    response = snapshot_to_response(snapshot)
    assert response.execution_id == execution_id.value
    assert response.status == ExecutionStatus.PENDING
```

Add tests for `to_get_execution_snapshot_query` and `to_cancel_execution_command` following the same actor/tenant patterns.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement mappers** (`MemoryQueryScopeMismatchError`, `_scope_from_request`, `_memory_query_from_request` with scope equality check)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP mappers"
```

---

### Task 4: Runtime HTTP error handlers

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/errors.py`
- Create: `services/tests/unit/bootstrap/http/test_execution_http_errors.py`

**Maps:** `ExecutionAuthorizationDenied`→403, `ExecutionNotFound`→404, `ExecutionIdempotencyConflict`→409, `InvalidExecutionTransition`→409, `OrchestrationUnavailable`→503, `MemoryQueryScopeMismatchError`→422 `validation_error`

- [ ] **Step 1–4:** Write probe-app tests for each runtime error (pattern in review v1 Task 4) plus:

```python
@pytest.mark.asyncio
async def test_memory_query_scope_mismatch_maps_to_422() -> None:
    from engrammesh.bootstrap.http.mappers import MemoryQueryScopeMismatchError

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def probe() -> None:
        raise MemoryQueryScopeMismatchError("memory_query.scope must match execution scope")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/probe")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
```

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: map runtime errors to HTTP envelopes"
```

---

### Task 5: JSON Schema contracts + mapper round-trip

**Files:**
- Create: `packages/contracts/jsonschema/runtime/v1/*.schema.json` (4 files)
- Create: `services/tests/contract/test_execution_http_schemas.py`

- [ ] **Step 1: Write contract tests** including round-trip:

```python
def test_snapshot_mapper_output_matches_response_schema() -> None:
    from engrammesh.bootstrap.http.mappers import snapshot_to_response
    # build minimal ExecutionSnapshot (or import helper), then:
    payload = snapshot_to_response(snapshot).model_dump(mode="json")
    Draft202012Validator(_load_snapshot_schema(), format_checker=FormatChecker()).validate(
        payload
    )


def test_start_result_mapper_output_matches_start_response_schema() -> None:
    from engrammesh.bootstrap.http.mappers import start_result_to_response
    # StartExecutionResult with created=True
    payload = start_result_to_response(result).model_dump(mode="json")
    Draft202012Validator(_load_start_response_schema(), format_checker=FormatChecker()).validate(
        payload
    )
```

- [ ] **Step 2–4:** Implement schemas; run `pytest services/tests/contract/test_execution_http_schemas.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP JSON Schema contracts"
```

---

### Task 6: Auth context refactor

**Files:**
- Modify: `services/src/engrammesh/bootstrap/auth/dependencies.py`
- Modify: `services/tests/unit/bootstrap/auth/test_dependencies.py` (if needed)

- [ ] **Step 1: Extract shared helper**

```python
@asynccontextmanager
async def _tenant_auth_context(
    *,
    oidc_enabled: bool,
    path_tenant_id: UUID,
    authorization: str | None,
    verifier: TokenVerifierPort | None,
) -> AsyncIterator[AuthenticatedPrincipal | None]:
    if not oidc_enabled:
        yield None
        return
    if verifier is None:
        raise ConfigurationError("oidc_misconfigured", "OIDC verifier is not configured")
    principal = await authenticate_tenant_request(
        path_tenant_id=path_tenant_id,
        authorization=authorization,
        verifier=verifier,
    )
    with PrincipalBinding(principal):
        yield principal


async def episode_auth_context(...):
    async with _tenant_auth_context(...) as principal:
        yield principal


async def execution_auth_context(...):
    async with _tenant_auth_context(...) as principal:
        yield principal
```

- [ ] **Step 2: Run existing auth tests — expect PASS** (no behavior change)

`uv run --python 3.14 --project services pytest services/tests/unit/bootstrap/auth/test_dependencies.py -v`

- [ ] **Step 3: Commit**

```bash
git commit -s -m "feat: add execution_auth_context and shared tenant auth helper"
```

---

### Task 7: HTTP routes + non-OIDC integration tests

**Files:**
- Modify: `services/src/engrammesh/bootstrap/http/app.py`
- Create: `services/tests/integration/http/execution_http_helpers.py`
- Create: `services/tests/integration/http/test_execution_http.py`

**Note:** This task owns `test_execution_http.py` end-to-end (smoke + full matrix). Do not recreate the file in a later task.

**Helpers** (`execution_http_helpers.py`):

```python
def make_start_execution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor_id": str(ACTOR_ID),
        "scope": {
            "tenant_id": str(TENANT_A),
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
        },
        "objective_ref": str(OBJECTIVE_REF),
        "root_agent_id": str(ROOT_AGENT_ID),
        "memory_query": None,
        "budget": {
            "max_input_tokens": 1000,
            "max_output_tokens": 500,
            "max_cost_micros": 100_000,
            "deadline": "2026-08-04T12:00:00+00:00",
        },
        "idempotency_key": "exec-1",
    }
    payload.update(overrides)
    return payload


async def seed_succeeded_execution(runtime: AppRuntime, execution_id: ExecutionId) -> None:
    from dataclasses import replace

    from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
        InMemoryOrchestratorPort,
    )
    from engrammesh.modules.runtime.domain.model import ExecutionStatus

    orchestrator = runtime.start_execution_handler()._orchestrator
    assert isinstance(orchestrator, InMemoryOrchestratorPort)

    async def _mark_succeeded(state):
        snapshot = state.snapshots[execution_id]
        return replace(
            state,
            snapshots={
                **dict(state.snapshots),
                execution_id: replace(snapshot, status=ExecutionStatus.SUCCEEDED),
            },
        )

    await orchestrator.database.write(_mark_succeeded)
```

**Integration test matrix** (`test_execution_http.py`):

| Test | Assertion |
|------|-----------|
| `test_post_start_returns_201` | `created=true` |
| `test_post_start_idempotent_replay_returns_200` | `created=false` |
| `test_post_start_idempotency_conflict_returns_409` | different `objective_ref`, same key |
| `test_post_start_invalid_correlation_id_returns_422` | bad `X-Correlation-Id` |
| `test_get_execution_after_start_returns_200` | |
| `test_get_unknown_execution_returns_404` | `execution_not_found` |
| `test_get_wrong_subject_returns_404` | |
| `test_get_missing_actor_id_returns_422` | OIDC off |
| `test_post_cancel_returns_200_cancelled` | |
| `test_post_cancel_body_tenant_mismatch_returns_422` | |
| `test_post_cancel_succeeded_execution_returns_409` | uses `seed_succeeded_execution` |
| `test_post_staging_environment_returns_403` | `execution_authorization_denied` |
| `test_runtime_disabled_returns_503` | `modules.runtime_enabled=false` |
| `test_start_get_cancel_composed_flow` | single test: start → get → cancel |

Reuse `client` fixture from `conftest.py` (`start_runtime_with_in_memory` enables runtime by default).

- [ ] **Step 1: Write failing integration tests (at least smoke + composed flow)**

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement routes in `app.py`**

- [ ] **Step 4: Run full matrix — expect PASS**

`uv run --python 3.14 --project services pytest services/tests/integration/http/test_execution_http.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -s -m "feat: add execution HTTP routes and integration coverage"
```

---

### Task 8: OIDC execution HTTP integration

**Files:**
- Create: `services/tests/integration/http/test_oidc_execution_http.py`

| Test | Assertion |
|------|-----------|
| `test_post_start_without_bearer_returns_401` | |
| `test_post_start_with_valid_bearer_returns_201` | no `actor_id` in body |
| `test_post_start_wrong_path_tenant_returns_403` | |
| `test_post_start_actor_id_in_body_returns_422` | |
| `test_get_without_bearer_returns_401` | |
| `test_get_with_valid_bearer_returns_200` | after start |
| `test_cancel_without_bearer_returns_401` | |
| `test_cancel_with_valid_bearer_returns_200` | after start |
| `test_get_actor_id_in_query_returns_422` | |
| `test_staging_with_injected_verifier_allows_start` | mirror `test_oidc_episode_http.py` |

Pass `token_verifier=make_static_dev_verifier()` to `create_app` where needed.

- [ ] **Step 1–4:** Implement tests; run `pytest services/tests/integration/http/test_oidc_execution_http.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -s -m "test: add OIDC execution HTTP integration coverage"
```

---

### Task 9: Documentation, CHANGELOG, and RFC follow-ups

**Files:**
- Modify: `services/README.md`, `services/README.zh-CN.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/rfcs/2026-08-04-execution-http-api.md`
- Modify: `docs/rfcs/2026-07-31-temporal-runtime-adapter.md` (④a ✅)
- Modify: `docs/rfcs/2026-07-31-oidc-tenant-context.md` (④ ✅ if not already)

- [ ] **Step 1: README updates**

- Add `## Execution HTTP API` section (endpoints, errors, OIDC, curl example)
- Update **Purpose and exact non-goals** — remove "does not contain an execution HTTP API"; list execution endpoints alongside episode APIs
- Remove execution HTTP from runtime non-goals bullet list

- [ ] **Step 2: CHANGELOG Unreleased**

```markdown
- Execution HTTP API: `POST/GET .../executions`, `POST .../cancel`, OIDC runtime
  authorization (`TenantScopedRuntimeAuthorization`), JSON Schema contracts, and
  integration coverage.
```

- [ ] **Step 3: Full verification**

```bash
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
```

- [ ] **Step 4: Commit**

```bash
git commit -s -m "docs: document execution HTTP API and update changelog"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| §4.2 OIDC runtime authorization | Task 1 |
| §5.1–5.3 Endpoints | Tasks 2, 3, 7 |
| §5.4 Snapshot response | Tasks 2, 3, 5 |
| §6 Error mapping (incl. `MemoryQueryScopeMismatchError`) | Task 4 |
| §7 JSON Schema + round-trip | Task 5 |
| §9.2 HTTP integration matrix | Task 7 |
| §9.3 OIDC integration | Task 8 |
| §9.4 Composed E2E | Task 7 (`test_start_get_cancel_composed_flow`) |
| §9.5 Contract round-trip | Task 5 |
| §10 Acceptance | Task 9 |
| CHANGELOG + README non-goals | Task 9 |

## Self-review (rev 2)

- Task 3 and Task 6 include complete code (no "similar to" placeholders).
- Tasks 7+8 merged route + integration to avoid file conflicts.
- OIDC staging regression and GET/Cancel happy paths covered in Task 8.
- `seed_succeeded_execution` uses `isinstance(InMemoryOrchestratorPort)` guard.
- Force-add plan on commit: `git add -f docs/superpowers/plans/2026-08-04-execution-http-api.md`
