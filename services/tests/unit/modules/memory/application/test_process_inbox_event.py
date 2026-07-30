from datetime import UTC, datetime
from typing import Never
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.process_inbox_event import (
    ProcessInboxEventHandler,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

CONSUMER_NAME = "episode-recorded-v1"
CORRELATION_ID = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
EVENT_ID = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
EPISODE_ID = MemoryId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
SUBJECT_ID = SubjectId(UUID("436b95a8-df23-4d6e-8200-d2058ad62d86"))
TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
OCCURRED_AT = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
PROCESSED_AT = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


class ProcessorFailure(RuntimeError):
    pass


class FixedClock:
    def __init__(
        self,
        calls: list[str],
        *,
        value: datetime = PROCESSED_AT,
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


def make_event(
    *,
    event_type: str = "memory.episode-recorded",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=EVENT_ID,
        event_type=event_type,
        schema_version=1,
        tenant_id=TENANT_ID,
        aggregate_id=EPISODE_ID,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=OCCURRED_AT,
        payload={"episode_id": str(EPISODE_ID)},
    )


class RecordingInboxStore:
    def __init__(
        self,
        calls: list[str],
        *,
        try_record_result: bool = True,
        try_record_error: BaseException | None = None,
        remove_error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.try_record_result = try_record_result
        self.try_record_error = try_record_error
        self.remove_error = remove_error
        self.try_record_kwargs: list[dict[str, object]] = []
        self.remove_event_ids: list[EventId] = []
        self.try_record_call_count = 0
        self.remove_call_count = 0

    async def try_record(
        self,
        *,
        event_id: EventId,
        consumer_name: str,
        event_type: str,
        tenant_id: TenantId,
        processed_at: datetime,
    ) -> bool:
        self.calls.append("store.try_record")
        self.try_record_call_count += 1
        if self.try_record_error is not None:
            raise self.try_record_error
        self.try_record_kwargs.append(
            {
                "event_id": event_id,
                "consumer_name": consumer_name,
                "event_type": event_type,
                "tenant_id": tenant_id,
                "processed_at": processed_at,
            }
        )
        return self.try_record_result

    async def remove_record(self, *, event_id: EventId) -> None:
        self.calls.append("store.remove_record")
        self.remove_call_count += 1
        if self.remove_error is not None:
            raise self.remove_error
        self.remove_event_ids.append(event_id)


class RecordingProcessor:
    def __init__(
        self,
        calls: list[str],
        *,
        supported_types: tuple[str, ...] = ("memory.episode-recorded",),
        process_error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.supported_types = supported_types
        self.process_error = process_error
        self.processed_events: list[EventEnvelope] = []
        self.process_call_count = 0

    def supports(self, event_type: str) -> bool:
        self.calls.append(f"processor.supports:{event_type}")
        return event_type in self.supported_types

    async def process(self, event: EventEnvelope) -> None:
        self.calls.append("processor.process")
        self.process_call_count += 1
        if self.process_error is not None:
            raise self.process_error
        self.processed_events.append(event)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


def make_handler(
    calls: list[str],
    *,
    store: RecordingInboxStore | None = None,
    processor: RecordingProcessor | None = None,
    consumer_name: str = CONSUMER_NAME,
    clock: FixedClock | None = None,
) -> ProcessInboxEventHandler:
    return ProcessInboxEventHandler(
        store=store if store is not None else RecordingInboxStore(calls),
        processors=(processor if processor is not None else RecordingProcessor(calls),),
        consumer_name=consumer_name,
        clock=clock if clock is not None else FixedClock(calls),
    )


@pytest.mark.asyncio
async def test_unsupported_event_type_skips_without_store() -> None:
    calls: list[str] = []
    store = RecordingInboxStore(calls)
    handler = make_handler(calls, store=store)

    result = await handler.handle(make_event(event_type="memory.other-event"))

    assert result.processed is False
    assert result.skipped is True
    assert store.try_record_call_count == 0
    assert calls == ["processor.supports:memory.other-event"]


@pytest.mark.asyncio
async def test_duplicate_try_record_skips_without_processing() -> None:
    calls: list[str] = []
    store = RecordingInboxStore(calls, try_record_result=False)
    processor = RecordingProcessor(calls)
    handler = make_handler(calls, store=store, processor=processor)

    result = await handler.handle(make_event())

    assert result.processed is False
    assert result.skipped is True
    assert processor.process_call_count == 0
    assert store.try_record_call_count == 1
    assert calls == [
        "processor.supports:memory.episode-recorded",
        "clock.now",
        "store.try_record",
    ]


@pytest.mark.asyncio
async def test_new_record_and_successful_process() -> None:
    calls: list[str] = []
    event = make_event()
    store = RecordingInboxStore(calls)
    processor = RecordingProcessor(calls)
    handler = make_handler(calls, store=store, processor=processor)

    result = await handler.handle(event)

    assert result.processed is True
    assert result.skipped is False
    assert processor.processed_events == [event]
    assert store.try_record_call_count == 1
    assert store.remove_call_count == 0
    assert calls == [
        "processor.supports:memory.episode-recorded",
        "clock.now",
        "store.try_record",
        "processor.process",
    ]


@pytest.mark.asyncio
async def test_processor_failure_removes_record_and_reraises() -> None:
    calls: list[str] = []
    store = RecordingInboxStore(calls)
    processor = RecordingProcessor(calls, process_error=ProcessorFailure("process"))
    handler = make_handler(calls, store=store, processor=processor)

    with pytest.raises(ProcessorFailure) as raised:
        await handler.handle(make_event())

    assert raised.value.args == ("process",)
    assert store.remove_call_count == 1
    assert store.remove_event_ids == [EVENT_ID]
    assert processor.process_call_count == 1
    assert calls == [
        "processor.supports:memory.episode-recorded",
        "clock.now",
        "store.try_record",
        "processor.process",
        "store.remove_record",
    ]


@pytest.mark.asyncio
async def test_try_record_receives_consumer_name_from_handler_config() -> None:
    calls: list[str] = []
    store = RecordingInboxStore(calls)
    handler = make_handler(calls, store=store, consumer_name="custom-consumer")

    await handler.handle(make_event())

    assert store.try_record_kwargs == [
        {
            "event_id": EVENT_ID,
            "consumer_name": "custom-consumer",
            "event_type": "memory.episode-recorded",
            "tenant_id": TENANT_ID,
            "processed_at": PROCESSED_AT,
        }
    ]
