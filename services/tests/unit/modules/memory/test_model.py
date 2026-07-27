from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

import pytest

from engrammesh.modules.memory.domain.model import (
    ApprovalStatus,
    Claim,
    ClaimStatus,
    Episode,
    EpistemicKind,
    EvidenceItem,
    EvidencePacket,
    EvidenceRef,
    MemoryScope,
    ProcedureVersion,
    RetentionClass,
    Sensitivity,
    SourceType,
    TemporalStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    MemoryId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


def scope_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "tenant_id": TenantId.new(),
        "subject_id": SubjectId.new(),
    }
    values.update(overrides)
    return values


def episode_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": MemoryId.new(),
        "scope": MemoryScope(**scope_values()),
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


def evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        episode_id=MemoryId.new(),
        source_span="paragraph:1",
        extractor_version="extractor-v1",
        model_ref="model-v1",
        prompt_version="prompt-v1",
    )


def procedure_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": MemoryId.new(),
        "version": 1,
        "content_ref": ArtifactId.new(),
        "input_schema": {"type": "object"},
        "preconditions": ("authorized",),
        "evaluation_score": 0.95,
        "approval_status": ApprovalStatus.CANDIDATE,
        "derived_from": (MemoryId.new(),),
        "created_by": SubjectId.new(),
    }
    values.update(overrides)
    return values


def claim_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": MemoryId.new(),
        "scope": MemoryScope(**scope_values()),
        "subject": "user",
        "predicate": "prefers",
        "object_value": "tea",
        "polarity": True,
        "epistemic_kind": EpistemicKind.OBSERVED,
        "confidence": 0.9,
        "valid_from": NOW,
        "valid_to": None,
        "recorded_from": NOW + timedelta(seconds=1),
        "recorded_to": None,
        "status": ClaimStatus.PROPOSED,
        "evidence": (evidence_ref(),),
    }
    values.update(overrides)
    return values


def test_scope_requires_tenant_and_subject_and_can_narrow_access() -> None:
    tenant_id = TenantId.new()
    subject_id = SubjectId.new()
    agent_id = AgentInstanceId.new()

    broad = MemoryScope(tenant_id=tenant_id, subject_id=subject_id)
    narrow = MemoryScope(
        tenant_id=tenant_id,
        subject_id=subject_id,
        workspace_id="workspace-1",
        agent_id=agent_id,
    )

    assert broad.workspace_id is None
    assert broad.agent_id is None
    assert narrow.workspace_id == "workspace-1"
    assert narrow.agent_id == agent_id


def test_scope_is_immutable() -> None:
    scope = MemoryScope(**scope_values())

    with pytest.raises(FrozenInstanceError):
        scope.workspace_id = "other"


def test_memory_enum_values_are_stable_strings() -> None:
    assert {item.value for item in SourceType} == {
        "user",
        "agent",
        "tool",
        "file",
        "system",
    }
    assert {item.value for item in Sensitivity} == {
        "public",
        "internal",
        "confidential",
        "restricted",
    }
    assert {item.value for item in RetentionClass} == {
        "ephemeral",
        "standard",
        "extended",
        "legal_hold",
    }
    assert {item.value for item in EpistemicKind} == {
        "observed",
        "extracted",
        "inferred",
        "human_confirmed",
    }
    assert {item.value for item in ClaimStatus} == {
        "proposed",
        "accepted",
        "disputed",
        "retracted",
        "superseded",
    }
    assert {item.value for item in TemporalStatus} == {
        "current",
        "historical",
        "transition",
    }
    assert {item.value for item in ApprovalStatus} == {
        "candidate",
        "evaluated",
        "approved",
        "rejected",
    }


def test_episode_keeps_explicit_retention_and_artifact_reference() -> None:
    content_ref = ArtifactId.new()

    episode = Episode(
        **episode_values(
            content_ref=content_ref,
            retention_class=RetentionClass.LEGAL_HOLD,
        )
    )

    assert episode.content_ref is content_ref
    assert episode.retention_class is RetentionClass.LEGAL_HOLD
    with pytest.raises(FrozenInstanceError):
        episode.content_ref = ArtifactId.new()


@pytest.mark.parametrize("field_name", ("observed_at", "ingested_at"))
def test_episode_rejects_naive_timestamps(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        Episode(
            **episode_values(
                **{field_name: datetime(2026, 7, 27, 10, 0)},  # noqa: DTZ001
            )
        )


@pytest.mark.parametrize("idempotency_key", ("", " ", "\t\n"))
def test_episode_rejects_blank_idempotency_key(idempotency_key: str) -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        Episode(**episode_values(idempotency_key=idempotency_key))


def test_claim_preserves_bitemporal_intervals_and_evidence() -> None:
    valid_to = NOW + timedelta(days=30)
    recorded_to = NOW + timedelta(days=1)
    reference = evidence_ref()

    claim = Claim(
        **claim_values(
            valid_to=valid_to,
            recorded_to=recorded_to,
            status=ClaimStatus.ACCEPTED,
            evidence=(reference,),
        )
    )

    assert (claim.valid_from, claim.valid_to) == (NOW, valid_to)
    assert claim.recorded_to == recorded_to
    assert claim.evidence == (reference,)
    assert isinstance(claim.evidence, tuple)


@pytest.mark.parametrize("status", tuple(ClaimStatus))
def test_claim_distinguishes_lifecycle_statuses(status: ClaimStatus) -> None:
    claim = Claim(**claim_values(status=status))

    assert claim.status is status


@pytest.mark.parametrize(
    ("start_name", "end_name"),
    (("valid_from", "valid_to"), ("recorded_from", "recorded_to")),
)
@pytest.mark.parametrize("offset", (timedelta(0), timedelta(seconds=-1)))
def test_claim_rejects_empty_or_reversed_half_open_intervals(
    start_name: str,
    end_name: str,
    offset: timedelta,
) -> None:
    start = NOW + timedelta(days=2)

    with pytest.raises(ValueError, match=end_name):
        Claim(
            **claim_values(
                **{
                    start_name: start,
                    end_name: start + offset,
                }
            )
        )


@pytest.mark.parametrize(
    "field_name",
    ("valid_from", "valid_to", "recorded_from", "recorded_to"),
)
def test_claim_rejects_naive_interval_timestamps(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        Claim(
            **claim_values(
                **{field_name: datetime(2026, 7, 27, 10, 0)},  # noqa: DTZ001
            )
        )


def test_claim_requires_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        Claim(**claim_values(evidence=()))


@pytest.mark.parametrize("confidence", (-0.01, 1.01))
def test_claim_rejects_confidence_outside_unit_interval(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        Claim(**claim_values(confidence=confidence))


@pytest.mark.parametrize("field_name", ("source_span", "extractor_version"))
@pytest.mark.parametrize("value", ("", " ", "\t\n"))
def test_evidence_reference_requires_provenance(
    field_name: str,
    value: str,
) -> None:
    values: dict[str, Any] = {
        "episode_id": MemoryId.new(),
        "source_span": "paragraph:1",
        "extractor_version": "extractor-v1",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        EvidenceRef(**values)


@pytest.mark.parametrize("version", (0, -1))
def test_procedure_requires_positive_version(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        ProcedureVersion(**procedure_values(version=version))


def test_procedure_is_trusted_only_after_approval() -> None:
    for status in ApprovalStatus:
        procedure = ProcedureVersion(
            **procedure_values(approval_status=status),
        )
        assert procedure.is_trusted is (status is ApprovalStatus.APPROVED)


def test_procedure_copies_input_schema_into_immutable_mapping() -> None:
    source_schema: dict[str, object] = {"type": "object"}
    procedure = ProcedureVersion(
        id=MemoryId.new(),
        version=1,
        content_ref=ArtifactId.new(),
        input_schema=source_schema,
        preconditions=(),
        evaluation_score=None,
        approval_status=ApprovalStatus.CANDIDATE,
        derived_from=(),
        created_by=SubjectId.new(),
    )
    source_schema["type"] = "array"

    assert isinstance(procedure.input_schema, MappingProxyType)
    assert procedure.input_schema == {"type": "object"}
    with pytest.raises(TypeError):
        procedure.input_schema["type"] = "string"  # type: ignore[index]


def test_evidence_packet_keeps_temporal_categories_distinct() -> None:
    items = tuple(
        EvidenceItem(
            claim=Claim(**claim_values()),
            temporal_status=status,
        )
        for status in TemporalStatus
    )

    packet = EvidencePacket(
        query_id="query-1",
        items=items,
        generated_at=NOW,
    )

    assert tuple(item.temporal_status for item in packet.items) == (
        TemporalStatus.CURRENT,
        TemporalStatus.HISTORICAL,
        TemporalStatus.TRANSITION,
    )


def test_evidence_packet_rejects_naive_generated_at() -> None:
    with pytest.raises(ValueError, match="generated_at"):
        EvidencePacket(
            query_id="query-1",
            items=(),
            generated_at=datetime(2026, 7, 27, 10, 0),  # noqa: DTZ001
        )
