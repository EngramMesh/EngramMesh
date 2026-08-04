"""Integration tests for PostgreSQL runtime schema migrations."""

import pytest
from psycopg import Connection

from engrammesh.modules.runtime.adapters.postgres.migrations import (
    apply_runtime_migrations,
)

pytestmark = pytest.mark.postgres


def test_apply_runtime_migrations_creates_runtime_tables(
    postgres_connection: Connection,
) -> None:
    apply_runtime_migrations(postgres_connection)
    rows = postgres_connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'runtime_%'
        ORDER BY table_name
        """
    ).fetchall()
    assert [row[0] for row in rows] == [
        "runtime_execution_snapshots",
        "runtime_schema_migrations",
        "runtime_start_idempotency",
    ]
