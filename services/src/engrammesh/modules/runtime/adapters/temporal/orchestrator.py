"""Temporal OrchestratorPort with shared start idempotency via ExecutionIndex."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import MappingProxyType
from typing import final

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
    _CommittedRuntimeState,
)
from engrammesh.modules.runtime.adapters.temporal.mappers import (
    payload_to_snapshot,
    spec_to_payload,
)
from engrammesh.modules.runtime.adapters.temporal.workflows import (
    ExecutionLifecycleWorkflow,
    workflow_id,
)
from engrammesh.modules.runtime.application.errors import OrchestrationUnavailable
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


def _snapshot_for_scope(
    snapshot: ExecutionSnapshot,
    scope: MemoryScope,
    execution_id: ExecutionId,
) -> ExecutionSnapshot:
    if snapshot.execution_id != execution_id or snapshot.scope != scope:
        raise ExecutionNotFound()
    return snapshot


@final
class TemporalOrchestratorPort:
    """OrchestratorPort backed by Temporal workflows and a shared idempotency index."""

    __slots__ = ("_client", "_clock", "_index", "_task_queue")

    def __init__(
        self,
        client: Client,
        *,
        task_queue: str,
        index: InMemoryRuntimeDatabase,
        clock: ClockPort,
    ) -> None:
        self._client = client
        self._task_queue = task_queue
        self._index = index
        self._clock = clock

    @property
    def index(self) -> InMemoryRuntimeDatabase:
        return self._index

    async def start(self, spec: ExecutionSpec) -> ExecutionSnapshot:
        fingerprint = _spec_fingerprint(spec)
        index_key = (spec.scope.tenant_id, spec.idempotency_key)
        start_result: dict[str, object] = {"is_new": False, "execution_id": None}

        def _register(state: _CommittedRuntimeState) -> _CommittedRuntimeState:
            existing_id = state.idempotency_index.get(index_key)
            if existing_id is not None:
                stored_fingerprint = state.fingerprints.get(existing_id)
                if stored_fingerprint != fingerprint:
                    raise ExecutionIdempotencyConflict()
                start_result["execution_id"] = existing_id
                start_result["is_new"] = False
                return state

            idempotency_index = dict(state.idempotency_index)
            idempotency_index[index_key] = spec.id
            fingerprints = dict(state.fingerprints)
            fingerprints[spec.id] = fingerprint
            start_result["execution_id"] = spec.id
            start_result["is_new"] = True
            return replace(
                state,
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await self._index.write(_register)
        execution_id = start_result["execution_id"]
        assert isinstance(execution_id, ExecutionId)

        if start_result["is_new"]:
            wf_id = workflow_id(spec.scope.tenant_id, execution_id)
            try:
                await self._client.start_workflow(
                    ExecutionLifecycleWorkflow.run,
                    spec_to_payload(spec),
                    id=wf_id,
                    task_queue=self._task_queue,
                )
            except WorkflowAlreadyStartedError:
                stored_fingerprint = await self._index.read(
                    lambda state: state.fingerprints.get(execution_id)
                )
                if stored_fingerprint != fingerprint:
                    raise ExecutionIdempotencyConflict() from None
            except RPCError as exc:
                raise OrchestrationUnavailable() from exc

        return await self._query_snapshot(
            spec.scope.tenant_id,
            execution_id,
            spec.scope,
        )

    async def get_snapshot(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
    ) -> ExecutionSnapshot:
        return await self._query_snapshot(scope.tenant_id, execution_id, scope)

    async def cancel(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
        idempotency_key: str,
    ) -> ExecutionSnapshot:
        del idempotency_key
        snapshot = await self._query_snapshot(scope.tenant_id, execution_id, scope)

        if snapshot.status in {
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
        }:
            return snapshot
        if snapshot.status is ExecutionStatus.SUCCEEDED:
            raise InvalidExecutionTransition()

        wf_id = workflow_id(scope.tenant_id, execution_id)
        try:
            handle = self._client.get_workflow_handle(wf_id)
            await handle.signal(ExecutionLifecycleWorkflow.request_cancel)
        except RPCError as exc:
            snapshot = await self._query_snapshot(scope.tenant_id, execution_id, scope)
            if snapshot.status is ExecutionStatus.SUCCEEDED:
                raise InvalidExecutionTransition() from exc
            if snapshot.status in {
                ExecutionStatus.CANCELLED,
                ExecutionStatus.FAILED,
            }:
                return snapshot
            raise OrchestrationUnavailable() from exc

        for _ in range(200):
            snapshot = await self._query_snapshot(scope.tenant_id, execution_id, scope)
            if snapshot.status is ExecutionStatus.CANCELLED:
                return snapshot
            if snapshot.status is ExecutionStatus.SUCCEEDED:
                raise InvalidExecutionTransition()
            if snapshot.status is ExecutionStatus.FAILED:
                return snapshot
            await asyncio.sleep(0.01)

        raise OrchestrationUnavailable()

    async def _query_snapshot(
        self,
        tenant_id: TenantId,
        execution_id: ExecutionId,
        scope: MemoryScope,
    ) -> ExecutionSnapshot:
        wf_id = workflow_id(tenant_id, execution_id)
        try:
            handle = self._client.get_workflow_handle(wf_id)
            payload = await handle.query(ExecutionLifecycleWorkflow.current_snapshot)
        except RPCError as exc:
            if exc.status is RPCStatusCode.NOT_FOUND:
                raise ExecutionNotFound() from exc
            raise OrchestrationUnavailable() from exc

        if not isinstance(payload, dict):
            raise OrchestrationUnavailable()

        snapshot = payload_to_snapshot(payload)
        return _snapshot_for_scope(snapshot, scope, execution_id)
