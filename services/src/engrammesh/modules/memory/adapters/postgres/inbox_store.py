"""PostgreSQL inbox deduplication store."""

from __future__ import annotations

from datetime import datetime
from typing import final

from psycopg.rows import dict_row

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.shared.kernel.ids import EventId, TenantId


@final
class PostgresInboxStore:
    """Durable inbox deduplication backed by memory_inbox_events."""

    __slots__ = ("_database",)

    def __init__(self, database: PostgresMemoryDatabase) -> None:
        self._database = database

    async def try_record(
        self,
        *,
        event_id: EventId,
        consumer_name: str,
        event_type: str,
        tenant_id: TenantId,
        processed_at: datetime,
    ) -> bool:
        async with (
            self._database.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                """
                INSERT INTO memory_inbox_events (
                    event_id,
                    consumer_name,
                    event_type,
                    tenant_id,
                    processed_at
                )
                VALUES (
                    %(event_id)s,
                    %(consumer_name)s,
                    %(event_type)s,
                    %(tenant_id)s,
                    %(processed_at)s
                )
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                {
                    "event_id": event_id.value,
                    "consumer_name": consumer_name,
                    "event_type": event_type,
                    "tenant_id": tenant_id.value,
                    "processed_at": processed_at,
                },
            )
            row = await cursor.fetchone()
        return row is not None

    async def remove_record(self, *, event_id: EventId) -> None:
        async with self._database.connection() as connection:
            await connection.execute(
                """
                DELETE FROM memory_inbox_events
                WHERE event_id = %(event_id)s
                """,
                {"event_id": event_id.value},
            )
