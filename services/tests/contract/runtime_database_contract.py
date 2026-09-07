"""Reusable behavioral contracts for RuntimeDatabasePort adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.shared.status_changed_event import (
    build_execution_status_changed_event,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.modules.runtime.ports import RuntimeDatabasePort, RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import (
    CommittedRuntimeState,
    empty_runtime_state,
)
from engrammesh.shared.kernel.ids import (
    CorrelationId,
    EventId,
    ExecutionId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
SCOPE = MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")

type RuntimeDatabaseFactory = Callable[[], Awaitable[RuntimeDatabasePort]]
type RuntimeDatabaseContractAssertion = Callable[
    [RuntimeDatabaseFactory],
    Awaitable[None],
]


def contract_snapshot() -> ExecutionSnapshot:
    """Canonical snapshot aligned with ``test_snapshot_codec``."""
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        scope=SCOPE,
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )


async def assert_read_empty_state(make_database: RuntimeDatabaseFactory) -> None:
    database = await make_database()
    state = await database.read(lambda committed: committed)
    assert state == empty_runtime_state()


async def assert_write_persists_idempotency_and_fingerprint(
    make_database: RuntimeDatabaseFactory,
) -> None:
    database = await make_database()
    tenant_id = TenantId.new()
    execution_id = ExecutionId.new()
    fingerprint = (str(tenant_id), "contract-fp")

    async def _register(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        del outbox
        idempotency_index = dict(state.idempotency_index)
        idempotency_index[(tenant_id, "start-key")] = execution_id
        fingerprints = dict(state.fingerprints)
        fingerprints[execution_id] = fingerprint
        return replace(
            state,
            idempotency_index=MappingProxyType(idempotency_index),
            fingerprints=MappingProxyType(fingerprints),
        )

    await database.write(_register)
    result = await database.read(
        lambda state: (
            state.idempotency_index.get((tenant_id, "start-key")),
            state.fingerprints.get(execution_id),
        )
    )
    assert result == (execution_id, fingerprint)


async def assert_write_persists_snapshot(
    make_database: RuntimeDatabaseFactory,
) -> None:
    database = await make_database()
    snapshot = contract_snapshot()

    async def _persist(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        del outbox
        snapshots = dict(state.snapshots)
        snapshots[snapshot.execution_id] = snapshot
        return replace(state, snapshots=MappingProxyType(snapshots))

    await database.write(_persist)
    loaded = await database.read(
        lambda state: state.snapshots.get(snapshot.execution_id)
    )
    assert loaded == snapshot


async def assert_write_replaces_state_atomically(
    make_database: RuntimeDatabaseFactory,
) -> None:
    database = await make_database()
    tenant_id = TenantId.new()
    execution_id = ExecutionId.new()
    snapshot = contract_snapshot()

    async def _seed(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        del outbox
        idempotency_index = dict(state.idempotency_index)
        idempotency_index[(tenant_id, "seed-key")] = execution_id
        fingerprints = dict(state.fingerprints)
        fingerprints[execution_id] = ("seed",)
        snapshots = dict(state.snapshots)
        snapshots[snapshot.execution_id] = snapshot
        return CommittedRuntimeState(
            snapshots=MappingProxyType(snapshots),
            idempotency_index=MappingProxyType(idempotency_index),
            fingerprints=MappingProxyType(fingerprints),
        )

    await database.write(_seed)

    with pytest.raises(RuntimeError, match="contract write failure"):
        async def _fail(
            state: CommittedRuntimeState,
            outbox: RuntimeOutboxPort,
        ) -> CommittedRuntimeState:
            del state, outbox
            raise RuntimeError("contract write failure")

        await database.write(_fail)

    after_failure = await database.read(lambda state: state)
    assert len(after_failure.snapshots) == 1
    assert len(after_failure.idempotency_index) == 1
    assert after_failure.snapshots[snapshot.execution_id] == snapshot
    assert after_failure.idempotency_index[(tenant_id, "seed-key")] == execution_id

    async def _clear(
        state: CommittedRuntimeState,
        outbox: RuntimeOutboxPort,
    ) -> CommittedRuntimeState:
        del state, outbox
        return empty_runtime_state()

    await database.write(_clear)

    cleared = await database.read(lambda state: state)
    assert cleared == empty_runtime_state()


async def assert_exception_after_outbox_publish_rolls_back(
    make_database: RuntimeDatabaseFactory,
) -> None:
    database = await make_database()
    snapshot = contract_snapshot()
    event = build_execution_status_changed_event(
        event_id=EventId.new(),
        correlation_id=CorrelationId(snapshot.execution_id.value),
        causation_id=None,
        previous_status=None,
        snapshot=snapshot,
    )

    with pytest.raises(RuntimeError, match="contract outbox-stage failure"):
        async def _stage_and_fail(
            state: CommittedRuntimeState,
            outbox: RuntimeOutboxPort,
        ) -> CommittedRuntimeState:
            await outbox.publish(event)
            raise RuntimeError("contract outbox-stage failure")

        await database.write(_stage_and_fail)

    outbox_count = await database.read(lambda state: len(state.outbox_events))
    assert outbox_count == 0


RUNTIME_DATABASE_CONTRACTS: tuple[
    tuple[str, RuntimeDatabaseContractAssertion],
    ...,
] = (
    ("read_empty_state", assert_read_empty_state),
    (
        "write_persists_idempotency_and_fingerprint",
        assert_write_persists_idempotency_and_fingerprint,
    ),
    ("write_persists_snapshot", assert_write_persists_snapshot),
    ("write_replaces_state_atomically", assert_write_replaces_state_atomically),
    (
        "exception_after_outbox_publish",
        assert_exception_after_outbox_publish_rolls_back,
    ),
)
