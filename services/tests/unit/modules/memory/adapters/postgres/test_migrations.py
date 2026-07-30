"""Unit tests for the PostgreSQL schema migration runner."""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import Connection

from engrammesh.modules.memory.adapters.postgres.migrations import (
    MIGRATIONS_DIR,
    apply_migrations,
)

POSTGRES_DSN_ENV = "ENGRAMMESH__POSTGRES__DSN"


@pytest.fixture
def postgres_connection() -> Iterator[Connection]:
    dsn = os.environ.get(POSTGRES_DSN_ENV)
    if dsn is None:
        pytest.skip(f"{POSTGRES_DSN_ENV} is not set")
    with psycopg.connect(dsn) as connection:
        apply_migrations(connection)
        connection.commit()
        yield connection
        with connection.transaction():
            connection.execute(
                """
                TRUNCATE memory_outbox_events,
                         memory_episode_idempotency,
                         memory_episodes
                RESTART IDENTITY CASCADE
                """
            )


def test_migrations_dir_contains_episode_outbox_sql() -> None:
    migration = MIGRATIONS_DIR / "001_episode_outbox.sql"
    assert migration.is_file()


@pytest.mark.postgres
def test_apply_migrations_records_applied_versions(
    postgres_connection: Connection,
) -> None:
    apply_migrations(postgres_connection)
    postgres_connection.commit()

    versions = {
        row[0]
        for row in postgres_connection.execute(
            "SELECT version FROM memory_schema_migrations ORDER BY version"
        )
    }

    assert versions == {"001_episode_outbox"}


@pytest.mark.postgres
def test_apply_migrations_is_idempotent(postgres_connection: Connection) -> None:
    apply_migrations(postgres_connection)
    postgres_connection.commit()

    apply_migrations(postgres_connection)
    postgres_connection.commit()

    count = postgres_connection.execute(
        "SELECT COUNT(*) FROM memory_schema_migrations"
    ).fetchone()[0]

    assert count == 1
