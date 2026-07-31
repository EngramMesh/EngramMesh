"""In-memory OrchestratorPort with start idempotency and legal cancel transitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import MappingProxyType
from typing import final

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
    _CommittedRuntimeState,
)
from engrammesh.modules.runtime.domain.errors import (
    ExecutionIdempotencyConflict,
    ExecutionNotFound,
    InvalidExecutionTransition,
)
from engrammesh.modules.runtime.domain.model import (
    ExecutionSnapshot,
    ExecutionSpec,
    ExecutionStatus,
)
from engrammesh.modules.runtime.domain.state import can_transition_execution
from engrammesh.modules.runtime.ports import ClockPort
from engrammesh.shared.kernel.ids import ExecutionId, TenantId


def _spec_fingerprint(spec: ExecutionSpec) -> tuple[object, ...]:
    mq = spec.memory_query
    mq_part: tuple[object, ...]
    if mq is None:
        mq_part = (None,)
    else:
        mq_part = (
            mq.query_id,
            mq.text,
            mq.limit,
            str(mq.scope),
            mq.valid_at,
            mq.recorded_at,
        )
    return (
        spec.scope.tenant_id,
        spec.scope.subject_id,
        spec.scope.workspace_id,
        spec.scope.agent_id,
        spec.objective_ref,
        spec.root_agent_id,
        mq_part,
        spec.budget.max_input_tokens,
        spec.budget.max_output_tokens,
        spec.budget.max_cost_micros,
        spec.budget.deadline,
        spec.idempotency_key,
    )


def _workflow_id(tenant_id: TenantId, execution_id: ExecutionId) -> str:
    return f"{tenant_id}:{execution_id}"


def _snapshot_for_scope(
    state: _CommittedRuntimeState,
    scope: MemoryScope,
    execution_id: ExecutionId,
) -> ExecutionSnapshot:
    snapshot = state.snapshots.get(execution_id)
    if snapshot is None or snapshot.scope != scope:
        raise ExecutionNotFound()
    return snapshot


def _commit_snapshot(
    state: _CommittedRuntimeState,
    snapshot: ExecutionSnapshot,
) -> _CommittedRuntimeState:
    snapshots = dict(state.snapshots)
    snapshots[snapshot.execution_id] = snapshot
    return replace(
        state,
        snapshots=MappingProxyType(snapshots),
    )


def _cancel_snapshot(
    snapshot: ExecutionSnapshot,
    *,
    updated_at: datetime,
) -> ExecutionSnapshot:
    if snapshot.status in {
        ExecutionStatus.CANCELLED,
        ExecutionStatus.FAILED,
    }:
        return snapshot
    if snapshot.status is ExecutionStatus.SUCCEEDED:
        raise InvalidExecutionTransition()

    current = snapshot
    if current.status is ExecutionStatus.CANCELLING:
        if not can_transition_execution(
            ExecutionStatus.CANCELLING,
            ExecutionStatus.CANCELLED,
        ):
            raise InvalidExecutionTransition()
        return replace(
            current,
            status=ExecutionStatus.CANCELLED,
            revision=current.revision + 1,
            updated_at=updated_at,
        )

    if not can_transition_execution(current.status, ExecutionStatus.CANCELLING):
        raise InvalidExecutionTransition()
    cancelling = replace(
        current,
        status=ExecutionStatus.CANCELLING,
        revision=current.revision + 1,
        updated_at=updated_at,
    )
    if not can_transition_execution(
        ExecutionStatus.CANCELLING,
        ExecutionStatus.CANCELLED,
    ):
        raise InvalidExecutionTransition()
    return replace(
        cancelling,
        status=ExecutionStatus.CANCELLED,
        revision=cancelling.revision + 1,
        updated_at=updated_at,
    )


@final
class InMemoryOrchestratorPort:
    """OrchestratorPort backed by an in-process execution index."""

    __slots__ = ("_clock", "_database")

    def __init__(
        self,
        clock: ClockPort,
        database: InMemoryRuntimeDatabase,
    ) -> None:
        self._clock = clock
        self._database = database

    @property
    def database(self) -> InMemoryRuntimeDatabase:
        return self._database

    async def start(self, spec: ExecutionSpec) -> ExecutionSnapshot:
        fingerprint = _spec_fingerprint(spec)
        index_key = (spec.scope.tenant_id, spec.idempotency_key)
        updated_at = await self._clock.now()

        def _start(state: _CommittedRuntimeState) -> _CommittedRuntimeState:
            existing_id = state.idempotency_index.get(index_key)
            if existing_id is not None:
                stored_fingerprint = state.fingerprints.get(existing_id)
                if stored_fingerprint != fingerprint:
                    raise ExecutionIdempotencyConflict()
                return state

            snapshot = ExecutionSnapshot(
                execution_id=spec.id,
                scope=spec.scope,
                revision=1,
                status=ExecutionStatus.PENDING,
                plan_revision=None,
                node_statuses=MappingProxyType({}),
                suspension=None,
                result_ref=None,
                failure=None,
                updated_at=updated_at,
            )
            snapshots = dict(state.snapshots)
            snapshots[snapshot.execution_id] = snapshot
            idempotency_index = dict(state.idempotency_index)
            idempotency_index[index_key] = snapshot.execution_id
            fingerprints = dict(state.fingerprints)
            fingerprints[snapshot.execution_id] = fingerprint
            return _CommittedRuntimeState(
                snapshots=MappingProxyType(snapshots),
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await self._database.write(_start)
        return await self._database.read(
            lambda state: state.snapshots[state.idempotency_index[index_key]]
        )

    async def get_snapshot(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
    ) -> ExecutionSnapshot:
        return await self._database.read(
            lambda state: _snapshot_for_scope(state, scope, execution_id)
        )

    async def cancel(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
        idempotency_key: str,
    ) -> ExecutionSnapshot:
        del idempotency_key
        updated_at = await self._clock.now()

        def _cancel(state: _CommittedRuntimeState) -> _CommittedRuntimeState:
            snapshot = _snapshot_for_scope(state, scope, execution_id)
            cancelled = _cancel_snapshot(snapshot, updated_at=updated_at)
            if cancelled is snapshot:
                return state
            return _commit_snapshot(state, cancelled)

        await self._database.write(_cancel)
        return await self._database.read(
            lambda state: _snapshot_for_scope(state, scope, execution_id)
        )
