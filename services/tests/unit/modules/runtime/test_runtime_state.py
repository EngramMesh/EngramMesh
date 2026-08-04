from types import MappingProxyType

from engrammesh.modules.runtime.runtime_state import (
    CommittedRuntimeState,
    empty_runtime_state,
)


def test_empty_runtime_state_has_no_entries() -> None:
    state = empty_runtime_state()
    assert state.snapshots == MappingProxyType({})
    assert state.idempotency_index == MappingProxyType({})
    assert state.fingerprints == MappingProxyType({})


def test_committed_runtime_state_is_frozen() -> None:
    assert isinstance(empty_runtime_state(), CommittedRuntimeState)
