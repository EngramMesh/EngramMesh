"""FastAPI application factory for episode ingest HTTP API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, Query
from starlette.responses import JSONResponse
from starlette.types import Lifespan

from engrammesh.bootstrap.auth.dependencies import episode_auth_context
from engrammesh.bootstrap.auth.ports import TokenVerifierPort
from engrammesh.bootstrap.composition import AppRuntime, ReadinessError
from engrammesh.bootstrap.http.errors import register_exception_handlers
from engrammesh.bootstrap.http.mappers import (
    episode_to_response,
    parse_correlation_id,
    resolve_query_actor_id,
    to_command,
    to_get_episode_query,
    to_list_episodes_query,
    to_response,
)
from engrammesh.bootstrap.http.schemas import ListEpisodesResponse, RecordEpisodeRequest
from engrammesh.shared.kernel.ids import AgentInstanceId, MemoryId, SubjectId, TenantId


def create_app(
    runtime: AppRuntime,
    *,
    lifespan: Lifespan[FastAPI],
    token_verifier: TokenVerifierPort | None = None,
) -> FastAPI:
    """Build the EngramMesh control API with the given runtime and lifespan."""
    verifier = (
        token_verifier if token_verifier is not None else runtime.token_verifier()
    )
    app = FastAPI(
        title="EngramMesh Control API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        try:
            await runtime.check_ready()
        except ReadinessError as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": exc.code},
            )
        return JSONResponse(content={"status": "ready"})

    @app.post("/v1/tenants/{tenant_id}/episodes")
    async def record_episode(
        tenant_id: UUID,
        body: RecordEpisodeRequest,
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> JSONResponse:
        async with episode_auth_context(
            oidc_enabled=runtime.settings.oidc.enabled,
            path_tenant_id=tenant_id,
            authorization=authorization,
            verifier=verifier,
        ) as principal:
            correlation_id = parse_correlation_id(x_correlation_id)
            command = to_command(
                path_tenant_id=TenantId(tenant_id),
                correlation_id=correlation_id,
                body=body,
                principal=principal,
            )
            result = await runtime.record_episode_handler().handle(command)
            response = to_response(result)
            return JSONResponse(
                status_code=201 if result.created else 200,
                content=response.model_dump(),
            )

    @app.get("/v1/tenants/{tenant_id}/episodes/{episode_id}")
    async def get_episode(
        tenant_id: UUID,
        episode_id: UUID,
        subject_id: Annotated[UUID, Query()],
        actor_id: Annotated[UUID | None, Query()] = None,
        workspace_id: Annotated[str | None, Query()] = None,
        agent_id: Annotated[UUID | None, Query()] = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> JSONResponse:
        async with episode_auth_context(
            oidc_enabled=runtime.settings.oidc.enabled,
            path_tenant_id=tenant_id,
            authorization=authorization,
            verifier=verifier,
        ) as principal:
            resolved_actor_id = resolve_query_actor_id(
                principal=principal,
                query_actor_id=actor_id,
            )
            query = to_get_episode_query(
                path_tenant_id=TenantId(tenant_id),
                episode_id=MemoryId(episode_id),
                actor_id=resolved_actor_id,
                subject_id=SubjectId(subject_id),
                workspace_id=workspace_id,
                agent_id=AgentInstanceId(agent_id) if agent_id is not None else None,
            )
            result = await runtime.get_episode_handler().handle(query)
            return JSONResponse(
                content=episode_to_response(result.episode).model_dump(mode="json")
            )

    @app.get("/v1/tenants/{tenant_id}/episodes")
    async def list_episodes(
        tenant_id: UUID,
        subject_id: Annotated[UUID, Query()],
        actor_id: Annotated[UUID | None, Query()] = None,
        workspace_id: Annotated[str | None, Query()] = None,
        agent_id: Annotated[UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query()] = None,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> JSONResponse:
        async with episode_auth_context(
            oidc_enabled=runtime.settings.oidc.enabled,
            path_tenant_id=tenant_id,
            authorization=authorization,
            verifier=verifier,
        ) as principal:
            resolved_actor_id = resolve_query_actor_id(
                principal=principal,
                query_actor_id=actor_id,
            )
            query = to_list_episodes_query(
                path_tenant_id=TenantId(tenant_id),
                actor_id=resolved_actor_id,
                subject_id=SubjectId(subject_id),
                workspace_id=workspace_id,
                agent_id=AgentInstanceId(agent_id) if agent_id is not None else None,
                limit=limit,
                cursor=cursor,
            )
            result = await runtime.list_episodes_handler().handle(query)
            response = ListEpisodesResponse(
                items=tuple(episode_to_response(item) for item in result.items),
                next_cursor=result.next_cursor,
            )
            return JSONResponse(content=response.model_dump(mode="json"))

    return app
