from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.memory.domain.episode_cursor import (
    decode_episode_cursor,
    encode_episode_cursor,
)
from engrammesh.modules.memory.domain.errors import InvalidEpisodeCursor
from engrammesh.shared.kernel.ids import MemoryId


def test_encode_decode_round_trip() -> None:
    ingested_at = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
    episode_id = MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db"))
    cursor = encode_episode_cursor(ingested_at=ingested_at, episode_id=episode_id)
    decoded_at, decoded_id = decode_episode_cursor(cursor)
    assert decoded_at == ingested_at
    assert decoded_id == episode_id


def test_decode_invalid_cursor_raises() -> None:
    with pytest.raises(InvalidEpisodeCursor):
        decode_episode_cursor("not-valid-base64!!!")
