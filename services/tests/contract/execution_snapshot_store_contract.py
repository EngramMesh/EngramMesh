"""Reusable behavioral contracts for ExecutionSnapshotStore adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.domain.errors import InvalidExecutionCursor
from engrammesh.modules.runtime.domain.execution_cursor import encode_execution_cursor
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.modules.runtime.ports import ExecutionSnapshotStore
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId

NOW = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
OTHER_SUBJECT = SubjectId(UUID("4e76d182-bd66-4958-b9f2-f4dc970d6d56"))
SCOPE = MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")
OTHER_SCOPE = MemoryScope(TENANT, OTHER_SUBJECT, workspace_id="ws-1")

type ExecutionSnapshotStoreFactory = Callable[[], Awaitable[ExecutionSnapshotStore]]
type ExecutionSnapshotStoreContractAssertion = Callable[
    [ExecutionSnapshotStoreFactory],
    Awaitable[None],
]


def _snapshot(
    *,
    execution_id: ExecutionId | None = None,
    scope: MemoryScope = SCOPE,
    updated_at: datetime = NOW,
    revision: int = 1,
) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=execution_id or ExecutionId.new(),
        scope=scope,
        revision=revision,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=updated_at,
    )


async def assert_empty_scope(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    assert await store.stream(SCOPE, limit=10) == ()


async def assert_single_snapshot(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    snapshot = _snapshot()
    await _seed_snapshot(store, snapshot)
    rows = await store.stream(SCOPE, limit=10)
    assert rows == (snapshot,)


async def assert_scope_mismatch(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    await _seed_snapshot(store, _snapshot(scope=OTHER_SCOPE))
    assert await store.stream(SCOPE, limit=10) == ()


async def assert_pagination(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    snapshots = [
        _snapshot(
            execution_id=ExecutionId(UUID(f"{index:032x}")),
            updated_at=NOW + timedelta(minutes=index),
            revision=index + 1,
        )
        for index in range(3)
    ]
    for snapshot in snapshots:
        await _seed_snapshot(store, snapshot)

    page_one = await store.stream(SCOPE, limit=2)
    assert len(page_one) == 2
    cursor = encode_execution_cursor(
        updated_at=page_one[-1].updated_at,
        execution_id=page_one[-1].execution_id,
    )
    page_two = await store.stream(SCOPE, limit=2, cursor=cursor)
    assert len(page_two) == 1
    assert page_one[0].execution_id != page_two[0].execution_id


async def assert_invalid_cursor(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    await _seed_snapshot(store, _snapshot())
    with pytest.raises(InvalidExecutionCursor):
        await store.stream(SCOPE, limit=10, cursor="bad")


async def assert_desc_order(make_store: ExecutionSnapshotStoreFactory) -> None:
    store = await make_store()
    older = _snapshot(
        execution_id=ExecutionId(UUID("11111111-1111-1111-1111-111111111111")),
        updated_at=NOW,
    )
    newer = _snapshot(
        execution_id=ExecutionId(UUID("22222222-2222-2222-2222-222222222222")),
        updated_at=NOW + timedelta(minutes=1),
        revision=2,
    )
    await _seed_snapshot(store, older)
    await _seed_snapshot(store, newer)
    rows = await store.stream(SCOPE, limit=10)
    assert rows[0].execution_id == newer.execution_id


async def _seed_snapshot(
    store: ExecutionSnapshotStore,
    snapshot: ExecutionSnapshot,
) -> None:
    seed = getattr(store, "replace_snapshot_for_tests", None)
    if callable(seed):
        seed(snapshot)
        return
    upsert = getattr(store, "upsert_snapshot", None)
    if callable(upsert):
        await upsert(snapshot)
        return
    msg = "store fixture must expose replace_snapshot_for_tests or upsert_snapshot"
    raise TypeError(msg)


EXECUTION_SNAPSHOT_STORE_CONTRACTS: tuple[
    tuple[str, ExecutionSnapshotStoreContractAssertion],
    ...,
] = (
    ("empty_scope", assert_empty_scope),
    ("single_snapshot", assert_single_snapshot),
    ("scope_mismatch", assert_scope_mismatch),
    ("pagination", assert_pagination),
    ("invalid_cursor", assert_invalid_cursor),
    ("desc_order", assert_desc_order),
)
