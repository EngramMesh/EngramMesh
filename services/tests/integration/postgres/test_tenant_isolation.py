"""PostgreSQL tenant isolation integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import psycopg
import pytest
import pytest_asyncio
from contract.memory_adapter_contract import (
    TENANT_A,
    TENANT_B,
    make_episode,
    make_event,
    make_scope,
    memory_id,
)

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


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_none(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    scope_a = make_scope(tenant_id=TENANT_A)
    scope_b = make_scope(tenant_id=TENANT_B)
    episode = make_episode(1, scope=scope_a)

    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()

    async with unit_of_work_factory.create() as unit_of_work:
        assert await unit_of_work.episodes.get(scope_b, episode.id) is None


@pytest.mark.asyncio
async def test_cross_tenant_stream_returns_empty(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    scope_a = make_scope(tenant_id=TENANT_A)
    scope_b = make_scope(tenant_id=TENANT_B)
    episode = make_episode(1, scope=scope_a)

    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()

    async with unit_of_work_factory.create() as unit_of_work:
        assert await unit_of_work.episodes.stream(scope_b) == ()


@pytest.mark.asyncio
async def test_same_subject_different_tenant_is_invisible(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    scope_a = make_scope(tenant_id=TENANT_A)
    scope_b = make_scope(tenant_id=TENANT_B)
    episode = make_episode(1, scope=scope_a)

    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()

    async with unit_of_work_factory.create() as unit_of_work:
        assert await unit_of_work.episodes.get(scope_b, episode.id) is None
        assert await unit_of_work.episodes.stream(scope_b) == ()
        assert await unit_of_work.episodes.get(scope_a, memory_id(99)) is None
        assert await unit_of_work.episodes.get(scope_a, episode.id) == episode


@pytest.mark.asyncio
async def test_outbox_publish_succeeds_when_episode_id_is_shared_across_tenants(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    shared_id = memory_id(42)
    scope_a = make_scope(tenant_id=TENANT_A)
    scope_b = make_scope(tenant_id=TENANT_B)
    episode_a = replace(
        make_episode(1, scope=scope_a),
        id=shared_id,
        idempotency_key="tenant-a",
    )
    episode_b = replace(
        make_episode(2, scope=scope_b),
        id=shared_id,
        idempotency_key="tenant-b",
    )

    for episode in (episode_a, episode_b):
        async with unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(episode)
            await unit_of_work.commit()

    event_a = make_event(1, episode=episode_a)
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.outbox.publish(event_a)
        await unit_of_work.commit()

    event_b = make_event(2, episode=episode_b)
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.outbox.publish(event_b)
        await unit_of_work.commit()
