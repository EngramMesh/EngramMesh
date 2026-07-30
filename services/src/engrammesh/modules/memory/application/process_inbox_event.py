"""Application orchestration for durable inbox event consumption."""

from collections.abc import Sequence
from typing import final

from engrammesh.modules.memory.application.contracts import ProcessInboxEventResult
from engrammesh.modules.memory.ports import (
    ClockPort,
    InboxEventProcessor,
    InboxStore,
)
from engrammesh.shared.kernel.events import EventEnvelope


@final
class ProcessInboxEventHandler:
    """Route relay-dispatched events through inbox dedup and processors."""

    def __init__(
        self,
        *,
        store: InboxStore,
        processors: Sequence[InboxEventProcessor],
        consumer_name: str,
        clock: ClockPort,
    ) -> None:
        self._store = store
        self._processors = tuple(processors)
        self._consumer_name = consumer_name
        self._clock = clock

    async def handle(self, event: EventEnvelope) -> ProcessInboxEventResult:
        processor = self._processor_for(event.event_type)
        if processor is None:
            return ProcessInboxEventResult(processed=False, skipped=True)

        processed_at = await self._clock.now()
        recorded = await self._store.try_record(
            event_id=event.event_id,
            consumer_name=self._consumer_name,
            event_type=event.event_type,
            tenant_id=event.tenant_id,
            processed_at=processed_at,
        )
        if not recorded:
            return ProcessInboxEventResult(processed=False, skipped=True)

        try:
            await processor.process(event)
        except Exception:
            await self._store.remove_record(event_id=event.event_id)
            raise

        return ProcessInboxEventResult(processed=True, skipped=False)

    def _processor_for(self, event_type: str) -> InboxEventProcessor | None:
        for processor in self._processors:
            if processor.supports(event_type):
                return processor
        return None
