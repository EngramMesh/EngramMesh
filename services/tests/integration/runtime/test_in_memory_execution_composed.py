"""Integration test for composed runtime execution via manually wired handlers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedRuntimeAuthorization,
    SystemUtcClock,
    UuidRuntimeIdentityPort,
)
from engrammesh.bootstrap.settings import Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.application.cancel_execution import (
    CancelExecutionHandler,
)
from engrammesh.modules.runtime.application.contracts import (
    CancelExecutionCommand,
    GetExecutionSnapshotQuery,
    StartExecutionCommand,
)
from engrammesh.modules.runtime.application.get_execution_snapshot import (
    GetExecutionSnapshotHandler,
)
from engrammesh.modules.runtime.application.start_execution import (
    StartExecutionHandler,
)
from engrammesh.modules.runtime.domain.model import Budget, ExecutionStatus
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
SCOPE = MemoryScope(TenantId(UUID(int=1)), SubjectId(UUID(int=2)))
ACTOR = SubjectId(UUID(int=3))


def _budget() -> Budget:
    return Budget(1000, 500, 100_000, NOW + timedelta(hours=1))


def _wire_handlers() -> tuple[
    StartExecutionHandler,
    GetExecutionSnapshotHandler,
    CancelExecutionHandler,
]:
    authorization = EnvironmentGatedRuntimeAuthorization(Environment.TEST)
    orchestrator = InMemoryOrchestratorPort(
        SystemUtcClock(),
        InMemoryRuntimeDatabase(),
    )
    return (
        StartExecutionHandler(
            authorization=authorization,
            identities=UuidRuntimeIdentityPort(),
            orchestrator=orchestrator,
        ),
        GetExecutionSnapshotHandler(
            authorization=authorization,
            orchestrator=orchestrator,
        ),
        CancelExecutionHandler(
            authorization=authorization,
            orchestrator=orchestrator,
        ),
    )


@pytest.mark.asyncio
async def test_composed_start_get_cancel_with_real_handlers() -> None:
    start_handler, get_handler, cancel_handler = _wire_handlers()

    start_result = await start_handler.handle(
        StartExecutionCommand(
            correlation_id=CorrelationId(UUID(int=1)),
            actor_id=ACTOR,
            scope=SCOPE,
            objective_ref=ArtifactId(UUID(int=4)),
            root_agent_id=AgentDefinitionId(UUID(int=5)),
            memory_query=None,
            budget=_budget(),
            idempotency_key="start-composed-1",
        )
    )
    assert start_result.created is True
    assert start_result.snapshot.status == ExecutionStatus.PENDING
    execution_id = start_result.snapshot.execution_id

    get_result = await get_handler.handle(
        GetExecutionSnapshotQuery(
            actor_id=ACTOR,
            scope=SCOPE,
            execution_id=execution_id,
        )
    )
    assert get_result.snapshot.execution_id == execution_id
    assert get_result.snapshot.status == ExecutionStatus.PENDING

    cancel_result = await cancel_handler.handle(
        CancelExecutionCommand(
            correlation_id=CorrelationId(UUID(int=2)),
            actor_id=ACTOR,
            scope=SCOPE,
            execution_id=execution_id,
            idempotency_key="cancel-composed-1",
        )
    )
    assert cancel_result.snapshot.execution_id == execution_id
    assert cancel_result.snapshot.status == ExecutionStatus.CANCELLED
