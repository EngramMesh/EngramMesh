"""Integration tests for composed Inbox consumer via AppRuntime."""

from __future__ import annotations

import psycopg
import pytest
from test_outbox_relay_composed import (
    FailingOutboxEventPublisher,
    PublishFailure,
    make_command,
    make_settings,
)

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.infrastructure import InboxOutboxEventPublisher
from engrammesh.bootstrap.settings import AppSettings, Environment


def count_inbox_events(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_inbox_events")
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def make_settings_inbox_disabled(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
            "inbox": {"enabled": False},
        }
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_runtime_records_relays_and_writes_inbox_row(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command(idempotency_key="inbox-composed-first")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        result = await runtime.relay_outbox_once()

    assert result.fetched == 1
    assert result.dispatched == 1
    assert result.published == 1
    assert count_inbox_events(postgres_connection) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_double_publish_dedupes_inbox_row(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command(idempotency_key="inbox-double-publish")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        await runtime.relay_outbox_once()
        event = runtime.logging_outbox_event_publisher.published[0]

        await runtime.outbox_event_publisher.publish(event)
        duplicate_result = await runtime.process_inbox_handler().handle(event)

    assert count_inbox_events(postgres_connection) == 1
    assert duplicate_result.processed is False
    assert duplicate_result.skipped is True


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_relay_retry_after_publish_failure_dedupes_inbox(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command(idempotency_key="inbox-relay-retry")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)

        failing_delegate = FailingOutboxEventPublisher(fail_on_index=1)
        runtime._outbox_publisher = InboxOutboxEventPublisher(
            inbox_handler=runtime.process_inbox_handler(),
            delegate=failing_delegate,
        )
        runtime._relay_handler = None

        with pytest.raises(PublishFailure, match="publish failed on second event"):
            await runtime.relay_outbox_once()

        assert failing_delegate.publish_calls == 1
        assert count_inbox_events(postgres_connection) == 1

        runtime._outbox_publisher = InboxOutboxEventPublisher(
            inbox_handler=runtime.process_inbox_handler(),
            delegate=runtime.logging_outbox_event_publisher,
        )
        runtime._relay_handler = None

        retry_result = await runtime.relay_outbox_once()

    assert retry_result.fetched == 1
    assert retry_result.dispatched == 1
    assert retry_result.published == 1
    assert count_inbox_events(postgres_connection) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_inbox_disabled_skips_inbox_writes(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings_inbox_disabled(postgres_dsn)
    command = make_command(idempotency_key="inbox-disabled")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        result = await runtime.relay_outbox_once()

    assert result.published == 1
    assert count_inbox_events(postgres_connection) == 0
