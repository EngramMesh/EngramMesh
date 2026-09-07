"""Stub Temporal activities for the minimal execution lifecycle workflow."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from temporalio import activity

from engrammesh.modules.runtime.adapters.temporal.mappers import (
    payload_to_snapshot,
    snapshot_to_payload,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.modules.runtime.domain.state import can_transition_execution
from engrammesh.modules.runtime.ports import RuntimeOutboxWriterPort
from engrammesh.shared.kernel.ids import CorrelationId

_writer: RuntimeOutboxWriterPort | None = None


def configure_runtime_outbox_writer(writer: RuntimeOutboxWriterPort | None) -> None:
    global _writer
    _writer = writer


def _parse_updated_at(updated_at_iso: str) -> datetime:
    parsed = datetime.fromisoformat(updated_at_iso)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = "updated_at must be timezone-aware"
        raise ValueError(msg)
    return parsed


async def _publish_status_changed(
    *,
    previous_status: ExecutionStatus | None,
    snapshot: ExecutionSnapshot,
) -> None:
    if _writer is None:
        return
    await _writer.publish_status_changed(
        previous_status,
        snapshot,
        CorrelationId(snapshot.execution_id.value),
    )


async def _advance_status(
    snapshot_payload: dict[str, Any],
    *,
    target: ExecutionStatus,
    updated_at_iso: str,
) -> dict[str, Any]:
    snapshot = payload_to_snapshot(snapshot_payload)
    if not can_transition_execution(snapshot.status, target):
        msg = f"illegal transition from {snapshot.status} to {target}"
        raise ValueError(msg)
    previous_status = snapshot.status
    advanced = replace(
        snapshot,
        status=target,
        revision=snapshot.revision + 1,
        updated_at=_parse_updated_at(updated_at_iso),
    )
    await _publish_status_changed(previous_status=previous_status, snapshot=advanced)
    return snapshot_to_payload(advanced)


async def _apply_cancel(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    snapshot = payload_to_snapshot(snapshot_payload)
    if snapshot.status in {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }:
        return snapshot_payload

    updated_at = _parse_updated_at(updated_at_iso)
    if snapshot.status is not ExecutionStatus.CANCELLING:
        if not can_transition_execution(snapshot.status, ExecutionStatus.CANCELLING):
            return snapshot_payload
        previous_status = snapshot.status
        snapshot = replace(
            snapshot,
            status=ExecutionStatus.CANCELLING,
            revision=snapshot.revision + 1,
            updated_at=updated_at,
        )
        await _publish_status_changed(previous_status=previous_status, snapshot=snapshot)

    if not can_transition_execution(snapshot.status, ExecutionStatus.CANCELLED):
        return snapshot_to_payload(snapshot)

    cancelled = replace(
        snapshot,
        status=ExecutionStatus.CANCELLED,
        revision=snapshot.revision + 1,
        updated_at=updated_at,
    )
    await _publish_status_changed(
        previous_status=snapshot.status,
        snapshot=cancelled,
    )
    return snapshot_to_payload(cancelled)


@activity.defn
async def advance_to_planning(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    """Advance execution state from pending to planning."""
    return await _advance_status(
        snapshot_payload,
        target=ExecutionStatus.PLANNING,
        updated_at_iso=updated_at_iso,
    )


@activity.defn
async def advance_to_running(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    """Advance execution state from planning to running."""
    return await _advance_status(
        snapshot_payload,
        target=ExecutionStatus.RUNNING,
        updated_at_iso=updated_at_iso,
    )


@activity.defn
async def advance_to_succeeded(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    """Advance execution state from running to succeeded."""
    return await _advance_status(
        snapshot_payload,
        target=ExecutionStatus.SUCCEEDED,
        updated_at_iso=updated_at_iso,
    )


@activity.defn
async def apply_execution_cancel(
    snapshot_payload: dict[str, Any],
    updated_at_iso: str,
) -> dict[str, Any]:
    """Apply legal cancel transitions and publish status-changed events."""
    return await _apply_cancel(snapshot_payload, updated_at_iso)
