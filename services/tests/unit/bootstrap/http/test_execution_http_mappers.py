from datetime import UTC, datetime
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
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
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


def test_to_get_execution_snapshot_query_maps_fields() -> None:
    execution_id = ExecutionId.new()
    query = to_get_execution_snapshot_query(
        path_tenant_id=TENANT_A,
        execution_id=execution_id,
        actor_id=ACTOR,
        subject_id=SUBJECT,
        workspace_id="ws-1",
        agent_id=None,
        principal=None,
    )
    assert query.actor_id == ACTOR
    assert query.scope.tenant_id == TENANT_A
    assert query.scope.subject_id == SUBJECT
    assert query.scope.workspace_id == "ws-1"
    assert query.execution_id == execution_id


def test_to_get_execution_snapshot_query_requires_actor_when_unauthenticated() -> None:
    with pytest.raises(ActorIdRequiredError):
        to_get_execution_snapshot_query(
            path_tenant_id=TENANT_A,
            execution_id=ExecutionId.new(),
            actor_id=None,
            subject_id=SUBJECT,
            workspace_id="ws-1",
            agent_id=None,
            principal=None,
        )


def test_to_get_execution_snapshot_query_rejects_actor_when_principal_present() -> None:
    from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal

    principal = AuthenticatedPrincipal(actor_id=ACTOR, tenant_id=TENANT_A)
    with pytest.raises(ActorIdNotAllowedError):
        to_get_execution_snapshot_query(
            path_tenant_id=TENANT_A,
            execution_id=ExecutionId.new(),
            actor_id=ACTOR,
            subject_id=SUBJECT,
            workspace_id="ws-1",
            agent_id=None,
            principal=principal,
        )


def _cancel_body(**overrides: object) -> CancelExecutionRequest:
    values: dict[str, object] = {
        "actor_id": ACTOR.value,
        "scope": _scope_request(),
        "idempotency_key": "cancel-1",
    }
    values.update(overrides)
    return CancelExecutionRequest(**values)  # type: ignore[arg-type]


def test_to_cancel_execution_command_maps_fields() -> None:
    execution_id = ExecutionId.new()
    command = to_cancel_execution_command(
        path_tenant_id=TENANT_A,
        correlation_id=CORRELATION,
        execution_id=execution_id,
        body=_cancel_body(),
        principal=None,
    )
    assert command.actor_id == ACTOR
    assert command.scope.tenant_id == TENANT_A
    assert command.scope.subject_id == SUBJECT
    assert command.execution_id == execution_id
    assert command.idempotency_key == "cancel-1"


def test_to_cancel_execution_command_raises_tenant_mismatch() -> None:
    with pytest.raises(TenantMismatchError):
        to_cancel_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            execution_id=ExecutionId.new(),
            body=_cancel_body(scope=_scope_request(tenant=TENANT_B.value)),
            principal=None,
        )


def test_to_cancel_execution_command_requires_actor_when_unauthenticated() -> None:
    with pytest.raises(ActorIdRequiredError):
        to_cancel_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            execution_id=ExecutionId.new(),
            body=_cancel_body(actor_id=None),
            principal=None,
        )


def test_to_cancel_execution_command_rejects_actor_when_principal_present() -> None:
    from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal

    principal = AuthenticatedPrincipal(actor_id=ACTOR, tenant_id=TENANT_A)
    with pytest.raises(ActorIdNotAllowedError):
        to_cancel_execution_command(
            path_tenant_id=TENANT_A,
            correlation_id=CORRELATION,
            execution_id=ExecutionId.new(),
            body=_cancel_body(),
            principal=principal,
        )
