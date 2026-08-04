"""Integration tests for PostgreSQL runtime database read/write."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
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
