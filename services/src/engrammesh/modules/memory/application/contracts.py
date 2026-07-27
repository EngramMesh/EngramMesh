"""Immutable commands and results for cognitive-memory applications."""

from dataclasses import dataclass
from datetime import datetime

from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    MemoryId,
    SubjectId,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RecordEpisodeCommand:
    """Request to record one immutable cognitive-memory episode."""

    correlation_id: CorrelationId
    actor_id: SubjectId
    scope: MemoryScope
    source_type: SourceType
    content_ref: ArtifactId
    observed_at: datetime
    content_hash: str
    idempotency_key: str
    sensitivity: Sensitivity
    retention_class: RetentionClass
    consent_basis: str

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        _require_non_blank(self.content_hash, "content_hash")
        _require_non_blank(self.idempotency_key, "idempotency_key")
        _require_non_blank(self.consent_basis, "consent_basis")


@dataclass(frozen=True, slots=True)
class RecordEpisodeResult:
    """Outcome of recording or replaying an episode command."""

    episode_id: MemoryId
    created: bool
