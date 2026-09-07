"""Integration tests for Temporal → snapshot projection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.outbox_writer import (
    InMemoryRuntimeOutboxWriter,
)
from engrammesh.modules.runtime.adapters.in_memory.snapshot_writer import (
    InMemoryRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
    apply_execution_cancel,
    configure_runtime_outbox_writer,
    configure_runtime_snapshot_writer,
)
from engrammesh.modules.runtime.adapters.temporal.orchestrator import (
    TemporalOrchestratorPort,
)
from engrammesh.modules.runtime.adapters.temporal.workflows import (
    ExecutionLifecycleWorkflow,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSpec,
    ExecutionStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    ExecutionId,
    SubjectId,
    TenantId,
)

pytestmark = pytest.mark.temporal

TASK_QUEUE = "temporal-snapshot-projection-test"
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
SUBJECT = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=NOW + timedelta(hours=1),
    )


def _spec() -> ExecutionSpec:
    return ExecutionSpec(
        id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key="snapshot-projection-start",
    )


@pytest.fixture
def snapshot_writer() -> InMemoryRuntimeSnapshotWriter:
    outbox = InMemoryRuntimeOutboxWriter()
    writer = InMemoryRuntimeSnapshotWriter()
    configure_runtime_outbox_writer(outbox)
    configure_runtime_snapshot_writer(writer)
    yield writer
    configure_runtime_outbox_writer(None)
    configure_runtime_snapshot_writer(None)


@pytest.fixture
def start_projection_writer() -> InMemoryRuntimeSnapshotWriter:
    outbox = InMemoryRuntimeOutboxWriter()
    writer = InMemoryRuntimeSnapshotWriter()
    configure_runtime_outbox_writer(outbox)
    yield writer
    configure_runtime_outbox_writer(None)


@pytest.mark.asyncio
async def test_start_projects_pending_snapshot_with_worker_running(
    start_projection_writer: InMemoryRuntimeSnapshotWriter,
) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker = Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
                apply_execution_cancel,
            ],
        )
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=InMemoryRuntimeDatabase(),
            clock=SystemUtcClock(),
            snapshot_writer=start_projection_writer,
        )
        spec = _spec()
        async with worker:
            await orchestrator.start(spec)
        assert spec.id in start_projection_writer.snapshots
        pending = next(
            snapshot
            for snapshot in start_projection_writer.upsert_history
            if snapshot.execution_id == spec.id
        )
        assert pending.status == ExecutionStatus.PENDING
        assert pending.revision == 1


async def _poll_until_succeeded(
    orchestrator: TemporalOrchestratorPort,
    scope: MemoryScope,
    execution_id: ExecutionId,
    *,
    env: WorkflowEnvironment,
) -> None:
    deadline = asyncio.get_running_loop().time() + 30.0
    while asyncio.get_running_loop().time() < deadline:
        snapshot = await orchestrator.get_snapshot(scope, execution_id)
        if snapshot.status is ExecutionStatus.SUCCEEDED:
            return
        await env.sleep(0.05)
    snapshot = await orchestrator.get_snapshot(scope, execution_id)
    assert snapshot.status is ExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_lifecycle_projects_terminal_status(
    snapshot_writer: InMemoryRuntimeSnapshotWriter,
) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker = Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
                apply_execution_cancel,
            ],
        )
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=InMemoryRuntimeDatabase(),
            clock=SystemUtcClock(),
            snapshot_writer=snapshot_writer,
        )
        spec = _spec()
        async with worker:
            await orchestrator.start(spec)
            await _poll_until_succeeded(
                orchestrator,
                spec.scope,
                spec.id,
                env=env,
            )
        assert spec.id in snapshot_writer.snapshots
        assert snapshot_writer.snapshots[spec.id].status == ExecutionStatus.SUCCEEDED
