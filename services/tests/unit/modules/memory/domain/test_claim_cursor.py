from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.memory.domain.claim_cursor import (
    decode_claim_cursor,
    encode_claim_cursor,
)
from engrammesh.modules.memory.domain.errors import InvalidClaimCursor
from engrammesh.shared.kernel.ids import MemoryId

CLAIM_ID = MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db"))
RECORDED_AT = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def test_round_trip_claim_cursor() -> None:
    cursor = encode_claim_cursor(recorded_from=RECORDED_AT, claim_id=CLAIM_ID)
    recorded_from, claim_id = decode_claim_cursor(cursor)
    assert recorded_from == RECORDED_AT
    assert claim_id == CLAIM_ID


def test_invalid_claim_cursor_raises() -> None:
    with pytest.raises(InvalidClaimCursor):
        decode_claim_cursor("not-a-cursor")
