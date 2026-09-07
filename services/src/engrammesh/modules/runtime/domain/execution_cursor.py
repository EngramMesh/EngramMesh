"""Opaque keyset cursors for execution listing."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.runtime.domain.errors import InvalidExecutionCursor
from engrammesh.shared.kernel.ids import ExecutionId


def _canonical_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "updated_at must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


def encode_execution_cursor(*, updated_at: datetime, execution_id: ExecutionId) -> str:
    payload = {
        "updated_at": _canonical_utc(updated_at).isoformat(),
        "execution_id": str(execution_id.value),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_execution_cursor(cursor: str) -> tuple[datetime, ExecutionId]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw.decode("utf-8"))
        updated_at = datetime.fromisoformat(payload["updated_at"])
        execution_id = ExecutionId(UUID(payload["execution_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise InvalidExecutionCursor() from None
    return _canonical_utc(updated_at), execution_id
