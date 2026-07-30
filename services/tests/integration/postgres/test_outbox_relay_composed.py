"""Integration tests for composed Outbox Relay via AppRuntime."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT_ID = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
CONTENT_REF = ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86"))
CORRELATION_ID = CorrelationId(UUID("02ffae84-2764-41f3-a22a-4d4652a7c139"))
OBSERVED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


class PublishFailure(RuntimeError):
    pass


class FailingOutboxEventPublisher:
    """Publisher that fails on a configured dispatch index."""

    __slots__ = ("_fail_on_index", "_published", "publish_calls")

    def __init__(self, *, fail_on_index: int) -> None:
        self._fail_on_index = fail_on_index
        self._published: list[EventEnvelope] = []
        self.publish_calls = 0

    @property
    def published(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._published)

    async def publish(self, event: EventEnvelope) -> None:
        self.publish_calls += 1
        if self.publish_calls == self._fail_on_index:
            raise PublishFailure("publish failed on second event")
        self._published.append(event)


def make_command(
    *,
    idempotency_key: str = "composed-relay-episode-42",
) -> RecordEpisodeCommand:
    return RecordEpisodeCommand(
        correlation_id=CORRELATION_ID,
        actor_id=ACTOR_ID,
        scope=MemoryScope(
            tenant_id=TENANT_A,
            subject_id=SUBJECT_ID,
            workspace_id="workspace-42",
        ),
        source_type=SourceType.USER,
        content_ref=CONTENT_REF,
        observed_at=OBSERVED_AT,
        content_hash="sha256:88c7355c",
        idempotency_key=idempotency_key,
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


def make_settings(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_runtime_records_and_relays_episode_event(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    command = make_command()

    async with create_runtime(settings) as runtime:
        publisher = runtime.logging_outbox_event_publisher
        await runtime.record_episode_handler().handle(command)
        result = await runtime.relay_outbox_once()
        published_events = publisher.published

    assert result.fetched == 1
    assert result.dispatched == 1
    assert result.published == 1
    assert len(published_events) == 1
    assert published_events[0].event_type == "memory.episode-recorded"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT published_at FROM memory_outbox_events WHERE published_at IS NOT NULL"
        )
        rows = cursor.fetchall()
    assert len(rows) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_replay_ingest_then_relay_publishes_nothing(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    settings = make_settings(postgres_dsn)
    command = make_command()

    async with create_runtime(settings) as runtime:
        handler = runtime.record_episode_handler()
        await handler.handle(command)
        first_relay = await runtime.relay_outbox_once()
        publisher = runtime.logging_outbox_event_publisher
        publisher_length = len(publisher.published)

        await handler.handle(
            replace(command, correlation_id=CorrelationId(UUID(int=99)))
        )
        second_relay = await runtime.relay_outbox_once()

        assert first_relay.published == 1
        assert second_relay.fetched == 0
        assert second_relay.published == 0
        assert len(publisher.published) == publisher_length


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_publish_failure_leaves_published_at_null(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    first_command = make_command(idempotency_key="relay-failure-first")
    second_command = make_command(idempotency_key="relay-failure-second")

    async with create_runtime(settings) as runtime:
        handler = runtime.record_episode_handler()
        await handler.handle(first_command)
        await handler.handle(second_command)

        failing_publisher = FailingOutboxEventPublisher(fail_on_index=2)
        runtime._outbox_publisher = failing_publisher
        runtime._relay_handler = None

        with pytest.raises(PublishFailure, match="publish failed on second event"):
            await runtime.relay_outbox_once()

        assert failing_publisher.publish_calls == 2
        assert len(failing_publisher.published) == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM memory_outbox_events WHERE published_at IS NULL"
        )
        assert cursor.fetchone()[0] == 2
