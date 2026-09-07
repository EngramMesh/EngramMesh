from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Never
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.application.contracts import ListExecutionsQuery
from engrammesh.modules.runtime.application.errors import ExecutionAuthorizationDenied
from engrammesh.modules.runtime.application.list_executions import ListExecutionsHandler
from engrammesh.modules.runtime.domain.errors import InvalidExecutionCursor
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot, ExecutionStatus
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
BASE_UPDATED_AT = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


@dataclass
class RecordingAuthorization:
    calls: list[str] = field(default_factory=list)
    allowed: bool = True

    async def authorize(self, request: RuntimeAuthorizationRequest) -> bool:
        self.calls.append("authorize")
        del request
        return self.allowed


def make_scope() -> MemoryScope:
    return MemoryScope(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
    )


def make_snapshot(index: int) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID(f"{index:032x}")),
        scope=make_scope(),
        revision=index + 1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=BASE_UPDATED_AT + timedelta(minutes=index),
    )


@pytest.mark.asyncio
async def test_list_returns_items_and_next_cursor() -> None:
    database = InMemoryRuntimeDatabase()
    snapshots = [make_snapshot(i) for i in range(3)]
    for snapshot in snapshots:
        database.replace_snapshot_for_tests(snapshot)
    handler = ListExecutionsHandler(
        authorization=RecordingAuthorization(),
        snapshot_store=database,
    )
    first_page = await handler.handle(
        ListExecutionsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=2,
        )
    )
    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None
    second_page = await handler.handle(
        ListExecutionsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=2,
            cursor=first_page.next_cursor,
        )
    )
    assert len(second_page.items) == 1
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_list_empty_scope_returns_empty() -> None:
    database = InMemoryRuntimeDatabase()
    handler = ListExecutionsHandler(
        authorization=RecordingAuthorization(),
        snapshot_store=database,
    )
    result = await handler.handle(
        ListExecutionsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=10,
        )
    )
    assert result.items == ()
    assert result.next_cursor is None


def test_list_rejects_limit_over_100() -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        ListExecutionsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=101,
        )


@pytest.mark.asyncio
async def test_list_denial_authorizes_first_and_accesses_nothing_else() -> None:
    authorization = RecordingAuthorization(allowed=False)
    handler = ListExecutionsHandler(
        authorization=authorization,
        snapshot_store=MustNotBeUsed(),
    )
    with pytest.raises(ExecutionAuthorizationDenied):
        await handler.handle(
            ListExecutionsQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
            )
        )
    assert authorization.calls == ["authorize"]


@pytest.mark.asyncio
async def test_list_invalid_cursor_propagates() -> None:
    database = InMemoryRuntimeDatabase()
    database.replace_snapshot_for_tests(make_snapshot(0))
    handler = ListExecutionsHandler(
        authorization=RecordingAuthorization(),
        snapshot_store=database,
    )
    with pytest.raises(InvalidExecutionCursor):
        await handler.handle(
            ListExecutionsQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
                cursor="bad",
            )
        )
