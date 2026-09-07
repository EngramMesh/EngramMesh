"""Unit tests for InMemoryRuntimeDatabase.stream()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.domain.errors import InvalidExecutionCursor
from engrammesh.modules.runtime.domain.execution_cursor import encode_execution_cursor
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId

NOW = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
SCOPE = MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")


def _snapshot(
    *,
    execution_id: ExecutionId | None = None,
    updated_at: datetime = NOW,
    revision: int = 1,
) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=execution_id or ExecutionId.new(),
        scope=SCOPE,
        revision=revision,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_stream_orders_by_updated_at_desc() -> None:
    database = InMemoryRuntimeDatabase()
    older = _snapshot(
        execution_id=ExecutionId(UUID("11111111-1111-1111-1111-111111111111")),
        updated_at=NOW,
    )
    newer = _snapshot(
        execution_id=ExecutionId(UUID("22222222-2222-2222-2222-222222222222")),
        updated_at=NOW + timedelta(minutes=1),
        revision=2,
    )
    database.replace_snapshot_for_tests(older)
    database.replace_snapshot_for_tests(newer)
    rows = await database.stream(SCOPE, limit=10)
    assert rows[0].execution_id == newer.execution_id


@pytest.mark.asyncio
async def test_stream_pagination_round_trip() -> None:
    database = InMemoryRuntimeDatabase()
    snapshots = [
        _snapshot(
            execution_id=ExecutionId(UUID(f"{index:032x}")),
            updated_at=NOW + timedelta(minutes=index),
            revision=index + 1,
        )
        for index in range(3)
    ]
    for snapshot in snapshots:
        database.replace_snapshot_for_tests(snapshot)

    page_one = await database.stream(SCOPE, limit=2)
    assert len(page_one) == 2
    cursor = encode_execution_cursor(
        updated_at=page_one[-1].updated_at,
        execution_id=page_one[-1].execution_id,
    )
    page_two = await database.stream(SCOPE, limit=2, cursor=cursor)
    assert len(page_two) == 1


@pytest.mark.asyncio
async def test_stream_invalid_cursor_raises() -> None:
    database = InMemoryRuntimeDatabase()
    database.replace_snapshot_for_tests(_snapshot())
    with pytest.raises(InvalidExecutionCursor):
        await database.stream(SCOPE, limit=10, cursor="bad")
