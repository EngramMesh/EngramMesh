"""Lock-serialized copy-on-write memory transactions."""

from types import TracebackType
from typing import Self, final

from engrammesh.modules.memory.adapters.in_memory.database import (
    InMemoryMemoryDatabase,
    _CommittedMemoryState,
)
from engrammesh.modules.memory.domain.model import Claim, Episode, MemoryScope
from engrammesh.modules.memory.ports import (
    AppendResult,
    ClaimProposal,
    ClaimStore,
    EpisodeStore,
    MemoryQuery,
    MemoryUnitOfWork,
    OutboxPort,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import MemoryId, TenantId, UUIDValue

_NOT_ACTIVE = "memory transaction is not active"
_ALREADY_ENTERED = "memory transaction cannot be entered more than once"
_ALREADY_COMMITTED = "memory transaction has already been committed"
_CLAIMS_UNAVAILABLE = "in-memory claim store is unavailable"
_CURSORS_UNAVAILABLE = "in-memory episode cursors are unavailable"
_EVENT_TENANT_MISMATCH = "outbox event tenant does not match episode tenant"


@final
class _TransactionState:
    __slots__ = (
        "active",
        "committed",
        "episodes",
        "events",
        "idempotency_index",
        "staged_episode_tenants",
    )

    def __init__(self, committed: _CommittedMemoryState) -> None:
        self.active = True
        self.committed = False
        self.episodes = list(committed.episodes)
        self.idempotency_index = dict(committed.idempotency_index)
        self.events = list(committed.events)
        self.staged_episode_tenants: dict[UUIDValue, TenantId] = {}

    def require_usable(self) -> None:
        if not self.active:
            raise RuntimeError(_NOT_ACTIVE)
        if self.committed:
            raise RuntimeError(_ALREADY_COMMITTED)


@final
class _InMemoryEpisodeStore:
    __slots__ = ("_state",)

    def __init__(self, state: _TransactionState) -> None:
        self._state = state

    async def append(self, episode: Episode) -> AppendResult:
        self._state.require_usable()
        idempotency_scope = (
            episode.scope.tenant_id,
            episode.idempotency_key,
        )
        existing_id = self._state.idempotency_index.get(idempotency_scope)
        if existing_id is not None:
            return AppendResult(episode_id=existing_id, created=False)
        self._state.episodes.append(episode)
        self._state.idempotency_index[idempotency_scope] = episode.id
        self._state.staged_episode_tenants[episode.id] = episode.scope.tenant_id
        return AppendResult(episode_id=episode.id, created=True)

    async def get(
        self,
        scope: MemoryScope,
        episode_id: MemoryId,
    ) -> Episode | None:
        self._state.require_usable()
        return next(
            (
                episode
                for episode in self._state.episodes
                if episode.id == episode_id and episode.scope == scope
            ),
            None,
        )

    async def stream(
        self,
        scope: MemoryScope,
        cursor: str | None = None,
    ) -> tuple[Episode, ...]:
        self._state.require_usable()
        if cursor is not None:
            raise ValueError(_CURSORS_UNAVAILABLE)
        return tuple(
            episode
            for episode in self._state.episodes
            if episode.scope == scope
        )


@final
class _UnavailableClaimStore:
    __slots__ = ("_state",)

    def __init__(self, state: _TransactionState) -> None:
        self._state = state

    async def add_proposal(self, proposal: ClaimProposal) -> None:
        self._state.require_usable()
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)

    async def current(self, query: MemoryQuery) -> tuple[Claim, ...]:
        self._state.require_usable()
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)

    async def history(
        self,
        scope: MemoryScope,
        claim_id: MemoryId,
    ) -> tuple[Claim, ...]:
        self._state.require_usable()
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)


@final
class _InMemoryOutbox:
    __slots__ = ("_state",)

    def __init__(self, state: _TransactionState) -> None:
        self._state = state

    async def publish(self, event: EventEnvelope) -> None:
        self._state.require_usable()
        aggregate_tenant = self._state.staged_episode_tenants.get(
            event.aggregate_id
        )
        if aggregate_tenant is not None and aggregate_tenant != event.tenant_id:
            raise ValueError(_EVENT_TENANT_MISMATCH)
        self._state.events.append(event)


@final
class _InMemoryMemoryUnitOfWork:
    __slots__ = (
        "_claims",
        "_database",
        "_entered",
        "_episodes",
        "_original",
        "_outbox",
        "_state",
    )

    def __init__(self, database: InMemoryMemoryDatabase) -> None:
        self._database = database
        self._entered = False
        self._state: _TransactionState | None = None
        self._original: _CommittedMemoryState | None = None
        self._episodes: EpisodeStore | None = None
        self._claims: ClaimStore | None = None
        self._outbox: OutboxPort | None = None

    async def __aenter__(self) -> Self:
        if self._entered:
            raise RuntimeError(_ALREADY_ENTERED)
        self._entered = True
        await self._database._lock.acquire()
        original = self._database._snapshot()
        state = _TransactionState(original)
        self._original = original
        self._state = state
        self._episodes = _InMemoryEpisodeStore(state)
        self._claims = _UnavailableClaimStore(state)
        self._outbox = _InMemoryOutbox(state)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        state = self._state
        original = self._original
        if state is None or original is None or not state.active:
            raise RuntimeError(_NOT_ACTIVE)
        try:
            if exc_type is not None and state.committed:
                self._database._restore(original)
        finally:
            state.active = False
            self._database._lock.release()

    def _require_usable(self) -> _TransactionState:
        state = self._state
        if state is None:
            raise RuntimeError(_NOT_ACTIVE)
        state.require_usable()
        return state

    @property
    def episodes(self) -> EpisodeStore:
        self._require_usable()
        if self._episodes is None:
            raise RuntimeError(_NOT_ACTIVE)
        return self._episodes

    @property
    def claims(self) -> ClaimStore:
        self._require_usable()
        if self._claims is None:
            raise RuntimeError(_NOT_ACTIVE)
        return self._claims

    @property
    def outbox(self) -> OutboxPort:
        self._require_usable()
        if self._outbox is None:
            raise RuntimeError(_NOT_ACTIVE)
        return self._outbox

    async def commit(self) -> None:
        state = self._require_usable()
        self._database._replace(
            episodes=state.episodes,
            idempotency_index=state.idempotency_index,
            events=state.events,
        )
        state.committed = True


@final
class InMemoryMemoryUnitOfWorkFactory:
    """Create single-use transactions for one in-memory database."""

    __slots__ = ("_database",)

    def __init__(self, database: InMemoryMemoryDatabase) -> None:
        self._database = database

    def create(self) -> MemoryUnitOfWork:
        """Create a fresh single-use memory transaction."""
        return _InMemoryMemoryUnitOfWork(self._database)
