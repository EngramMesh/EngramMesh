"""Committed in-memory state owned by the memory adapter."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from engrammesh.modules.memory.domain.model import Episode
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import MemoryId, TenantId

type _IdempotencyIndex = Mapping[tuple[TenantId, str], MemoryId]


@dataclass(frozen=True, slots=True)
class _CommittedMemoryState:
    episodes: tuple[Episode, ...]
    idempotency_index: _IdempotencyIndex
    events: tuple[EventEnvelope, ...]


def _empty_state() -> _CommittedMemoryState:
    return _CommittedMemoryState(
        episodes=(),
        idempotency_index=MappingProxyType({}),
        events=(),
    )


@final
class InMemoryMemoryDatabase:
    """Own committed memory records behind immutable snapshots."""

    __slots__ = ("_lock", "_state")

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = _empty_state()

    @property
    def episodes(self) -> tuple[Episode, ...]:
        """Return the current committed Episodes in insertion order."""
        return self._state.episodes

    @property
    def events(self) -> tuple[EventEnvelope, ...]:
        """Return the current committed Outbox events in publication order."""
        return self._state.events

    def _snapshot(self) -> _CommittedMemoryState:
        return self._state

    def _replace(
        self,
        *,
        episodes: list[Episode],
        idempotency_index: dict[tuple[TenantId, str], MemoryId],
        events: list[EventEnvelope],
    ) -> None:
        self._state = _CommittedMemoryState(
            episodes=tuple(episodes),
            idempotency_index=MappingProxyType(dict(idempotency_index)),
            events=tuple(events),
        )
