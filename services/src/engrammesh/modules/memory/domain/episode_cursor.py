"""Opaque keyset cursors for episode listing."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.domain.errors import InvalidEpisodeCursor
from engrammesh.shared.kernel.ids import MemoryId


def _canonical_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "ingested_at must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


def encode_episode_cursor(*, ingested_at: datetime, episode_id: MemoryId) -> str:
    payload = {
        "ingested_at": _canonical_utc(ingested_at).isoformat(),
        "episode_id": str(episode_id.value),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_episode_cursor(cursor: str) -> tuple[datetime, MemoryId]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw.decode("utf-8"))
        ingested_at = datetime.fromisoformat(payload["ingested_at"])
        episode_id = MemoryId(UUID(payload["episode_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise InvalidEpisodeCursor() from None
    return _canonical_utc(ingested_at), episode_id
