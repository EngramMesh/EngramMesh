from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.runtime.domain.errors import InvalidExecutionCursor
from engrammesh.modules.runtime.domain.execution_cursor import (
    decode_execution_cursor,
    encode_execution_cursor,
)
from engrammesh.shared.kernel.ids import ExecutionId

UPDATED_AT = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
EXECUTION_ID = ExecutionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))


def test_round_trip_cursor() -> None:
    cursor = encode_execution_cursor(
        updated_at=UPDATED_AT,
        execution_id=EXECUTION_ID,
    )
    decoded_at, decoded_id = decode_execution_cursor(cursor)
    assert decoded_at == UPDATED_AT
    assert decoded_id == EXECUTION_ID


def test_invalid_cursor_raises() -> None:
    with pytest.raises(InvalidExecutionCursor):
        decode_execution_cursor("not-valid")
