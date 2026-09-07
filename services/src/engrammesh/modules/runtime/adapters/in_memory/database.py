"""Committed in-memory state for durable execution snapshots and idempotency."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from types import MappingProxyType
from typing import TypeVar, final

from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import (
    CommittedRuntimeState,
    empty_runtime_state,
)
from engrammesh.shared.kernel.events import EventEnvelope

_T = TypeVar("_T")


class _BufferingRuntimeOutbox:
    """Collect outbox events until an in-memory write commits."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self._events.append(event)

    def buffered_events(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._events)


@final
class InMemoryRuntimeDatabase:
    """Own committed execution snapshots and start-idempotency indexes."""

    __slots__ = ("_lock", "_state")

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = empty_runtime_state()

    async def read(self, callback: Callable[[CommittedRuntimeState], _T]) -> _T:
        """Run *callback* against the current committed state under the lock."""
        async with self._lock:
            return callback(self._state)

    async def write(
        self,
        callback: Callable[
            [CommittedRuntimeState, RuntimeOutboxPort],
            Awaitable[CommittedRuntimeState],
        ],
    ) -> None:
        """Atomically replace committed state with *callback*'s result."""
        async with self._lock:
            outbox = _BufferingRuntimeOutbox()
            result = await callback(self._state, outbox)
            self._state = replace(
                result,
                outbox_events=result.outbox_events + outbox.buffered_events(),
            )

    def replace_snapshot_for_tests(self, snapshot: ExecutionSnapshot) -> None:
        """Replace one snapshot synchronously for adapter unit tests only."""
        committed = self._state
        snapshots = dict(committed.snapshots)
        snapshots[snapshot.execution_id] = snapshot
        self._state = replace(
            committed,
            snapshots=MappingProxyType(snapshots),
        )


ExecutionIndex = InMemoryRuntimeDatabase
