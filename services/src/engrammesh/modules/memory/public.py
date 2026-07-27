"""Supported cross-module cognitive-memory contracts."""

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
    "EpistemicKind",
    "EvidenceItem",
    "EvidencePacket",
    "EvidenceRef",
    "MemoryQuery",
    "MemoryScope",
    "ProcedureVersion",
    "RetentionClass",
    "Sensitivity",
    "SourceType",
    "TemporalStatus",
)
