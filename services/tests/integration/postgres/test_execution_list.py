"""PostgreSQL integration tests for execution list and snapshot projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedRuntimeAuthorization,
    SystemUtcClock,
)
from engrammesh.bootstrap.settings import Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.identities import (
    UuidRuntimeIdentityPort,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.postgres.snapshot_store import (
    PostgresExecutionSnapshotStore,
)
from engrammesh.modules.runtime.adapters.postgres.snapshot_writer import (
    PostgresRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.application.contracts import (
    ListExecutionsQuery,
    StartExecutionCommand,
)
from engrammesh.modules.runtime.application.list_executions import ListExecutionsHandler
from engrammesh.modules.runtime.application.start_execution import StartExecutionHandler
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    ExecutionId,
    SubjectId,
    TenantId,
)

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
SCOPE = MemoryScope(TENANT, SUBJECT, workspace_id="workspace-42")
EXECUTION_ID = ExecutionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))


def _snapshot(
    *,
    revision: int,
    status: ExecutionStatus = ExecutionStatus.PENDING,
) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=EXECUTION_ID,
        scope=SCOPE,
        revision=revision,
        status=status,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )


def _budget() -> Budget:
    return Budget(1000, 500, 100_000, NOW + timedelta(hours=1))


@pytest.mark.asyncio
async def test_postgres_snapshot_writer_revision_monotonic(postgres_dsn: str) -> None:
    writer = PostgresRuntimeSnapshotWriter(postgres_dsn)
    database = PostgresRuntimeDatabase(postgres_dsn)
    await writer.open()
    await database.open()
    await writer.upsert_snapshot(_snapshot(revision=2))
    await writer.upsert_snapshot(_snapshot(revision=1))
    store = PostgresExecutionSnapshotStore(database)
    rows = await store.stream(SCOPE, limit=10)
    assert len(rows) == 1
    assert rows[0].revision == 2
    await writer.close()
    await database.close()


@pytest.mark.asyncio
async def test_postgres_snapshot_writer_equal_revision_is_noop(postgres_dsn: str) -> None:
    writer = PostgresRuntimeSnapshotWriter(postgres_dsn)
    database = PostgresRuntimeDatabase(postgres_dsn)
    await writer.open()
    await database.open()
    first = _snapshot(revision=2, status=ExecutionStatus.PENDING)
    second = _snapshot(revision=2, status=ExecutionStatus.PLANNING)
    await writer.upsert_snapshot(first)
    await writer.upsert_snapshot(second)
    store = PostgresExecutionSnapshotStore(database)
    rows = await store.stream(SCOPE, limit=10)
    assert rows[0].status == ExecutionStatus.PENDING
    await writer.close()
    await database.close()


@pytest.mark.asyncio
async def test_in_memory_orchestrator_start_then_list(postgres_dsn: str) -> None:
    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    authorization = EnvironmentGatedRuntimeAuthorization(Environment.TEST)
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    start_handler = StartExecutionHandler(
        authorization=authorization,
        identities=UuidRuntimeIdentityPort(),
        orchestrator=orchestrator,
    )
    list_handler = ListExecutionsHandler(
        authorization=authorization,
        snapshot_store=PostgresExecutionSnapshotStore(database),
    )
    start_result = await start_handler.handle(
        StartExecutionCommand(
            correlation_id=CorrelationId.new(),
            actor_id=ACTOR,
            scope=SCOPE,
            objective_ref=ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")),
            root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
            memory_query=None,
            budget=_budget(),
            idempotency_key="postgres-list-start",
        )
    )
    listed = await list_handler.handle(
        ListExecutionsQuery(actor_id=ACTOR, scope=SCOPE, limit=10)
    )
    assert any(
        item.execution_id == start_result.snapshot.execution_id for item in listed.items
    )
    match = next(
        item
        for item in listed.items
        if item.execution_id == start_result.snapshot.execution_id
    )
    assert match.revision == 1
    await database.close()


@pytest.mark.asyncio
async def test_start_then_list_survives_database_restart(postgres_dsn: str) -> None:
    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    authorization = EnvironmentGatedRuntimeAuthorization(Environment.TEST)
    orchestrator = InMemoryOrchestratorPort(SystemUtcClock(), database)
    start_handler = StartExecutionHandler(
        authorization=authorization,
        identities=UuidRuntimeIdentityPort(),
        orchestrator=orchestrator,
    )
    list_handler = ListExecutionsHandler(
        authorization=authorization,
        snapshot_store=PostgresExecutionSnapshotStore(database),
    )
    start_result = await start_handler.handle(
        StartExecutionCommand(
            correlation_id=CorrelationId.new(),
            actor_id=ACTOR,
            scope=SCOPE,
            objective_ref=ArtifactId(UUID("b3f68fda-e18e-56ed-b758-87e206986e97")),
            root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
            memory_query=None,
            budget=_budget(),
            idempotency_key="postgres-list-restart",
        )
    )
    first_list = await list_handler.handle(
        ListExecutionsQuery(actor_id=ACTOR, scope=SCOPE, limit=10)
    )
    await database.close()

    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    list_handler = ListExecutionsHandler(
        authorization=authorization,
        snapshot_store=PostgresExecutionSnapshotStore(database),
    )
    second_list = await list_handler.handle(
        ListExecutionsQuery(actor_id=ACTOR, scope=SCOPE, limit=10)
    )
    assert any(
        item.execution_id == start_result.snapshot.execution_id for item in second_list.items
    )
    assert len(second_list.items) == len(first_list.items)
    await database.close()
