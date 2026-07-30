"""Bind every reusable episode adapter contract to the PostgreSQL adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import replace

import psycopg
import pytest
import pytest_asyncio
from memory_adapter_contract import (
    EPISODE_ADAPTER_CONTRACTS,
    MemoryAdapterContractAssertion,
    MemoryAdapterHarnessFactory,
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
from engrammesh.modules.memory.ports import MemoryUnitOfWorkFactory
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import MemoryId

pytestmark = pytest.mark.postgres


class PostgresMemoryAdapterHarness:
    """Expose public construction and committed-state probes for one database."""

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
    def make_harness() -> PostgresMemoryAdapterHarness:
        return PostgresMemoryAdapterHarness(postgres_database, postgres_dsn)

    yield make_harness


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    EPISODE_ADAPTER_CONTRACTS,
    ids=[case_name for case_name, _ in EPISODE_ADAPTER_CONTRACTS],
)
async def test_postgres_episode_adapter_contract(
    case_name: str,
    assert_contract: MemoryAdapterContractAssertion,
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    del case_name
    await assert_contract(harness_factory)
