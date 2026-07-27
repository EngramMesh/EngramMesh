import asyncio
import inspect
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest

from engrammesh.modules.memory import adapters
from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.memory.ports import (
    ClaimProposal,
    ClaimStore,
    EpisodeStore,
    MemoryQuery,
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

TENANT_A = TenantId(UUID("725a5253-f2d9-409d-bd1a-0af9b9297df2"))
TENANT_B = TenantId(UUID("7cfaea82-fc64-4f73-a8cd-11b4a234980d"))
SUBJECT_A = SubjectId(UUID("49c29202-7e63-4813-8a2c-b956c4c2983d"))
SUBJECT_B = SubjectId(UUID("3a5bc1d8-25b2-42f7-a6bd-54a2c7e27d23"))
ACTOR_ID = SubjectId(UUID("b0d94ed4-69de-40e1-b813-377c81e741ea"))
CONTENT_REF = ArtifactId(UUID("612b2367-b392-4f2b-83a7-e4c6ed84060b"))
CORRELATION_ID = CorrelationId(
    UUID("5a0ea6ae-68bd-4799-9f22-574094400e8f")
)
OBSERVED_AT = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 27, 9, 1, tzinfo=UTC)


def memory_id(value: int) -> MemoryId:
    return MemoryId(UUID(int=value))


def event_id(value: int) -> EventId:
    return EventId(UUID(int=value))


def make_scope(
    *,
    tenant_id: TenantId = TENANT_A,
    subject_id: SubjectId = SUBJECT_A,
    workspace_id: str | None = "workspace-a",
) -> MemoryScope:
    return MemoryScope(
        tenant_id=tenant_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
    )


def make_episode(
    identifier: int,
    *,
    scope: MemoryScope | None = None,
    idempotency_key: str | None = None,
) -> Episode:
    return Episode(
        id=memory_id(identifier),
        scope=scope or make_scope(),
        actor_id=ACTOR_ID,
        source_type=SourceType.USER,
        content_ref=CONTENT_REF,
        observed_at=OBSERVED_AT,
        ingested_at=INGESTED_AT,
        content_hash=f"sha256:{identifier}",
        idempotency_key=idempotency_key or f"episode-{identifier}",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


def make_event(
    identifier: int,
    *,
    aggregate_id: MemoryId,
    tenant_id: TenantId = TENANT_A,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id(identifier),
        event_type="memory.episode-recorded",
        schema_version=1,
        tenant_id=tenant_id,
        aggregate_id=aggregate_id,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=INGESTED_AT,
        payload={"episode_id": str(aggregate_id)},
    )


def public_methods(value: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(value, inspect.isfunction)
        if not name.startswith("_")
    }


def test_adapter_package_has_exact_public_exports() -> None:
    assert adapters.__all__ == [
        "InMemoryMemoryDatabase",
        "InMemoryMemoryUnitOfWorkFactory",
    ]
    assert public_methods(InMemoryMemoryDatabase) == set()
    assert public_methods(InMemoryMemoryUnitOfWorkFactory) == {"create"}


def test_database_exposes_only_read_only_tuple_snapshots() -> None:
    database = InMemoryMemoryDatabase()

    assert database.episodes == ()
    assert database.events == ()
    assert not hasattr(database, "__dict__")
    with pytest.raises(AttributeError):
        database.episodes = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        database.events = ()  # type: ignore[misc]


def test_factory_and_transaction_adapters_conform_to_ports() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    unit_of_work = factory.create()

    assert isinstance(factory, MemoryUnitOfWorkFactory)
    assert isinstance(unit_of_work, MemoryUnitOfWork)


@pytest.mark.asyncio
async def test_commit_atomically_publishes_staged_episode_and_event() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episode = make_episode(1)
    event = make_event(1, aggregate_id=episode.id)

    async with factory.create() as unit_of_work:
        assert isinstance(unit_of_work.episodes, EpisodeStore)
        assert isinstance(unit_of_work.claims, ClaimStore)
        assert isinstance(unit_of_work.outbox, OutboxPort)
        result = await unit_of_work.episodes.append(episode)
        await unit_of_work.outbox.publish(event)
        assert database.episodes == ()
        assert database.events == ()
        await unit_of_work.commit()

    assert result.episode_id == episode.id
    assert result.created is True
    assert database.episodes == (episode,)
    assert database.events == (event,)


@pytest.mark.asyncio
async def test_exit_without_commit_discards_real_staged_state() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episode = make_episode(1)

    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.outbox.publish(
            make_event(1, aggregate_id=episode.id)
        )

    assert database.episodes == ()
    assert database.events == ()


@pytest.mark.asyncio
async def test_exception_after_commit_restores_exact_original_state() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    original_episode = make_episode(1)
    original_event = make_event(1, aggregate_id=original_episode.id)
    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(original_episode)
        await unit_of_work.outbox.publish(original_event)
        await unit_of_work.commit()

    original_episode_snapshot = database.episodes
    original_event_snapshot = database.events
    staged_episode = make_episode(2)

    with pytest.raises(RuntimeError, match="application failure"):
        async with factory.create() as unit_of_work:
            await unit_of_work.episodes.append(staged_episode)
            await unit_of_work.outbox.publish(
                make_event(2, aggregate_id=staged_episode.id)
            )
            await unit_of_work.commit()
            raise RuntimeError("application failure")

    assert database.episodes is original_episode_snapshot
    assert database.events is original_event_snapshot


@pytest.mark.asyncio
async def test_idempotency_is_scoped_to_exact_tenant_and_keeps_first_id() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    first = make_episode(1, idempotency_key="shared-key")
    same_tenant_duplicate = make_episode(2, idempotency_key="shared-key")
    other_tenant = make_episode(
        3,
        scope=make_scope(tenant_id=TENANT_B),
        idempotency_key="shared-key",
    )

    async with factory.create() as unit_of_work:
        first_result = await unit_of_work.episodes.append(first)
        duplicate_result = await unit_of_work.episodes.append(
            same_tenant_duplicate
        )
        other_tenant_result = await unit_of_work.episodes.append(other_tenant)
        await unit_of_work.commit()

    assert first_result.created is True
    assert duplicate_result.episode_id == first.id
    assert duplicate_result.created is False
    assert other_tenant_result.episode_id == other_tenant.id
    assert other_tenant_result.created is True
    assert database.episodes == (first, other_tenant)


@pytest.mark.asyncio
async def test_get_and_stream_require_the_exact_memory_scope() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    scope = make_scope()
    same_tenant_other_subject = make_scope(subject_id=SUBJECT_B)
    same_subject_other_workspace = make_scope(workspace_id="workspace-b")
    first = make_episode(1, scope=scope)
    second = make_episode(2, scope=scope)
    hidden = make_episode(3, scope=same_tenant_other_subject)

    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(first)
        await unit_of_work.episodes.append(hidden)
        await unit_of_work.episodes.append(second)
        await unit_of_work.commit()

    async with factory.create() as unit_of_work:
        assert await unit_of_work.episodes.get(scope, first.id) == first
        assert (
            await unit_of_work.episodes.get(
                same_tenant_other_subject,
                first.id,
            )
            is None
        )
        assert (
            await unit_of_work.episodes.get(
                same_subject_other_workspace,
                first.id,
            )
            is None
        )
        assert await unit_of_work.episodes.stream(scope) == (first, second)
        with pytest.raises(
            ValueError,
            match="in-memory episode cursors are unavailable",
        ):
            await unit_of_work.episodes.stream(scope, cursor="next")


@pytest.mark.asyncio
async def test_lifecycle_misuse_raises_static_runtime_errors() -> None:
    database = InMemoryMemoryDatabase()
    unit_of_work = InMemoryMemoryUnitOfWorkFactory(database).create()

    for access in (
        lambda: unit_of_work.episodes,
        lambda: unit_of_work.claims,
        lambda: unit_of_work.outbox,
    ):
        with pytest.raises(
            RuntimeError,
            match="memory transaction is not active",
        ):
            access()
    with pytest.raises(RuntimeError, match="memory transaction is not active"):
        await unit_of_work.commit()

    async with unit_of_work:
        episode_store = unit_of_work.episodes
        with pytest.raises(
            RuntimeError,
            match="memory transaction cannot be entered more than once",
        ):
            await unit_of_work.__aenter__()
        await unit_of_work.commit()
        with pytest.raises(
            RuntimeError,
            match="memory transaction has already been committed",
        ):
            await unit_of_work.commit()

    with pytest.raises(RuntimeError, match="memory transaction is not active"):
        await unit_of_work.commit()
    with pytest.raises(RuntimeError, match="memory transaction is not active"):
        await episode_store.stream(make_scope())


@pytest.mark.asyncio
async def test_claim_store_is_explicitly_unavailable() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)

    async with factory.create() as unit_of_work:
        claims = unit_of_work.claims
        with pytest.raises(
            NotImplementedError,
            match="in-memory claim store is unavailable",
        ):
            await claims.add_proposal(cast(ClaimProposal, object()))
        with pytest.raises(
            NotImplementedError,
            match="in-memory claim store is unavailable",
        ):
            await claims.current(cast(MemoryQuery, object()))
        with pytest.raises(
            NotImplementedError,
            match="in-memory claim store is unavailable",
        ):
            await claims.history(make_scope(), memory_id(1))


@pytest.mark.asyncio
async def test_outbox_preserves_order_and_enforces_correlated_tenant() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episode = make_episode(1)
    first = make_event(1, aggregate_id=episode.id)
    second = make_event(2, aggregate_id=episode.id)
    uncorrelated = make_event(
        3,
        aggregate_id=memory_id(99),
        tenant_id=TENANT_B,
    )
    mismatched = make_event(
        4,
        aggregate_id=episode.id,
        tenant_id=TENANT_B,
    )

    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.outbox.publish(first)
        await unit_of_work.outbox.publish(second)
        await unit_of_work.outbox.publish(uncorrelated)
        with pytest.raises(
            ValueError,
            match="outbox event tenant does not match episode tenant",
        ):
            await unit_of_work.outbox.publish(mismatched)
        await unit_of_work.commit()

    assert database.events == (first, second, uncorrelated)


@pytest.mark.asyncio
async def test_outbox_does_not_correlate_against_committed_episodes() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    episode = make_episode(1)
    async with factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()
    event = make_event(
        1,
        aggregate_id=episode.id,
        tenant_id=TENANT_B,
    )

    async with factory.create() as unit_of_work:
        await unit_of_work.outbox.publish(event)
        await unit_of_work.commit()

    assert database.events == (event,)


@pytest.mark.asyncio
async def test_transactions_serialize_concurrent_writers() -> None:
    database = InMemoryMemoryDatabase()
    factory = InMemoryMemoryUnitOfWorkFactory(database)
    entered: list[int] = []

    async def append(identifier: int) -> None:
        async with factory.create() as unit_of_work:
            entered.append(identifier)
            await asyncio.sleep(0)
            await unit_of_work.episodes.append(make_episode(identifier))
            await unit_of_work.commit()

    await asyncio.gather(append(1), append(2), append(3))

    assert entered == [1, 2, 3]
    assert database.episodes == (
        make_episode(1),
        make_episode(2),
        make_episode(3),
    )
