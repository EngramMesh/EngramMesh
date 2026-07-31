from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Never
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
from engrammesh.modules.runtime.application.contracts import (
    GetExecutionSnapshotQuery,
    StartExecutionCommand,
)
from engrammesh.modules.runtime.application.errors import ExecutionAuthorizationDenied
from engrammesh.modules.runtime.application.get_execution_snapshot import (
    GetExecutionSnapshotHandler,
)
from engrammesh.modules.runtime.application.start_execution import (
    StartExecutionHandler,
)
from engrammesh.modules.runtime.domain.errors import ExecutionNotFound
from engrammesh.modules.runtime.domain.model import Budget
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
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
ACTOR = SubjectId(UUID(int=3))
EXECUTION_ID = ExecutionId(UUID(int=100))


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


@dataclass
class RecordingAuthorization:
    calls: list[RuntimeAuthorizationRequest] = field(default_factory=list)
    allowed: bool = True

    async def authorize(self, request: RuntimeAuthorizationRequest) -> bool:
        self.calls.append(request)
        return self.allowed


def _budget() -> Budget:
    return Budget(1000, 500, 100_000, NOW + timedelta(hours=1))


def _start_handler(
    orchestrator: InMemoryOrchestratorPort,
) -> StartExecutionHandler:
    class SeqIds:
        async def new_execution_id(self) -> ExecutionId:
            return EXECUTION_ID

    return StartExecutionHandler(
        authorization=RecordingAuthorization(),
        identities=SeqIds(),
        orchestrator=orchestrator,
    )


@pytest.mark.asyncio
async def test_get_execution_snapshot_returns_snapshot_when_found() -> None:
    orchestrator = InMemoryOrchestratorPort(
        SystemUtcClock(),
        InMemoryRuntimeDatabase(),
    )
    await _start_handler(orchestrator).handle(
        StartExecutionCommand(
            correlation_id=CorrelationId(UUID(int=1)),
            actor_id=ACTOR,
            scope=SCOPE,
            objective_ref=ArtifactId(UUID(int=4)),
            root_agent_id=AgentDefinitionId(UUID(int=5)),
            memory_query=None,
            budget=_budget(),
            idempotency_key="start-1",
        )
    )
    handler = GetExecutionSnapshotHandler(
        authorization=RecordingAuthorization(),
        orchestrator=orchestrator,
    )
    result = await handler.handle(
        GetExecutionSnapshotQuery(
            actor_id=ACTOR,
            scope=SCOPE,
            execution_id=EXECUTION_ID,
        )
    )
    assert result.snapshot.execution_id == EXECUTION_ID


@pytest.mark.asyncio
async def test_get_execution_snapshot_raises_not_found() -> None:
    orchestrator = InMemoryOrchestratorPort(
        SystemUtcClock(),
        InMemoryRuntimeDatabase(),
    )
    handler = GetExecutionSnapshotHandler(
        authorization=RecordingAuthorization(),
        orchestrator=orchestrator,
    )
    with pytest.raises(ExecutionNotFound):
        await handler.handle(
            GetExecutionSnapshotQuery(
                actor_id=ACTOR,
                scope=SCOPE,
                execution_id=EXECUTION_ID,
            )
        )


@pytest.mark.asyncio
async def test_get_execution_snapshot_denial_authorizes_first_and_accesses_nothing_else() -> None:
    authorization = RecordingAuthorization(allowed=False)
    handler = GetExecutionSnapshotHandler(
        authorization=authorization,
        orchestrator=MustNotBeUsed(),
    )
    with pytest.raises(ExecutionAuthorizationDenied):
        await handler.handle(
            GetExecutionSnapshotQuery(
                actor_id=ACTOR,
                scope=SCOPE,
                execution_id=EXECUTION_ID,
            )
        )
    assert len(authorization.calls) == 1
    assert authorization.calls[0].action == "get_execution"
