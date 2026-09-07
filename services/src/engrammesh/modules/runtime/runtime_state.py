"""Committed runtime state shared by database adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import ExecutionId, TenantId

type IdempotencyIndex = Mapping[tuple[TenantId, str], ExecutionId]
type FingerprintIndex = Mapping[ExecutionId, tuple[object, ...]]


@dataclass(frozen=True, slots=True)
class CommittedRuntimeState:
    snapshots: Mapping[ExecutionId, ExecutionSnapshot]
    idempotency_index: IdempotencyIndex
    fingerprints: FingerprintIndex
    outbox_events: tuple[EventEnvelope, ...] = ()


def empty_runtime_state() -> CommittedRuntimeState:
    return CommittedRuntimeState(
        snapshots=MappingProxyType({}),
        idempotency_index=MappingProxyType({}),
        fingerprints=MappingProxyType({}),
    )
