"""Integration tests for composed runtime handlers with PostgresRuntimeDatabase."""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import AsyncMock
from uuid import UUID

import psycopg
import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.temporal.mappers import snapshot_to_payload
from engrammesh.modules.runtime.adapters.temporal.orchestrator import (
    TemporalOrchestratorPort,
)
from engrammesh.modules.runtime.application.contracts import (
    CancelExecutionCommand,
    GetExecutionSnapshotQuery,
    StartExecutionCommand,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
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

TENANT_A = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
TENANT_B = TenantId(UUID("e63173e8-8f03-4f34-beac-2020676684c0"))
SUBJECT_ID = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
OBJECTIVE_REF = ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86"))
ROOT_AGENT_ID = AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
CORRELATION_ID = CorrelationId(UUID("02ffae84-2764-41f3-a22a-4d4652a7c139"))
BUDGET_DEADLINE = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.postgres


def _settings(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )


def _scope(tenant_id: TenantId) -> MemoryScope:
    return MemoryScope(
        tenant_id=tenant_id,
        subject_id=SUBJECT_ID,
        workspace_id="workspace-42",
    )


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=BUDGET_DEADLINE,
    )


def _start_command(
    *,
    tenant_id: TenantId = TENANT_A,
    idempotency_key: str = "pg-runtime-start",
) -> StartExecutionCommand:
    return StartExecutionCommand(
        correlation_id=CORRELATION_ID,
        actor_id=ACTOR_ID,
        scope=_scope(tenant_id),
        objective_ref=OBJECTIVE_REF,
        root_agent_id=ROOT_AGENT_ID,
        memory_query=None,
        budget=_budget(),
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_start_get_cancel_with_postgres_runtime_database(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    async with create_runtime(_settings(postgres_dsn)) as runtime:
        orchestrator = runtime.start_execution_handler()._orchestrator
        assert isinstance(orchestrator, InMemoryOrchestratorPort)
        assert isinstance(orchestrator.database, PostgresRuntimeDatabase)

        start_result = await runtime.start_execution_handler().handle(
            _start_command(idempotency_key="pg-runtime-flow")
        )
        assert start_result.created is True
        execution_id = start_result.snapshot.execution_id

        get_result = await runtime.get_execution_snapshot_handler().handle(
            GetExecutionSnapshotQuery(
                actor_id=ACTOR_ID,
                scope=_scope(TENANT_A),
                execution_id=execution_id,
            )
        )
        assert get_result.snapshot.execution_id == execution_id
        assert get_result.snapshot.status is ExecutionStatus.PENDING

        cancel_result = await runtime.cancel_execution_handler().handle(
            CancelExecutionCommand(
                correlation_id=CORRELATION_ID,
                actor_id=ACTOR_ID,
                scope=_scope(TENANT_A),
                execution_id=execution_id,
                idempotency_key="pg-runtime-cancel",
            )
        )
        assert cancel_result.snapshot.status is ExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_idempotency_survives_runtime_database_restart(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    settings = _settings(postgres_dsn)
    command = _start_command(idempotency_key="pg-runtime-restart")

    runtime = create_runtime(settings)
    await runtime.startup()
    try:
        first = await runtime.start_execution_handler().handle(command)
        assert first.created is True
        execution_id = first.snapshot.execution_id
    finally:
        await runtime.shutdown()

    restarted = create_runtime(settings)
    await restarted.startup()
    try:
        replay = await restarted.start_execution_handler().handle(command)
        assert replay.created is False
        assert replay.snapshot.execution_id == execution_id
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_cross_tenant_idempotency_keys_are_isolated(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    shared_key = "shared-idempotency-key"

    async with create_runtime(_settings(postgres_dsn)) as runtime:
        handler = runtime.start_execution_handler()
        tenant_a = await handler.handle(
            _start_command(tenant_id=TENANT_A, idempotency_key=shared_key)
        )
        tenant_b = await handler.handle(
            _start_command(tenant_id=TENANT_B, idempotency_key=shared_key)
        )

    assert tenant_a.created is True
    assert tenant_b.created is True
    assert tenant_a.snapshot.execution_id != tenant_b.snapshot.execution_id


@pytest.mark.asyncio
async def test_temporal_orchestrator_persists_idempotency_only(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    spec = ExecutionSpec(
        id=ExecutionId.new(),
        scope=_scope(TENANT_A),
        objective_ref=OBJECTIVE_REF,
        root_agent_id=ROOT_AGENT_ID,
        memory_query=None,
        budget=_budget(),
        idempotency_key="temporal-idempotency-only",
    )
    snapshot = ExecutionSnapshot(
        execution_id=spec.id,
        scope=spec.scope,
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=datetime.now(UTC),
    )

    client = AsyncMock()
    client.start_workflow = AsyncMock()
    handle = AsyncMock()
    handle.query = AsyncMock(return_value=snapshot_to_payload(snapshot))
    client.get_workflow_handle = AsyncMock(return_value=handle)

    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    try:
        orchestrator = TemporalOrchestratorPort(
            client,
            task_queue="test-queue",
            index=database,
            clock=SystemUtcClock(),
        )
        result = await orchestrator.start(spec)
        assert result.execution_id == spec.id

        with postgres_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM runtime_start_idempotency")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM runtime_execution_snapshots")
            assert cursor.fetchone()[0] == 0
    finally:
        await database.close()
