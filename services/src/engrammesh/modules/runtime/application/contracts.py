from dataclasses import dataclass
from datetime import datetime

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionStatus,
)
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


@dataclass(frozen=True, slots=True)
class ListExecutionsQuery:
    actor_id: SubjectId
    scope: MemoryScope
    limit: int
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.limit <= 0 or self.limit > 100:
            raise ValueError("limit must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class ExecutionListItem:
    execution_id: ExecutionId
    scope: MemoryScope
    revision: int
    status: ExecutionStatus
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ListExecutionsResult:
    items: tuple[ExecutionListItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RelayRuntimeOutboxCommand:
    batch_size: int


@dataclass(frozen=True, slots=True)
class RelayRuntimeOutboxResult:
    fetched: int
    dispatched: int
    published: int
    remaining_unpublished: int
