"""HTTP transport mappers for episode ingest, read, and execution."""

from uuid import UUID

from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.http.schemas import (
    BudgetRequest,
    CancelExecutionRequest,
    EpisodeResponse,
    ExecutionSnapshotResponse,
    FailureResponse,
    MemoryQueryRequest,
    RecordEpisodeRequest,
    RecordEpisodeResponse,
    ScopeRequest,
    ScopeResponse,
    StartExecutionRequest,
    StartExecutionResponse,
    SuspensionResponse,
)
from engrammesh.modules.memory.application.contracts import (
    GetEpisodeQuery,
    ListEpisodesQuery,
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.domain.model import Episode, MemoryScope
from engrammesh.modules.memory.ports import MemoryQuery
from engrammesh.modules.runtime.application.contracts import (
    CancelExecutionCommand,
    GetExecutionSnapshotQuery,
    StartExecutionCommand,
    StartExecutionResult,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    Failure,
    Suspension,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    ExecutionId,
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


class MemoryQueryScopeMismatchError(ValueError):
    """memory_query.scope does not match execution scope."""


def _scope_from_request(
    *,
    path_tenant_id: TenantId,
    scope: ScopeRequest,
) -> MemoryScope:
    """Map an HTTP scope request to a domain memory scope."""
    if scope.tenant_id != path_tenant_id.value:
        raise TenantMismatchError(
            "path tenant_id does not match body scope.tenant_id"
        )
    return MemoryScope(
        tenant_id=path_tenant_id,
        subject_id=SubjectId(scope.subject_id),
        workspace_id=scope.workspace_id,
        agent_id=(
            AgentInstanceId(scope.agent_id)
            if scope.agent_id is not None
            else None
        ),
    )


def _budget_from_request(budget: BudgetRequest) -> Budget:
    """Map an HTTP budget request to a domain execution budget."""
    return Budget(
        max_input_tokens=budget.max_input_tokens,
        max_output_tokens=budget.max_output_tokens,
        max_cost_micros=budget.max_cost_micros,
        deadline=budget.deadline,
    )


def _memory_query_from_request(
    *,
    memory_query: MemoryQueryRequest,
    execution_scope: MemoryScope,
) -> MemoryQuery:
    """Map an HTTP memory query request to a domain memory query."""
    query_scope = MemoryScope(
        tenant_id=TenantId(memory_query.scope.tenant_id),
        subject_id=SubjectId(memory_query.scope.subject_id),
        workspace_id=memory_query.scope.workspace_id,
        agent_id=(
            AgentInstanceId(memory_query.scope.agent_id)
            if memory_query.scope.agent_id is not None
            else None
        ),
    )
    if query_scope != execution_scope:
        raise MemoryQueryScopeMismatchError(
            "memory_query.scope must match execution scope"
        )
    return MemoryQuery(
        query_id=memory_query.query_id,
        scope=query_scope,
        text=memory_query.text,
        valid_at=memory_query.valid_at,
        recorded_at=memory_query.recorded_at,
        limit=memory_query.limit,
    )


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


def to_start_execution_command(
    *,
    path_tenant_id: TenantId,
    correlation_id: CorrelationId,
    body: StartExecutionRequest,
    principal: AuthenticatedPrincipal | None = None,
) -> StartExecutionCommand:
    """Map an HTTP request body to a start-execution application command."""
    scope = _scope_from_request(path_tenant_id=path_tenant_id, scope=body.scope)
    actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=body.actor_id,
    )
    memory_query = (
        _memory_query_from_request(
            memory_query=body.memory_query,
            execution_scope=scope,
        )
        if body.memory_query is not None
        else None
    )
    return StartExecutionCommand(
        correlation_id=correlation_id,
        actor_id=actor_id,
        scope=scope,
        objective_ref=ArtifactId(body.objective_ref),
        root_agent_id=AgentDefinitionId(body.root_agent_id),
        memory_query=memory_query,
        budget=_budget_from_request(body.budget),
        idempotency_key=body.idempotency_key,
    )


def to_get_execution_snapshot_query(
    *,
    path_tenant_id: TenantId,
    execution_id: ExecutionId,
    actor_id: SubjectId | None = None,
    subject_id: SubjectId,
    workspace_id: str | None,
    agent_id: AgentInstanceId | None,
    principal: AuthenticatedPrincipal | None = None,
) -> GetExecutionSnapshotQuery:
    """Map HTTP path and query parameters to a get-snapshot application query."""
    resolved_actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=actor_id.value if actor_id is not None else None,
    )
    return GetExecutionSnapshotQuery(
        actor_id=resolved_actor_id,
        scope=MemoryScope(
            tenant_id=path_tenant_id,
            subject_id=subject_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
        ),
        execution_id=execution_id,
    )


def to_cancel_execution_command(
    *,
    path_tenant_id: TenantId,
    correlation_id: CorrelationId,
    execution_id: ExecutionId,
    body: CancelExecutionRequest,
    principal: AuthenticatedPrincipal | None = None,
) -> CancelExecutionCommand:
    """Map an HTTP request body to a cancel-execution application command."""
    scope = _scope_from_request(path_tenant_id=path_tenant_id, scope=body.scope)
    actor_id = _resolve_actor_id(
        principal=principal,
        body_or_query_actor_id=body.actor_id,
    )
    return CancelExecutionCommand(
        correlation_id=correlation_id,
        actor_id=actor_id,
        scope=scope,
        execution_id=execution_id,
        idempotency_key=body.idempotency_key,
    )


def _failure_to_response(failure: Failure) -> FailureResponse:
    return FailureResponse(
        category=failure.category,
        code=failure.code,
        message=failure.message,
        details_ref=(
            failure.details_ref.value
            if failure.details_ref is not None
            else None
        ),
    )


def _suspension_to_response(suspension: Suspension) -> SuspensionResponse:
    return SuspensionResponse(
        request_id=suspension.request_id,
        idempotency_key=suspension.idempotency_key,
        execution_id=suspension.execution_id.value,
        node_id=(
            suspension.node_id.value
            if suspension.node_id is not None
            else None
        ),
        kind=suspension.kind,
        request_ref=suspension.request_ref.value,
        requested_at=suspension.requested_at,
        expires_at=suspension.expires_at,
    )


def snapshot_to_response(snapshot: ExecutionSnapshot) -> ExecutionSnapshotResponse:
    """Map a domain execution snapshot to an HTTP response body."""
    return ExecutionSnapshotResponse(
        execution_id=snapshot.execution_id.value,
        scope=ScopeResponse(
            tenant_id=snapshot.scope.tenant_id.value,
            subject_id=snapshot.scope.subject_id.value,
            workspace_id=snapshot.scope.workspace_id,
            agent_id=(
                snapshot.scope.agent_id.value
                if snapshot.scope.agent_id is not None
                else None
            ),
        ),
        revision=snapshot.revision,
        status=snapshot.status,
        plan_revision=snapshot.plan_revision,
        node_statuses={
            str(node_id): status
            for node_id, status in snapshot.node_statuses.items()
        },
        suspension=(
            _suspension_to_response(snapshot.suspension)
            if snapshot.suspension is not None
            else None
        ),
        result_ref=(
            snapshot.result_ref.value
            if snapshot.result_ref is not None
            else None
        ),
        failure=(
            _failure_to_response(snapshot.failure)
            if snapshot.failure is not None
            else None
        ),
        updated_at=snapshot.updated_at,
    )


def start_result_to_response(result: StartExecutionResult) -> StartExecutionResponse:
    """Map a start-execution application result to an HTTP response body."""
    snapshot_response = snapshot_to_response(result.snapshot)
    return StartExecutionResponse(
        **snapshot_response.model_dump(),
        created=result.created,
    )
