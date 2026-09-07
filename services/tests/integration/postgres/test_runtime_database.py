"""Integration tests for PostgreSQL runtime database read/write."""

import asyncio
from dataclasses import replace
from types import MappingProxyType

import pytest

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.ids import ExecutionId, TenantId

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_runtime_database_write_then_read_round_trip(
    postgres_dsn: str,
) -> None:
    database = PostgresRuntimeDatabase(postgres_dsn)
    await database.open()
    try:
        tenant_id = TenantId.new()
        execution_id = ExecutionId.new()

        def _register(state):
            idempotency_index = dict(state.idempotency_index)
            idempotency_index[(tenant_id, "start-key")] = execution_id
            fingerprints = dict(state.fingerprints)
            fingerprints[execution_id] = (str(tenant_id), "fp")
            return replace(
                state,
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await database.write(_register)
        result = await database.read(
            lambda state: state.idempotency_index.get((tenant_id, "start-key"))
        )
        assert result == execution_id
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_concurrent_idempotency_registration_is_idempotent(
    postgres_dsn: str,
) -> None:
    database_a = PostgresRuntimeDatabase(postgres_dsn)
    database_b = PostgresRuntimeDatabase(postgres_dsn)
    await database_a.open()
    await database_b.open()
    try:
        tenant_id = TenantId.new()
        key = "concurrent-start"
        shared_fingerprint = (str(tenant_id), "race-fp")

        def _register(state: CommittedRuntimeState) -> CommittedRuntimeState:
            index_key = (tenant_id, key)
            existing_id = state.idempotency_index.get(index_key)
            if existing_id is not None:
                return state
            execution_id = ExecutionId.new()
            idempotency_index = dict(state.idempotency_index)
            idempotency_index[index_key] = execution_id
            fingerprints = dict(state.fingerprints)
            fingerprints[execution_id] = shared_fingerprint
            return replace(
                state,
                idempotency_index=MappingProxyType(idempotency_index),
                fingerprints=MappingProxyType(fingerprints),
            )

        await asyncio.gather(
            database_a.write(_register),
            database_b.write(_register),
        )

        final_state = await database_a.read(lambda state: state)
        assert len(final_state.idempotency_index) == 1
        assert (tenant_id, key) in final_state.idempotency_index
    finally:
        await database_a.close()
        await database_b.close()
