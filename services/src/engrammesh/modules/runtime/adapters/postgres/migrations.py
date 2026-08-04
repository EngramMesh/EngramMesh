"""Versioned SQL migrations for the PostgreSQL runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS runtime_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL
)
"""


def apply_runtime_migrations(connection: Connection) -> None:
    """Apply pending SQL migrations in lexical order inside one transaction."""
    with connection.transaction():
        connection.execute(_BOOTSTRAP_SQL)
        applied_versions = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM runtime_schema_migrations"
            )
        }
        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_path.stem
            if version in applied_versions:
                continue
            connection.execute(migration_path.read_text(encoding="utf-8"))
            connection.execute(
                """
                INSERT INTO runtime_schema_migrations (version, applied_at)
                VALUES (%s, NOW())
                """,
                (version,),
            )
