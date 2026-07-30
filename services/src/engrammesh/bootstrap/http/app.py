"""FastAPI application factory for episode ingest HTTP API."""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Header
from starlette.responses import JSONResponse
from starlette.types import Lifespan

from engrammesh.bootstrap.composition import AppRuntime, ReadinessError
from engrammesh.bootstrap.http.errors import register_exception_handlers
from engrammesh.bootstrap.http.mappers import (
    parse_correlation_id,
    to_command,
    to_response,
)
from engrammesh.bootstrap.http.schemas import RecordEpisodeRequest
from engrammesh.shared.kernel.ids import TenantId


def create_app(
    runtime: AppRuntime,
    *,
    lifespan: Lifespan[FastAPI],
) -> FastAPI:
    """Build the EngramMesh control API with the given runtime and lifespan."""
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
    ) -> JSONResponse:
        correlation_id = parse_correlation_id(x_correlation_id)
        command = to_command(
            path_tenant_id=TenantId(tenant_id),
            correlation_id=correlation_id,
            body=body,
        )
        result = await runtime.record_episode_handler().handle(command)
        response = to_response(result)
        return JSONResponse(
            status_code=201 if result.created else 200,
            content=response.model_dump(),
        )

    return app
