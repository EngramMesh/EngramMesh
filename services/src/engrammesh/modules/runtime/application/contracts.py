from dataclasses import dataclass

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.modules.runtime.domain.model import Budget, ExecutionSnapshot
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    CorrelationId,
    ExecutionId,
    SubjectId,
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class StartExecutionCommand:
    correlation_id: CorrelationId
    actor_id: SubjectId
    scope: MemoryScope
    objective_ref: ArtifactId
    root_agent_id: AgentDefinitionId
    memory_query: MemoryQuery | None
    budget: Budget
    idempotency_key: str

    def __post_init__(self) -> None:
        _require_non_blank(self.idempotency_key, "idempotency_key")


@dataclass(frozen=True, slots=True)
class StartExecutionResult:
    snapshot: ExecutionSnapshot
    created: bool


@dataclass(frozen=True, slots=True)
class GetExecutionSnapshotQuery:
    actor_id: SubjectId
    scope: MemoryScope
    execution_id: ExecutionId


@dataclass(frozen=True, slots=True)
class GetExecutionSnapshotResult:
    snapshot: ExecutionSnapshot


@dataclass(frozen=True, slots=True)
class CancelExecutionCommand:
    correlation_id: CorrelationId
    actor_id: SubjectId
    scope: MemoryScope
    execution_id: ExecutionId
    idempotency_key: str

    def __post_init__(self) -> None:
        _require_non_blank(self.idempotency_key, "idempotency_key")


@dataclass(frozen=True, slots=True)
class CancelExecutionResult:
    snapshot: ExecutionSnapshot
