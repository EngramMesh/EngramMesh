"""Transactional PostgreSQL memory unit of work."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, Self, final

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.mappers import (
    episode_request_fingerprint,
    episode_request_fingerprint_from_row,
    episode_to_row,
    event_to_row,
    row_to_episode,
)
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict
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
from engrammesh.shared.kernel.ids import MemoryId

_NOT_ACTIVE = "memory transaction is not active"
_ALREADY_ENTERED = "memory transaction cannot be entered more than once"
_ALREADY_COMMITTED = "memory transaction has already been committed"
_CLAIMS_UNAVAILABLE = "in-memory claim store is unavailable"
_CURSORS_UNAVAILABLE = "in-memory episode cursors are unavailable"
_EPISODE_RECORDED = "memory.episode-recorded"
_EVENT_AGGREGATE_UNKNOWN = "outbox episode event aggregate is unknown"
_EVENT_TENANT_MISMATCH = "outbox event tenant does not match episode tenant"

_EPISODE_COLUMNS = (
    "tenant_id",
    "episode_id",
    "subject_id",
    "workspace_id",
    "agent_id",
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
)

_IDEMPOTENCY_COLUMNS = (
    "tenant_id",
    "idempotency_key",
    "episode_id",
    "subject_id",
    "workspace_id",
    "agent_id",
    "actor_id",
    "source_type",
    "content_ref",
    "observed_at",
    "content_hash",
    "sensitivity",
    "retention_class",
    "consent_basis",
)

_OUTBOX_COLUMNS = (
    "event_id",
    "event_type",
    "schema_version",
    "tenant_id",
    "aggregate_id",
    "aggregate_version",
    "correlation_id",
    "causation_id",
    "occurred_at",
    "payload",
    "published_at",
)


@final
class _PostgresTransactionState:
    __slots__ = ("active", "committed", "connection")

    def __init__(self, connection: AsyncConnection) -> None:
        self.active = True
        self.committed = False
        self.connection = connection

    def require_usable(self) -> None:
        if not self.active:
            raise RuntimeError(_NOT_ACTIVE)
        if self.committed:
            raise RuntimeError(_ALREADY_COMMITTED)


@final
class _PostgresEpisodeStore:
    __slots__ = ("_state",)

    def __init__(self, state: _PostgresTransactionState) -> None:
        self._state = state

    async def append(self, episode: Episode) -> AppendResult:
        self._state.require_usable()
        connection = self._state.connection
        await connection.execute(
            """
            SELECT pg_advisory_xact_lock(
                hashtext(%(tenant_id)s::text),
                hashtext(%(idempotency_key)s)
            )
            """,
            {
                "tenant_id": episode.scope.tenant_id.value,
                "idempotency_key": episode.idempotency_key,
            },
        )
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT
                    tenant_id,
                    idempotency_key,
                    episode_id,
                    subject_id,
                    workspace_id,
                    agent_id,
                    actor_id,
                    source_type,
                    content_ref,
                    observed_at,
                    content_hash,
                    sensitivity,
                    retention_class,
                    consent_basis
                FROM memory_episode_idempotency
                WHERE tenant_id = %(tenant_id)s
                  AND idempotency_key = %(idempotency_key)s
                """,
                {
                    "tenant_id": episode.scope.tenant_id.value,
                    "idempotency_key": episode.idempotency_key,
                },
            )
            existing = await cursor.fetchone()
        if existing is not None:
            if episode_request_fingerprint(episode) != (
                episode_request_fingerprint_from_row(existing)
            ):
                raise EpisodeIdempotencyConflict()
            return AppendResult(
                episode_id=MemoryId(existing["episode_id"]),
                created=False,
            )

        episode_row = episode_to_row(episode)
        await connection.execute(
            f"""
            INSERT INTO memory_episodes ({", ".join(_EPISODE_COLUMNS)})
            VALUES ({", ".join(f"%({column})s" for column in _EPISODE_COLUMNS)})
            """,
            episode_row,
        )
        idempotency_row = _idempotency_row_from_episode(episode)
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                f"""
                INSERT INTO memory_episode_idempotency (
                    {", ".join(_IDEMPOTENCY_COLUMNS)}
                )
                VALUES ({", ".join(f"%({column})s" for column in _IDEMPOTENCY_COLUMNS)})
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING episode_id
                """,
                idempotency_row,
            )
            inserted = await cursor.fetchone()
        if inserted is None:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    SELECT
                        tenant_id,
                        idempotency_key,
                        episode_id,
                        subject_id,
                        workspace_id,
                        agent_id,
                        actor_id,
                        source_type,
                        content_ref,
                        observed_at,
                        content_hash,
                        sensitivity,
                        retention_class,
                        consent_basis
                    FROM memory_episode_idempotency
                    WHERE tenant_id = %(tenant_id)s
                      AND idempotency_key = %(idempotency_key)s
                    """,
                    {
                        "tenant_id": episode.scope.tenant_id.value,
                        "idempotency_key": episode.idempotency_key,
                    },
                )
                conflicting = await cursor.fetchone()
            if conflicting is None:
                msg = "idempotency insert conflict without a stored row"
                raise RuntimeError(msg)
            if episode_request_fingerprint(episode) != (
                episode_request_fingerprint_from_row(conflicting)
            ):
                raise EpisodeIdempotencyConflict()
            return AppendResult(
                episode_id=MemoryId(conflicting["episode_id"]),
                created=False,
            )
        return AppendResult(episode_id=episode.id, created=True)

    async def get(
        self,
        scope: MemoryScope,
        episode_id: MemoryId,
    ) -> Episode | None:
        self._state.require_usable()
        async with self._state.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                f"""
                SELECT {", ".join(_EPISODE_COLUMNS)}
                FROM memory_episodes
                WHERE tenant_id = %(tenant_id)s
                  AND episode_id = %(episode_id)s
                  AND subject_id = %(subject_id)s
                  AND workspace_id IS NOT DISTINCT FROM %(workspace_id)s
                  AND agent_id IS NOT DISTINCT FROM %(agent_id)s
                """,
                _scope_params(scope, episode_id=episode_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return row_to_episode(row)

    async def stream(
        self,
        scope: MemoryScope,
        cursor: str | None = None,
    ) -> tuple[Episode, ...]:
        self._state.require_usable()
        if cursor is not None:
            raise ValueError(_CURSORS_UNAVAILABLE)
        async with self._state.connection.cursor(row_factory=dict_row) as cursor_:
            await cursor_.execute(
                f"""
                SELECT {", ".join(_EPISODE_COLUMNS)}
                FROM memory_episodes
                WHERE tenant_id = %(tenant_id)s
                  AND subject_id = %(subject_id)s
                  AND workspace_id IS NOT DISTINCT FROM %(workspace_id)s
                  AND agent_id IS NOT DISTINCT FROM %(agent_id)s
                ORDER BY ingested_at ASC, episode_id ASC
                """,
                _scope_params(scope),
            )
            rows = await cursor_.fetchall()
        return tuple(row_to_episode(row) for row in rows)


@final
class _UnavailableClaimStore:
    __slots__ = ("_state",)

    def __init__(self, state: _PostgresTransactionState) -> None:
        self._state = state

    async def add_proposal(self, proposal: ClaimProposal) -> None:
        self._state.require_usable()
        del proposal
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)

    async def current(self, query: MemoryQuery) -> tuple[Claim, ...]:
        self._state.require_usable()
        del query
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)

    async def history(
        self,
        scope: MemoryScope,
        claim_id: MemoryId,
    ) -> tuple[Claim, ...]:
        self._state.require_usable()
        del scope, claim_id
        raise NotImplementedError(_CLAIMS_UNAVAILABLE)


@final
class _PostgresOutboxPort:
    __slots__ = ("_state",)

    def __init__(self, state: _PostgresTransactionState) -> None:
        self._state = state

    async def publish(self, event: EventEnvelope) -> None:
        self._state.require_usable()
        if event.event_type == _EPISODE_RECORDED:
            async with self._state.connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    SELECT tenant_id
                    FROM memory_episodes
                    WHERE episode_id = %(aggregate_id)s
                    """,
                    {"aggregate_id": event.aggregate_id.value},
                )
                aggregate = await cursor.fetchone()
            if aggregate is None:
                raise ValueError(_EVENT_AGGREGATE_UNKNOWN)
            if aggregate["tenant_id"] != event.tenant_id.value:
                raise ValueError(_EVENT_TENANT_MISMATCH)
        event_row = event_to_row(event)
        await self._state.connection.execute(
            f"""
            INSERT INTO memory_outbox_events ({", ".join(_OUTBOX_COLUMNS)})
            VALUES ({", ".join(f"%({column})s" for column in _OUTBOX_COLUMNS)})
            """,
            {**event_row, "published_at": None, "payload": Jsonb(event_row["payload"])},
        )


@final
class PostgresMemoryUnitOfWork:
    """Single-use PostgreSQL transaction for memory persistence."""

    __slots__ = (
        "_claims",
        "_connection",
        "_connection_cm",
        "_database",
        "_entered",
        "_episodes",
        "_outbox",
        "_state",
        "_transaction_cm",
    )

    def __init__(self, database: PostgresMemoryDatabase) -> None:
        self._database = database
        self._entered = False
        self._connection_cm: (
            AbstractAsyncContextManager[AsyncConnection] | None
        ) = None
        self._connection: AsyncConnection | None = None
        self._transaction_cm: Any = None
        self._state: _PostgresTransactionState | None = None
        self._episodes: EpisodeStore | None = None
        self._claims: ClaimStore | None = None
        self._outbox: OutboxPort | None = None

    async def __aenter__(self) -> Self:
        if self._entered:
            raise RuntimeError(_ALREADY_ENTERED)
        self._entered = True
        self._connection_cm = self._database.connection()
        self._connection = await self._connection_cm.__aenter__()
        self._transaction_cm = self._connection.transaction()
        await self._transaction_cm.__aenter__()
        state = _PostgresTransactionState(self._connection)
        self._state = state
        self._episodes = _PostgresEpisodeStore(state)
        self._claims = _UnavailableClaimStore(state)
        self._outbox = _PostgresOutboxPort(state)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        state = self._state
        if state is None or not state.active:
            raise RuntimeError(_NOT_ACTIVE)
        transaction_cm = self._transaction_cm
        connection_cm = self._connection_cm
        try:
            if transaction_cm is not None and not state.committed:
                if exc_type is None:
                    await transaction_cm.__aexit__(
                        RuntimeError,
                        RuntimeError("memory transaction rolled back"),
                        None,
                    )
                else:
                    await transaction_cm.__aexit__(
                        exc_type,
                        exc_value,
                        traceback,
                    )
        finally:
            state.active = False
            if connection_cm is not None:
                await connection_cm.__aexit__(exc_type, exc_value, traceback)
            self._connection = None
            self._transaction_cm = None
            self._connection_cm = None

    def _require_usable(self) -> _PostgresTransactionState:
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
        transaction_cm = self._transaction_cm
        if transaction_cm is None:
            raise RuntimeError(_NOT_ACTIVE)
        await transaction_cm.__aexit__(None, None, None)
        self._transaction_cm = None
        state.committed = True


@final
class PostgresMemoryUnitOfWorkFactory:
    """Create single-use PostgreSQL memory transactions."""

    __slots__ = ("_database",)

    def __init__(self, database: PostgresMemoryDatabase) -> None:
        self._database = database

    def create(self) -> MemoryUnitOfWork:
        """Create a fresh single-use memory transaction."""
        return PostgresMemoryUnitOfWork(self._database)


def _idempotency_row_from_episode(episode: Episode) -> dict[str, object]:
    row = episode_to_row(episode)
    return {
        "tenant_id": row["tenant_id"],
        "idempotency_key": row["idempotency_key"],
        "episode_id": row["episode_id"],
        "subject_id": row["subject_id"],
        "workspace_id": row["workspace_id"],
        "agent_id": row["agent_id"],
        "actor_id": row["actor_id"],
        "source_type": row["source_type"],
        "content_ref": row["content_ref"],
        "observed_at": row["observed_at"],
        "content_hash": row["content_hash"],
        "sensitivity": row["sensitivity"],
        "retention_class": row["retention_class"],
        "consent_basis": row["consent_basis"],
    }


def _scope_params(
    scope: MemoryScope,
    *,
    episode_id: MemoryId | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {
        "tenant_id": scope.tenant_id.value,
        "subject_id": scope.subject_id.value,
        "workspace_id": scope.workspace_id,
        "agent_id": scope.agent_id.value if scope.agent_id is not None else None,
    }
    if episode_id is not None:
        params["episode_id"] = episode_id.value
    return params
