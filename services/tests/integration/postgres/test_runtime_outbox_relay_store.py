"""Integration tests for PostgresRuntimeOutboxRelayStore."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
import pytest_asyncio
from psycopg.types.json import Jsonb

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import event_to_row
from engrammesh.modules.runtime.adapters.postgres.outbox_relay import (
    PostgresRuntimeOutboxRelayStore,
)
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    ExecutionId,
    TenantId,
)

pytestmark = pytest.mark.postgres

TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
CORRELATION_ID = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
EXECUTION_ID = ExecutionId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
EVENT_ID_EARLY = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
EVENT_ID_LATE = EventId(UUID("8fa7198e-8caa-5d3b-9bb6-00117cf4dc0a"))
EVENT_ID_PUBLISHED = EventId(UUID("9fb82a9f-9dbb-6e4c-acc7-11228d05ed1b"))
OCCURRED_AT_EARLY = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OCCURRED_AT_LATE = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
ALREADY_PUBLISHED_AT = datetime(2026, 7, 27, 7, 0, tzinfo=UTC)


def make_event(
    event_id: EventId,
    *,
    occurred_at: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type="runtime.execution-status-changed",
        schema_version=1,
        tenant_id=TENANT_ID,
        aggregate_id=EXECUTION_ID,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=occurred_at,
        payload={"execution_id": str(EXECUTION_ID), "status": "pending"},
    )


async def publish_event(
    database: PostgresRuntimeDatabase,
    event: EventEnvelope,
) -> None:
    async def _publish(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        await outbox.publish(event)
        return state

    await database.write(_publish)


def insert_outbox_event(
    connection: psycopg.Connection,
    event: EventEnvelope,
    *,
    published_at: datetime | None = None,
) -> None:
    row = event_to_row(event)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO runtime_outbox_events (
                event_id,
                event_type,
                schema_version,
                tenant_id,
                aggregate_id,
                aggregate_version,
                correlation_id,
                causation_id,
                occurred_at,
                payload,
                published_at
            )
            VALUES (
                %(event_id)s,
                %(event_type)s,
                %(schema_version)s,
                %(tenant_id)s,
                %(aggregate_id)s,
                %(aggregate_version)s,
                %(correlation_id)s,
                %(causation_id)s,
                %(occurred_at)s,
                %(payload)s,
                %(published_at)s
            )
            """,
            {
                **row,
                "published_at": published_at,
                "payload": Jsonb(row["payload"]),
            },
        )
    connection.commit()


@pytest_asyncio.fixture
async def runtime_database(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> AsyncIterator[PostgresRuntimeDatabase]:
    del postgres_connection
    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def relay_store(
    runtime_database: PostgresRuntimeDatabase,
) -> PostgresRuntimeOutboxRelayStore:
    return PostgresRuntimeOutboxRelayStore(runtime_database)


@pytest.mark.asyncio
async def test_fetch_unpublished_orders_by_occurred_at_then_event_id(
    relay_store: PostgresRuntimeOutboxRelayStore,
    runtime_database: PostgresRuntimeDatabase,
) -> None:
    later_occurred_smaller_id = make_event(
        EVENT_ID_EARLY,
        occurred_at=OCCURRED_AT_LATE,
    )
    earlier_occurred_larger_id = make_event(
        EVENT_ID_LATE,
        occurred_at=OCCURRED_AT_EARLY,
    )
    await publish_event(runtime_database, earlier_occurred_larger_id)
    await publish_event(runtime_database, later_occurred_smaller_id)

    fetched = await relay_store.fetch_unpublished(limit=10)

    assert [event.event_id for event in fetched] == [
        EVENT_ID_LATE,
        EVENT_ID_EARLY,
    ]


@pytest.mark.asyncio
async def test_mark_published_sets_published_at(
    relay_store: PostgresRuntimeOutboxRelayStore,
    runtime_database: PostgresRuntimeDatabase,
    postgres_connection: psycopg.Connection,
) -> None:
    event_1 = make_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY)
    event_2 = make_event(EVENT_ID_LATE, occurred_at=OCCURRED_AT_LATE)
    await publish_event(runtime_database, event_1)
    await publish_event(runtime_database, event_2)

    await relay_store.mark_published(
        event_ids=(EVENT_ID_EARLY, EVENT_ID_LATE),
        published_at=PUBLISHED_AT,
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, published_at
            FROM runtime_outbox_events
            WHERE event_id = ANY(%s::uuid[])
            ORDER BY event_id ASC
            """,
            ([EVENT_ID_EARLY.value, EVENT_ID_LATE.value],),
        )
        rows = cursor.fetchall()

    assert len(rows) == 2
    for _, published_at in rows:
        assert published_at == PUBLISHED_AT


@pytest.mark.asyncio
async def test_count_unpublished(
    relay_store: PostgresRuntimeOutboxRelayStore,
    runtime_database: PostgresRuntimeDatabase,
    postgres_connection: psycopg.Connection,
) -> None:
    await publish_event(
        runtime_database,
        make_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY),
    )
    await publish_event(
        runtime_database,
        make_event(EVENT_ID_LATE, occurred_at=OCCURRED_AT_LATE),
    )
    insert_outbox_event(
        postgres_connection,
        make_event(EVENT_ID_PUBLISHED, occurred_at=OCCURRED_AT_LATE),
        published_at=ALREADY_PUBLISHED_AT,
    )

    count = await relay_store.count_unpublished()

    assert count == 2


@pytest.mark.asyncio
async def test_fetch_unpublished_excludes_already_published_rows(
    relay_store: PostgresRuntimeOutboxRelayStore,
    runtime_database: PostgresRuntimeDatabase,
    postgres_connection: psycopg.Connection,
) -> None:
    unpublished = make_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY)
    published = make_event(EVENT_ID_PUBLISHED, occurred_at=OCCURRED_AT_LATE)
    await publish_event(runtime_database, unpublished)
    insert_outbox_event(
        postgres_connection,
        published,
        published_at=ALREADY_PUBLISHED_AT,
    )

    fetched = await relay_store.fetch_unpublished(limit=10)

    assert len(fetched) == 1
    assert fetched[0].event_id == EVENT_ID_EARLY
