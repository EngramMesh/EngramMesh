from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.shared.status_changed_event import (
    build_execution_status_changed_event,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
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


def test_build_execution_status_changed_event_first_transition() -> None:
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
    event = build_execution_status_changed_event(
        event_id=EventId(UUID(int=9)),
        correlation_id=CorrelationId(EXECUTION_ID.value),
        causation_id=None,
        previous_status=None,
        snapshot=snapshot,
    )
    assert event.event_type == "runtime.execution-status-changed"
    assert event.schema_version == 1
    assert event.aggregate_id == EXECUTION_ID
    assert event.payload == {
        "execution_id": str(EXECUTION_ID),
        "revision": 1,
        "previous_status": None,
        "status": "pending",
        "updated_at": "2026-09-07T09:00:00+00:00",
    }
