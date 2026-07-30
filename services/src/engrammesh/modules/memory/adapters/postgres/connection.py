"""Async PostgreSQL connection pool for the memory adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import final

import psycopg
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from engrammesh.modules.memory.adapters.postgres.migrations import apply_migrations


@final
class PostgresMemoryDatabase:
    """Own a psycopg async pool and apply schema migrations on first use."""

    __slots__ = ("_dsn", "_migration_lock", "_migrations_applied", "_pool")

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: AsyncConnectionPool | None = None
        self._migrations_applied = False
        self._migration_lock = asyncio.Lock()

    async def open(self) -> None:
        """Open the connection pool."""
        if self._pool is not None:
            return
        pool = AsyncConnectionPool(self._dsn, open=False)
        await pool.open()
        self._pool = pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
        self._migrations_applied = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        """Borrow a pooled connection with migrations applied once."""
        pool = self._pool
        if pool is None:
            msg = "postgres memory database is not open"
            raise RuntimeError(msg)
        await self._ensure_migrations()
        async with pool.connection() as connection:
            yield connection

    async def _ensure_migrations(self) -> None:
        async with self._migration_lock:
            if self._migrations_applied:
                return
            await asyncio.to_thread(_apply_migrations_from_dsn, self._dsn)
            self._migrations_applied = True


def _apply_migrations_from_dsn(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        apply_migrations(connection)
