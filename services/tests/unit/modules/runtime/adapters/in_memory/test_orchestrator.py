"""Unit tests for the in-memory OrchestratorPort."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
    _spec_fingerprint,
)
from engrammesh.modules.runtime.domain.errors import (
    ExecutionIdempotencyConflict,
    ExecutionNotFound,
    InvalidExecutionTransition,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSpec,
    ExecutionStatus,
)
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
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


def _spec(
    *,
    execution_id: ExecutionId | None = None,
    key: str = "exec-1",
) -> ExecutionSpec:
    return ExecutionSpec(
        id=execution_id or ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key=key,
    )


@pytest.fixture
def orchestrator() -> InMemoryOrchestratorPort:
    return InMemoryOrchestratorPort(
        clock=SystemUtcClock(),
        database=InMemoryRuntimeDatabase(),
    )


@pytest.mark.asyncio
async def test_start_creates_pending_snapshot(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    snapshot = await orchestrator.start(_spec())

    assert snapshot.status == ExecutionStatus.PENDING
    assert snapshot.revision == 1
    assert snapshot.scope == MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")


@pytest.mark.asyncio
async def test_start_exact_replay_is_idempotent(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    first = await orchestrator.start(
        _spec(execution_id=ExecutionId.new(), key="replay")
    )
    second = await orchestrator.start(
        _spec(execution_id=ExecutionId.new(), key="replay")
    )

    assert second.execution_id == first.execution_id
    assert second.revision == first.revision


@pytest.mark.asyncio
async def test_start_conflict_on_mismatched_replay(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
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


@pytest.mark.asyncio
async def test_start_replay_without_snapshot_raises_not_found(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    spec = _spec(key="orphan-idem")
    fingerprint = _spec_fingerprint(spec)
    index_key = (spec.scope.tenant_id, spec.idempotency_key)
    execution_id = ExecutionId.new()

    async def _seed_idempotency_only(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        del outbox
        idempotency_index = dict(state.idempotency_index)
        idempotency_index[index_key] = execution_id
        fingerprints = dict(state.fingerprints)
        fingerprints[execution_id] = fingerprint
        return CommittedRuntimeState(
            snapshots=state.snapshots,
            idempotency_index=MappingProxyType(idempotency_index),
            fingerprints=MappingProxyType(fingerprints),
        )

    await orchestrator.database.write(_seed_idempotency_only)

    with pytest.raises(ExecutionNotFound):
        await orchestrator.start(
            _spec(execution_id=ExecutionId.new(), key="orphan-idem")
        )


@pytest.mark.asyncio
async def test_get_snapshot_returns_stored_snapshot(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    created = await orchestrator.start(_spec())
    fetched = await orchestrator.get_snapshot(created.scope, created.execution_id)

    assert fetched == created


@pytest.mark.asyncio
async def test_get_snapshot_raises_not_found_for_scope_mismatch(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    created = await orchestrator.start(_spec())

    with pytest.raises(ExecutionNotFound):
        await orchestrator.get_snapshot(
            MemoryScope(TenantId.new(), SUBJECT),
            created.execution_id,
        )


@pytest.mark.asyncio
async def test_get_snapshot_raises_not_found_for_unknown_execution(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    scope = MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")

    with pytest.raises(ExecutionNotFound):
        await orchestrator.get_snapshot(scope, ExecutionId.new())


@pytest.mark.asyncio
async def test_cancel_reaches_cancelled(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    created = await orchestrator.start(_spec())
    cancelled = await orchestrator.cancel(
        created.scope,
        created.execution_id,
        "cancel-1",
    )

    assert cancelled.status == ExecutionStatus.CANCELLED
    assert cancelled.revision == created.revision + 2


@pytest.mark.asyncio
async def test_cancel_is_idempotent_from_terminal(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    created = await orchestrator.start(_spec())
    first = await orchestrator.cancel(
        created.scope,
        created.execution_id,
        "cancel-1",
    )
    second = await orchestrator.cancel(
        created.scope,
        created.execution_id,
        "cancel-2",
    )

    assert second.status == ExecutionStatus.CANCELLED
    assert second.execution_id == first.execution_id
    assert second.revision == first.revision


@pytest.mark.asyncio
async def test_cancel_raises_invalid_transition_from_terminal_success(
    orchestrator: InMemoryOrchestratorPort,
) -> None:
    created = await orchestrator.start(_spec())
    succeeded = replace(
        created,
        status=ExecutionStatus.SUCCEEDED,
        revision=created.revision + 1,
    )
    orchestrator.database.replace_snapshot_for_tests(succeeded)

    with pytest.raises(InvalidExecutionTransition):
        await orchestrator.cancel(created.scope, created.execution_id, "cancel-2")


@pytest.mark.asyncio
async def test_start_emits_pending_status_changed_event() -> None:
    database = InMemoryRuntimeDatabase()
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    spec = _spec()
    await orchestrator.start(spec)
    events = await database.read(lambda state: state.outbox_events)
    assert len(events) == 1
    assert events[0].event_type == "runtime.execution-status-changed"
    assert events[0].payload["status"] == "pending"
    assert events[0].payload["previous_status"] is None


@pytest.mark.asyncio
async def test_idempotent_start_emits_no_events() -> None:
    database = InMemoryRuntimeDatabase()
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    spec = _spec(key="idem-outbox")
    await orchestrator.start(spec)
    events_after_first = await database.read(lambda state: state.outbox_events)
    await orchestrator.start(_spec(execution_id=ExecutionId.new(), key="idem-outbox"))
    events_after_replay = await database.read(lambda state: state.outbox_events)
    assert events_after_replay == events_after_first


@pytest.mark.asyncio
async def test_cancel_from_running_emits_cancelling_and_cancelled_events() -> None:
    database = InMemoryRuntimeDatabase()
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    created = await orchestrator.start(_spec())
    running = replace(created, status=ExecutionStatus.RUNNING, revision=created.revision + 1)
    database.replace_snapshot_for_tests(running)

    await orchestrator.cancel(running.scope, running.execution_id, "cancel-outbox")

    events = await database.read(lambda state: state.outbox_events)
    cancel_events = events[1:]
    assert len(cancel_events) == 2
    assert cancel_events[0].payload["previous_status"] == "running"
    assert cancel_events[0].payload["status"] == "cancelling"
    assert cancel_events[1].payload["previous_status"] == "cancelling"
    assert cancel_events[1].payload["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_from_cancelling_emits_single_cancelled_event() -> None:
    database = InMemoryRuntimeDatabase()
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    created = await orchestrator.start(_spec())
    cancelling = replace(
        created,
        status=ExecutionStatus.CANCELLING,
        revision=created.revision + 1,
    )
    database.replace_snapshot_for_tests(cancelling)

    await orchestrator.cancel(cancelling.scope, cancelling.execution_id, "cancel-outbox")

    events = await database.read(lambda state: state.outbox_events)
    cancel_events = events[1:]
    assert len(cancel_events) == 1
    assert cancel_events[0].payload["previous_status"] == "cancelling"
    assert cancel_events[0].payload["status"] == "cancelled"
