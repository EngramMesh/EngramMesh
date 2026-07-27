"""Shared event envelope contract."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from .ids import CorrelationId, EventId, TenantId, UUIDValue


def _freeze_json_value(value: object, path: str = "payload") -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                msg = f"{path} keys must be strings"
                raise TypeError(msg)
            frozen[key] = _freeze_json_value(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list | tuple):
        return tuple(
            _freeze_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{path} must contain only finite numbers"
        raise ValueError(msg)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    msg = f"{path} contains unsupported value type {type(value).__name__}"
    raise TypeError(msg)


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
        payload = _freeze_json_value(self.payload)
        if not isinstance(payload, Mapping):
            msg = "payload must be a mapping"
            raise TypeError(msg)
        object.__setattr__(self, "payload", payload)
