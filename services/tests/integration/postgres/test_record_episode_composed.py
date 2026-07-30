"""Integration tests for composed RecordEpisodeHandler via AppRuntime."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.application.errors import EpisodeAuthorizationDenied
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
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


def make_command(
    *,
    idempotency_key: str = "composed-episode-42",
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


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_runtime_records_episode_and_outbox(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )
    command = make_command()

    async with create_runtime(settings) as runtime:
        result = await runtime.record_episode_handler().handle(command)

    assert result.created is True
    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_episodes")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM memory_outbox_events")
        assert cursor.fetchone()[0] == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_runtime_replay_does_not_duplicate_outbox(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )
    command = make_command()

    async with create_runtime(settings) as runtime:
        handler = runtime.record_episode_handler()
        first = await handler.handle(command)
        replay = await handler.handle(
            replace(command, correlation_id=CorrelationId(UUID(int=99)))
        )

    assert first.created is True
    assert replay.created is False
    assert replay.episode_id == first.episode_id
    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_episodes")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM memory_outbox_events")
        assert cursor.fetchone()[0] == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_composed_runtime_denies_staging_authorization(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = AppSettings.model_validate(
        {
            "environment": Environment.STAGING,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "staging", "task_queue": "staging"},
        }
    )
    async with create_runtime(settings) as runtime:
        with pytest.raises(EpisodeAuthorizationDenied):
            await runtime.record_episode_handler().handle(make_command())

    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_episodes")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM memory_outbox_events")
        assert cursor.fetchone()[0] == 0
