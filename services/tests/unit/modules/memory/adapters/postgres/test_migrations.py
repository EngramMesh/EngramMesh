"""Unit tests for the PostgreSQL schema migration runner."""

from __future__ import annotations

import pytest
from psycopg import Connection

from engrammesh.modules.memory.adapters.postgres.migrations import (
    MIGRATIONS_DIR,
    apply_migrations,
)


def test_migrations_dir_contains_episode_outbox_sql() -> None:
    migration = MIGRATIONS_DIR / "001_episode_outbox.sql"
    assert migration.is_file()


def test_migrations_dir_contains_outbox_relay_index_sql() -> None:
    migration = MIGRATIONS_DIR / "002_outbox_relay_index.sql"
    assert migration.is_file()


@pytest.mark.postgres
def test_apply_migrations_records_applied_versions(
    postgres_connection: Connection,
) -> None:
    apply_migrations(postgres_connection)

    versions = {
        row[0]
        for row in postgres_connection.execute(
            "SELECT version FROM memory_schema_migrations ORDER BY version"
        )
    }

    assert versions == {"001_episode_outbox", "002_outbox_relay_index"}


@pytest.mark.postgres
def test_apply_migrations_is_idempotent(postgres_connection: Connection) -> None:
    apply_migrations(postgres_connection)
    apply_migrations(postgres_connection)

    count = postgres_connection.execute(
        "SELECT COUNT(*) FROM memory_schema_migrations"
    ).fetchone()[0]

    assert count == 2
