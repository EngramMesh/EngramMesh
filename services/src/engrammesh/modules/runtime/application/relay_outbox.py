"""Application orchestration for relaying unpublished runtime outbox events."""

from typing import final

from engrammesh.modules.runtime.application.contracts import (
    RelayRuntimeOutboxCommand,
    RelayRuntimeOutboxResult,
)
from engrammesh.modules.runtime.ports import (
    ClockPort,
    RuntimeOutboxEventPublisher,
    RuntimeOutboxRelayStore,
)


@final
class RelayRuntimeOutboxEventsHandler:
    """Poll unpublished runtime outbox events, dispatch, and mark published."""

    def __init__(
        self,
        *,
        clock: ClockPort,
        store: RuntimeOutboxRelayStore,
        publisher: RuntimeOutboxEventPublisher,
    ) -> None:
        self._clock = clock
        self._store = store
        self._publisher = publisher

    async def handle(
        self, command: RelayRuntimeOutboxCommand
    ) -> RelayRuntimeOutboxResult:
        events = await self._store.fetch_unpublished(limit=command.batch_size)
        if not events:
            remaining = await self._store.count_unpublished()
            return RelayRuntimeOutboxResult(
                fetched=0,
                dispatched=0,
                published=0,
                remaining_unpublished=remaining,
            )
        published_at = await self._clock.now()
        dispatched = 0
        for event in events:
            await self._publisher.publish(event)
            dispatched += 1
        await self._store.mark_published(
            event_ids=tuple(event.event_id for event in events),
            published_at=published_at,
        )
        remaining = await self._store.count_unpublished()
        return RelayRuntimeOutboxResult(
            fetched=len(events),
            dispatched=dispatched,
            published=len(events),
            remaining_unpublished=remaining,
        )
