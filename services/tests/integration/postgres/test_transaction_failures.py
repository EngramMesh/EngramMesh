"""PostgreSQL transaction failure integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio
from contract.memory_adapter_contract import make_episode, make_event
from psycopg import errors as pg_errors

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.unit_of_work import (
    PostgresMemoryUnitOfWorkFactory,
)

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
def unit_of_work_factory(
    postgres_database: PostgresMemoryDatabase,
) -> PostgresMemoryUnitOfWorkFactory:
    return PostgresMemoryUnitOfWorkFactory(postgres_database)


def _count_rows(dsn: str, table: str) -> int:
    with (
        psycopg.connect(dsn) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_duplicate_outbox_event_rolls_back_entire_transaction(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
    postgres_dsn: str,
) -> None:
    episode = make_episode(1)
    event = make_event(1, episode=episode)

    with pytest.raises(pg_errors.UniqueViolation):
        async with unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(episode)
            await unit_of_work.outbox.publish(event)
            await unit_of_work.outbox.publish(event)

    assert _count_rows(postgres_dsn, "memory_episodes") == 0
    assert _count_rows(postgres_dsn, "memory_episode_idempotency") == 0
    assert _count_rows(postgres_dsn, "memory_outbox_events") == 0


@pytest.mark.asyncio
async def test_sql_error_before_commit_leaves_prior_commits_unchanged(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
    postgres_dsn: str,
) -> None:
    committed = make_episode(1)
    failed = make_episode(2)
    event = make_event(1, episode=failed)

    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(committed)
        await unit_of_work.commit()

    with pytest.raises(pg_errors.UniqueViolation):
        async with unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(failed)
            await unit_of_work.outbox.publish(event)
            await unit_of_work.outbox.publish(event)

    assert _count_rows(postgres_dsn, "memory_episodes") == 1
    assert _count_rows(postgres_dsn, "memory_episode_idempotency") == 1
    assert _count_rows(postgres_dsn, "memory_outbox_events") == 0
