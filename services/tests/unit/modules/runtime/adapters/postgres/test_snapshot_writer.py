"""Unit tests for PostgresRuntimeSnapshotWriter upsert semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.postgres.snapshot_writer import (
    PostgresRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
EXECUTION_ID = ExecutionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))


def _snapshot(revision: int) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=EXECUTION_ID,
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        revision=revision,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_upsert_snapshot_executes_insert_on_conflict_sql() -> None:
    writer = PostgresRuntimeSnapshotWriter("postgresql://example")
    cursor = AsyncMock()
    connection = MagicMock()
    connection.cursor.return_value.__aenter__.return_value = cursor
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=None)

    mock_runtime_connection = MagicMock()
    mock_runtime_connection.connection.return_value = connection
    writer._connection = mock_runtime_connection

    await writer.upsert_snapshot(_snapshot(1))

    cursor.execute.assert_awaited_once()
    sql = cursor.execute.await_args.args[0]
    assert "ON CONFLICT (tenant_id, execution_id) DO UPDATE" in sql
    assert "runtime_execution_snapshots.revision < EXCLUDED.revision" in sql
