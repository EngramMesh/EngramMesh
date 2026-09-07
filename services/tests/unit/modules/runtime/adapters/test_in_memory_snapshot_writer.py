"""Unit tests for InMemoryRuntimeSnapshotWriter upsert semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.snapshot_writer import (
    InMemoryRuntimeSnapshotWriter,
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
async def test_upsert_ignores_lower_revision() -> None:
    writer = InMemoryRuntimeSnapshotWriter()
    await writer.upsert_snapshot(_snapshot(revision=2))
    await writer.upsert_snapshot(_snapshot(revision=1))
    assert writer.snapshots[EXECUTION_ID].revision == 2
