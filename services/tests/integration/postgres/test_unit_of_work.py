"""Focused Task 3 integration tests for the PostgreSQL memory unit of work."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import cast

import psycopg
import pytest
import pytest_asyncio
from contract.memory_adapter_contract import (
    TENANT_B,
    MemoryAdapterHarnessFactory,
    assert_cancellation_after_commit_remains_and_releases_lock,
    assert_cancellation_inside_transaction_rolls_back_and_releases_lock,
    assert_commit_persists_episode_and_outbox_atomically,
    assert_divergent_idempotency_conflicts,
    assert_exact_idempotent_replay,
    assert_exit_without_commit_rolls_back,
    assert_first_append_get_and_stream,
    make_episode,
    make_event,
    make_scope,
)
from psycopg.rows import dict_row

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.mappers import (
    row_to_episode,
    row_to_event,
)
from engrammesh.modules.memory.adapters.postgres.unit_of_work import (
    PostgresMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.domain.model import Episode
from engrammesh.modules.memory.ports import (
    ClaimProposal,
    MemoryQuery,
    MemoryUnitOfWorkFactory,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import MemoryId

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def postgres_database(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> AsyncIterator[PostgresMemoryDatabase]:
    del postgres_connection
    database = PostgresMemoryDatabase(postgres_dsn)
    await database.open()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def harness_factory(
    postgres_database: PostgresMemoryDatabase,
    postgres_dsn: str,
) -> Iterator[MemoryAdapterHarnessFactory]:
    def make_harness() -> _Harness:
        return _Harness(postgres_database, postgres_dsn)

    yield make_harness


class _Harness:
    """Minimal committed-state probe for focused contract assertions."""

    def __init__(self, database: PostgresMemoryDatabase, dsn: str) -> None:
        self._database = database
        self._dsn = dsn

    @property
    def unit_of_work_factory(self) -> MemoryUnitOfWorkFactory:
        return PostgresMemoryUnitOfWorkFactory(self._database)

    @property
    def committed_episodes(self) -> tuple[Episode, ...]:
        return _load_committed_episodes(self._dsn)

    @property
    def committed_events(self) -> tuple[EventEnvelope, ...]:
        return _load_committed_events(self._dsn)


def _load_committed_episodes(dsn: str) -> tuple[Episode, ...]:
    with (
        psycopg.connect(dsn) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                tenant_id,
                episode_id,
                subject_id,
                workspace_id,
                agent_id,
                actor_id,
                source_type,
                content_ref,
                observed_at,
                ingested_at,
                content_hash,
                idempotency_key,
                sensitivity,
                retention_class,
                consent_basis
            FROM memory_episodes
            ORDER BY ingested_at ASC, episode_id ASC
            """
        )
        return tuple(row_to_episode(row) for row in cursor.fetchall())


def _load_committed_events(dsn: str) -> tuple[EventEnvelope, ...]:
    with (
        psycopg.connect(dsn) as connection,
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute(
            """
            SELECT
                event_id,
                event_type,
                schema_version,
                tenant_id,
                aggregate_id,
                aggregate_version,
                correlation_id,
                causation_id,
                occurred_at,
                payload
            FROM memory_outbox_events
            ORDER BY occurred_at ASC, event_id ASC
            """
        )
        return tuple(
            _normalize_loaded_event(row_to_event(row))
            for row in cursor.fetchall()
        )


def _normalize_loaded_event(event: EventEnvelope) -> EventEnvelope:
    aggregate_id = event.aggregate_id
    if not isinstance(aggregate_id, MemoryId):
        return replace(event, aggregate_id=MemoryId(aggregate_id.value))
    return event


@pytest.mark.asyncio
async def test_first_append_get_and_stream(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_first_append_get_and_stream(harness_factory)


@pytest.mark.asyncio
async def test_exact_idempotent_replay(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_exact_idempotent_replay(harness_factory)


@pytest.mark.asyncio
async def test_divergent_idempotency_conflicts(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_divergent_idempotency_conflicts(harness_factory)


@pytest.mark.asyncio
async def test_exit_without_commit_rolls_back(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_exit_without_commit_rolls_back(harness_factory)


@pytest.mark.asyncio
async def test_episode_recorded_outbox_integrity(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    harness = harness_factory()
    committed = make_episode(1)
    unknown = make_episode(99)

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(committed)
        await unit_of_work.commit()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        with pytest.raises(
            ValueError,
            match="outbox episode event aggregate is unknown",
        ):
            await unit_of_work.outbox.publish(make_event(4, episode=unknown))
        with pytest.raises(
            ValueError,
            match="outbox event tenant does not match episode tenant",
        ):
            await unit_of_work.outbox.publish(
                replace(
                    make_event(5, episode=committed),
                    tenant_id=TENANT_B,
                )
            )

    assert harness.committed_episodes == (committed,)
    assert harness.committed_events == ()


@pytest.mark.asyncio
async def test_non_episode_event_types_publish_without_validation(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    harness = harness_factory()
    staged = make_episode(2)
    other_event = make_event(
        3,
        episode=make_episode(99),
        event_type="memory.projection-requested",
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(staged)
        await unit_of_work.outbox.publish(other_event)
        await unit_of_work.commit()

    assert harness.committed_episodes == (staged,)
    assert harness.committed_events == (other_event,)


@pytest.mark.asyncio
async def test_commit_persists_episode_and_outbox_atomically(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_commit_persists_episode_and_outbox_atomically(
        harness_factory
    )


@pytest.mark.asyncio
async def test_cancellation_inside_transaction_rolls_back_and_releases_lock(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_cancellation_inside_transaction_rolls_back_and_releases_lock(
        harness_factory
    )


@pytest.mark.asyncio
async def test_cancellation_after_commit_remains_and_releases_lock(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    await assert_cancellation_after_commit_remains_and_releases_lock(
        harness_factory
    )


@pytest.mark.asyncio
async def test_cursor_rejection_matches_in_memory_message(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    harness = harness_factory()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        with pytest.raises(
            ValueError,
            match="in-memory episode cursors are unavailable",
        ):
            await unit_of_work.episodes.stream(make_scope(), cursor="next")


@pytest.mark.asyncio
async def test_claims_unavailable_matches_in_memory_message(
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    harness = harness_factory()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        with pytest.raises(
            NotImplementedError,
            match="in-memory claim store is unavailable",
        ):
            await unit_of_work.claims.add_proposal(cast(ClaimProposal, object()))
        with pytest.raises(
            NotImplementedError,
            match="in-memory claim store is unavailable",
        ):
            await unit_of_work.claims.current(cast(MemoryQuery, object()))
