"""Bind PostgreSQL claim adapter contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import pytest_asyncio
from memory_adapter_contract import (
    CLAIM_ADAPTER_CONTRACTS,
    MemoryAdapterContractAssertion,
    MemoryAdapterHarnessFactory,
)
from test_postgres_memory_adapter_contract import PostgresMemoryAdapterHarness

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
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
    CLAIM_ADAPTER_CONTRACTS,
    ids=[case_name for case_name, _ in CLAIM_ADAPTER_CONTRACTS],
)
async def test_postgres_claim_adapter_contract(
    case_name: str,
    assert_contract: MemoryAdapterContractAssertion,
    harness_factory: MemoryAdapterHarnessFactory,
) -> None:
    del case_name
    await assert_contract(harness_factory)
