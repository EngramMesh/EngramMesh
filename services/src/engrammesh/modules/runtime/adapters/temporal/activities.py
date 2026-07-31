"""Stub Temporal activities for the minimal execution lifecycle workflow."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from temporalio import activity

from engrammesh.modules.runtime.adapters.temporal.mappers import (
    payload_to_snapshot,
    snapshot_to_payload,
)
from engrammesh.modules.runtime.domain.model import ExecutionStatus
from engrammesh.modules.runtime.domain.state import can_transition_execution


def _parse_updated_at(updated_at_iso: str) -> datetime:
    parsed = datetime.fromisoformat(updated_at_iso)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = "updated_at must be timezone-aware"
        raise ValueError(msg)
    return parsed


def _advance_status(
    snapshot_payload: dict[str, object],
    *,
    target: ExecutionStatus,
    updated_at_iso: str,
) -> dict[str, object]:
    snapshot = payload_to_snapshot(snapshot_payload)
    if not can_transition_execution(snapshot.status, target):
        msg = f"illegal transition from {snapshot.status} to {target}"
        raise ValueError(msg)
    advanced = replace(
        snapshot,
        status=target,
        revision=snapshot.revision + 1,
        updated_at=_parse_updated_at(updated_at_iso),
    )
    return snapshot_to_payload(advanced)


@activity.defn
async def advance_to_planning(
    snapshot_payload: dict[str, object],
    updated_at_iso: str,
) -> dict[str, object]:
    """Advance execution state from pending to planning."""
    return _advance_status(
        snapshot_payload,
        target=ExecutionStatus.PLANNING,
        updated_at_iso=updated_at_iso,
    )


@activity.defn
async def advance_to_running(
    snapshot_payload: dict[str, object],
    updated_at_iso: str,
) -> dict[str, object]:
    """Advance execution state from planning to running."""
    return _advance_status(
        snapshot_payload,
        target=ExecutionStatus.RUNNING,
        updated_at_iso=updated_at_iso,
    )


@activity.defn
async def advance_to_succeeded(
    snapshot_payload: dict[str, object],
    updated_at_iso: str,
) -> dict[str, object]:
    """Advance execution state from running to succeeded."""
    return _advance_status(
        snapshot_payload,
        target=ExecutionStatus.SUCCEEDED,
        updated_at_iso=updated_at_iso,
    )
