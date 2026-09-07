"""In-memory runtime outbox writer for Temporal activity integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final
from uuid import uuid4

from engrammesh.modules.runtime.adapters.shared.status_changed_event import (
    build_execution_status_changed_event,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import CorrelationId, EventId


@final
@dataclass
class InMemoryRuntimeOutboxWriter:
    """Collect published status-changed events for assertions."""

    events: list[EventEnvelope] = field(default_factory=list)

    async def publish_status_changed(
        self,
        previous_status: ExecutionStatus | None,
        snapshot: ExecutionSnapshot,
        correlation_id: CorrelationId,
    ) -> None:
        self.events.append(
            build_execution_status_changed_event(
                event_id=EventId(uuid4()),
                correlation_id=correlation_id,
                causation_id=None,
                previous_status=previous_status,
                snapshot=snapshot,
            )
        )
