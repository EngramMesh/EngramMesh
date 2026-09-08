"""Opaque keyset cursors for claim listing."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.domain.errors import InvalidClaimCursor
from engrammesh.shared.kernel.ids import MemoryId


def _canonical_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "recorded_from must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


def encode_claim_cursor(*, recorded_from: datetime, claim_id: MemoryId) -> str:
    payload = {
        "recorded_from": _canonical_utc(recorded_from).isoformat(),
        "claim_id": str(claim_id.value),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_claim_cursor(cursor: str) -> tuple[datetime, MemoryId]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw.decode("utf-8"))
        recorded_from = datetime.fromisoformat(payload["recorded_from"])
        claim_id = MemoryId(UUID(payload["claim_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise InvalidClaimCursor() from None
    return _canonical_utc(recorded_from), claim_id
