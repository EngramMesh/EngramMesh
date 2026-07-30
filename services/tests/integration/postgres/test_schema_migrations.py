"""Integration tests for PostgreSQL episode schema migrations."""

import pytest
from psycopg import Connection

pytestmark = pytest.mark.postgres


def _table_names(connection: Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        """
    )
    return {row[0] for row in rows}


def _index_names(connection: Connection, table_name: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = %s
        """,
        (table_name,),
    )
    return {row[0] for row in rows}


def _constraint_columns(
    connection: Connection,
    *,
    table_name: str,
    constraint_type: str,
) -> list[tuple[str, ...]]:
    rows = connection.execute(
        """
        SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = %s
        ORDER BY tc.constraint_name, kcu.ordinal_position
        """,
        (table_name, constraint_type),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for constraint_name, column_name, _ in rows:
        grouped.setdefault(constraint_name, []).append(column_name)
    return [tuple(columns) for columns in grouped.values()]


def test_schema_creates_expected_tables(migrated_postgres_connection: Connection) -> None:
    tables = _table_names(migrated_postgres_connection)

    assert {
        "memory_schema_migrations",
        "memory_episodes",
        "memory_episode_idempotency",
        "memory_outbox_events",
    }.issubset(tables)


def test_memory_episodes_has_tenant_idempotency_unique(
    migrated_postgres_connection: Connection,
) -> None:
    primary_keys = _constraint_columns(
        migrated_postgres_connection,
        table_name="memory_episodes",
        constraint_type="PRIMARY KEY",
    )
    unique_constraints = _constraint_columns(
        migrated_postgres_connection,
        table_name="memory_episodes",
        constraint_type="UNIQUE",
    )

    assert primary_keys == [("tenant_id", "episode_id")]
    assert ("tenant_id", "idempotency_key") in unique_constraints


def test_memory_episode_idempotency_references_episodes(
    migrated_postgres_connection: Connection,
) -> None:
    row = migrated_postgres_connection.execute(
        """
        SELECT
            con.conname,
            rel.relname AS foreign_table_name,
            con.conkey,
            con.confkey
        FROM pg_constraint AS con
        JOIN pg_class AS rel
          ON rel.oid = con.confrelid
        JOIN pg_class AS src
          ON src.oid = con.conrelid
        JOIN pg_namespace AS nsp
          ON nsp.oid = src.relnamespace
        WHERE nsp.nspname = 'public'
          AND src.relname = 'memory_episode_idempotency'
          AND con.contype = 'f'
        """
    ).fetchone()
    assert row is not None

    constraint_name, foreign_table_name, local_attnums, foreign_attnums = row
    local_columns = migrated_postgres_connection.execute(
        """
        SELECT attname
        FROM pg_attribute
        WHERE attrelid = 'memory_episode_idempotency'::regclass
          AND attnum = ANY(%s)
        ORDER BY array_position(%s, attnum)
        """,
        (local_attnums, local_attnums),
    ).fetchall()
    foreign_columns = migrated_postgres_connection.execute(
        """
        SELECT attname
        FROM pg_attribute
        WHERE attrelid = 'memory_episodes'::regclass
          AND attnum = ANY(%s)
        ORDER BY array_position(%s, attnum)
        """,
        (foreign_attnums, foreign_attnums),
    ).fetchall()

    assert constraint_name == "memory_episode_idempotency_episode_fkey"
    assert foreign_table_name == "memory_episodes"
    assert [column[0] for column in local_columns] == ["tenant_id", "episode_id"]
    assert [column[0] for column in foreign_columns] == ["tenant_id", "episode_id"]


def test_memory_outbox_events_has_publication_order_index(
    migrated_postgres_connection: Connection,
) -> None:
    indexes = _index_names(migrated_postgres_connection, "memory_outbox_events")

    assert "memory_outbox_events_tenant_occurred_event_idx" in indexes


def test_memory_outbox_events_has_unpublished_order_partial_index(
    migrated_postgres_connection: Connection,
) -> None:
    indexes = _index_names(migrated_postgres_connection, "memory_outbox_events")

    assert "memory_outbox_events_unpublished_order_idx" in indexes

    row = migrated_postgres_connection.execute(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'memory_outbox_events'
          AND indexname = 'memory_outbox_events_unpublished_order_idx'
        """
    ).fetchone()
    assert row is not None

    indexdef = row[0].lower()
    assert "published_at is null" in indexdef
    assert "occurred_at" in indexdef
    assert "event_id" in indexdef
