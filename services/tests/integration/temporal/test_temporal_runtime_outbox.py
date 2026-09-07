"""Integration tests for runtime outbox publishing from Temporal activities."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from temporalio import activity
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
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
    apply_execution_cancel,
    configure_runtime_outbox_writer,
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

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
SUBJECT = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))
TASK_QUEUE = "temporal-runtime-outbox-test"
SLOW_ACTIVITY_DELAY_S = 0.5


@activity.defn(name="advance_to_planning")
async def slow_advance_to_planning(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    await asyncio.sleep(SLOW_ACTIVITY_DELAY_S)
    return await advance_to_planning(snapshot_payload, updated_at_iso)


@activity.defn(name="advance_to_running")
async def slow_advance_to_running(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    await asyncio.sleep(SLOW_ACTIVITY_DELAY_S)
    return await advance_to_running(snapshot_payload, updated_at_iso)


@activity.defn(name="advance_to_succeeded")
async def slow_advance_to_succeeded(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    await asyncio.sleep(SLOW_ACTIVITY_DELAY_S)
    return await advance_to_succeeded(snapshot_payload, updated_at_iso)


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=NOW + timedelta(hours=1),
    )


def _spec(*, key: str = "outbox-lifecycle") -> ExecutionSpec:
    return ExecutionSpec(
        id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=None,
        budget=_budget(),
        idempotency_key=key,
    )


def _production_activities() -> list[object]:
    return [
        advance_to_planning,
        advance_to_running,
        advance_to_succeeded,
        apply_execution_cancel,
    ]


@pytest.fixture
def runtime_outbox_writer() -> InMemoryRuntimeOutboxWriter:
    writer = InMemoryRuntimeOutboxWriter()
    configure_runtime_outbox_writer(writer)
    yield writer
    configure_runtime_outbox_writer(None)


async def _poll_until(
    orchestrator: TemporalOrchestratorPort,
    scope: MemoryScope,
    execution_id: ExecutionId,
    *,
    target: ExecutionStatus,
    env: WorkflowEnvironment,
    timeout_s: float = 30.0,
) -> ExecutionStatus:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        snapshot = await orchestrator.get_snapshot(scope, execution_id)
        if snapshot.status is target:
            return snapshot.status
        await env.sleep(0.05)
    snapshot = await orchestrator.get_snapshot(scope, execution_id)
    return snapshot.status


async def _poll_until_active(
    orchestrator: TemporalOrchestratorPort,
    scope: MemoryScope,
    execution_id: ExecutionId,
    *,
    env: WorkflowEnvironment,
) -> ExecutionStatus:
    deadline = asyncio.get_running_loop().time() + 10.0
    while asyncio.get_running_loop().time() < deadline:
        snapshot = await orchestrator.get_snapshot(scope, execution_id)
        if snapshot.status in {
            ExecutionStatus.PENDING,
            ExecutionStatus.PLANNING,
            ExecutionStatus.RUNNING,
        }:
            return snapshot.status
        if snapshot.status in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
        }:
            return snapshot.status
        await env.sleep(0.01)
    snapshot = await orchestrator.get_snapshot(scope, execution_id)
    return snapshot.status


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_temporal_lifecycle_emits_three_status_changed_events(
    runtime_outbox_writer: InMemoryRuntimeOutboxWriter,
) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        spec = _spec()
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=_production_activities(),
        ):
            started = await orchestrator.start(spec)
            final_status = await _poll_until(
                orchestrator,
                spec.scope,
                started.execution_id,
                target=ExecutionStatus.SUCCEEDED,
                env=env,
            )
            assert final_status is ExecutionStatus.SUCCEEDED

    assert len(runtime_outbox_writer.events) == 3
    assert [event.payload["status"] for event in runtime_outbox_writer.events] == [
        "planning",
        "running",
        "succeeded",
    ]


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_temporal_cancel_mid_flight_emits_cancel_events(
    runtime_outbox_writer: InMemoryRuntimeOutboxWriter,
) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        spec = _spec(key="outbox-cancel")
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                slow_advance_to_planning,
                slow_advance_to_running,
                slow_advance_to_succeeded,
                apply_execution_cancel,
            ],
        ):
            started = await orchestrator.start(spec)
            status = await _poll_until_active(
                orchestrator,
                spec.scope,
                started.execution_id,
                env=env,
            )
            assert status in {
                ExecutionStatus.PENDING,
                ExecutionStatus.PLANNING,
                ExecutionStatus.RUNNING,
            }

            cancelled = await orchestrator.cancel(
                spec.scope,
                started.execution_id,
                "cancel-outbox-1",
            )
            assert cancelled.status is ExecutionStatus.CANCELLED

    cancel_statuses = [
        event.payload["status"]
        for event in runtime_outbox_writer.events
        if event.payload["status"] in {"cancelling", "cancelled"}
    ]
    assert 1 <= len(cancel_statuses) <= 2
    assert cancel_statuses[-1] == "cancelled"
