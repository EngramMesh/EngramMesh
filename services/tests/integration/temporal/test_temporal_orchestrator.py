"""Integration tests for TemporalOrchestratorPort with WorkflowEnvironment."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
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
    _CommittedRuntimeState,
)
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
)
from engrammesh.modules.runtime.adapters.temporal.orchestrator import (
    TemporalOrchestratorPort,
    _spec_fingerprint,
)
from engrammesh.modules.runtime.adapters.temporal.workflows import (
    ExecutionLifecycleWorkflow,
)
from engrammesh.modules.runtime.application.errors import OrchestrationUnavailable
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
TASK_QUEUE = "temporal-orchestrator-test"
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
        try:
            snapshot = await orchestrator.get_snapshot(scope, execution_id)
        except OrchestrationUnavailable:
            await env.sleep(0.05)
            continue
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
    """Return the first in-flight status before terminal completion."""
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


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_temporal_start_get_succeeds() -> None:
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
            activities=[
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
            ],
        ):
            started = await orchestrator.start(spec)
            assert started.status is ExecutionStatus.PENDING

            final_status = await _poll_until(
                orchestrator,
                spec.scope,
                started.execution_id,
                target=ExecutionStatus.SUCCEEDED,
                env=env,
            )
            assert final_status is ExecutionStatus.SUCCEEDED

            fetched = await orchestrator.get_snapshot(spec.scope, started.execution_id)
            assert fetched.status is ExecutionStatus.SUCCEEDED
            assert fetched.execution_id == started.execution_id


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_temporal_start_idempotent_replay() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
            ],
        ):
            first = await orchestrator.start(
                _spec(execution_id=ExecutionId.new(), key="replay")
            )
            second = await orchestrator.start(
                _spec(execution_id=ExecutionId.new(), key="replay")
            )

            assert second.execution_id == first.execution_id


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_temporal_cancel_from_running() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        spec = _spec(key="cancel-running")
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                slow_advance_to_planning,
                slow_advance_to_running,
                slow_advance_to_succeeded,
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
                "cancel-1",
            )
            assert cancelled.status is ExecutionStatus.CANCELLED


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_temporal_survives_worker_restart() -> None:
    # Local dev server is required here: time-skipping test server does not
    # reliably resume in-flight workflows across worker process restarts.
    async with await WorkflowEnvironment.start_local() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        spec = _spec(key="worker-restart")
        worker_kwargs = {
            "client": env.client,
            "task_queue": TASK_QUEUE,
            "workflows": [ExecutionLifecycleWorkflow],
            "activities": [
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
            ],
        }

        async with Worker(**worker_kwargs):
            started = await orchestrator.start(spec)
            await _poll_until_active(
                orchestrator,
                spec.scope,
                started.execution_id,
                env=env,
            )

        async with Worker(**worker_kwargs):
            final_status = await _poll_until(
                orchestrator,
                spec.scope,
                started.execution_id,
                target=ExecutionStatus.SUCCEEDED,
                env=env,
                timeout_s=30.0,
            )
            assert final_status is ExecutionStatus.SUCCEEDED


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_temporal_recovers_orphaned_index_entry() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        index = InMemoryRuntimeDatabase()
        orchestrator = TemporalOrchestratorPort(
            env.client,
            task_queue=TASK_QUEUE,
            index=index,
            clock=SystemUtcClock(),
        )
        spec = _spec(execution_id=ExecutionId.new(), key="orphan-recovery")
        fingerprint = _spec_fingerprint(spec)
        index_key = (spec.scope.tenant_id, spec.idempotency_key)

        def _seed_orphan(state: _CommittedRuntimeState) -> _CommittedRuntimeState:
            idempotency_index = dict(state.idempotency_index)
            idempotency_index[index_key] = spec.id
            fingerprints = dict(state.fingerprints)
            fingerprints[spec.id] = fingerprint
            return replace(
                state,
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await index.write(_seed_orphan)

        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ExecutionLifecycleWorkflow],
            activities=[
                advance_to_planning,
                advance_to_running,
                advance_to_succeeded,
            ],
        ):
            started = await orchestrator.start(
                _spec(execution_id=ExecutionId.new(), key="orphan-recovery")
            )
            assert started.execution_id == spec.id
            assert started.status is ExecutionStatus.PENDING

            final_status = await _poll_until(
                orchestrator,
                spec.scope,
                started.execution_id,
                target=ExecutionStatus.SUCCEEDED,
                env=env,
            )
            assert final_status is ExecutionStatus.SUCCEEDED
