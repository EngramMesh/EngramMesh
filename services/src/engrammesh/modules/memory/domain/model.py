"""Immutable cognitive-memory domain contracts."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    MemoryId,
    SubjectId,
    TenantId,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


def _require_optional_aware(value: datetime | None, field_name: str) -> None:
    if value is not None:
        _require_aware(value, field_name)


def _require_half_open_interval(
    start: datetime,
    end: datetime | None,
    start_name: str,
    end_name: str,
) -> None:
    _require_aware(start, start_name)
    _require_optional_aware(end, end_name)
    if end is not None and end <= start:
        msg = f"{end_name} must be later than {start_name}"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Tenant and subject boundary, optionally narrowed by workspace or agent."""

    tenant_id: TenantId
    subject_id: SubjectId
    workspace_id: str | None = None
    agent_id: AgentInstanceId | None = None


class SourceType(StrEnum):
    """Origin category for an observed episode."""

    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    FILE = "file"
    SYSTEM = "system"


class Sensitivity(StrEnum):
    """Information-sensitivity classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class RetentionClass(StrEnum):
    """Explicit retention policy class."""

    EPHEMERAL = "ephemeral"
    STANDARD = "standard"
    EXTENDED = "extended"
    LEGAL_HOLD = "legal_hold"


@dataclass(frozen=True, slots=True)
class Episode:
    """Immutable observation whose content is stored by artifact reference."""

    id: MemoryId
    scope: MemoryScope
    actor_id: SubjectId
    source_type: SourceType
    content_ref: ArtifactId
    observed_at: datetime
    ingested_at: datetime
    content_hash: str
    idempotency_key: str
    sensitivity: Sensitivity
    retention_class: RetentionClass
    consent_basis: str

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        _require_aware(self.ingested_at, "ingested_at")
        if not self.idempotency_key.strip():
            msg = "idempotency_key must not be blank"
            raise ValueError(msg)


class EpistemicKind(StrEnum):
    """How a claim became known."""

    OBSERVED = "observed"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    HUMAN_CONFIRMED = "human_confirmed"


class ClaimStatus(StrEnum):
    """Lifecycle state of a versioned claim."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    RETRACTED = "retracted"
    SUPERSEDED = "superseded"


class TemporalStatus(StrEnum):
    """Temporal role of evidence in a query result."""

    CURRENT = "current"
    HISTORICAL = "historical"
    TRANSITION = "transition"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Provenance reference from a claim to an episode."""

    episode_id: MemoryId
    source_span: str
    extractor_version: str
    model_ref: str | None = None
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        if not self.source_span.strip():
            msg = "source_span must not be blank"
            raise ValueError(msg)
        if not self.extractor_version.strip():
            msg = "extractor_version must not be blank"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Claim:
    """Bitemporal, evidence-backed semantic claim."""

    id: MemoryId
    scope: MemoryScope
    subject: str
    predicate: str
    object_value: str
    polarity: bool
    epistemic_kind: EpistemicKind
    confidence: float
    valid_from: datetime
    valid_to: datetime | None
    recorded_from: datetime
    recorded_to: datetime | None
    status: ClaimStatus
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        _require_half_open_interval(
            self.valid_from,
            self.valid_to,
            "valid_from",
            "valid_to",
        )
        _require_half_open_interval(
            self.recorded_from,
            self.recorded_to,
            "recorded_from",
            "recorded_to",
        )
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        if not self.evidence:
            msg = "evidence must contain at least one reference"
            raise ValueError(msg)
        object.__setattr__(self, "evidence", tuple(self.evidence))


class ApprovalStatus(StrEnum):
    """Evaluation and approval lifecycle for a procedure version."""

    CANDIDATE = "candidate"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ProcedureVersion:
    """Versioned procedural memory contract."""

    id: MemoryId
    version: int
    content_ref: ArtifactId
    input_schema: Mapping[str, object]
    preconditions: tuple[str, ...]
    evaluation_score: float | None
    approval_status: ApprovalStatus
    derived_from: tuple[MemoryId, ...]
    created_by: SubjectId

    def __post_init__(self) -> None:
        if self.version <= 0:
            msg = "version must be positive"
            raise ValueError(msg)
        object.__setattr__(
            self,
            "input_schema",
            MappingProxyType(dict(self.input_schema)),
        )
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "derived_from", tuple(self.derived_from))

    @property
    def is_trusted(self) -> bool:
        """Return whether this exact version is approved for trusted use."""
        return self.approval_status is ApprovalStatus.APPROVED


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A scored claim candidate with an explicit temporal role."""

    claim: Claim
    temporal_status: TemporalStatus
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    temporal_score: float = 0.0
    graph_score: float = 0.0
    rerank_score: float = 0.0


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    """Immutable evidence selected for one memory query."""

    query_id: str
    items: tuple[EvidenceItem, ...]
    generated_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.generated_at, "generated_at")
        object.__setattr__(self, "items", tuple(self.items))
