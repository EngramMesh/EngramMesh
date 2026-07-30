from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.episode_recorded_processor import (
    EpisodeRecordedProcessor,
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
)

ACTOR_ID = SubjectId(UUID("29ee5d4a-8988-48b9-bd24-e65ba7eb3de5"))
AGENT_ID = AgentInstanceId(UUID("b93676a1-4671-47da-a32e-cd4615588188"))
CONTENT_REF = ArtifactId(UUID("a49f42ec-453a-46ba-98d7-32dda8d6ad7e"))
CORRELATION_ID = CorrelationId(
    UUID("223fdcf1-87da-43f4-b453-02bded156035")
)
EPISODE_ID = MemoryId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
EVENT_ID = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
SUBJECT_ID = SubjectId(UUID("436b95a8-df23-4d6e-8200-d2058ad62d86"))
TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
OBSERVED_AT = datetime(2026, 7, 27, 8, 29, 58, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)


def make_valid_event(**overrides: object) -> EventEnvelope:
    """Build a memory.episode-recorded v1 envelope matching record_episode payload shape."""
    payload = {
        "episode_id": str(EPISODE_ID),
        "scope": {
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
            "agent_id": str(AGENT_ID),
        },
        "actor_id": str(ACTOR_ID),
        "source_type": "user",
        "content_ref": str(CONTENT_REF),
        "observed_at": OBSERVED_AT.isoformat(),
        "ingested_at": INGESTED_AT.isoformat(),
        "content_hash": "sha256:88c7355c",
        "idempotency_key": "episode-42",
        "sensitivity": "confidential",
        "retention_class": "standard",
        "consent_basis": "user_request",
    }
    if "payload" in overrides:
        payload = overrides.pop("payload")  # type: ignore[assignment]
    defaults: dict[str, object] = {
        "event_id": EVENT_ID,
        "event_type": "memory.episode-recorded",
        "schema_version": 1,
        "tenant_id": TENANT_ID,
        "aggregate_id": EPISODE_ID,
        "aggregate_version": 1,
        "correlation_id": CORRELATION_ID,
        "causation_id": None,
        "occurred_at": INGESTED_AT,
        "payload": payload,
    }
    defaults.update(overrides)
    return EventEnvelope(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def processor() -> EpisodeRecordedProcessor:
    return EpisodeRecordedProcessor()


def test_supports_returns_true_only_for_episode_recorded(
    processor: EpisodeRecordedProcessor,
) -> None:
    assert processor.supports("memory.episode-recorded") is True
    assert processor.supports("memory.other-event") is False
    assert processor.supports("") is False


@pytest.mark.asyncio
async def test_valid_full_payload_passes(
    processor: EpisodeRecordedProcessor,
) -> None:
    await processor.process(make_valid_event())


@pytest.mark.asyncio
async def test_wrong_schema_version_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    with pytest.raises(ValueError, match="schema_version must be 1"):
        await processor.process(make_valid_event(schema_version=2))


@pytest.mark.asyncio
async def test_aggregate_id_mismatch_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    other_id = MemoryId(UUID("605fe709-954b-49e7-80c7-a70764127a88"))
    with pytest.raises(
        ValueError,
        match="aggregate_id must match payload episode_id",
    ):
        await processor.process(make_valid_event(aggregate_id=other_id))


@pytest.mark.parametrize(
    "missing_field",
    (
        "episode_id",
        "scope",
        "actor_id",
        "source_type",
        "content_ref",
        "observed_at",
        "ingested_at",
        "content_hash",
        "idempotency_key",
        "sensitivity",
        "retention_class",
        "consent_basis",
    ),
)
@pytest.mark.asyncio
async def test_missing_required_payload_field_raises(
    processor: EpisodeRecordedProcessor,
    missing_field: str,
) -> None:
    event = make_valid_event()
    payload = dict(event.payload)
    del payload[missing_field]
    with pytest.raises(
        ValueError,
        match=f"payload missing required field {missing_field!r}",
    ):
        await processor.process(replace(event, payload=payload))


@pytest.mark.asyncio
async def test_scope_containing_tenant_id_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    event = make_valid_event()
    payload = dict(event.payload)
    scope = dict(payload["scope"])  # type: ignore[arg-type]
    scope["tenant_id"] = str(TENANT_ID)
    payload["scope"] = scope
    with pytest.raises(
        ValueError,
        match="payload.scope must not contain tenant_id",
    ):
        await processor.process(replace(event, payload=payload))


@pytest.mark.asyncio
async def test_scope_not_mapping_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    event = make_valid_event()
    payload = dict(event.payload)
    payload["scope"] = "not-a-mapping"
    with pytest.raises(TypeError, match="payload.scope must be an object"):
        await processor.process(replace(event, payload=payload))


@pytest.mark.asyncio
async def test_scope_missing_subject_id_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    event = make_valid_event()
    payload = dict(event.payload)
    scope = dict(payload["scope"])  # type: ignore[arg-type]
    del scope["subject_id"]
    payload["scope"] = scope
    with pytest.raises(
        ValueError,
        match="payload.scope missing required field 'subject_id'",
    ):
        await processor.process(replace(event, payload=payload))


@pytest.mark.asyncio
async def test_wrong_event_type_raises(
    processor: EpisodeRecordedProcessor,
) -> None:
    with pytest.raises(
        ValueError,
        match="expected event_type 'memory.episode-recorded'",
    ):
        await processor.process(
            make_valid_event(event_type="memory.other-event")
        )
