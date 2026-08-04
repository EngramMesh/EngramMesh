"""HTTP transport schemas for episode ingest, read, and execution."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from engrammesh.modules.memory.domain.model import (
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.runtime.domain.model import (
    ExecutionStatus,
    FailureCategory,
    NodeStatus,
    SuspensionKind,
)


class _HttpSchemaModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)
    return value


def _require_timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)
    return value


class ScopeRequest(_HttpSchemaModel):
    """HTTP memory scope with tenant_id for path/body consistency checks."""

    tenant_id: UUID
    subject_id: UUID
    workspace_id: str | None = None
    agent_id: UUID | None = None

    @field_validator("workspace_id")
    @classmethod
    def _validate_workspace_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, "workspace_id")


class RecordEpisodeRequest(_HttpSchemaModel):
    """HTTP request body for recording one episode."""

    actor_id: UUID | None = None
    scope: ScopeRequest
    source_type: SourceType
    content_ref: UUID
    observed_at: datetime
    content_hash: str
    idempotency_key: str
    sensitivity: Sensitivity
    retention_class: RetentionClass
    consent_basis: str


class RecordEpisodeResponse(_HttpSchemaModel):
    """HTTP response body for a recorded or replayed episode."""

    episode_id: str
    created: bool


class ScopeResponse(_HttpSchemaModel):
    """HTTP memory scope in episode read responses."""

    tenant_id: UUID
    subject_id: UUID
    workspace_id: str | None = None
    agent_id: UUID | None = None


class EpisodeResponse(_HttpSchemaModel):
    """HTTP response body for one episode."""

    episode_id: str
    scope: ScopeResponse
    actor_id: UUID
    source_type: SourceType
    content_ref: UUID
    observed_at: datetime
    ingested_at: datetime
    content_hash: str
    idempotency_key: str
    sensitivity: Sensitivity
    retention_class: RetentionClass
    consent_basis: str


class ListEpisodesResponse(_HttpSchemaModel):
    """HTTP response body for a paginated episode list."""

    items: tuple[EpisodeResponse, ...]
    next_cursor: str | None


class BudgetRequest(_HttpSchemaModel):
    """HTTP request body for execution budget limits."""

    max_input_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(ge=0)
    max_cost_micros: int = Field(ge=0)
    deadline: datetime

    @field_validator("deadline")
    @classmethod
    def _validate_deadline(cls, value: datetime) -> datetime:
        return _require_timezone_aware(value, "deadline")


class MemoryQueryRequest(_HttpSchemaModel):
    """HTTP request body for optional execution memory context."""

    query_id: str
    scope: ScopeRequest
    text: str
    valid_at: datetime | None = None
    recorded_at: datetime | None = None
    limit: int = Field(default=10, gt=0)

    @field_validator("query_id")
    @classmethod
    def _validate_query_id(cls, value: str) -> str:
        return _require_non_blank(value, "query_id")

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _require_non_blank(value, "text")

    @field_validator("valid_at", "recorded_at")
    @classmethod
    def _validate_optional_timestamps(
        cls,
        value: datetime | None,
        info: ValidationInfo,
    ) -> datetime | None:
        if value is None:
            return None
        field_name = info.field_name or "timestamp"
        return _require_timezone_aware(value, field_name)


class StartExecutionRequest(_HttpSchemaModel):
    """HTTP request body for starting one durable execution."""

    actor_id: UUID | None = None
    scope: ScopeRequest
    objective_ref: UUID
    root_agent_id: UUID
    memory_query: MemoryQueryRequest | None = None
    budget: BudgetRequest
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _validate_idempotency_key(cls, value: str) -> str:
        return _require_non_blank(value, "idempotency_key")


class CancelExecutionRequest(_HttpSchemaModel):
    """HTTP request body for cancelling one durable execution."""

    actor_id: UUID | None = None
    scope: ScopeRequest
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _validate_idempotency_key(cls, value: str) -> str:
        return _require_non_blank(value, "idempotency_key")


class FailureResponse(_HttpSchemaModel):
    """HTTP response body for a classified execution failure."""

    category: FailureCategory
    code: str
    message: str
    details_ref: UUID | None = None


class SuspensionResponse(_HttpSchemaModel):
    """HTTP response body for a durable execution suspension."""

    request_id: str
    idempotency_key: str
    execution_id: UUID
    node_id: UUID | None = None
    kind: SuspensionKind
    request_ref: UUID
    requested_at: datetime
    expires_at: datetime


class ExecutionSnapshotResponse(_HttpSchemaModel):
    """HTTP response body for one durable execution snapshot."""

    execution_id: UUID
    scope: ScopeResponse
    revision: int
    status: ExecutionStatus
    plan_revision: int | None = None
    node_statuses: dict[str, NodeStatus]
    suspension: SuspensionResponse | None = None
    result_ref: UUID | None = None
    failure: FailureResponse | None = None
    updated_at: datetime


class StartExecutionResponse(ExecutionSnapshotResponse):
    """HTTP response body for a started or replayed execution."""

    created: bool
