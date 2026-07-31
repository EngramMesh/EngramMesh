from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.application.contracts import (
    CancelExecutionCommand,
    GetExecutionSnapshotQuery,
    StartExecutionCommand,
)
from engrammesh.modules.runtime.domain.model import Budget
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    ExecutionId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
SCOPE = MemoryScope(TenantId(UUID(int=1)), SubjectId(UUID(int=2)))


def _budget() -> Budget:
    return Budget(1000, 500, 100_000, NOW + timedelta(hours=1))


def test_start_execution_command_accepts_valid_input() -> None:
    cmd = StartExecutionCommand(
        correlation_id=CorrelationId(UUID(int=1)),
        actor_id=SubjectId(UUID(int=3)),
        scope=SCOPE,
        objective_ref=ArtifactId(UUID(int=4)),
        root_agent_id=AgentDefinitionId(UUID(int=5)),
        memory_query=None,
        budget=_budget(),
        idempotency_key="start-1",
    )
    assert cmd.idempotency_key == "start-1"


def test_start_execution_command_rejects_blank_idempotency_key() -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        StartExecutionCommand(
            correlation_id=CorrelationId(UUID(int=1)),
            actor_id=SubjectId(UUID(int=3)),
            scope=SCOPE,
            objective_ref=ArtifactId(UUID(int=4)),
            root_agent_id=AgentDefinitionId(UUID(int=5)),
            memory_query=None,
            budget=_budget(),
            idempotency_key="   ",
        )


def test_get_execution_snapshot_query_requires_scope() -> None:
    q = GetExecutionSnapshotQuery(
        actor_id=SubjectId(UUID(int=3)),
        scope=SCOPE,
        execution_id=ExecutionId(UUID(int=9)),
    )
    assert q.execution_id == ExecutionId(UUID(int=9))


def test_cancel_execution_command_carries_cancel_idempotency_key() -> None:
    cmd = CancelExecutionCommand(
        correlation_id=CorrelationId(UUID(int=2)),
        actor_id=SubjectId(UUID(int=3)),
        scope=SCOPE,
        execution_id=ExecutionId(UUID(int=9)),
        idempotency_key="cancel-1",
    )
    assert cmd.idempotency_key == "cancel-1"
