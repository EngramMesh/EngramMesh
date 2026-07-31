"""HTTP transport mappers for episode ingest and read."""

from uuid import UUID

from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.http.schemas import (
    EpisodeResponse,
    RecordEpisodeRequest,
    RecordEpisodeResponse,
    ScopeResponse,
)
from engrammesh.modules.memory.application.contracts import (
    GetEpisodeQuery,
    ListEpisodesQuery,
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.domain.model import Episode, MemoryScope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    MemoryId,
    SubjectId,
    TenantId,
)


class TenantMismatchError(ValueError):
    """Path tenant_id does not match body scope.tenant_id."""


class InvalidCorrelationIdError(ValueError):
    """X-Correlation-Id header is not a valid UUID."""


class LimitOutOfRangeError(ValueError):
    """HTTP list limit outside allowed bounds."""


class ActorIdNotAllowedError(ValueError):
    """actor_id must not be supplied when a principal is authenticated."""


class ActorIdRequiredError(ValueError):
    """actor_id is required when no principal is authenticated."""


def _resolve_actor_id(
    *,
    principal: AuthenticatedPrincipal | None,
    body_or_query_actor_id: UUID | None,
) -> SubjectId:
    """Resolve actor_id from JWT principal or explicit request value."""
    if principal is not None:
        if body_or_query_actor_id is not None:
            raise ActorIdNotAllowedError(
                "actor_id must not be provided when authenticated"
            )
        return principal.actor_id
    if body_or_query_actor_id is None:
        raise ActorIdRequiredError("actor_id is required when not authenticated")
    return SubjectId(body_or_query_actor_id)


def resolve_query_actor_id(
    *,
    principal: AuthenticatedPrincipal | None,
    query_actor_id: UUID | None,
) -> SubjectId:
    """Resolve actor_id for episode read query parameters."""
    return _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=query_actor_id,
    )


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
    principal: AuthenticatedPrincipal | None = None,
) -> RecordEpisodeCommand:
    """Map an HTTP request body to a record-episode application command."""
    if body.scope.tenant_id != path_tenant_id.value:
        raise TenantMismatchError(
            "path tenant_id does not match body scope.tenant_id"
        )
    actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=body.actor_id,
    )
    return RecordEpisodeCommand(
        correlation_id=correlation_id,
        actor_id=actor_id,
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


def episode_to_response(episode: Episode) -> EpisodeResponse:
    """Map a domain episode to an HTTP response body."""
    return EpisodeResponse(
        episode_id=str(episode.id.value),
        scope=ScopeResponse(
            tenant_id=episode.scope.tenant_id.value,
            subject_id=episode.scope.subject_id.value,
            workspace_id=episode.scope.workspace_id,
            agent_id=(
                episode.scope.agent_id.value
                if episode.scope.agent_id is not None
                else None
            ),
        ),
        actor_id=episode.actor_id.value,
        source_type=episode.source_type,
        content_ref=episode.content_ref.value,
        observed_at=episode.observed_at,
        ingested_at=episode.ingested_at,
        content_hash=episode.content_hash,
        idempotency_key=episode.idempotency_key,
        sensitivity=episode.sensitivity,
        retention_class=episode.retention_class,
        consent_basis=episode.consent_basis,
    )


def to_get_episode_query(
    *,
    path_tenant_id: TenantId,
    episode_id: MemoryId,
    actor_id: SubjectId | None = None,
    subject_id: SubjectId,
    workspace_id: str | None,
    agent_id: AgentInstanceId | None,
    principal: AuthenticatedPrincipal | None = None,
) -> GetEpisodeQuery:
    """Map HTTP path and query parameters to a get-episode application query."""
    resolved_actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=actor_id.value if actor_id is not None else None,
    )
    return GetEpisodeQuery(
        actor_id=resolved_actor_id,
        scope=MemoryScope(
            tenant_id=path_tenant_id,
            subject_id=subject_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
        ),
        episode_id=episode_id,
    )


def to_list_episodes_query(
    *,
    path_tenant_id: TenantId,
    actor_id: SubjectId | None = None,
    subject_id: SubjectId,
    workspace_id: str | None,
    agent_id: AgentInstanceId | None,
    limit: int,
    cursor: str | None,
    principal: AuthenticatedPrincipal | None = None,
) -> ListEpisodesQuery:
    """Map HTTP path and query parameters to a list-episodes application query."""
    if limit < 1 or limit > 100:
        raise LimitOutOfRangeError("limit must be between 1 and 100")
    resolved_actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=actor_id.value if actor_id is not None else None,
    )
    return ListEpisodesQuery(
        actor_id=resolved_actor_id,
        scope=MemoryScope(
            tenant_id=path_tenant_id,
            subject_id=subject_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
        ),
        limit=limit,
        cursor=cursor,
    )
