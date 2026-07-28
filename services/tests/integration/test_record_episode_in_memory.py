import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID

import pytest

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.application.record_episode import (
    RecordEpisodeHandler,
)
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    ClaimStore,
    EpisodeStore,
    MemoryUnitOfWork,
    MemoryUnitOfWorkFactory,
    OutboxPort,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
TENANT_B = TenantId(UUID("e63173e8-8f03-4f34-beac-2020676684c0"))
SUBJECT_ID = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
CONTENT_REF = ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86"))
CORRELATION_ID = CorrelationId(
    UUID("02ffae84-2764-41f3-a22a-4d4652a7c139")
)
OBSERVED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 27, 10, 1, tzinfo=UTC)


class AdapterFailure(RuntimeError):
    pass


class AllowingAuthorization:
    async def authorize(self, request: AuthorizationRequest) -> bool:
        return True


class FixedClock:
    async def now(self) -> datetime:
        return INGESTED_AT


class SequentialIdentities:
    def __init__(self) -> None:
        self._memory_id = 0
        self._event_id = 1000

    async def new_memory_id(self) -> MemoryId:
        self._memory_id += 1
        return MemoryId(UUID(int=self._memory_id))

    async def new_event_id(self) -> EventId:
        self._event_id += 1
        return EventId(UUID(int=self._event_id))


class FaultInjectingOutbox:
    def __init__(
        self,
        wrapped: OutboxPort,
        *,
        after_publish: bool,
    ) -> None:
        self._wrapped = wrapped
        self._after_publish = after_publish

    async def publish(self, event: EventEnvelope) -> None:
        if not self._after_publish:
            raise AdapterFailure("injected outbox failure")
        await self._wrapped.publish(event)
        raise AdapterFailure("injected outbox failure")


class FaultInjectingUnitOfWork:
    def __init__(
        self,
        wrapped: MemoryUnitOfWork,
        *,
        after_publish: bool,
    ) -> None:
        self._wrapped = wrapped
        self._after_publish = after_publish
        self._outbox: FaultInjectingOutbox | None = None

    async def __aenter__(self) -> Self:
        await self._wrapped.__aenter__()
        self._outbox = FaultInjectingOutbox(
            self._wrapped.outbox,
            after_publish=self._after_publish,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._wrapped.__aexit__(exc_type, exc_value, traceback)

    @property
    def episodes(self) -> EpisodeStore:
        return self._wrapped.episodes

    @property
    def claims(self) -> ClaimStore:
        return self._wrapped.claims

    @property
    def outbox(self) -> OutboxPort:
        if self._outbox is None:
            raise RuntimeError("fault-injecting transaction is not active")
        return self._outbox

    async def commit(self) -> None:
        await self._wrapped.commit()


class FaultInjectingFactory:
    def __init__(
        self,
        wrapped: MemoryUnitOfWorkFactory,
        *,
        after_publish: bool,
    ) -> None:
        self._wrapped = wrapped
        self._after_publish = after_publish

    def create(self) -> MemoryUnitOfWork:
        return FaultInjectingUnitOfWork(
            self._wrapped.create(),
            after_publish=self._after_publish,
        )


def make_command(
    *,
    tenant_id: TenantId = TENANT_A,
    idempotency_key: str = "episode-42",
) -> RecordEpisodeCommand:
    return RecordEpisodeCommand(
        correlation_id=CORRELATION_ID,
        actor_id=ACTOR_ID,
        scope=MemoryScope(
            tenant_id=tenant_id,
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


def make_handler(
    factory: MemoryUnitOfWorkFactory,
) -> RecordEpisodeHandler:
    return RecordEpisodeHandler(
        authorization=AllowingAuthorization(),
        clock=FixedClock(),
        identities=SequentialIdentities(),
        unit_of_work_factory=factory,
    )


@pytest.mark.asyncio
async def test_real_handler_first_write_replay_and_tenant_reuse() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    handler = make_handler(factory)
    command = make_command()

    first = await handler.handle(command)
    replay = await handler.handle(command)
    other_tenant = await handler.handle(
        replace(command, scope=replace(command.scope, tenant_id=TENANT_B))
    )

    assert first.created is True
    assert replay.episode_id == first.episode_id
    assert replay.created is False
    assert other_tenant.created is True
    assert other_tenant.episode_id != first.episode_id
    assert len(database.episodes) == 2
    assert [episode.scope.tenant_id for episode in database.episodes] == [
        TENANT_A,
        TENANT_B,
    ]
    assert len(database.events) == 2
    assert [event.tenant_id for event in database.events] == [
        TENANT_A,
        TENANT_B,
    ]


@pytest.mark.asyncio
async def test_real_handler_replays_with_new_correlation_without_new_event(
) -> None:
    database = InMemoryMemoryDatabase()
    handler = make_handler(InMemoryMemoryUnitOfWorkFactory(database))
    command = make_command()
    retry_correlation_id = CorrelationId(
        UUID("171a1c4e-502b-47d0-abca-a95cd4f8fe0b")
    )

    first = await handler.handle(command)
    replay = await handler.handle(
        replace(command, correlation_id=retry_correlation_id)
    )

    assert first.created is True
    assert replay.episode_id == first.episode_id
    assert replay.created is False
    assert len(database.episodes) == 1
    assert len(database.events) == 1
    assert database.events[0].correlation_id == command.correlation_id
    assert database.events[0].correlation_id != retry_correlation_id


@pytest.mark.asyncio
@pytest.mark.parametrize("after_publish", [False, True])
async def test_real_handler_rolls_back_staged_episode_and_outbox(
    *,
    after_publish: bool,
) -> None:
    database = InMemoryMemoryDatabase()
    real_factory = InMemoryMemoryUnitOfWorkFactory(database)
    faulting_factory = FaultInjectingFactory(
        real_factory,
        after_publish=after_publish,
    )
    handler = make_handler(faulting_factory)

    with pytest.raises(AdapterFailure, match="injected outbox failure"):
        await handler.handle(make_command())

    assert database.episodes == ()
    assert database.events == ()
    retry = await make_handler(real_factory).handle(make_command())
    assert retry.created is True
    assert len(database.episodes) == 1
    assert len(database.events) == 1
    assert database.events[0].aggregate_id == database.episodes[0].id


@pytest.mark.asyncio
async def test_concurrent_duplicate_commands_converge_through_real_handler(
) -> None:
    database = InMemoryMemoryDatabase()
    handler = make_handler(InMemoryMemoryUnitOfWorkFactory(database))
    command = make_command()

    results = await asyncio.gather(
        *(handler.handle(command) for _ in range(20))
    )

    assert sum(result.created for result in results) == 1
    assert {result.episode_id for result in results} == {
        database.episodes[0].id
    }
    assert len(database.episodes) == 1
    assert len(database.events) == 1
    assert database.events[0].tenant_id == TENANT_A
