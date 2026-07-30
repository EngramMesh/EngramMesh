"""Shared PostgreSQL integration test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import Connection

from engrammesh.modules.memory.adapters.postgres.migrations import apply_migrations

POSTGRES_DSN_ENV = "ENGRAMMESH__POSTGRES__DSN"

_DATA_TABLES = (
    "memory_outbox_events",
    "memory_episode_idempotency",
    "memory_episodes",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("postgres") is not None:
            item.add_marker(pytest.mark.xdist_group(name="postgres_serial"))


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
        connection.commit()
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
