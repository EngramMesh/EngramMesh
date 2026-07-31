"""Unit tests for TemporalOrchestratorPort start idempotency edge cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from temporalio.service import RPCError, RPCStatusCode

from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.temporal.orchestrator import (
    TemporalOrchestratorPort,
)
from engrammesh.modules.runtime.application.errors import OrchestrationUnavailable
from engrammesh.modules.runtime.domain.model import Budget, ExecutionSpec
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    ExecutionId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
SUBJECT = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=NOW + timedelta(hours=1),
    )


def _spec(*, key: str = "rollback-test") -> ExecutionSpec:
    return ExecutionSpec(
        id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_start_rolls_back_index_when_workflow_start_fails() -> None:
    index = InMemoryRuntimeDatabase()
    client = AsyncMock()
    client.start_workflow = AsyncMock(
        side_effect=RPCError(
            "unavailable",
            RPCStatusCode.UNAVAILABLE,
            b"",
        )
    )
    orchestrator = TemporalOrchestratorPort(
        client,
        task_queue="test-queue",
        index=index,
        clock=SystemUtcClock(),
    )
    spec = _spec()

    with pytest.raises(OrchestrationUnavailable):
        await orchestrator.start(spec)

    index_size = await index.read(lambda state: len(state.idempotency_index))
    assert index_size == 0
