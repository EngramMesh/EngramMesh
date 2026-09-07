"""Bind execution snapshot store contracts to PostgreSQL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import execution_snapshot_store_contract as contract
import pytest
import pytest_asyncio
from execution_snapshot_store_contract import EXECUTION_SNAPSHOT_STORE_CONTRACTS

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.postgres.snapshot_store import (
    PostgresExecutionSnapshotStore,
)
from engrammesh.modules.runtime.adapters.postgres.snapshot_writer import (
    PostgresRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.modules.runtime.ports import ExecutionSnapshotStore

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def postgres_store_harness(
    postgres_dsn: str,
) -> tuple[PostgresExecutionSnapshotStore, PostgresRuntimeSnapshotWriter]:
    database = PostgresRuntimeDatabase(postgres_dsn)
    writer = PostgresRuntimeSnapshotWriter(postgres_dsn)
    await database.open()
    await writer.open()
    async with database.connection() as connection:
        await connection.execute("DELETE FROM runtime_execution_snapshots")
    store = PostgresExecutionSnapshotStore(database)
    yield store, writer
    async with database.connection() as connection:
        await connection.execute("DELETE FROM runtime_execution_snapshots")
    await writer.close()
    await database.close()


@pytest.fixture
def make_store(
    postgres_store_harness: tuple[PostgresExecutionSnapshotStore, PostgresRuntimeSnapshotWriter],
) -> Callable[[], Awaitable[ExecutionSnapshotStore]]:
    store, writer = postgres_store_harness

    async def _seed_snapshot(
        target_store: ExecutionSnapshotStore,
        snapshot: ExecutionSnapshot,
    ) -> None:
        del target_store
        await writer.upsert_snapshot(snapshot)

    contract._seed_snapshot = _seed_snapshot

    async def factory() -> ExecutionSnapshotStore:
        return store

    return factory


@pytest.mark.parametrize(
    ("name", "assertion"),
    EXECUTION_SNAPSHOT_STORE_CONTRACTS,
    ids=[name for name, _ in EXECUTION_SNAPSHOT_STORE_CONTRACTS],
)
@pytest.mark.asyncio
async def test_postgres_execution_snapshot_store_contract(
    name: str,
    assertion: Callable[[Callable[[], Awaitable[ExecutionSnapshotStore]]], Awaitable[None]],
    make_store: Callable[[], Awaitable[ExecutionSnapshotStore]],
) -> None:
    del name
    await assertion(make_store)
