"""PostgreSQL-backed committed runtime state."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TypeVar, final

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from engrammesh.modules.runtime.adapters.postgres.connection import (
    PostgresRuntimeConnection,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import (
    _as_uuid,
    _to_json_value,
    idempotency_to_row,
    row_to_fingerprint,
    row_to_snapshot,
    snapshot_to_row,
)
from engrammesh.modules.runtime.adapters.shared.snapshot_codec import (
    fingerprint_to_json,
)
from engrammesh.modules.runtime.runtime_state import (
    CommittedRuntimeState,
    empty_runtime_state,
)
from engrammesh.shared.kernel.ids import ExecutionId, TenantId

_T = TypeVar("_T")

_MAX_IDEMPOTENCY_WRITE_RETRIES = 5


class _IdempotencyInsertRaceError(Exception):
    """Concurrent idempotency insert; retry write from fresh committed state."""


_IDEMPOTENCY_COLUMNS = (
    "tenant_id",
    "idempotency_key",
    "execution_id",
    "fingerprint",
    "created_at",
)

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
class PostgresRuntimeDatabase:
    """Persist committed execution snapshots and start-idempotency indexes."""

    __slots__ = ("_connection", "_lock")

    def __init__(self, dsn: str) -> None:
        self._connection = PostgresRuntimeConnection(dsn)
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        """Open the connection pool and apply runtime migrations."""
        await self._connection.open()

    async def close(self) -> None:
        """Close the connection pool."""
        await self._connection.close()

    async def read(self, callback: Callable[[CommittedRuntimeState], _T]) -> _T:
        """Run *callback* against the current committed state."""
        async with _transactional_connection(self._lock, self._connection) as connection:
            state = await _load_state(connection)
            return callback(state)

    async def write(
        self,
        callback: Callable[[CommittedRuntimeState], CommittedRuntimeState],
    ) -> None:
        """Atomically replace committed state with *callback*'s result."""
        async with self._lock, self._connection.connection() as connection:
            for _ in range(_MAX_IDEMPOTENCY_WRITE_RETRIES):
                async with connection.transaction():
                    before = await _load_state(connection)
                    after = callback(before)
                    try:
                        await _persist_state(connection, before, after)
                    except _IdempotencyInsertRaceError:
                        continue
                    return
            msg = "runtime idempotency write exceeded retry limit"
            raise RuntimeError(msg)


@asynccontextmanager
async def _transactional_connection(
    lock: asyncio.Lock,
    connection_pool: PostgresRuntimeConnection,
) -> AsyncIterator[AsyncConnection]:
    async with lock, connection_pool.connection() as connection:  # noqa: SIM117
        async with connection.transaction():
            yield connection


async def _load_state(connection: AsyncConnection) -> CommittedRuntimeState:
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
            SELECT tenant_id, idempotency_key, execution_id, fingerprint
            FROM runtime_start_idempotency
            """
        )
        idempotency_rows = await cursor.fetchall()
        await cursor.execute(
            """
            SELECT tenant_id, execution_id, subject_id, workspace_id, agent_id,
                   revision, status, snapshot, updated_at
            FROM runtime_execution_snapshots
            """
        )
        snapshot_rows = await cursor.fetchall()

    idempotency_index: dict[tuple[TenantId, str], ExecutionId] = {}
    fingerprints: dict[ExecutionId, tuple[object, ...]] = {}
    for row in idempotency_rows:
        tenant_id = TenantId(_as_uuid(row["tenant_id"]))
        idempotency_key = str(row["idempotency_key"])
        execution_id = ExecutionId(_as_uuid(row["execution_id"]))
        idempotency_index[(tenant_id, idempotency_key)] = execution_id
        fingerprints[execution_id] = row_to_fingerprint(row)

    snapshots = {
        ExecutionId(_as_uuid(row["execution_id"])): row_to_snapshot(row)
        for row in snapshot_rows
    }
    if not idempotency_index and not snapshots:
        return empty_runtime_state()
    return CommittedRuntimeState(
        snapshots=MappingProxyType(snapshots),
        idempotency_index=MappingProxyType(idempotency_index),
        fingerprints=MappingProxyType(fingerprints),
    )


async def _persist_state(
    connection: AsyncConnection,
    before: CommittedRuntimeState,
    after: CommittedRuntimeState,
) -> None:
    await _persist_idempotency(connection, before, after)
    await _persist_snapshots(connection, before, after)


async def _persist_idempotency(
    connection: AsyncConnection,
    before: CommittedRuntimeState,
    after: CommittedRuntimeState,
) -> None:
    before_keys = set(before.idempotency_index.keys())
    after_keys = set(after.idempotency_index.keys())
    created_at = datetime.now(UTC)

    async with connection.cursor() as cursor:
        for key in before_keys - after_keys:
            tenant_id, idempotency_key = key
            await cursor.execute(
                """
                DELETE FROM runtime_start_idempotency
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (tenant_id.value, idempotency_key),
            )

        for key in after_keys - before_keys:
            tenant_id, idempotency_key = key
            execution_id = after.idempotency_index[key]
            fingerprint = after.fingerprints[execution_id]
            row = idempotency_to_row(
                tenant_id,
                idempotency_key,
                execution_id,
                fingerprint,
                created_at=created_at,
            )
            async with connection.cursor(row_factory=dict_row) as returning_cursor:
                await returning_cursor.execute(
                    f"""
                    INSERT INTO runtime_start_idempotency ({", ".join(_IDEMPOTENCY_COLUMNS)})
                    VALUES ({", ".join("%s" for _ in _IDEMPOTENCY_COLUMNS)})
                    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                    RETURNING execution_id
                    """,
                    (
                        row["tenant_id"],
                        row["idempotency_key"],
                        row["execution_id"],
                        Jsonb(_to_json_value(row["fingerprint"])),
                        row["created_at"],
                    ),
                )
                inserted = await returning_cursor.fetchone()
            if inserted is None:
                raise _IdempotencyInsertRaceError()

        for key in before_keys & after_keys:
            tenant_id, idempotency_key = key
            before_execution_id = before.idempotency_index[key]
            after_execution_id = after.idempotency_index[key]
            before_fingerprint = before.fingerprints.get(before_execution_id)
            after_fingerprint = after.fingerprints[after_execution_id]
            if (
                before_execution_id == after_execution_id
                and before_fingerprint == after_fingerprint
            ):
                continue
            await cursor.execute(
                """
                UPDATE runtime_start_idempotency
                SET execution_id = %s, fingerprint = %s
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (
                    after_execution_id.value,
                    Jsonb(
                        _to_json_value(fingerprint_to_json(after_fingerprint))
                    ),
                    tenant_id.value,
                    idempotency_key,
                ),
            )


async def _persist_snapshots(
    connection: AsyncConnection,
    before: CommittedRuntimeState,
    after: CommittedRuntimeState,
) -> None:
    before_ids = set(before.snapshots.keys())
    after_ids = set(after.snapshots.keys())

    async with connection.cursor() as cursor:
        for execution_id in before_ids - after_ids:
            snapshot = before.snapshots[execution_id]
            await cursor.execute(
                """
                DELETE FROM runtime_execution_snapshots
                WHERE tenant_id = %s AND execution_id = %s
                """,
                (snapshot.scope.tenant_id.value, execution_id.value),
            )

        for execution_id in after_ids - before_ids:
            row = snapshot_to_row(after.snapshots[execution_id])
            await cursor.execute(
                f"""
                INSERT INTO runtime_execution_snapshots ({", ".join(_SNAPSHOT_COLUMNS)})
                VALUES ({", ".join("%s" for _ in _SNAPSHOT_COLUMNS)})
                """,
                (
                    row["tenant_id"],
                    row["execution_id"],
                    row["subject_id"],
                    row["workspace_id"],
                    row["agent_id"],
                    row["revision"],
                    row["status"],
                    Jsonb(_to_json_value(row["snapshot"])),
                    row["updated_at"],
                ),
            )

        for execution_id in before_ids & after_ids:
            before_snapshot = before.snapshots[execution_id]
            after_snapshot = after.snapshots[execution_id]
            if before_snapshot == after_snapshot:
                continue
            row = snapshot_to_row(after_snapshot)
            await cursor.execute(
                """
                UPDATE runtime_execution_snapshots
                SET subject_id = %s,
                    workspace_id = %s,
                    agent_id = %s,
                    revision = %s,
                    status = %s,
                    snapshot = %s,
                    updated_at = %s
                WHERE tenant_id = %s AND execution_id = %s
                """,
                (
                    row["subject_id"],
                    row["workspace_id"],
                    row["agent_id"],
                    row["revision"],
                    row["status"],
                    Jsonb(_to_json_value(row["snapshot"])),
                    row["updated_at"],
                    row["tenant_id"],
                    row["execution_id"],
                ),
            )


