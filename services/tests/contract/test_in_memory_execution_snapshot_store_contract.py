"""Bind execution snapshot store contracts to the in-memory runtime database."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from execution_snapshot_store_contract import EXECUTION_SNAPSHOT_STORE_CONTRACTS

from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.ports import ExecutionSnapshotStore


async def _make_store() -> ExecutionSnapshotStore:
    return InMemoryRuntimeDatabase()


@pytest.mark.parametrize(
    ("name", "assertion"),
    EXECUTION_SNAPSHOT_STORE_CONTRACTS,
    ids=[name for name, _ in EXECUTION_SNAPSHOT_STORE_CONTRACTS],
)
@pytest.mark.asyncio
async def test_in_memory_execution_snapshot_store_contract(
    name: str,
    assertion: Callable[[Callable[[], Awaitable[ExecutionSnapshotStore]]], Awaitable[None]],
) -> None:
    del name
    await assertion(_make_store)
