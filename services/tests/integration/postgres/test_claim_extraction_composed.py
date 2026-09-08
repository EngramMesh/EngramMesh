"""Integration tests for claim extraction via composed inbox path."""

from __future__ import annotations

import psycopg
import pytest
from test_outbox_relay_composed import make_command, make_settings

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import AppSettings, Environment


def count_claim_proposals(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_claim_proposals")
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def count_inbox_events(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_inbox_events")
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def make_settings_claim_extraction_disabled(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
            "claim_extraction": {"enabled": False},
        }
    )


def count_claim_proposed_outbox_events(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM memory_outbox_events
            WHERE event_type = 'memory.claim-proposed'
            """
        )
        row = cursor.fetchone()
        assert row is not None
        return row[0]


def count_unpublished_claim_proposed_outbox_events(
    connection: psycopg.Connection,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM memory_outbox_events
            WHERE event_type = 'memory.claim-proposed'
              AND published_at IS NULL
            """
        )
        row = cursor.fetchone()
        assert row is not None
        return row[0]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_record_relay_inbox_persists_claim_proposal_and_outbox_event(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command(idempotency_key="claim-proposed-outbox-first")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        await runtime.relay_outbox_once()

        assert count_claim_proposals(postgres_connection) == 1
        assert count_claim_proposed_outbox_events(postgres_connection) == 1
        assert count_unpublished_claim_proposed_outbox_events(postgres_connection) == 1

        await runtime.relay_outbox_once()

        published = [
            event
            for event in runtime.logging_outbox_event_publisher.published
            if event.event_type == "memory.claim-proposed"
        ]
        assert len(published) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_duplicate_inbox_delivery_does_not_duplicate_claims(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command(idempotency_key="claim-extraction-dedup")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        await runtime.relay_outbox_once()
        event = runtime.logging_outbox_event_publisher.published[0]
        duplicate_result = await runtime.process_inbox_handler().handle(event)

    assert count_claim_proposals(postgres_connection) == 1
    assert count_claim_proposed_outbox_events(postgres_connection) == 1
    assert duplicate_result.processed is False
    assert duplicate_result.skipped is True


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_claim_extraction_disabled_skips_persistence(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings_claim_extraction_disabled(postgres_dsn)
    command = make_command(idempotency_key="claim-extraction-disabled")

    async with create_runtime(settings) as runtime:
        await runtime.record_episode_handler().handle(command)
        await runtime.relay_outbox_once()

    assert count_claim_proposals(postgres_connection) == 0
    assert count_inbox_events(postgres_connection) == 1
