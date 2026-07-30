"""Shared PostgreSQL test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import Connection

from engrammesh.modules.memory.adapters.postgres.migrations import apply_migrations

POSTGRES_DSN_ENV = "ENGRAMMESH__POSTGRES__DSN"

_DATA_TABLES = (
    "memory_inbox_events",
    "memory_outbox_events",
    "memory_episode_idempotency",
    "memory_episodes",
)


def _postgres_dsn() -> str | None:
    return os.environ.get(POSTGRES_DSN_ENV)


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = _postgres_dsn()
    if dsn is None:
        pytest.skip(f"{POSTGRES_DSN_ENV} is not set")
    return dsn


@pytest.fixture
def postgres_connection(postgres_dsn: str) -> Iterator[Connection]:
    with psycopg.connect(postgres_dsn) as connection:
        apply_migrations(connection)
        yield connection
        with connection.transaction():
            connection.execute(
                "TRUNCATE "
                + ", ".join(_DATA_TABLES)
                + " RESTART IDENTITY CASCADE"
            )


@pytest.fixture
def migrated_postgres_connection(postgres_connection: Connection) -> Connection:
    return postgres_connection
