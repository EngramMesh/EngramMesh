"""Row mappers between PostgreSQL records and memory domain types."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from engrammesh.modules.memory.domain.model import (
    Claim,
    ClaimStatus,
    Episode,
    EpistemicKind,
    EvidenceRef,
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

EpisodeRequestFingerprint = tuple[
    TenantId,
    SubjectId,
    str | None,
    AgentInstanceId | None,
    SubjectId,
    SourceType,
    ArtifactId,
    datetime,
    str,
    Sensitivity,
    RetentionClass,
    str,
]


def episode_to_row(episode: Episode) -> dict[str, object]:
    """Serialize an Episode into memory_episodes column values."""
    return {
        "tenant_id": episode.scope.tenant_id.value,
        "episode_id": episode.id.value,
        "subject_id": episode.scope.subject_id.value,
        "workspace_id": episode.scope.workspace_id,
        "agent_id": (
            episode.scope.agent_id.value
            if episode.scope.agent_id is not None
            else None
        ),
        "actor_id": episode.actor_id.value,
        "source_type": episode.source_type.value,
        "content_ref": episode.content_ref.value,
        "observed_at": episode.observed_at,
        "ingested_at": episode.ingested_at,
        "content_hash": episode.content_hash,
        "idempotency_key": episode.idempotency_key,
        "sensitivity": episode.sensitivity.value,
        "retention_class": episode.retention_class.value,
        "consent_basis": episode.consent_basis,
    }


def row_to_episode(row: Mapping[str, object]) -> Episode:
    """Deserialize a memory_episodes row into an Episode."""
    agent_id = row["agent_id"]
    return Episode(
        id=MemoryId(_as_uuid(row["episode_id"])),
        scope=MemoryScope(
            tenant_id=TenantId(_as_uuid(row["tenant_id"])),
            subject_id=SubjectId(_as_uuid(row["subject_id"])),
            workspace_id=_optional_text(row["workspace_id"]),
            agent_id=(
                AgentInstanceId(_as_uuid(agent_id))
                if agent_id is not None
                else None
            ),
        ),
        actor_id=SubjectId(_as_uuid(row["actor_id"])),
        source_type=SourceType(str(row["source_type"])),
        content_ref=ArtifactId(_as_uuid(row["content_ref"])),
        observed_at=_as_datetime(row["observed_at"]),
        ingested_at=_as_datetime(row["ingested_at"]),
        content_hash=str(row["content_hash"]),
        idempotency_key=str(row["idempotency_key"]),
        sensitivity=Sensitivity(str(row["sensitivity"])),
        retention_class=RetentionClass(str(row["retention_class"])),
        consent_basis=str(row["consent_basis"]),
    )


def event_to_row(event: EventEnvelope) -> dict[str, object]:
    """Serialize an EventEnvelope into memory_outbox_events column values."""
    return {
        "event_id": event.event_id.value,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "tenant_id": event.tenant_id.value,
        "aggregate_id": event.aggregate_id.value,
        "aggregate_version": event.aggregate_version,
        "correlation_id": event.correlation_id.value,
        "causation_id": (
            event.causation_id.value if event.causation_id is not None else None
        ),
        "occurred_at": event.occurred_at,
        "payload": _to_json_value(event.payload),
    }


def row_to_event(row: Mapping[str, object]) -> EventEnvelope:
    """Deserialize a memory_outbox_events row into an EventEnvelope."""
    causation_id = row["causation_id"]
    payload = row["payload"]
    if not isinstance(payload, Mapping):
        msg = "payload must be a mapping"
        raise TypeError(msg)
    return EventEnvelope(
        event_id=EventId(_as_uuid(row["event_id"])),
        event_type=str(row["event_type"]),
        schema_version=_as_int(row["schema_version"]),
        tenant_id=TenantId(_as_uuid(row["tenant_id"])),
        aggregate_id=UUIDValue(_as_uuid(row["aggregate_id"])),
        aggregate_version=_as_int(row["aggregate_version"]),
        correlation_id=CorrelationId(_as_uuid(row["correlation_id"])),
        causation_id=(
            EventId(_as_uuid(causation_id)) if causation_id is not None else None
        ),
        occurred_at=_as_datetime(row["occurred_at"]),
        payload=dict(payload),
    )


def claim_to_row(claim: Claim, *, episode_id: MemoryId) -> dict[str, object]:
    """Serialize a Claim into memory_claim_proposals column values."""
    evidence = claim.evidence[0]
    return {
        "tenant_id": claim.scope.tenant_id.value,
        "claim_id": claim.id.value,
        "episode_id": episode_id.value,
        "subject_id": claim.scope.subject_id.value,
        "workspace_id": claim.scope.workspace_id,
        "agent_id": (
            claim.scope.agent_id.value
            if claim.scope.agent_id is not None
            else None
        ),
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object_value": claim.object_value,
        "polarity": claim.polarity,
        "epistemic_kind": claim.epistemic_kind.value,
        "confidence": claim.confidence,
        "valid_from": claim.valid_from,
        "valid_to": claim.valid_to,
        "recorded_from": claim.recorded_from,
        "recorded_to": claim.recorded_to,
        "status": claim.status.value,
        "evidence": [
            {
                "episode_id": str(item.episode_id.value),
                "source_span": item.source_span,
                "extractor_version": item.extractor_version,
                "model_ref": item.model_ref,
                "prompt_version": item.prompt_version,
            }
            for item in claim.evidence
        ],
        "extractor_version": evidence.extractor_version,
    }


def row_to_claim(row: Mapping[str, object]) -> Claim:
    """Deserialize a memory_claim_proposals row into a Claim."""
    evidence_raw = row["evidence"]
    if not isinstance(evidence_raw, list):
        msg = "evidence must be a list"
        raise TypeError(msg)
    evidence = tuple(
        EvidenceRef(
            episode_id=MemoryId(_as_uuid(item["episode_id"])),
            source_span=str(item["source_span"]),
            extractor_version=str(item["extractor_version"]),
            model_ref=_optional_text(item.get("model_ref")),
            prompt_version=_optional_text(item.get("prompt_version")),
        )
        for item in evidence_raw
    )
    agent_id = row["agent_id"]
    return Claim(
        id=MemoryId(_as_uuid(row["claim_id"])),
        scope=MemoryScope(
            tenant_id=TenantId(_as_uuid(row["tenant_id"])),
            subject_id=SubjectId(_as_uuid(row["subject_id"])),
            workspace_id=_optional_text(row["workspace_id"]),
            agent_id=(
                AgentInstanceId(_as_uuid(agent_id))
                if agent_id is not None
                else None
            ),
        ),
        subject=str(row["subject"]),
        predicate=str(row["predicate"]),
        object_value=str(row["object_value"]),
        polarity=bool(row["polarity"]),
        epistemic_kind=EpistemicKind(str(row["epistemic_kind"])),
        confidence=_as_float(row["confidence"]),
        valid_from=_as_datetime(row["valid_from"]),
        valid_to=(
            _as_datetime(row["valid_to"]) if row["valid_to"] is not None else None
        ),
        recorded_from=_as_datetime(row["recorded_from"]),
        recorded_to=(
            _as_datetime(row["recorded_to"])
            if row["recorded_to"] is not None
            else None
        ),
        status=ClaimStatus(str(row["status"])),
        evidence=evidence,
    )


def episode_request_fingerprint(episode: Episode) -> EpisodeRequestFingerprint:
    """Return Episode-defining fields used for idempotency replay comparison."""
    return (
        episode.scope.tenant_id,
        episode.scope.subject_id,
        episode.scope.workspace_id,
        episode.scope.agent_id,
        episode.actor_id,
        episode.source_type,
        episode.content_ref,
        episode.observed_at,
        episode.content_hash,
        episode.sensitivity,
        episode.retention_class,
        episode.consent_basis,
    )


def episode_request_fingerprint_from_row(
    row: Mapping[str, object],
) -> EpisodeRequestFingerprint:
    """Return Episode-defining fields from an idempotency or episode row."""
    agent_id = row["agent_id"]
    return (
        TenantId(_as_uuid(row["tenant_id"])),
        SubjectId(_as_uuid(row["subject_id"])),
        _optional_text(row["workspace_id"]),
        AgentInstanceId(_as_uuid(agent_id)) if agent_id is not None else None,
        SubjectId(_as_uuid(row["actor_id"])),
        SourceType(str(row["source_type"])),
        ArtifactId(_as_uuid(row["content_ref"])),
        _as_datetime(row["observed_at"]),
        str(row["content_hash"]),
        Sensitivity(str(row["sensitivity"])),
        RetentionClass(str(row["retention_class"])),
        str(row["consent_basis"]),
    )


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    msg = f"expected UUID or UUID text, got {type(value).__name__}"
    raise TypeError(msg)


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    msg = f"expected datetime, got {type(value).__name__}"
    raise TypeError(msg)


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return int(value)
    msg = f"expected int, got {type(value).__name__}"
    raise TypeError(msg)


def _as_float(value: object) -> float:
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return float(value)
    msg = f"expected float, got {type(value).__name__}"
    raise TypeError(msg)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_json_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json_value(item) for item in value]
    return value
