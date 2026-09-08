"""PostgreSQL ClaimStore integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio
from contract.memory_adapter_contract import (
    SUBJECT_B,
    make_claim_proposal,
    make_episode,
    make_scope,
    memory_id,
)

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.unit_of_work import (
    PostgresMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.ports import MemoryQuery

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def unit_of_work_factory(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> AsyncIterator[PostgresMemoryUnitOfWorkFactory]:
    del postgres_connection
    database = PostgresMemoryDatabase(postgres_dsn)
    await database.open()
    try:
        yield PostgresMemoryUnitOfWorkFactory(database)
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_add_proposal_persists_claim(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    episode = make_episode(1)
    proposal = make_claim_proposal(episode, memory_id(100))
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.claims.add_proposal(proposal)
        await unit_of_work.commit()
    async with unit_of_work_factory.create() as unit_of_work:
        results = await unit_of_work.claims.current(
            MemoryQuery(query_id="q1", scope=episode.scope, text="ignored")
        )
        assert len(results) == 1
        assert results[0].id == memory_id(100)


@pytest.mark.asyncio
async def test_add_proposal_is_idempotent_for_same_episode_and_extractor(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    episode = make_episode(2)
    proposal = make_claim_proposal(episode, memory_id(101))
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        first = await unit_of_work.claims.add_proposal(proposal)
        second = await unit_of_work.claims.add_proposal(proposal)
        assert first.created is True
        assert second.created is False
        assert second.claim_id == memory_id(101)
        await unit_of_work.commit()
    async with unit_of_work_factory.create() as unit_of_work:
        results = await unit_of_work.claims.current(
            MemoryQuery(query_id="q1", scope=episode.scope, text="ignored")
        )
        assert len(results) == 1


@pytest.mark.asyncio
async def test_current_orders_by_recorded_from_desc_then_claim_id(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    scope = make_scope()
    async with unit_of_work_factory.create() as unit_of_work:
        for index in range(3):
            episode = make_episode(index, scope=scope)
            await unit_of_work.episodes.append(episode)
            await unit_of_work.claims.add_proposal(
                make_claim_proposal(episode, memory_id(200 + index))
            )
        await unit_of_work.commit()
    async with unit_of_work_factory.create() as unit_of_work:
        results = await unit_of_work.claims.current(
            MemoryQuery(query_id="q1", scope=scope, text="ignored", limit=2)
        )
        assert len(results) == 2
        assert results[0].id == memory_id(202)
        assert results[1].id == memory_id(201)


@pytest.mark.asyncio
async def test_history_returns_claim_in_scope(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    episode = make_episode(10)
    claim_id = memory_id(300)
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.claims.add_proposal(make_claim_proposal(episode, claim_id))
        await unit_of_work.commit()
    async with unit_of_work_factory.create() as unit_of_work:
        history = await unit_of_work.claims.history(episode.scope, claim_id)
        assert len(history) == 1
        assert history[0].id == claim_id


@pytest.mark.asyncio
async def test_history_returns_empty_on_scope_mismatch(
    unit_of_work_factory: PostgresMemoryUnitOfWorkFactory,
) -> None:
    episode = make_episode(11)
    claim_id = memory_id(301)
    async with unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.claims.add_proposal(make_claim_proposal(episode, claim_id))
        await unit_of_work.commit()
    wrong_scope = make_scope(subject_id=SUBJECT_B)
    async with unit_of_work_factory.create() as unit_of_work:
        history = await unit_of_work.claims.history(wrong_scope, claim_id)
        assert history == ()
