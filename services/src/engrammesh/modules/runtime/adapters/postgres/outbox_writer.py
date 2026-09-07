"""Standalone PostgreSQL runtime outbox writer for Temporal activities."""

from __future__ import annotations

from typing import final
from uuid import uuid4

from psycopg.types.json import Jsonb

from engrammesh.modules.runtime.adapters.postgres.connection import (
    PostgresRuntimeConnection,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import (
    _to_json_value,
    event_to_row,
)
from engrammesh.modules.runtime.adapters.shared.status_changed_event import (
    build_execution_status_changed_event,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.shared.kernel.ids import CorrelationId, EventId

_OUTBOX_COLUMNS = (
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
class PostgresRuntimeOutboxWriter:
    """Insert runtime outbox rows outside database write transactions."""

    __slots__ = ("_connection",)

    def __init__(self, dsn: str) -> None:
        self._connection = PostgresRuntimeConnection(dsn)

    async def open(self) -> None:
        """Open the connection pool."""
        await self._connection.open()

    async def close(self) -> None:
        """Close the connection pool."""
        await self._connection.close()

    async def publish_status_changed(
        self,
        previous_status: ExecutionStatus | None,
        snapshot: ExecutionSnapshot,
        correlation_id: CorrelationId,
    ) -> None:
        event = build_execution_status_changed_event(
            event_id=EventId(uuid4()),
            correlation_id=correlation_id,
            causation_id=None,
            previous_status=previous_status,
            snapshot=snapshot,
        )
        row = event_to_row(event)
        async with (
            self._connection.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                f"""
                INSERT INTO runtime_outbox_events ({", ".join(_OUTBOX_COLUMNS)})
                VALUES ({", ".join("%s" for _ in _OUTBOX_COLUMNS)})
                """,
                (
                    row["event_id"],
                    row["event_type"],
                    row["schema_version"],
                    row["tenant_id"],
                    row["aggregate_id"],
                    row["aggregate_version"],
                    row["correlation_id"],
                    row["causation_id"],
                    row["occurred_at"],
                    Jsonb(_to_json_value(row["payload"])),
                ),
            )
