"""Shared runtime outbox event builders."""

from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import CorrelationId, EventId


def build_execution_status_changed_event(
    *,
    event_id: EventId,
    correlation_id: CorrelationId,
    causation_id: EventId | None,
    previous_status: ExecutionStatus | None,
    snapshot: ExecutionSnapshot,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type="runtime.execution-status-changed",
        schema_version=1,
        tenant_id=snapshot.scope.tenant_id,
        aggregate_id=snapshot.execution_id,
        aggregate_version=snapshot.revision,
        correlation_id=correlation_id,
        causation_id=causation_id,
        occurred_at=snapshot.updated_at,
        payload={
            "execution_id": str(snapshot.execution_id),
            "revision": snapshot.revision,
            "previous_status": (
                None if previous_status is None else previous_status.value
            ),
            "status": snapshot.status.value,
            "updated_at": snapshot.updated_at.isoformat(),
        },
    )
