"""Standalone PostgreSQL runtime snapshot writer for Temporal side effects."""

from __future__ import annotations

from typing import final

from psycopg.types.json import Jsonb

from engrammesh.modules.runtime.adapters.postgres.connection import (
    PostgresRuntimeConnection,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import (
    snapshot_to_row,
    to_json_value,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot

_SNAPSHOT_COLUMNS = (
    "tenant_id",
    "execution_id",
    "subject_id",
    "workspace_id",
    "agent_id",
    "revision",
    "status",
    "snapshot",
    "updated_at",
)


@final
class PostgresRuntimeSnapshotWriter:
    __slots__ = ("_connection",)

    def __init__(self, dsn: str) -> None:
        self._connection = PostgresRuntimeConnection(dsn)

    async def open(self) -> None:
        await self._connection.open()

    async def close(self) -> None:
        await self._connection.close()

    async def upsert_snapshot(self, snapshot: ExecutionSnapshot) -> None:
        row = snapshot_to_row(snapshot)
        async with (
            self._connection.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                f"""
                INSERT INTO runtime_execution_snapshots ({", ".join(_SNAPSHOT_COLUMNS)})
                VALUES ({", ".join("%s" for _ in _SNAPSHOT_COLUMNS)})
                ON CONFLICT (tenant_id, execution_id) DO UPDATE
                SET subject_id = EXCLUDED.subject_id,
                    workspace_id = EXCLUDED.workspace_id,
                    agent_id = EXCLUDED.agent_id,
                    revision = EXCLUDED.revision,
                    status = EXCLUDED.status,
                    snapshot = EXCLUDED.snapshot,
                    updated_at = EXCLUDED.updated_at
                WHERE runtime_execution_snapshots.revision < EXCLUDED.revision
                """,
                (
                    row["tenant_id"],
                    row["execution_id"],
                    row["subject_id"],
                    row["workspace_id"],
                    row["agent_id"],
                    row["revision"],
                    row["status"],
                    Jsonb(to_json_value(row["snapshot"])),
                    row["updated_at"],
                ),
            )
