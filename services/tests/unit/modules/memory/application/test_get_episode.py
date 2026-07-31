from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Never
from uuid import UUID

import pytest

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.contracts import GetEpisodeQuery
from engrammesh.modules.memory.application.errors import (
    EpisodeNotFound,
    EpisodeReadAuthorizationDenied,
)
from engrammesh.modules.memory.application.get_episode import GetEpisodeHandler
from engrammesh.modules.memory.domain.model import (
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
EPISODE_ID = MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db"))


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


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


def make_episode() -> object:
    from engrammesh.modules.memory.domain.model import Episode

    return Episode(
        id=EPISODE_ID,
        scope=make_scope(),
        actor_id=ACTOR,
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")),
        observed_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 7, 27, 10, 1, tzinfo=UTC),
        content_hash="sha256:88c7355c",
        idempotency_key="episode-42",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


@pytest.mark.asyncio
async def test_get_episode_returns_episode_when_found() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episode = make_episode()
    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()
    handler = GetEpisodeHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    result = await handler.handle(
        GetEpisodeQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            episode_id=EPISODE_ID,
        )
    )
    assert result.episode == episode


@pytest.mark.asyncio
async def test_get_episode_raises_not_found() -> None:
    factory = InMemoryMemoryUnitOfWorkFactory(InMemoryMemoryDatabase())
    handler = GetEpisodeHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    with pytest.raises(EpisodeNotFound):
        await handler.handle(
            GetEpisodeQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                episode_id=EPISODE_ID,
            )
        )


@pytest.mark.asyncio
async def test_get_episode_denial_authorizes_first_and_accesses_nothing_else() -> None:
    authorization = RecordingAuthorization(allowed=False)
    handler = GetEpisodeHandler(
        authorization=authorization,
        unit_of_work_factory=MustNotBeUsed(),
    )
    with pytest.raises(EpisodeReadAuthorizationDenied):
        await handler.handle(
            GetEpisodeQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                episode_id=EPISODE_ID,
            )
        )
    assert authorization.calls == ["authorize"]
