"""Bind reusable OrchestratorPort contracts to the in-memory adapter."""

import pytest
from orchestrator_adapter_contract import (
    ORCHESTRATOR_PORT_CONTRACTS,
    OrchestratorContractAssertion,
)

from engrammesh.bootstrap.infrastructure import SystemUtcClock
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.ports import OrchestratorPort


class InMemoryOrchestratorHarness:
    def __init__(self) -> None:
        self._database = InMemoryRuntimeDatabase()
        self._orchestrator = InMemoryOrchestratorPort(
            clock=SystemUtcClock(),
            database=self._database,
        )

    @property
    def orchestrator(self) -> OrchestratorPort:
        return self._orchestrator


def _make_harness() -> InMemoryOrchestratorHarness:
    return InMemoryOrchestratorHarness()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assert_contract",
    ORCHESTRATOR_PORT_CONTRACTS,
    ids=[fn.__name__ for fn in ORCHESTRATOR_PORT_CONTRACTS],
)
async def test_in_memory_orchestrator_adapter_contract(
    assert_contract: OrchestratorContractAssertion,
) -> None:
    await assert_contract(_make_harness)
