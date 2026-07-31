"""Reusable behavioral contracts for OrchestratorPort adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.domain.errors import (
    ExecutionIdempotencyConflict,
    ExecutionNotFound,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSpec,
    ExecutionStatus,
)
from engrammesh.modules.runtime.ports import OrchestratorPort
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


class OrchestratorAdapterHarness(Protocol):
    @property
    def orchestrator(self) -> OrchestratorPort: ...


type OrchestratorHarnessFactory = Callable[[], OrchestratorAdapterHarness]
type OrchestratorContractAssertion = Callable[[OrchestratorHarnessFactory], Awaitable[None]]


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=NOW + timedelta(hours=1),
    )


def _spec(*, execution_id: ExecutionId | None = None, key: str = "exec-1") -> ExecutionSpec:
    return ExecutionSpec(
        id=execution_id or ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key=key,
    )


async def start_creates_pending_snapshot(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    snapshot = await orchestrator.start(_spec())
    assert snapshot.status == ExecutionStatus.PENDING
    assert snapshot.revision == 1


async def start_exact_replay_is_idempotent(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    first = await orchestrator.start(_spec(execution_id=ExecutionId.new(), key="replay"))
    second = await orchestrator.start(_spec(execution_id=ExecutionId.new(), key="replay"))
    assert second.execution_id == first.execution_id


async def start_conflict_on_mismatched_replay(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    await orchestrator.start(_spec(key="conflict"))
    different_scope = ExecutionSpec(
        id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SubjectId.new(), workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key="conflict",
    )
    with pytest.raises(ExecutionIdempotencyConflict):
        await orchestrator.start(different_scope)


async def get_snapshot_is_tenant_scoped(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    created = await orchestrator.start(_spec())
    with pytest.raises(ExecutionNotFound):
        await orchestrator.get_snapshot(
            MemoryScope(TenantId.new(), SUBJECT),
            created.execution_id,
        )


async def cancel_reaches_cancelled(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    created = await orchestrator.start(_spec())
    cancelled = await orchestrator.cancel(created.scope, created.execution_id, "cancel-1")
    assert cancelled.status == ExecutionStatus.CANCELLED


async def cancel_is_idempotent_from_terminal(factory: OrchestratorHarnessFactory) -> None:
    orchestrator = factory().orchestrator
    created = await orchestrator.start(_spec())
    first = await orchestrator.cancel(created.scope, created.execution_id, "cancel-1")
    second = await orchestrator.cancel(created.scope, created.execution_id, "cancel-2")
    assert second.status == ExecutionStatus.CANCELLED
    assert second.execution_id == first.execution_id


ORCHESTRATOR_PORT_CONTRACTS: tuple[OrchestratorContractAssertion, ...] = (
    start_creates_pending_snapshot,
    start_exact_replay_is_idempotent,
    start_conflict_on_mismatched_replay,
    get_snapshot_is_tenant_scoped,
    cancel_reaches_cancelled,
    cancel_is_idempotent_from_terminal,
)
