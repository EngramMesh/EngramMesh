"""HTTP transport mappers for episode ingest."""

from uuid import UUID

from engrammesh.bootstrap.http.schemas import (
    RecordEpisodeRequest,
    RecordEpisodeResponse,
)
from engrammesh.modules.memory.application.contracts import (
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.domain.model import MemoryScope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)


class TenantMismatchError(ValueError):
    """Path tenant_id does not match body scope.tenant_id."""


class InvalidCorrelationIdError(ValueError):
    """X-Correlation-Id header is not a valid UUID."""


def parse_correlation_id(header_value: str | None) -> CorrelationId:
    """Parse or generate a correlation identifier from an HTTP header value."""
    if header_value is None:
        return CorrelationId.new()
    try:
        return CorrelationId(UUID(header_value))
    except ValueError:
        raise InvalidCorrelationIdError("correlation id must be a UUID")


def to_command(
    *,
    path_tenant_id: TenantId,
    correlation_id: CorrelationId,
    body: RecordEpisodeRequest,
) -> RecordEpisodeCommand:
    """Map an HTTP request body to a record-episode application command."""
    if body.scope.tenant_id != path_tenant_id.value:
        raise TenantMismatchError(
            "path tenant_id does not match body scope.tenant_id"
        )
    return RecordEpisodeCommand(
        correlation_id=correlation_id,
        actor_id=SubjectId(body.actor_id),
        scope=MemoryScope(
            tenant_id=path_tenant_id,
            subject_id=SubjectId(body.scope.subject_id),
            workspace_id=body.scope.workspace_id,
            agent_id=(
                AgentInstanceId(body.scope.agent_id)
                if body.scope.agent_id is not None
                else None
            ),
        ),
        source_type=body.source_type,
        content_ref=ArtifactId(body.content_ref),
        observed_at=body.observed_at,
        content_hash=body.content_hash,
        idempotency_key=body.idempotency_key,
        sensitivity=body.sensitivity,
        retention_class=body.retention_class,
        consent_basis=body.consent_basis,
    )


def to_response(result: RecordEpisodeResult) -> RecordEpisodeResponse:
    """Map a record-episode application result to an HTTP response body."""
    return RecordEpisodeResponse(
        episode_id=str(result.episode_id.value),
        created=result.created,
    )
