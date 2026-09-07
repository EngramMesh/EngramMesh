"""PostgreSQL execution snapshot store for scope-accurate list reads."""

from __future__ import annotations

from typing import final

from psycopg.rows import dict_row

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import row_to_snapshot
from engrammesh.modules.runtime.domain.execution_cursor import (
    decode_execution_cursor,
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


def _scope_params(scope: MemoryScope) -> dict[str, object]:
    return {
        "tenant_id": scope.tenant_id.value,
        "subject_id": scope.subject_id.value,
        "workspace_id": scope.workspace_id,
        "agent_id": scope.agent_id.value if scope.agent_id is not None else None,
    }


@final
class PostgresExecutionSnapshotStore:
    """Read execution snapshots from the runtime projection table."""

    __slots__ = ("_database",)

    def __init__(self, database: PostgresRuntimeDatabase) -> None:
        self._database = database

    async def stream(
        self,
        scope: MemoryScope,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> tuple[ExecutionSnapshot, ...]:
        if cursor is not None and limit is None:
            msg = "cursor requires limit"
            raise ValueError(msg)
        if limit is not None and limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)

        params = _scope_params(scope)
        cursor_clause = ""
        if cursor is not None:
            cursor_at, cursor_id = decode_execution_cursor(cursor)
            params["cursor_updated_at"] = cursor_at
            params["cursor_execution_id"] = cursor_id.value
            cursor_clause = """
              AND (updated_at, execution_id) < (%(cursor_updated_at)s, %(cursor_execution_id)s)
            """
        limit_clause = ""
        if limit is not None:
            params["limit"] = limit
            limit_clause = "LIMIT %(limit)s"

        async with (
            self._database.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor_,
        ):
            await cursor_.execute(
                f"""
                SELECT {", ".join(_SNAPSHOT_COLUMNS)}
                FROM runtime_execution_snapshots
                WHERE tenant_id = %(tenant_id)s
                  AND subject_id = %(subject_id)s
                  AND workspace_id IS NOT DISTINCT FROM %(workspace_id)s
                  AND agent_id IS NOT DISTINCT FROM %(agent_id)s
                  {cursor_clause}
                ORDER BY updated_at DESC, execution_id DESC
                {limit_clause}
                """,
                params,
            )
            rows = await cursor_.fetchall()
        return tuple(row_to_snapshot(row) for row in rows)
