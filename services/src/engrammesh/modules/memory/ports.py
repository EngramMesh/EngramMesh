"""Asynchronous ports and immutable DTOs for cognitive memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, runtime_checkable

from engrammesh.modules.memory.domain.model import (
    Claim,
    Episode,
    EvidenceItem,
    EvidencePacket,
    MemoryScope,
    Sensitivity,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import EventId, MemoryId, SubjectId


def _require_optional_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and (
        value.tzinfo is None or value.utcoffset() is None
    ):
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    """Scoped request for cognitive-memory evidence."""

    query_id: str
    scope: MemoryScope
    text: str
    valid_at: datetime | None = None
    recorded_at: datetime | None = None
    limit: int = 10

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            msg = "query_id must not be blank"
            raise ValueError(msg)
        if not self.text.strip():
            msg = "text must not be blank"
            raise ValueError(msg)
        _require_optional_aware(self.valid_at, "valid_at")
        _require_optional_aware(self.recorded_at, "recorded_at")
        if self.limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AppendResult:
    """Outcome of an idempotent episode append."""

    episode_id: MemoryId
    created: bool


@dataclass(frozen=True, slots=True)
class ClaimProposal:
    """Claim awaiting admission and lifecycle processing."""

    claim: Claim


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """Immutable candidate evidence returned by an index."""

    scope: MemoryScope
    items: tuple[EvidenceItem, ...]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if any(item.claim.scope != self.scope for item in items):
            msg = "every evidence item claim scope must match candidate scope"
            raise ValueError(msg)
        object.__setattr__(self, "items", items)


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Scoped authorization decision request."""

    actor_id: SubjectId
    scope: MemoryScope
    action: str
    sensitivity: Sensitivity


@runtime_checkable
class EpisodeStore(Protocol):
    """Episode fact-store boundary."""

    async def append(self, episode: Episode) -> AppendResult: ...

    async def get(
        self,
        scope: MemoryScope,
        episode_id: MemoryId,
    ) -> Episode | None: ...

    async def stream(
        self,
        scope: MemoryScope,
        cursor: str | None = None,
    ) -> tuple[Episode, ...]: ...


@runtime_checkable
class ClaimStore(Protocol):
    """Claim fact-store boundary."""

    async def add_proposal(self, proposal: ClaimProposal) -> None: ...

    async def current(self, query: MemoryQuery) -> tuple[Claim, ...]: ...

    async def history(
        self,
        scope: MemoryScope,
        claim_id: MemoryId,
    ) -> tuple[Claim, ...]: ...


@runtime_checkable
class CandidateIndex(Protocol):
    """Rebuildable candidate-index boundary."""

    async def search(self, query: MemoryQuery) -> CandidateSet: ...

    async def upsert(
        self,
        scope: MemoryScope,
        items: tuple[EvidenceItem, ...],
    ) -> None: ...

    async def remove(
        self,
        scope: MemoryScope,
        memory_ids: tuple[MemoryId, ...],
    ) -> None: ...


@runtime_checkable
class MemoryAuthorizationPort(Protocol):
    """Memory-access authorization boundary."""

    async def authorize(self, request: AuthorizationRequest) -> bool: ...


@runtime_checkable
class MemoryExtractorPort(Protocol):
    """Episode-to-claim extraction boundary."""

    async def propose(self, episode: Episode) -> tuple[ClaimProposal, ...]: ...


@runtime_checkable
class EntityResolverPort(Protocol):
    """Entity-match proposal boundary."""

    async def propose_matches(
        self,
        scope: MemoryScope,
        claim: Claim,
    ) -> tuple[MemoryId, ...]: ...


@runtime_checkable
class MemoryRerankerPort(Protocol):
    """Candidate reranking boundary."""

    async def rerank(
        self,
        query: MemoryQuery,
        candidates: CandidateSet,
    ) -> EvidencePacket: ...


@runtime_checkable
class ClockPort(Protocol):
    """Current-time provider for deterministic applications."""

    async def now(self) -> datetime: ...


@runtime_checkable
class MemoryIdentityPort(Protocol):
    """Memory and event identity provider."""

    async def new_memory_id(self) -> MemoryId: ...

    async def new_event_id(self) -> EventId: ...


@runtime_checkable
class OutboxPort(Protocol):
    """Transactional domain-event publication boundary."""

    async def publish(self, event: EventEnvelope) -> None: ...


@runtime_checkable
class MemoryUnitOfWork(Protocol):
    """Atomic episode and claim persistence boundary."""

    async def __aenter__(self) -> MemoryUnitOfWork: ...  # noqa: PYI034

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @property
    def episodes(self) -> EpisodeStore: ...

    @property
    def claims(self) -> ClaimStore: ...

    @property
    def outbox(self) -> OutboxPort: ...

    async def commit(self) -> None: ...


@runtime_checkable
class MemoryUnitOfWorkFactory(Protocol):
    """Synchronous factory for memory units of work."""

    def create(self) -> MemoryUnitOfWork: ...
