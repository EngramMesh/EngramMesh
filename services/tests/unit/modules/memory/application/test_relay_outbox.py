from datetime import UTC, datetime
from typing import Never
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.contracts import RelayOutboxCommand
from engrammesh.modules.memory.application.relay_outbox import RelayOutboxEventsHandler
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

CORRELATION_ID = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
EVENT_ID_1 = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
EVENT_ID_2 = EventId(UUID("8fa7198e-8caa-5d3b-9bb6-00117cf4dc0a"))
EPISODE_ID = MemoryId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
SUBJECT_ID = SubjectId(UUID("436b95a8-df23-4d6e-8200-d2058ad62d86"))
TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
OCCURRED_AT = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


class AdapterFailure(RuntimeError):
    pass


class FixedClock:
    def __init__(
        self,
        calls: list[str],
        *,
        value: datetime = PUBLISHED_AT,
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.value = value
        self.error = error
        self.call_count = 0

    async def now(self) -> datetime:
        self.calls.append("clock.now")
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.value


def make_event(event_id: EventId) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type="memory.episode-recorded",
        schema_version=1,
        tenant_id=TENANT_ID,
        aggregate_id=EPISODE_ID,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=OCCURRED_AT,
        payload={"episode_id": str(EPISODE_ID)},
    )


class RecordingRelayStore:
    def __init__(
        self,
        calls: list[str],
        *,
        events: tuple[EventEnvelope, ...] = (),
        remaining: int = 0,
        fetch_error: BaseException | None = None,
        mark_error: BaseException | None = None,
        count_error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.events = events
        self.remaining = remaining
        self.fetch_error = fetch_error
        self.mark_error = mark_error
        self.count_error = count_error
        self.marked_event_ids: list[tuple[EventId, ...]] = []
        self.marked_published_at: list[datetime] = []
        self.mark_call_count = 0

    async def fetch_unpublished(self, *, limit: int) -> tuple[EventEnvelope, ...]:
        self.calls.append(f"store.fetch_unpublished:{limit}")
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.events

    async def mark_published(
        self,
        *,
        event_ids: tuple[EventId, ...],
        published_at: datetime,
    ) -> None:
        self.calls.append("store.mark_published")
        self.mark_call_count += 1
        if self.mark_error is not None:
            raise self.mark_error
        self.marked_event_ids.append(event_ids)
        self.marked_published_at.append(published_at)

    async def count_unpublished(self) -> int:
        self.calls.append("store.count_unpublished")
        if self.count_error is not None:
            raise self.count_error
        return self.remaining


class RecordingEventPublisher:
    def __init__(
        self,
        calls: list[str],
        *,
        fail_on_index: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.fail_on_index = fail_on_index
        self.error = error
        self.published: list[EventEnvelope] = []
        self.publish_call_count = 0

    async def publish(self, event: EventEnvelope) -> None:
        self.calls.append("publisher.publish")
        self.publish_call_count += 1
        if self.error is not None:
            raise self.error
        if self.fail_on_index is not None and (
            self.publish_call_count == self.fail_on_index
        ):
            raise AdapterFailure("publish")
        self.published.append(event)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


@pytest.mark.asyncio
async def test_empty_batch_returns_zeros_and_remaining_count() -> None:
    calls: list[str] = []
    store = RecordingRelayStore(calls, remaining=3)
    handler = RelayOutboxEventsHandler(
        clock=MustNotBeUsed(),
        store=store,
        publisher=MustNotBeUsed(),
    )

    result = await handler.handle(RelayOutboxCommand(batch_size=10))

    assert result.fetched == 0
    assert result.dispatched == 0
    assert result.published == 0
    assert result.remaining_unpublished == 3
    assert calls == ["store.fetch_unpublished:10", "store.count_unpublished"]


@pytest.mark.asyncio
async def test_full_batch_dispatches_marks_and_returns_counts() -> None:
    calls: list[str] = []
    event_1 = make_event(EVENT_ID_1)
    event_2 = make_event(EVENT_ID_2)
    store = RecordingRelayStore(
        calls,
        events=(event_1, event_2),
        remaining=0,
    )
    clock = FixedClock(calls)
    publisher = RecordingEventPublisher(calls)
    handler = RelayOutboxEventsHandler(
        clock=clock,
        store=store,
        publisher=publisher,
    )

    result = await handler.handle(RelayOutboxCommand(batch_size=10))

    assert result.fetched == 2
    assert result.dispatched == 2
    assert result.published == 2
    assert result.remaining_unpublished == 0
    assert publisher.published == [event_1, event_2]
    assert store.mark_call_count == 1
    assert store.marked_event_ids == [(EVENT_ID_1, EVENT_ID_2)]
    assert store.marked_published_at == [PUBLISHED_AT]
    assert clock.call_count == 1
    assert calls == [
        "store.fetch_unpublished:10",
        "clock.now",
        "publisher.publish",
        "publisher.publish",
        "store.mark_published",
        "store.count_unpublished",
    ]


@pytest.mark.asyncio
async def test_publish_failure_reraises_without_marking() -> None:
    calls: list[str] = []
    event_1 = make_event(EVENT_ID_1)
    event_2 = make_event(EVENT_ID_2)
    store = RecordingRelayStore(
        calls,
        events=(event_1, event_2),
        remaining=2,
    )
    clock = FixedClock(calls)
    publisher = RecordingEventPublisher(calls, fail_on_index=2)
    handler = RelayOutboxEventsHandler(
        clock=clock,
        store=store,
        publisher=publisher,
    )

    with pytest.raises(AdapterFailure) as raised:
        await handler.handle(RelayOutboxCommand(batch_size=10))

    assert raised.value.args == ("publish",)
    assert publisher.publish_call_count == 2
    assert publisher.published == [event_1]
    assert store.mark_call_count == 0
    assert clock.call_count == 1
    assert calls == [
        "store.fetch_unpublished:10",
        "clock.now",
        "publisher.publish",
        "publisher.publish",
    ]
