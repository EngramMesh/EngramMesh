"""Temporal workflow for the minimal durable execution lifecycle."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
    apply_execution_cancel,
)
from engrammesh.modules.runtime.adapters.temporal.mappers import (
    initial_snapshot_payload,
)
from engrammesh.shared.kernel.ids import ExecutionId, TenantId


def workflow_id(tenant_id: TenantId, execution_id: ExecutionId) -> str:
    """Return the stable Temporal workflow identifier for one execution."""
    return f"{tenant_id}:{execution_id}"


_ACTIVITY_RETRY = RetryPolicy(maximum_attempts=3)
_ACTIVITY_TIMEOUT = timedelta(seconds=30)


@workflow.defn
class ExecutionLifecycleWorkflow:
    """Minimal lifecycle: pending → planning → running → succeeded."""

    def __init__(self) -> None:
        self._snapshot: dict[str, Any] = {}
        self._cancel_requested = False

    @workflow.run
    async def run(self, spec_payload: dict[str, Any]) -> None:
        self._snapshot = initial_snapshot_payload(
            spec_payload,
            updated_at=workflow.now(),
        )

        if self._cancel_requested:
            await self._apply_cancel()
            return

        self._snapshot = await workflow.execute_activity(
            advance_to_planning,
            args=[self._snapshot, workflow.now().isoformat()],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY,
        )

        if self._cancel_requested:
            await self._apply_cancel()
            return

        self._snapshot = await workflow.execute_activity(
            advance_to_running,
            args=[self._snapshot, workflow.now().isoformat()],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY,
        )

        if self._cancel_requested:
            await self._apply_cancel()
            return

        self._snapshot = await workflow.execute_activity(
            advance_to_succeeded,
            args=[self._snapshot, workflow.now().isoformat()],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY,
        )

    @workflow.signal
    def request_cancel(self) -> None:
        self._cancel_requested = True

    @workflow.query
    def current_snapshot(self) -> dict[str, Any]:
        return self._snapshot

    async def _apply_cancel(self) -> None:
        self._snapshot = await workflow.execute_activity(
            apply_execution_cancel,
            args=[self._snapshot, workflow.now().isoformat()],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_ACTIVITY_RETRY,
        )
