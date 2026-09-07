"""Bind reusable runtime database contracts to the PostgreSQL adapter."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import psycopg
import pytest
from runtime_database_contract import (
    RUNTIME_DATABASE_CONTRACTS,
    RuntimeDatabaseContractAssertion,
)

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.ids import ExecutionId, TenantId

pytestmark = pytest.mark.postgres

_RUNTIME_TABLES = (
    "runtime_execution_snapshots",
    "runtime_start_idempotency",
)


def _truncate_runtime_tables(dsn: str) -> None:
    with (
        psycopg.connect(dsn) as connection,
        connection.transaction(),
    ):
        connection.execute(
            "TRUNCATE "
            + ", ".join(_RUNTIME_TABLES)
            + " RESTART IDENTITY CASCADE"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    RUNTIME_DATABASE_CONTRACTS,
    ids=[case_name for case_name, _ in RUNTIME_DATABASE_CONTRACTS],
)
async def test_postgres_runtime_database_contract(
    case_name: str,
    assert_contract: RuntimeDatabaseContractAssertion,
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del case_name, postgres_connection
    _truncate_runtime_tables(postgres_dsn)
    opened: list[PostgresRuntimeDatabase] = []

    async def make_database() -> PostgresRuntimeDatabase:
        database = PostgresRuntimeDatabase(postgres_dsn)
        await database.open()
        opened.append(database)
        return database

    try:
        await assert_contract(make_database)
    finally:
        for database in opened:
            await database.close()


@pytest.mark.asyncio
async def test_postgres_runtime_database_survives_reinstantiation(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    _truncate_runtime_tables(postgres_dsn)

    tenant_id = TenantId.new()
    execution_id = ExecutionId.new()

    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    try:

        async def _register(
            state: CommittedRuntimeState,
            outbox: RuntimeOutboxPort,
        ) -> CommittedRuntimeState:
            del outbox
            idempotency_index = dict(state.idempotency_index)
            idempotency_index[(tenant_id, "restart-key")] = execution_id
            fingerprints = dict(state.fingerprints)
            fingerprints[execution_id] = (str(tenant_id), "restart-fp")
            return replace(
                state,
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await database.write(_register)
    finally:
        await database.close()

    restarted = PostgresRuntimeDatabase(postgres_dsn)
    await restarted.open()
    try:
        result = await restarted.read(
            lambda state: state.idempotency_index.get((tenant_id, "restart-key"))
        )
        assert result == execution_id
        fingerprint = await restarted.read(
            lambda state: state.fingerprints.get(execution_id)
        )
        assert fingerprint == (str(tenant_id), "restart-fp")
    finally:
        await restarted.close()
