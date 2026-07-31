"""HTTP transport schemas for episode ingest and read."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from engrammesh.modules.memory.domain.model import (
    RetentionClass,
    Sensitivity,
    SourceType,
)


class _HttpSchemaModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScopeRequest(_HttpSchemaModel):
    """HTTP memory scope with tenant_id for path/body consistency checks."""

    tenant_id: UUID
    subject_id: UUID
    workspace_id: str | None = None
    agent_id: UUID | None = None


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
