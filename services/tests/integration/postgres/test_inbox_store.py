"""Integration tests for PostgresInboxStore."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
import pytest_asyncio

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.inbox_store import (
    PostgresInboxStore,
)
from engrammesh.shared.kernel.ids import EventId, TenantId

pytestmark = pytest.mark.postgres

TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
EVENT_ID = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
OTHER_EVENT_ID = EventId(UUID("8fa7198e-8caa-5d3b-9bb6-00117cf4dc0a"))
PROCESSED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
CONSUMER_NAME = "episode-recorded-v1"
EVENT_TYPE = "memory.episode-recorded"


@pytest_asyncio.fixture
async def postgres_database(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> AsyncIterator[PostgresMemoryDatabase]:
    del postgres_connection
    database = PostgresMemoryDatabase(postgres_dsn)
    await database.open()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def inbox_store(
    postgres_database: PostgresMemoryDatabase,
) -> PostgresInboxStore:
    return PostgresInboxStore(postgres_database)


def fetch_inbox_row(
    connection: psycopg.Connection,
    event_id: EventId,
) -> tuple[UUID, str, str, UUID, datetime] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, consumer_name, event_type, tenant_id, processed_at
            FROM memory_inbox_events
            WHERE event_id = %s
            """,
            (event_id.value,),
        )
        return cursor.fetchone()


@pytest.mark.asyncio
async def test_try_record_inserts_new_event(
    inbox_store: PostgresInboxStore,
    postgres_connection: psycopg.Connection,
) -> None:
    recorded = await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )

    assert recorded is True
    row = fetch_inbox_row(postgres_connection, EVENT_ID)
    assert row is not None
    event_id, consumer_name, event_type, tenant_id, processed_at = row
    assert event_id == EVENT_ID.value
    assert consumer_name == CONSUMER_NAME
    assert event_type == EVENT_TYPE
    assert tenant_id == TENANT_ID.value
    assert processed_at == PROCESSED_AT


@pytest.mark.asyncio
async def test_try_record_returns_false_for_duplicate_event_id(
    inbox_store: PostgresInboxStore,
    postgres_connection: psycopg.Connection,
) -> None:
    first = await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )
    second = await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name="other-consumer",
        event_type="other.event",
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )

    assert first is True
    assert second is False
    row = fetch_inbox_row(postgres_connection, EVENT_ID)
    assert row is not None
    _, consumer_name, event_type, _, _ = row
    assert consumer_name == CONSUMER_NAME
    assert event_type == EVENT_TYPE


@pytest.mark.asyncio
async def test_remove_record_deletes_row(
    inbox_store: PostgresInboxStore,
    postgres_connection: psycopg.Connection,
) -> None:
    await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )

    await inbox_store.remove_record(event_id=EVENT_ID)

    assert fetch_inbox_row(postgres_connection, EVENT_ID) is None


@pytest.mark.asyncio
async def test_remove_record_allows_retry_after_processor_failure(
    inbox_store: PostgresInboxStore,
    postgres_connection: psycopg.Connection,
) -> None:
    await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )
    await inbox_store.remove_record(event_id=EVENT_ID)

    retried = await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )

    assert retried is True
    assert fetch_inbox_row(postgres_connection, EVENT_ID) is not None


@pytest.mark.asyncio
async def test_try_record_allows_distinct_event_ids(
    inbox_store: PostgresInboxStore,
    postgres_connection: psycopg.Connection,
) -> None:
    first = await inbox_store.try_record(
        event_id=EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )
    second = await inbox_store.try_record(
        event_id=OTHER_EVENT_ID,
        consumer_name=CONSUMER_NAME,
        event_type=EVENT_TYPE,
        tenant_id=TENANT_ID,
        processed_at=PROCESSED_AT,
    )

    assert first is True
    assert second is True
    assert fetch_inbox_row(postgres_connection, EVENT_ID) is not None
    assert fetch_inbox_row(postgres_connection, OTHER_EVENT_ID) is not None
