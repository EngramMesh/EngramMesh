"""Bind reusable runtime database contracts to the in-memory adapter."""

import pytest
from runtime_database_contract import (
    RUNTIME_DATABASE_CONTRACTS,
    RuntimeDatabaseContractAssertion,
)

from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.ports import RuntimeDatabasePort


async def _make_database() -> RuntimeDatabasePort:
    return InMemoryRuntimeDatabase()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    RUNTIME_DATABASE_CONTRACTS,
    ids=[case_name for case_name, _ in RUNTIME_DATABASE_CONTRACTS],
)
async def test_in_memory_runtime_database_contract(
    case_name: str,
    assert_contract: RuntimeDatabaseContractAssertion,
) -> None:
    del case_name
    await assert_contract(_make_database)
