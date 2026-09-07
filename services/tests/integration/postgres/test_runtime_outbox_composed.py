"""Integration tests for composed runtime outbox relay via AppRuntime."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.application.contracts import StartExecutionCommand
from engrammesh.modules.runtime.domain.model import Budget
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT_ID = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
OBJECTIVE_REF = ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86"))
ROOT_AGENT_ID = AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
CORRELATION_ID = CorrelationId(UUID("02ffae84-2764-41f3-a22a-4d4652a7c139"))
BUDGET_DEADLINE = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class PublishFailure(RuntimeError):
    pass


class FailingRuntimeOutboxEventPublisher:
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


def make_settings(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )


def make_start_command(
    *,
    idempotency_key: str = "composed-runtime-relay-1",
    correlation_id: CorrelationId = CORRELATION_ID,
) -> StartExecutionCommand:
    return StartExecutionCommand(
        correlation_id=correlation_id,
        actor_id=ACTOR_ID,
        scope=MemoryScope(
            tenant_id=TENANT_A,
            subject_id=SUBJECT_ID,
            workspace_id="workspace-42",
        ),
        objective_ref=OBJECTIVE_REF,
        root_agent_id=ROOT_AGENT_ID,
        memory_query=None,
        budget=Budget(1000, 500, 100_000, BUDGET_DEADLINE),
        idempotency_key=idempotency_key,
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_start_relay_publishes_status_changed_event(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)

    async with create_runtime(settings) as runtime:
        result = await runtime.start_execution_handler().handle(make_start_command())
        assert result.created is True
        relay = await runtime.relay_runtime_outbox_once()
        assert relay.published == 1
        published = runtime.logging_runtime_outbox_event_publisher.published
        assert len(published) == 1
        assert published[0].payload["status"] == "pending"

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT published_at FROM runtime_outbox_events WHERE published_at IS NOT NULL"
        )
        assert len(cursor.fetchall()) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_idempotent_start_relay_publishes_nothing_on_replay(
    postgres_dsn: str,
) -> None:
    settings = make_settings(postgres_dsn)

    async with create_runtime(settings) as runtime:
        handler = runtime.start_execution_handler()
        await handler.handle(make_start_command())
        first_relay = await runtime.relay_runtime_outbox_once()
        publisher = runtime.logging_runtime_outbox_event_publisher
        publisher_length = len(publisher.published)

        await handler.handle(
            replace(
                make_start_command(),
                correlation_id=CorrelationId(UUID(int=99)),
            )
        )
        second_relay = await runtime.relay_runtime_outbox_once()

        assert first_relay.published == 1
        assert second_relay.fetched == 0
        assert second_relay.published == 0
        assert len(publisher.published) == publisher_length


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_relay_mid_batch_failure_does_not_mark_published(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    first_command = make_start_command(idempotency_key="runtime-relay-failure-first")
    second_command = make_start_command(idempotency_key="runtime-relay-failure-second")

    async with create_runtime(settings) as runtime:
        handler = runtime.start_execution_handler()
        await handler.handle(first_command)
        await handler.handle(second_command)

        failing_publisher = FailingRuntimeOutboxEventPublisher(fail_on_index=2)
        runtime._logging_runtime_outbox_publisher = failing_publisher
        runtime._runtime_relay_handler = None

        with pytest.raises(PublishFailure, match="publish failed on second event"):
            await runtime.relay_runtime_outbox_once()

        assert failing_publisher.publish_calls == 2
        assert len(failing_publisher.published) == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM runtime_outbox_events WHERE published_at IS NULL"
        )
        assert cursor.fetchone()[0] == 2


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unpublished_row_survives_runtime_database_restart(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = make_settings(postgres_dsn)
    runtime = create_runtime(settings)
    await runtime.startup()
    try:
        await runtime.start_execution_handler().handle(make_start_command())
        database = runtime._runtime_database
        assert isinstance(database, PostgresRuntimeDatabase)
        await database.close()
        await database.open()
        relay = await runtime.relay_runtime_outbox_once()
        assert relay.published == 1
    finally:
        await runtime.shutdown()

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM runtime_outbox_events WHERE published_at IS NOT NULL"
        )
        assert cursor.fetchone()[0] == 1
