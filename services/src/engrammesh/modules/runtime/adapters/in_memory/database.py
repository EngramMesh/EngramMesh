"""Committed in-memory state for durable execution snapshots and idempotency."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TypeVar, final

from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.shared.kernel.ids import ExecutionId, TenantId

type _IdempotencyIndex = Mapping[tuple[TenantId, str], ExecutionId]
type _FingerprintIndex = Mapping[ExecutionId, tuple[object, ...]]


@dataclass(frozen=True, slots=True)
class _CommittedRuntimeState:
    snapshots: Mapping[ExecutionId, ExecutionSnapshot]
    idempotency_index: _IdempotencyIndex
    fingerprints: _FingerprintIndex


def _empty_state() -> _CommittedRuntimeState:
    return _CommittedRuntimeState(
        snapshots=MappingProxyType({}),
        idempotency_index=MappingProxyType({}),
        fingerprints=MappingProxyType({}),
    )


_T = TypeVar("_T")


@final
class InMemoryRuntimeDatabase:
    """Own committed execution snapshots and start-idempotency indexes."""

    __slots__ = ("_lock", "_state")

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = _empty_state()

    async def read(self, callback: Callable[[_CommittedRuntimeState], _T]) -> _T:
        """Run *callback* against the current committed state under the lock."""
        async with self._lock:
            return callback(self._state)

    async def write(
        self,
        callback: Callable[[_CommittedRuntimeState], _CommittedRuntimeState],
    ) -> None:
        """Atomically replace committed state with *callback*'s result."""
        async with self._lock:
            self._state = callback(self._state)

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
