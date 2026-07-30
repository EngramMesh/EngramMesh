"""HTTP transport schemas for episode ingest."""

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

    actor_id: UUID
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
