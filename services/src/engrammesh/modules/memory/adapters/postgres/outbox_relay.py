"""PostgreSQL outbox relay polling store."""

from __future__ import annotations

from datetime import datetime
from typing import final

from psycopg.rows import dict_row

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.mappers import row_to_event
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import EventId

_FETCH_COLUMNS = (
    "event_id",
    "event_type",
    "schema_version",
    "tenant_id",
    "aggregate_id",
    "aggregate_version",
    "correlation_id",
    "causation_id",
    "occurred_at",
    "payload",
)


@final
class PostgresOutboxRelayStore:
    """Poll unpublished outbox rows and mark them published outside UoW."""

    __slots__ = ("_database",)

    def __init__(self, database: PostgresMemoryDatabase) -> None:
        self._database = database

    async def fetch_unpublished(self, *, limit: int) -> tuple[EventEnvelope, ...]:
        async with (
            self._database.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                f"""
                SELECT {", ".join(_FETCH_COLUMNS)}
                FROM memory_outbox_events
                WHERE published_at IS NULL
                ORDER BY occurred_at ASC, event_id ASC
                LIMIT %(limit)s
                """,
                {"limit": limit},
            )
            rows = await cursor.fetchall()
        return tuple(row_to_event(row) for row in rows)

    async def mark_published(
        self,
        *,
        event_ids: tuple[EventId, ...],
        published_at: datetime,
    ) -> None:
        if not event_ids:
            return
        async with self._database.connection() as connection:
            await connection.execute(
                """
                UPDATE memory_outbox_events
                SET published_at = %(published_at)s
                WHERE event_id = ANY(%(event_ids)s::uuid[])
                  AND published_at IS NULL
                """,
                {
                    "published_at": published_at,
                    "event_ids": [event_id.value for event_id in event_ids],
                },
            )

    async def count_unpublished(self) -> int:
        async with (
            self._database.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                """
                SELECT COUNT(*) FROM memory_outbox_events
                WHERE published_at IS NULL
                """
            )
            row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row[0])
