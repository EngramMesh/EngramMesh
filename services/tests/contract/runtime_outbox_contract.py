"""Reusable behavioral contracts for RuntimeOutboxRelayStore adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.ports import RuntimeOutboxPort, RuntimeOutboxRelayStore
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    ExecutionId,
    TenantId,
)

TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
CORRELATION_ID = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
EXECUTION_ID = ExecutionId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
EVENT_ID_EARLY = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
EVENT_ID_LATE = EventId(UUID("8fa7198e-8caa-5d3b-9bb6-00117cf4dc0a"))
EVENT_ID_PUBLISHED = EventId(UUID("9fb82a9f-9dbb-6e4c-acc7-11228d05ed1b"))
OCCURRED_AT_EARLY = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
OCCURRED_AT_LATE = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
ALREADY_PUBLISHED_AT = datetime(2026, 7, 27, 7, 0, tzinfo=UTC)

type RuntimeOutboxRelayHarnessFactory = Callable[[], Awaitable[RuntimeOutboxRelayHarness]]
type RuntimeOutboxContractAssertion = Callable[
    [RuntimeOutboxRelayHarnessFactory],
    Awaitable[None],
]


class RuntimeOutboxRelayHarness(Protocol):
    async def relay_store(self) -> RuntimeOutboxRelayStore: ...

    async def publish_unpublished(self, event: EventEnvelope) -> None: ...

    async def insert_published(
        self,
        event: EventEnvelope,
        *,
        published_at: datetime,
    ) -> None: ...

    async def published_at_for(self, event_id: EventId) -> datetime | None: ...

    async def close(self) -> None: ...


def contract_event(
    event_id: EventId,
    *,
    occurred_at: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type="runtime.execution-status-changed",
        schema_version=1,
        tenant_id=TENANT_ID,
        aggregate_id=EXECUTION_ID,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=occurred_at,
        payload={"execution_id": str(EXECUTION_ID), "status": "pending"},
    )


async def publish_via_in_memory_database(
    database: InMemoryRuntimeDatabase,
    event: EventEnvelope,
) -> None:
    async def _publish(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        await outbox.publish(event)
        return state

    await database.write(_publish)


class InMemoryRuntimeOutboxRelayStore:
    """Relay store backed by committed in-memory outbox events."""

    __slots__ = ("_database", "_published_at")

    def __init__(self, database: InMemoryRuntimeDatabase) -> None:
        self._database = database
        self._published_at: dict[EventId, datetime] = {}

    async def fetch_unpublished(self, *, limit: int) -> tuple[EventEnvelope, ...]:
        events = await self._database.read(lambda state: state.outbox_events)
        unpublished = [
            event
            for event in events
            if event.event_id not in self._published_at
        ]
        unpublished.sort(key=lambda event: (event.occurred_at, event.event_id.value))
        return tuple(unpublished[:limit])

    async def mark_published(
        self,
        *,
        event_ids: tuple[EventId, ...],
        published_at: datetime,
    ) -> None:
        for event_id in event_ids:
            self._published_at[event_id] = published_at

    async def count_unpublished(self) -> int:
        events = await self._database.read(lambda state: state.outbox_events)
        return sum(
            1 for event in events if event.event_id not in self._published_at
        )


class InMemoryRuntimeOutboxRelayHarness:
    """Harness binding relay contracts to the in-memory runtime database."""

    __slots__ = ("_database", "_relay_store")

    def __init__(self) -> None:
        self._database = InMemoryRuntimeDatabase()
        self._relay_store = InMemoryRuntimeOutboxRelayStore(self._database)

    async def relay_store(self) -> RuntimeOutboxRelayStore:
        return self._relay_store

    async def publish_unpublished(self, event: EventEnvelope) -> None:
        await publish_via_in_memory_database(self._database, event)

    async def insert_published(
        self,
        event: EventEnvelope,
        *,
        published_at: datetime,
    ) -> None:
        await publish_via_in_memory_database(self._database, event)
        await self._relay_store.mark_published(
            event_ids=(event.event_id,),
            published_at=published_at,
        )

    async def published_at_for(self, event_id: EventId) -> datetime | None:
        return self._relay_store._published_at.get(event_id)

    async def close(self) -> None:
        return None


async def assert_fetch_unpublished_orders_by_occurred_at_then_event_id(
    make_harness: RuntimeOutboxRelayHarnessFactory,
) -> None:
    harness = await make_harness()
    try:
        relay_store = await harness.relay_store()
        await harness.publish_unpublished(
            contract_event(EVENT_ID_LATE, occurred_at=OCCURRED_AT_EARLY)
        )
        await harness.publish_unpublished(
            contract_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_LATE)
        )
        fetched = await relay_store.fetch_unpublished(limit=10)
        assert [event.event_id for event in fetched] == [EVENT_ID_LATE, EVENT_ID_EARLY]
    finally:
        await harness.close()


async def assert_mark_published_sets_published_at(
    make_harness: RuntimeOutboxRelayHarnessFactory,
) -> None:
    harness = await make_harness()
    try:
        relay_store = await harness.relay_store()
        await harness.publish_unpublished(
            contract_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY)
        )
        await harness.publish_unpublished(
            contract_event(EVENT_ID_LATE, occurred_at=OCCURRED_AT_LATE)
        )
        await relay_store.mark_published(
            event_ids=(EVENT_ID_EARLY, EVENT_ID_LATE),
            published_at=PUBLISHED_AT,
        )
        assert await harness.published_at_for(EVENT_ID_EARLY) == PUBLISHED_AT
        assert await harness.published_at_for(EVENT_ID_LATE) == PUBLISHED_AT
    finally:
        await harness.close()


async def assert_count_unpublished(
    make_harness: RuntimeOutboxRelayHarnessFactory,
) -> None:
    harness = await make_harness()
    try:
        relay_store = await harness.relay_store()
        await harness.publish_unpublished(
            contract_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY)
        )
        await harness.publish_unpublished(
            contract_event(EVENT_ID_LATE, occurred_at=OCCURRED_AT_LATE)
        )
        await harness.insert_published(
            contract_event(EVENT_ID_PUBLISHED, occurred_at=OCCURRED_AT_LATE),
            published_at=ALREADY_PUBLISHED_AT,
        )
        assert await relay_store.count_unpublished() == 2
    finally:
        await harness.close()


async def assert_fetch_unpublished_excludes_already_published_rows(
    make_harness: RuntimeOutboxRelayHarnessFactory,
) -> None:
    harness = await make_harness()
    try:
        relay_store = await harness.relay_store()
        await harness.publish_unpublished(
            contract_event(EVENT_ID_EARLY, occurred_at=OCCURRED_AT_EARLY)
        )
        await harness.insert_published(
            contract_event(EVENT_ID_PUBLISHED, occurred_at=OCCURRED_AT_LATE),
            published_at=ALREADY_PUBLISHED_AT,
        )
        fetched = await relay_store.fetch_unpublished(limit=10)
        assert len(fetched) == 1
        assert fetched[0].event_id == EVENT_ID_EARLY
    finally:
        await harness.close()


RUNTIME_OUTBOX_CONTRACTS: tuple[
    tuple[str, RuntimeOutboxContractAssertion],
    ...,
] = (
    (
        "fetch_unpublished_orders_by_occurred_at_then_event_id",
        assert_fetch_unpublished_orders_by_occurred_at_then_event_id,
    ),
    ("mark_published_sets_published_at", assert_mark_published_sets_published_at),
    ("count_unpublished", assert_count_unpublished),
    (
        "fetch_unpublished_excludes_already_published_rows",
        assert_fetch_unpublished_excludes_already_published_rows,
    ),
)
