"""Pure legal-transition predicates for durable execution state."""

from collections.abc import Mapping
from types import MappingProxyType

from engrammesh.modules.runtime.domain.model import ExecutionStatus, NodeStatus

EXECUTION_TRANSITIONS: Mapping[ExecutionStatus, frozenset[ExecutionStatus]] = (
    MappingProxyType(
        {
            ExecutionStatus.PENDING: frozenset(
                {
                    ExecutionStatus.PLANNING,
                    ExecutionStatus.CANCELLING,
                }
            ),
            ExecutionStatus.PLANNING: frozenset(
                {
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.WAITING,
                    ExecutionStatus.CANCELLING,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.RUNNING: frozenset(
                {
                    ExecutionStatus.WAITING,
                    ExecutionStatus.RETRYING,
                    ExecutionStatus.CANCELLING,
                    ExecutionStatus.COMPENSATING,
                    ExecutionStatus.SUCCEEDED,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.WAITING: frozenset(
                {
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.CANCELLING,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.RETRYING: frozenset(
                {
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.CANCELLING,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.CANCELLING: frozenset(
                {
                    ExecutionStatus.COMPENSATING,
                    ExecutionStatus.CANCELLED,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.COMPENSATING: frozenset(
                {
                    ExecutionStatus.CANCELLED,
                    ExecutionStatus.FAILED,
                }
            ),
            ExecutionStatus.SUCCEEDED: frozenset(),
            ExecutionStatus.FAILED: frozenset(),
            ExecutionStatus.CANCELLED: frozenset(),
        }
    )
)

NODE_TRANSITIONS: Mapping[NodeStatus, frozenset[NodeStatus]] = MappingProxyType(
    {
        NodeStatus.PENDING: frozenset(
            {
                NodeStatus.READY,
                NodeStatus.SKIPPED,
                NodeStatus.CANCELLED,
            }
        ),
        NodeStatus.READY: frozenset(
            {
                NodeStatus.RUNNING,
                NodeStatus.SKIPPED,
                NodeStatus.CANCELLED,
            }
        ),
        NodeStatus.RUNNING: frozenset(
            {
                NodeStatus.WAITING,
                NodeStatus.RETRYING,
                NodeStatus.CANCELLING,
                NodeStatus.COMPENSATING,
                NodeStatus.SUCCEEDED,
                NodeStatus.FAILED,
            }
        ),
        NodeStatus.WAITING: frozenset(
            {
                NodeStatus.RUNNING,
                NodeStatus.CANCELLING,
                NodeStatus.FAILED,
            }
        ),
        NodeStatus.RETRYING: frozenset(
            {
                NodeStatus.RUNNING,
                NodeStatus.CANCELLING,
                NodeStatus.FAILED,
            }
        ),
        NodeStatus.CANCELLING: frozenset(
            {
                NodeStatus.COMPENSATING,
                NodeStatus.CANCELLED,
                NodeStatus.FAILED,
            }
        ),
        NodeStatus.COMPENSATING: frozenset(
            {
                NodeStatus.COMPENSATED,
                NodeStatus.FAILED,
            }
        ),
        NodeStatus.SUCCEEDED: frozenset(),
        NodeStatus.FAILED: frozenset(),
        NodeStatus.CANCELLED: frozenset(),
        NodeStatus.SKIPPED: frozenset(),
        NodeStatus.COMPENSATED: frozenset(),
    }
)


def can_transition_execution(
    current: ExecutionStatus,
    target: ExecutionStatus,
) -> bool:
    """Return whether the execution transition is legal."""
    return target in EXECUTION_TRANSITIONS[current]


def can_transition_node(current: NodeStatus, target: NodeStatus) -> bool:
    """Return whether the node transition is legal."""
    return target in NODE_TRANSITIONS[current]
