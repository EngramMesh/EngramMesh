"""Unit tests for PostgreSQL episode and event row mappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from engrammesh.modules.memory.adapters.postgres.mappers import (
    episode_request_fingerprint,
    episode_to_row,
    event_to_row,
    row_to_episode,
    row_to_event,
)
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
    UUIDValue,
)

NOW = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)


def episode_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": MemoryId.new(),
        "scope": MemoryScope(
            tenant_id=TenantId.new(),
            subject_id=SubjectId.new(),
        ),
        "actor_id": SubjectId.new(),
        "source_type": SourceType.USER,
        "content_ref": ArtifactId.new(),
        "observed_at": NOW,
        "ingested_at": NOW + timedelta(seconds=1),
        "content_hash": "sha256:abc",
        "idempotency_key": "episode-1",
        "sensitivity": Sensitivity.CONFIDENTIAL,
        "retention_class": RetentionClass.STANDARD,
        "consent_basis": "user_request",
    }
    values.update(overrides)
    return values


def envelope_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "event_id": EventId.new(),
        "event_type": "memory.episode-recorded",
        "schema_version": 1,
        "tenant_id": TenantId.new(),
        "aggregate_id": UUIDValue.new(),
        "aggregate_version": 1,
        "correlation_id": CorrelationId.new(),
        "causation_id": None,
        "occurred_at": NOW,
        "payload": {"episode_id": "ep-1"},
    }
    values.update(overrides)
    return values


def test_episode_round_trip_preserves_utc_timestamps() -> None:
    episode = Episode(**episode_values())

    row = episode_to_row(episode)
    restored = row_to_episode(row)

    assert restored == episode
    assert restored.observed_at.tzinfo is not None
    assert restored.ingested_at.tzinfo is not None


def test_episode_round_trip_preserves_nullable_scope_fields() -> None:
    episode = Episode(
        **episode_values(
            scope=MemoryScope(
                tenant_id=TenantId.new(),
                subject_id=SubjectId.new(),
                workspace_id=None,
                agent_id=None,
            ),
        )
    )

    restored = row_to_episode(episode_to_row(episode))

    assert restored.scope.workspace_id is None
    assert restored.scope.agent_id is None


def test_episode_round_trip_preserves_optional_scope_values() -> None:
    agent_id = AgentInstanceId.new()
    episode = Episode(
        **episode_values(
            scope=MemoryScope(
                tenant_id=TenantId.new(),
                subject_id=SubjectId.new(),
                workspace_id="workspace-a",
                agent_id=agent_id,
            ),
        )
    )

    restored = row_to_episode(episode_to_row(episode))

    assert restored.scope.workspace_id == "workspace-a"
    assert restored.scope.agent_id == agent_id


def test_event_round_trip_preserves_payload_and_nullable_causation() -> None:
    event = EventEnvelope(**envelope_values(causation_id=None))

    row = event_to_row(event)
    restored = row_to_event(row)

    assert restored == event
    assert restored.causation_id is None
    assert restored.payload == {"episode_id": "ep-1"}


def test_event_round_trip_preserves_causation_id() -> None:
    causation_id = EventId.new()
    event = EventEnvelope(**envelope_values(causation_id=causation_id))

    restored = row_to_event(event_to_row(event))

    assert restored.causation_id == causation_id


def test_event_round_trip_preserves_nested_payload() -> None:
    event = EventEnvelope(
        **envelope_values(
            payload={
                "episode_id": "ep-1",
                "metadata": {"source": "user", "tags": ["a", "b"]},
            },
        )
    )

    restored = row_to_event(event_to_row(event))

    assert restored.payload == {
        "episode_id": "ep-1",
        "metadata": {"source": "user", "tags": ("a", "b")},
    }


def test_episode_request_fingerprint_ignores_episode_id_and_ingested_at() -> None:
    base = episode_values()
    first = Episode(**base)
    second = Episode(
        **{
            **base,
            "id": MemoryId.new(),
            "ingested_at": base["ingested_at"] + timedelta(hours=1),
        }
    )

    assert episode_request_fingerprint(first) == episode_request_fingerprint(second)


def test_episode_request_fingerprint_changes_when_request_fields_differ() -> None:
    base = episode_values()
    first = Episode(**base)
    second = Episode(**{**base, "content_hash": "sha256:def"})

    assert episode_request_fingerprint(first) != episode_request_fingerprint(second)
