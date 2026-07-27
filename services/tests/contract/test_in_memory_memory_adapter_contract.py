"""Bind every reusable memory adapter contract to the in-memory adapter."""

import pytest
from memory_adapter_contract import (
    MEMORY_ADAPTER_CONTRACTS,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    MEMORY_ADAPTER_CONTRACTS,
    ids=[case_name for case_name, _ in MEMORY_ADAPTER_CONTRACTS],
)
async def test_in_memory_memory_adapter_contract(
    case_name: str,
    assert_contract: MemoryAdapterContractAssertion,
) -> None:
    del case_name
    await assert_contract(InMemoryMemoryAdapterHarness)
