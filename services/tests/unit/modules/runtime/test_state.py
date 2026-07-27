from engrammesh.modules.runtime.domain.model import ExecutionStatus, NodeStatus
from engrammesh.modules.runtime.domain.state import (
    EXECUTION_TRANSITIONS,
    NODE_TRANSITIONS,
    can_transition_execution,
    can_transition_node,
)


def test_execution_transitions_cover_durable_lifecycle_paths() -> None:
    expected_paths = (
        (ExecutionStatus.PENDING, ExecutionStatus.PLANNING),
        (ExecutionStatus.PLANNING, ExecutionStatus.RUNNING),
        (ExecutionStatus.RUNNING, ExecutionStatus.WAITING),
        (ExecutionStatus.WAITING, ExecutionStatus.RUNNING),
        (ExecutionStatus.RUNNING, ExecutionStatus.RETRYING),
        (ExecutionStatus.RETRYING, ExecutionStatus.RUNNING),
        (ExecutionStatus.RUNNING, ExecutionStatus.CANCELLING),
        (ExecutionStatus.CANCELLING, ExecutionStatus.COMPENSATING),
        (ExecutionStatus.COMPENSATING, ExecutionStatus.CANCELLED),
        (ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED),
        (ExecutionStatus.RUNNING, ExecutionStatus.FAILED),
    )

    assert all(can_transition_execution(source, target) for source, target in expected_paths)
    assert not can_transition_execution(
        ExecutionStatus.PENDING,
        ExecutionStatus.SUCCEEDED,
    )
    assert not can_transition_execution(
        ExecutionStatus.WAITING,
        ExecutionStatus.PLANNING,
    )


def test_node_transitions_cover_execution_and_compensation_paths() -> None:
    expected_paths = (
        (NodeStatus.PENDING, NodeStatus.READY),
        (NodeStatus.READY, NodeStatus.RUNNING),
        (NodeStatus.RUNNING, NodeStatus.WAITING),
        (NodeStatus.WAITING, NodeStatus.RUNNING),
        (NodeStatus.RUNNING, NodeStatus.RETRYING),
        (NodeStatus.RETRYING, NodeStatus.RUNNING),
        (NodeStatus.RUNNING, NodeStatus.CANCELLING),
        (NodeStatus.CANCELLING, NodeStatus.COMPENSATING),
        (NodeStatus.COMPENSATING, NodeStatus.COMPENSATED),
        (NodeStatus.RUNNING, NodeStatus.SUCCEEDED),
        (NodeStatus.RUNNING, NodeStatus.FAILED),
    )

    assert all(can_transition_node(source, target) for source, target in expected_paths)
    assert not can_transition_node(NodeStatus.PENDING, NodeStatus.SUCCEEDED)
    assert not can_transition_node(NodeStatus.WAITING, NodeStatus.READY)


def test_execution_terminal_states_are_monotonic() -> None:
    terminal_states = {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }

    assert all(EXECUTION_TRANSITIONS[status] == frozenset() for status in terminal_states)
    assert all(
        not can_transition_execution(source, target)
        for source in terminal_states
        for target in ExecutionStatus
    )


def test_node_terminal_states_are_monotonic() -> None:
    terminal_states = {
        NodeStatus.SUCCEEDED,
        NodeStatus.FAILED,
        NodeStatus.CANCELLED,
        NodeStatus.SKIPPED,
        NodeStatus.COMPENSATED,
    }

    assert all(NODE_TRANSITIONS[status] == frozenset() for status in terminal_states)
    assert all(
        not can_transition_node(source, target)
        for source in terminal_states
        for target in NodeStatus
    )
