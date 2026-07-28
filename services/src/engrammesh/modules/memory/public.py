"""Supported cross-module cognitive-memory contracts."""

from engrammesh.modules.memory.application.contracts import (
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.application.errors import (
    EpisodeAuthorizationDenied,
)
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict
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
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    CandidateSet,
    ClaimProposal,
    MemoryQuery,
)

__all__ = (
    "ApprovalStatus",
    "AuthorizationRequest",
    "CandidateSet",
    "Claim",
    "ClaimProposal",
    "ClaimStatus",
    "Episode",
    "EpisodeAuthorizationDenied",
    "EpisodeIdempotencyConflict",
    "EpistemicKind",
    "EvidenceItem",
    "EvidencePacket",
    "EvidenceRef",
    "MemoryQuery",
    "MemoryScope",
    "ProcedureVersion",
    "RecordEpisodeCommand",
    "RecordEpisodeResult",
    "RetentionClass",
    "Sensitivity",
    "SourceType",
    "TemporalStatus",
)
