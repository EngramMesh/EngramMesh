"""Committed in-memory state for durable execution snapshots and idempotency."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from types import MappingProxyType
from typing import TypeVar, final

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.domain.execution_cursor import (
    decode_execution_cursor,
)
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

    async def stream(
        self,
        scope: MemoryScope,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> tuple[ExecutionSnapshot, ...]:
        if cursor is not None and limit is None:
            msg = "cursor requires limit"
            raise ValueError(msg)
        if limit is not None and limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)

        async with self._lock:
            rows = [
                snapshot
                for snapshot in self._state.snapshots.values()
                if snapshot.scope == scope
            ]

        rows.sort(
            key=lambda snapshot: (snapshot.updated_at, snapshot.execution_id.value),
            reverse=True,
        )

        if cursor is not None:
            cursor_at, cursor_id = decode_execution_cursor(cursor)
            cursor_key = (cursor_at, cursor_id.value)
            rows = [
                snapshot
                for snapshot in rows
                if (snapshot.updated_at, snapshot.execution_id.value) < cursor_key
            ]

        if limit is not None:
            rows = rows[:limit]
        return tuple(rows)


ExecutionIndex = InMemoryRuntimeDatabase
