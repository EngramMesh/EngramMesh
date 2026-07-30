"""Application orchestration for relaying unpublished outbox events."""

from typing import final

from engrammesh.modules.memory.application.contracts import (
    RelayOutboxCommand,
    RelayOutboxResult,
)
from engrammesh.modules.memory.ports import (
    ClockPort,
    OutboxEventPublisher,
    OutboxRelayStore,
)


@final
class RelayOutboxEventsHandler:
    """Poll unpublished outbox events, dispatch, and mark published."""

    def __init__(
        self,
        *,
        clock: ClockPort,
        store: OutboxRelayStore,
        publisher: OutboxEventPublisher,
    ) -> None:
        self._clock = clock
        self._store = store
        self._publisher = publisher

    async def handle(self, command: RelayOutboxCommand) -> RelayOutboxResult:
        events = await self._store.fetch_unpublished(limit=command.batch_size)
        if not events:
            remaining = await self._store.count_unpublished()
            return RelayOutboxResult(
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
        return RelayOutboxResult(
            fetched=len(events),
            dispatched=dispatched,
            published=len(events),
            remaining_unpublished=remaining,
        )
