"""Integration tests for the PostgreSQL memory connection pool."""

from __future__ import annotations

import pytest
from psycopg import Connection

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_connection_pool_applies_migrations_on_first_connection(
    postgres_dsn: str,
) -> None:
    database = PostgresMemoryDatabase(postgres_dsn)
    await database.open()
    try:
        async with database.connection() as connection:
            versions = await _fetch_migration_versions(connection)
            assert "001_episode_outbox" in versions
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_connection_pool_releases_connections_after_use(
    postgres_dsn: str,
) -> None:
    database = PostgresMemoryDatabase(postgres_dsn)
    await database.open()
    try:
        async with database.connection():
            pass

        async with database.connection() as connection:
            versions = await _fetch_migration_versions(connection)
            assert "001_episode_outbox" in versions
    finally:
        await database.close()


async def _fetch_migration_versions(connection: Connection) -> set[str]:
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT version FROM memory_schema_migrations")
        rows = await cursor.fetchall()
    return {row[0] for row in rows}
