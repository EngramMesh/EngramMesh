from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import pytest

from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import CorrelationId, EventId, TenantId, UUIDValue


def envelope_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "event_id": EventId.new(),
        "event_type": "memory.created",
        "schema_version": 1,
        "tenant_id": TenantId.new(),
        "aggregate_id": UUIDValue.new(),
        "aggregate_version": 1,
        "correlation_id": CorrelationId.new(),
        "causation_id": None,
        "occurred_at": datetime.now(UTC),
        "payload": {"memory_type": "episodic"},
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("event_type", ("", " ", "\t\n"))
def test_event_envelope_rejects_blank_event_type(event_type: str) -> None:
    with pytest.raises(ValueError, match="event_type"):
        EventEnvelope(**envelope_values(event_type=event_type))


@pytest.mark.parametrize(
    ("field_name", "value"),
    (("schema_version", 0), ("schema_version", -1), ("aggregate_version", 0), ("aggregate_version", -1)),
)
def test_event_envelope_rejects_non_positive_versions(field_name: str, value: int) -> None:
    with pytest.raises(ValueError, match=field_name):
        EventEnvelope(**envelope_values(**{field_name: value}))


def test_event_envelope_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="occurred_at"):
        EventEnvelope(**envelope_values(occurred_at=datetime(2026, 1, 1)))  # noqa: DTZ001


def test_event_envelope_copies_payload_into_immutable_mapping() -> None:
    source = {"memory_type": "episodic"}
    envelope = EventEnvelope(**envelope_values(payload=source))
    source["memory_type"] = "semantic"

    assert isinstance(envelope.payload, MappingProxyType)
    assert envelope.payload == {"memory_type": "episodic"}
    with pytest.raises(TypeError):
        envelope.payload["memory_type"] = "procedural"  # type: ignore[index]


def test_event_envelope_preserves_absent_causation_id() -> None:
    envelope = EventEnvelope(**envelope_values(causation_id=None))

    assert envelope.causation_id is None


def test_event_envelope_is_immutable() -> None:
    envelope = EventEnvelope(**envelope_values())

    with pytest.raises(FrozenInstanceError):
        envelope.event_type = "memory.updated"
