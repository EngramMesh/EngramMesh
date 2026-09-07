"""Unit tests for transaction-scoped outbox on InMemoryRuntimeDatabase."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.shared.status_changed_event import (
    build_execution_status_changed_event,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    ExecutionId,
    SubjectId,
    TenantId,
)

UPDATED_AT = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
EXECUTION_ID = ExecutionId(UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
TENANT_ID = TenantId(UUID("11111111-2222-3333-4444-555555555555"))


def make_status_changed_event() -> EventEnvelope:
    snapshot = ExecutionSnapshot(
        execution_id=EXECUTION_ID,
        scope=MemoryScope(TENANT_ID, SubjectId(UUID(int=1))),
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses={},
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=UPDATED_AT,
    )
    return build_execution_status_changed_event(
        event_id=EventId(UUID(int=9)),
        correlation_id=CorrelationId(EXECUTION_ID.value),
        causation_id=None,
        previous_status=None,
        snapshot=snapshot,
    )


@pytest.mark.asyncio
async def test_in_memory_write_persists_buffered_outbox_events() -> None:
    database = InMemoryRuntimeDatabase()
    event = make_status_changed_event()

    async def _mutate(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        await outbox.publish(event)
        return state

    await database.write(_mutate)
    stored = await database.read(lambda state: state.outbox_events)
    assert stored == (event,)
