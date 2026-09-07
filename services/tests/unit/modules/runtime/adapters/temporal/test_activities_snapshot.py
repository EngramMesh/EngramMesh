"""Unit tests for execution snapshot projection from Temporal activities."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.outbox_writer import (
    InMemoryRuntimeOutboxWriter,
)
from engrammesh.modules.runtime.adapters.in_memory.snapshot_writer import (
    InMemoryRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    configure_runtime_outbox_writer,
    configure_runtime_snapshot_writer,
)
from engrammesh.modules.runtime.adapters.temporal.mappers import snapshot_to_payload
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
SUBJECT = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))


def _pending_snapshot() -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws-1"),
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_advance_status_upserts_snapshot() -> None:
    writer = InMemoryRuntimeSnapshotWriter()
    configure_runtime_snapshot_writer(writer)
    configure_runtime_outbox_writer(InMemoryRuntimeOutboxWriter())
    payload = snapshot_to_payload(_pending_snapshot())
    await advance_to_planning(payload, NOW.isoformat())
    assert writer.snapshots
    configure_runtime_snapshot_writer(None)
    configure_runtime_outbox_writer(None)
