"""Bind every reusable memory adapter contract to the in-memory adapter."""

import ast
import asyncio
import inspect

import memory_adapter_contract
import pytest
from memory_adapter_contract import (
    EPISODE_ADAPTER_CONTRACTS,
    IN_MEMORY_CAPABILITY_CONTRACTS,
    AsyncStartBarrier,
    MemoryAdapterContractAssertion,
)

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.domain.model import Episode
from engrammesh.modules.memory.ports import MemoryUnitOfWorkFactory
from engrammesh.shared.kernel.events import EventEnvelope


class InMemoryMemoryAdapterHarness:
    """Expose public construction and committed-state probes for one database."""

    def __init__(self) -> None:
        self._database = InMemoryMemoryDatabase()
        self._unit_of_work_factory = InMemoryMemoryUnitOfWorkFactory(
            self._database
        )

    @property
    def unit_of_work_factory(self) -> MemoryUnitOfWorkFactory:
        return self._unit_of_work_factory

    @property
    def committed_episodes(self) -> tuple[Episode, ...]:
        return self._database.episodes

    @property
    def committed_events(self) -> tuple[EventEnvelope, ...]:
        return self._database.events


def test_reusable_contract_has_no_internal_application_imports() -> None:
    syntax = ast.parse(inspect.getsource(memory_adapter_contract))
    imported_modules = {
        node.module
        for node in ast.walk(syntax)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not {
        module
        for module in imported_modules
        if module.startswith("engrammesh.modules.memory.application")
    }


@pytest.mark.asyncio
async def test_async_start_barrier_waits_for_every_participant() -> None:
    barrier = AsyncStartBarrier(parties=3)
    tasks = [
        asyncio.create_task(barrier.arrive_and_wait()) for _ in range(3)
    ]

    try:
        async with asyncio.timeout(1):
            await barrier.wait_until_full()
        assert barrier.arrived == 3
        assert all(task.done() is False for task in tasks)

        barrier.release()
        async with asyncio.timeout(1):
            await asyncio.gather(*tasks)
    finally:
        barrier.release()
        for task in tasks:
            if not task.done():
                task.cancel()
        async with asyncio.timeout(1):
            await asyncio.gather(*tasks, return_exceptions=True)


def test_contract_registries_are_separate_and_complete() -> None:
    episode_names = tuple(name for name, _ in EPISODE_ADAPTER_CONTRACTS)
    capability_names = tuple(
        name for name, _ in IN_MEMORY_CAPABILITY_CONTRACTS
    )

    assert episode_names == (
        "first_append_get_stream",
        "exact_scope_denial",
        "exact_replay",
        "divergent_idempotency_conflict",
        "different_tenant_same_key",
        "outbox_order",
        "episode_outbox_integrity",
        "exit_without_commit",
        "exception_after_episode",
        "exception_after_outbox",
        "commit_persistence",
        "concurrent_duplicate_convergence",
        "uow_single_use",
        "cancel_inside_transaction",
        "cancel_after_commit",
    )
    assert capability_names == (
        "claims_unavailable",
        "cursor_pagination",
        "cancel_while_queued",
    )
    assert set(episode_names).isdisjoint(capability_names)
    assert len(episode_names) + len(capability_names) == 18


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    EPISODE_ADAPTER_CONTRACTS,
    ids=[case_name for case_name, _ in EPISODE_ADAPTER_CONTRACTS],
)
async def test_in_memory_episode_adapter_contract(
    case_name: str,
    assert_contract: MemoryAdapterContractAssertion,
) -> None:
    del case_name
    await assert_contract(InMemoryMemoryAdapterHarness)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    IN_MEMORY_CAPABILITY_CONTRACTS,
    ids=[case_name for case_name, _ in IN_MEMORY_CAPABILITY_CONTRACTS],
)
async def test_in_memory_capability_contract(
    case_name: str,
    assert_contract: MemoryAdapterContractAssertion,
) -> None:
    del case_name
    await assert_contract(InMemoryMemoryAdapterHarness)
