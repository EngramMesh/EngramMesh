from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.application.contracts import StartExecutionCommand
from engrammesh.modules.runtime.application.errors import ExecutionAuthorizationDenied
from engrammesh.modules.runtime.application.start_execution import (
    StartExecutionHandler,
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


def _command() -> StartExecutionCommand:
    return StartExecutionCommand(
        correlation_id=CorrelationId(UUID(int=1)),
        actor_id=SubjectId(UUID(int=3)),
        scope=SCOPE,
        objective_ref=ArtifactId(UUID(int=4)),
        root_agent_id=AgentDefinitionId(UUID(int=5)),
        memory_query=None,
        budget=_budget(),
        idempotency_key="start-1",
    )


class Allow:
    async def authorize(self, request: object) -> bool:
        del request
        return True


class Deny:
    async def authorize(self, request: object) -> bool:
        del request
        return False


class SeqIds:
    def __init__(self, *ids: ExecutionId) -> None:
        self._ids = list(ids)

    async def new_execution_id(self) -> ExecutionId:
        return self._ids.pop(0)


@pytest.mark.asyncio
async def test_start_returns_created_true_on_first_call() -> None:
    handler = StartExecutionHandler(
        authorization=Allow(),
        identities=SeqIds(ExecutionId(UUID(int=100))),
        orchestrator=InMemoryOrchestratorPort(SystemUtcClock(), InMemoryRuntimeDatabase()),
    )
    result = await handler.handle(_command())
    assert result.created is True
    assert result.snapshot.execution_id == ExecutionId(UUID(int=100))


@pytest.mark.asyncio
async def test_start_returns_created_false_on_idempotent_replay() -> None:
    database = InMemoryRuntimeDatabase()
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    handler = StartExecutionHandler(
        authorization=Allow(),
        identities=SeqIds(ExecutionId(UUID(int=100)), ExecutionId(UUID(int=200))),
        orchestrator=orchestrator,
    )
    first = await handler.handle(_command())
    second = await handler.handle(_command())
    assert first.created is True
    assert second.created is False
    assert second.snapshot.execution_id == first.snapshot.execution_id


@pytest.mark.asyncio
async def test_start_raises_when_unauthorized() -> None:
    handler = StartExecutionHandler(
        authorization=Deny(),
        identities=SeqIds(ExecutionId(UUID(int=100))),
        orchestrator=InMemoryOrchestratorPort(SystemUtcClock(), InMemoryRuntimeDatabase()),
    )
    with pytest.raises(ExecutionAuthorizationDenied):
        await handler.handle(_command())
