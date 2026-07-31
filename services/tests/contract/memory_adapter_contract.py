"""Reusable behavioral contracts for memory persistence adapters.

The assertions in this module depend only on public memory ports and immutable
domain types. Adapter bindings supply construction plus read-only committed
state probes through :class:`MemoryAdapterHarness`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

import pytest

from engrammesh.modules.memory.domain.episode_cursor import encode_episode_cursor
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.memory.ports import (
    AppendResult,
    ClaimProposal,
    MemoryQuery,
    MemoryUnitOfWorkFactory,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
TENANT_B = TenantId(UUID("2cbd33ac-f165-4c30-8573-4d55c7e0462d"))
SUBJECT_A = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))
SUBJECT_B = SubjectId(UUID("ba183a68-1f3d-4a49-8537-85951929a044"))
ACTOR_ID = SubjectId(UUID("a00af086-f564-47af-8498-fad15464ff68"))
AGENT_ID = AgentInstanceId(
    UUID("9a1b0fc5-5fb6-4d9a-a5bf-e98a0841fa32")
)
CONTENT_REF = ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f"))
CORRELATION_ID = CorrelationId(
    UUID("7d0655d5-f3a5-488a-98e0-11763b4979dc")
)
OBSERVED_AT = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 27, 12, 1, tzinfo=UTC)


class MemoryAdapterHarness(Protocol):
    """Adapter construction and read-only probes used by contract assertions."""

    @property
    def unit_of_work_factory(self) -> MemoryUnitOfWorkFactory: ...

    @property
    def committed_episodes(self) -> tuple[Episode, ...]: ...

    @property
    def committed_events(self) -> tuple[EventEnvelope, ...]: ...


type MemoryAdapterHarnessFactory = Callable[[], MemoryAdapterHarness]
type MemoryAdapterContractAssertion = Callable[
    [MemoryAdapterHarnessFactory],
    Awaitable[None],
]

CONTRACT_TIMEOUT_SECONDS = 5.0


class AsyncStartBarrier:
    """Release asynchronous participants only after all have arrived."""

    __slots__ = ("_all_arrived", "_arrived", "_parties", "_release")

    def __init__(self, *, parties: int) -> None:
        if parties <= 0:
            raise ValueError("parties must be positive")
        self._parties = parties
        self._arrived = 0
        self._all_arrived = asyncio.Event()
        self._release = asyncio.Event()

    @property
    def arrived(self) -> int:
        return self._arrived

    async def arrive_and_wait(self) -> None:
        self._arrived += 1
        if self._arrived > self._parties:
            raise RuntimeError("too many start-barrier participants")
        if self._arrived == self._parties:
            self._all_arrived.set()
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            await self._release.wait()

    async def wait_until_full(self) -> None:
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            await self._all_arrived.wait()

    def release(self) -> None:
        self._release.set()


async def _cancel_and_drain_tasks[T](
    tasks: tuple[asyncio.Task[T], ...],
) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
        await asyncio.gather(*tasks, return_exceptions=True)


def memory_id(value: int) -> MemoryId:
    return MemoryId(UUID(int=value))


def event_id(value: int) -> EventId:
    return EventId(UUID(int=value))


def make_scope(
    *,
    tenant_id: TenantId = TENANT_A,
    subject_id: SubjectId = SUBJECT_A,
    workspace_id: str | None = "workspace-a",
    agent_id: AgentInstanceId | None = None,
) -> MemoryScope:
    return MemoryScope(
        tenant_id=tenant_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
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
        content_hash=f"sha256:{identifier:064x}",
        idempotency_key=idempotency_key or f"episode-{identifier}",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


def make_event(
    identifier: int,
    *,
    episode: Episode,
    event_type: str = "memory.episode-recorded",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id(identifier),
        event_type=event_type,
        schema_version=1,
        tenant_id=episode.scope.tenant_id,
        aggregate_id=episode.id,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=episode.ingested_at,
        payload={"episode_id": str(episode.id)},
    )


async def assert_first_append_get_and_stream(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    scope = make_scope()
    episode = make_episode(1, scope=scope)

    async with harness.unit_of_work_factory.create() as unit_of_work:
        result = await unit_of_work.episodes.append(episode)
        assert result.episode_id == episode.id
        assert result.created is True
        assert await unit_of_work.episodes.get(scope, episode.id) == episode
        assert await unit_of_work.episodes.stream(scope) == (episode,)
        await unit_of_work.commit()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        assert await unit_of_work.episodes.get(scope, episode.id) == episode
        assert await unit_of_work.episodes.stream(scope) == (episode,)

    assert harness.committed_episodes == (episode,)


async def assert_exact_scope_denial(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    scope = make_scope(agent_id=AGENT_ID)
    episode = make_episode(1, scope=scope)
    denied_scopes = (
        make_scope(tenant_id=TENANT_B, agent_id=AGENT_ID),
        make_scope(subject_id=SUBJECT_B, agent_id=AGENT_ID),
        make_scope(workspace_id="workspace-b", agent_id=AGENT_ID),
        make_scope(agent_id=None),
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.commit()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        for denied_scope in denied_scopes:
            assert (
                await unit_of_work.episodes.get(denied_scope, episode.id)
                is None
            )
            assert await unit_of_work.episodes.stream(denied_scope) == ()
        assert await unit_of_work.episodes.get(scope, memory_id(99)) is None


async def assert_exact_idempotent_replay(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    first = make_episode(1, idempotency_key="shared-key")
    replay = replace(
        first,
        id=memory_id(2),
        ingested_at=first.ingested_at + timedelta(hours=1),
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        first_result = await unit_of_work.episodes.append(first)
        await unit_of_work.commit()
    async with harness.unit_of_work_factory.create() as unit_of_work:
        replay_result = await unit_of_work.episodes.append(replay)
        await unit_of_work.commit()

    assert first_result.created is True
    assert replay_result.created is False
    assert replay_result.episode_id == first.id
    assert harness.committed_episodes == (first,)


async def assert_divergent_idempotency_conflicts(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    first = make_episode(1, idempotency_key="shared-key")
    variants = (
        replace(
            first,
            id=memory_id(2),
            scope=replace(first.scope, subject_id=SUBJECT_B),
        ),
        replace(
            first,
            id=memory_id(3),
            scope=replace(first.scope, workspace_id="workspace-b"),
        ),
        replace(
            first,
            id=memory_id(4),
            scope=replace(first.scope, agent_id=AGENT_ID),
        ),
        replace(first, id=memory_id(5), actor_id=SUBJECT_B),
        replace(first, id=memory_id(6), source_type=SourceType.AGENT),
        replace(
            first,
            id=memory_id(7),
            content_ref=ArtifactId(
                UUID("b41f7014-d39b-4d47-b5cb-4cef87111458")
            ),
        ),
        replace(
            first,
            id=memory_id(8),
            observed_at=first.observed_at + timedelta(seconds=1),
        ),
        replace(first, id=memory_id(9), content_hash="sha256:different"),
        replace(
            first,
            id=memory_id(10),
            sensitivity=Sensitivity.RESTRICTED,
        ),
        replace(
            first,
            id=memory_id(11),
            retention_class=RetentionClass.EXTENDED,
        ),
        replace(first, id=memory_id(12), consent_basis="legal_obligation"),
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(first)
        await unit_of_work.commit()

    for variant in variants:
        async with harness.unit_of_work_factory.create() as unit_of_work:
            with pytest.raises(EpisodeIdempotencyConflict) as raised:
                await unit_of_work.episodes.append(variant)
            assert raised.value.args == ()
            assert await unit_of_work.episodes.stream(first.scope) == (first,)
            await unit_of_work.commit()

    assert harness.committed_episodes == (first,)
    assert harness.committed_events == ()


async def assert_different_tenants_may_reuse_idempotency_key(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    first = make_episode(1, idempotency_key="shared-key")
    second = make_episode(
        2,
        scope=make_scope(tenant_id=TENANT_B),
        idempotency_key="shared-key",
    )

    for episode in (first, second):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            result = await unit_of_work.episodes.append(episode)
            assert result.episode_id == episode.id
            assert result.created is True
            await unit_of_work.commit()

    assert harness.committed_episodes == (first, second)


async def assert_outbox_publication_order(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    episode = make_episode(1)
    events = (
        make_event(1, episode=episode),
        make_event(2, episode=episode),
        make_event(3, episode=episode),
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        for event in events:
            await unit_of_work.outbox.publish(event)
        assert harness.committed_events == ()
        await unit_of_work.commit()

    assert harness.committed_events == events


async def assert_episode_outbox_requires_visible_matching_aggregate(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    committed = make_episode(1)
    staged = make_episode(2)
    unknown = make_episode(99)
    committed_event = make_event(1, episode=committed)
    staged_event = make_event(2, episode=staged)
    other_event = make_event(
        3,
        episode=unknown,
        event_type="memory.projection-requested",
    )

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(committed)
        await unit_of_work.commit()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.outbox.publish(committed_event)
        await unit_of_work.episodes.append(staged)
        await unit_of_work.outbox.publish(staged_event)

        with pytest.raises(
            ValueError,
            match="outbox episode event aggregate is unknown",
        ):
            await unit_of_work.outbox.publish(make_event(4, episode=unknown))
        with pytest.raises(
            ValueError,
            match="outbox event tenant does not match episode tenant",
        ):
            await unit_of_work.outbox.publish(
                replace(
                    make_event(5, episode=committed),
                    tenant_id=TENANT_B,
                )
            )

        await unit_of_work.outbox.publish(other_event)
        await unit_of_work.commit()

    assert harness.committed_episodes == (committed, staged)
    assert harness.committed_events == (
        committed_event,
        staged_event,
        other_event,
    )


async def assert_exit_without_commit_rolls_back(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    episode = make_episode(1)

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.outbox.publish(make_event(1, episode=episode))

    assert harness.committed_episodes == ()
    assert harness.committed_events == ()


async def assert_exception_after_episode_staging_rolls_back(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    episode = make_episode(1)

    with pytest.raises(RuntimeError, match="contract episode-stage failure"):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(episode)
            raise RuntimeError("contract episode-stage failure")

    assert harness.committed_episodes == ()
    assert harness.committed_events == ()


async def assert_exception_after_outbox_staging_rolls_back(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    episode = make_episode(1)

    with pytest.raises(RuntimeError, match="contract outbox-stage failure"):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(episode)
            await unit_of_work.outbox.publish(make_event(1, episode=episode))
            raise RuntimeError("contract outbox-stage failure")

    assert harness.committed_episodes == ()
    assert harness.committed_events == ()


async def assert_commit_persists_episode_and_outbox_atomically(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    episode = make_episode(1)
    event = make_event(1, episode=episode)

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(episode)
        await unit_of_work.outbox.publish(event)
        assert harness.committed_episodes == ()
        assert harness.committed_events == ()
        await unit_of_work.commit()

    assert harness.committed_episodes == (episode,)
    assert harness.committed_events == (event,)


async def assert_twenty_concurrent_duplicates_converge(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    barrier = AsyncStartBarrier(parties=20)
    first = make_episode(1, idempotency_key="shared-key")

    async def append(identifier: int) -> AppendResult:
        episode = replace(
            first,
            id=memory_id(identifier),
            ingested_at=first.ingested_at + timedelta(seconds=identifier),
        )
        event = make_event(identifier, episode=episode)
        await barrier.arrive_and_wait()
        async with harness.unit_of_work_factory.create() as unit_of_work:
            result = await unit_of_work.episodes.append(episode)
            if result.created:
                await unit_of_work.outbox.publish(event)
            await unit_of_work.commit()
        return result

    tasks = tuple(
        asyncio.create_task(append(value)) for value in range(1, 21)
    )
    try:
        await barrier.wait_until_full()
        assert barrier.arrived == 20
        assert all(task.done() is False for task in tasks)
        assert harness.committed_episodes == ()
        assert harness.committed_events == ()
        barrier.release()
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            results = await asyncio.gather(*tasks)
    finally:
        barrier.release()
        await _cancel_and_drain_tasks(tasks)

    assert sum(result.created for result in results) == 1
    assert len({result.episode_id for result in results}) == 1
    assert len(harness.committed_episodes) == 1
    assert len(harness.committed_events) == 1
    assert {result.episode_id for result in results} == {
        harness.committed_episodes[0].id
    }
    assert (
        harness.committed_events[0].aggregate_id
        == harness.committed_episodes[0].id
    )


async def assert_unit_of_work_is_single_use(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    unit_of_work = harness.unit_of_work_factory.create()

    for access in (
        lambda: unit_of_work.episodes,
        lambda: unit_of_work.claims,
        lambda: unit_of_work.outbox,
    ):
        with pytest.raises(RuntimeError):
            access()
    with pytest.raises(RuntimeError):
        await unit_of_work.commit()

    async with unit_of_work:
        held_store = unit_of_work.episodes
        with pytest.raises(RuntimeError):
            await unit_of_work.__aenter__()
        await unit_of_work.commit()
        with pytest.raises(RuntimeError):
            await unit_of_work.commit()

    with pytest.raises(RuntimeError):
        await unit_of_work.commit()
    with pytest.raises(RuntimeError):
        await held_store.stream(make_scope())
    with pytest.raises(RuntimeError):
        await unit_of_work.__aenter__()


async def assert_claim_operations_are_unavailable(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()

    async with harness.unit_of_work_factory.create() as unit_of_work:
        with pytest.raises(NotImplementedError):
            await unit_of_work.claims.add_proposal(
                cast(ClaimProposal, object())
            )
        with pytest.raises(NotImplementedError):
            await unit_of_work.claims.current(cast(MemoryQuery, object()))
        with pytest.raises(NotImplementedError):
            await unit_of_work.claims.history(make_scope(), memory_id(1))


async def assert_cursor_pagination_is_stable(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    scope = make_scope()
    async with harness.unit_of_work_factory.create() as unit_of_work:
        for index in range(3):
            await unit_of_work.episodes.append(make_episode(index))
        await unit_of_work.commit()
    async with harness.unit_of_work_factory.create() as unit_of_work:
        page_one = await unit_of_work.episodes.stream(scope, limit=2)
        assert len(page_one) == 2
        cursor = encode_episode_cursor(
            ingested_at=page_one[-1].ingested_at,
            episode_id=page_one[-1].id,
        )
        page_two = await unit_of_work.episodes.stream(
            scope, limit=2, cursor=cursor
        )
        assert len(page_two) == 1
        assert page_one[0].id != page_two[0].id


async def assert_cancellation_while_queued_releases_lock(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    staged = make_episode(1)
    persisted = make_episode(2)
    entry_attempted = asyncio.Event()
    waiter_entered = False

    async def wait_for_transaction() -> None:
        nonlocal waiter_entered
        unit_of_work = harness.unit_of_work_factory.create()
        entry_attempted.set()
        async with unit_of_work:
            waiter_entered = True

    async with harness.unit_of_work_factory.create() as holder:
        await holder.episodes.append(staged)
        waiting_task = asyncio.create_task(wait_for_transaction())
        try:
            async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
                await entry_attempted.wait()
            await asyncio.sleep(0)
            assert waiter_entered is False
            assert waiting_task.done() is False
            waiting_task.cancel()
            async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
                with pytest.raises(asyncio.CancelledError):
                    await waiting_task
        finally:
            await _cancel_and_drain_tasks((waiting_task,))

    async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(persisted)
            await unit_of_work.commit()

    assert harness.committed_episodes == (persisted,)
    assert harness.committed_events == ()


async def assert_cancellation_inside_transaction_rolls_back_and_releases_lock(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    staged = make_episode(1)
    persisted = make_episode(2)
    body_entered = asyncio.Event()
    never_set = asyncio.Event()

    async def stage_then_wait() -> None:
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(staged)
            await unit_of_work.outbox.publish(
                make_event(1, episode=staged)
            )
            body_entered.set()
            async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
                await never_set.wait()

    transaction_task = asyncio.create_task(stage_then_wait())
    try:
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            await body_entered.wait()
        transaction_task.cancel()
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            with pytest.raises(asyncio.CancelledError):
                await transaction_task
    finally:
        await _cancel_and_drain_tasks((transaction_task,))

    async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(persisted)
            await unit_of_work.commit()

    assert harness.committed_episodes == (persisted,)
    assert harness.committed_events == ()


async def assert_cancellation_after_commit_remains_and_releases_lock(
    make_harness: MemoryAdapterHarnessFactory,
) -> None:
    harness = make_harness()
    original = make_episode(1)
    committed = make_episode(2)
    persisted = make_episode(3)
    original_event = make_event(1, episode=original)
    committed_event = make_event(2, episode=committed)
    persisted_event = make_event(3, episode=persisted)

    async with harness.unit_of_work_factory.create() as unit_of_work:
        await unit_of_work.episodes.append(original)
        await unit_of_work.outbox.publish(original_event)
        await unit_of_work.commit()

    commit_finished = asyncio.Event()
    never_set = asyncio.Event()

    async def commit_then_wait() -> None:
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(committed)
            await unit_of_work.outbox.publish(committed_event)
            await unit_of_work.commit()
            commit_finished.set()
            async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
                await never_set.wait()

    transaction_task = asyncio.create_task(commit_then_wait())
    try:
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            await commit_finished.wait()
        assert harness.committed_episodes == (original, committed)
        assert harness.committed_events == (original_event, committed_event)
        transaction_task.cancel()
        async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
            with pytest.raises(asyncio.CancelledError):
                await transaction_task
    finally:
        await _cancel_and_drain_tasks((transaction_task,))

    assert harness.committed_episodes == (original, committed)
    assert harness.committed_events == (original_event, committed_event)

    async with asyncio.timeout(CONTRACT_TIMEOUT_SECONDS):
        async with harness.unit_of_work_factory.create() as unit_of_work:
            await unit_of_work.episodes.append(persisted)
            await unit_of_work.outbox.publish(persisted_event)
            await unit_of_work.commit()

    assert harness.committed_episodes == (original, committed, persisted)
    assert harness.committed_events == (
        original_event,
        committed_event,
        persisted_event,
    )


EPISODE_ADAPTER_CONTRACTS: tuple[
    tuple[str, MemoryAdapterContractAssertion],
    ...,
] = (
    ("first_append_get_stream", assert_first_append_get_and_stream),
    ("exact_scope_denial", assert_exact_scope_denial),
    ("exact_replay", assert_exact_idempotent_replay),
    ("divergent_idempotency_conflict", assert_divergent_idempotency_conflicts),
    (
        "different_tenant_same_key",
        assert_different_tenants_may_reuse_idempotency_key,
    ),
    ("outbox_order", assert_outbox_publication_order),
    (
        "episode_outbox_integrity",
        assert_episode_outbox_requires_visible_matching_aggregate,
    ),
    ("exit_without_commit", assert_exit_without_commit_rolls_back),
    (
        "exception_after_episode",
        assert_exception_after_episode_staging_rolls_back,
    ),
    (
        "exception_after_outbox",
        assert_exception_after_outbox_staging_rolls_back,
    ),
    ("commit_persistence", assert_commit_persists_episode_and_outbox_atomically),
    (
        "concurrent_duplicate_convergence",
        assert_twenty_concurrent_duplicates_converge,
    ),
    ("uow_single_use", assert_unit_of_work_is_single_use),
    (
        "cancel_inside_transaction",
        assert_cancellation_inside_transaction_rolls_back_and_releases_lock,
    ),
    (
        "cancel_after_commit",
        assert_cancellation_after_commit_remains_and_releases_lock,
    ),
)

IN_MEMORY_CAPABILITY_CONTRACTS: tuple[
    tuple[str, MemoryAdapterContractAssertion],
    ...,
] = (
    ("claims_unavailable", assert_claim_operations_are_unavailable),
    ("cursor_pagination", assert_cursor_pagination_is_stable),
    (
        "cancel_while_queued",
        assert_cancellation_while_queued_releases_lock,
    ),
)
