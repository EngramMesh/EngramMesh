from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.contracts import ListEpisodesQuery
from engrammesh.modules.memory.application.errors import EpisodeReadAuthorizationDenied
from engrammesh.modules.memory.application.list_episodes import ListEpisodesHandler
from engrammesh.modules.memory.domain.errors import InvalidEpisodeCursor
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.memory.ports import AuthorizationRequest
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
EPISODE_IDS = (
    MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db")),
    MemoryId(UUID("940ddfba-f834-486b-b918-bbb87a6bf9db")),
    MemoryId(UUID("a40ddfba-f834-486b-b918-bbb87a6bf9db")),
)
BASE_INGESTED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


@dataclass
class RecordingAuthorization:
    calls: list[str] = field(default_factory=list)
    allowed: bool = True

    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append("authorize")
        return self.allowed


def make_scope() -> MemoryScope:
    return MemoryScope(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
    )


def make_episode(index: int) -> Episode:
    return Episode(
        id=EPISODE_IDS[index],
        scope=make_scope(),
        actor_id=ACTOR,
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")),
        observed_at=BASE_INGESTED_AT + timedelta(minutes=index),
        ingested_at=BASE_INGESTED_AT + timedelta(minutes=index),
        content_hash=f"sha256:episode-{index}",
        idempotency_key=f"episode-{index}",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


@pytest.mark.asyncio
async def test_list_returns_items_and_next_cursor() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episodes = [make_episode(i) for i in range(3)]
    async with factory.create() as unit_of_work:
        for episode in episodes:
            await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()
    handler = ListEpisodesHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    first_page = await handler.handle(
        ListEpisodesQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=2,
        )
    )
    assert first_page.items == tuple(episodes[:2])
    assert first_page.next_cursor is not None
    second_page = await handler.handle(
        ListEpisodesQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=2,
            cursor=first_page.next_cursor,
        )
    )
    assert second_page.items == (episodes[2],)
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_list_empty_scope_returns_empty() -> None:
    factory = InMemoryMemoryUnitOfWorkFactory(InMemoryMemoryDatabase())
    handler = ListEpisodesHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    result = await handler.handle(
        ListEpisodesQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=10,
        )
    )
    assert result.items == ()
    assert result.next_cursor is None


def test_list_rejects_limit_over_100() -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        ListEpisodesQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=101,
        )


@pytest.mark.asyncio
async def test_list_unauthorized_raises() -> None:
    authorization = RecordingAuthorization(allowed=False)
    factory = InMemoryMemoryUnitOfWorkFactory(InMemoryMemoryDatabase())
    handler = ListEpisodesHandler(
        authorization=authorization,
        unit_of_work_factory=factory,
    )
    with pytest.raises(EpisodeReadAuthorizationDenied):
        await handler.handle(
            ListEpisodesQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
            )
        )
    assert authorization.calls == ["authorize"]


@pytest.mark.asyncio
async def test_list_invalid_cursor_propagates() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(make_episode(0))
        await unit_of_work.commit()
    handler = ListEpisodesHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    with pytest.raises(InvalidEpisodeCursor):
        await handler.handle(
            ListEpisodesQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
                cursor="bad",
            )
        )
