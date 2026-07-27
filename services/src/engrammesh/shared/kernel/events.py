"""Shared event envelope contract."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from .ids import CorrelationId, EventId, TenantId, UUIDValue


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Immutable metadata and payload for a domain event."""

    event_id: EventId
    event_type: str
    schema_version: int
    tenant_id: TenantId
    aggregate_id: UUIDValue
    aggregate_version: int
    correlation_id: CorrelationId
    causation_id: EventId | None
    occurred_at: datetime
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            msg = "event_type must not be blank"
            raise ValueError(msg)
        if self.schema_version <= 0:
            msg = "schema_version must be positive"
            raise ValueError(msg)
        if self.aggregate_version <= 0:
            msg = "aggregate_version must be positive"
            raise ValueError(msg)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            msg = "occurred_at must be timezone-aware"
            raise ValueError(msg)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
