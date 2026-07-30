import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from engrammesh.bootstrap.composition import ReadinessError
from engrammesh.bootstrap.http.errors import (
    error_envelope,
    register_exception_handlers,
)
from engrammesh.bootstrap.http.mappers import (
    InvalidCorrelationIdError,
    TenantMismatchError,
)
from engrammesh.bootstrap.settings import ConfigurationError
from engrammesh.modules.memory.application.errors import EpisodeAuthorizationDenied
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict


def test_error_envelope_builds_canonical_shape() -> None:
    envelope = error_envelope(
        "validation_error",
        "request validation failed",
        details=({"type": "missing", "loc": ("body", "actor_id"), "msg": "required"},),
    )
    assert envelope == {
        "error": {
            "code": "validation_error",
            "message": "request validation failed",
            "details": [
                {
                    "type": "missing",
                    "loc": ("body", "actor_id"),
                    "msg": "required",
                }
            ],
        }
    }


@pytest.fixture
def error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/episode-authorization-denied")
    async def episode_authorization_denied() -> None:
        raise EpisodeAuthorizationDenied()

    @app.get("/episode-idempotency-conflict")
    async def episode_idempotency_conflict() -> None:
        raise EpisodeIdempotencyConflict()

    @app.get("/tenant-mismatch")
    async def tenant_mismatch() -> None:
        raise TenantMismatchError("path tenant_id does not match body scope.tenant_id")

    @app.get("/invalid-correlation-id")
    async def invalid_correlation_id() -> None:
        raise InvalidCorrelationIdError("correlation id must be a UUID")

    @app.get("/configuration-error")
    async def configuration_error() -> None:
        raise ConfigurationError("memory_disabled", "memory module is disabled")

    @app.get("/readiness-error")
    async def readiness_error() -> None:
        raise ReadinessError("runtime_not_started")

    @app.get("/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("unexpected")

    return app


@pytest.mark.asyncio
async def test_episode_authorization_denied_maps_to_403(
    error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/episode-authorization-denied")
    assert response.status_code == 403
    assert response.json() == error_envelope(
        "episode_authorization_denied",
        "episode recording is not authorized",
    )


@pytest.mark.asyncio
async def test_episode_idempotency_conflict_maps_to_409(
    error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/episode-idempotency-conflict")
    assert response.status_code == 409
    assert response.json() == error_envelope(
        "episode_idempotency_conflict",
        "idempotency key conflicts with an existing episode",
    )


@pytest.mark.asyncio
async def test_tenant_mismatch_maps_to_422(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/tenant-mismatch")
    assert response.status_code == 422
    assert response.json() == error_envelope(
        "validation_error",
        "request validation failed",
        details=(
            {
                "type": "value_error",
                "loc": ["scope", "tenant_id"],
                "msg": "path tenant_id does not match body scope.tenant_id",
            },
        ),
    )


@pytest.mark.asyncio
async def test_invalid_correlation_id_maps_to_422(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/invalid-correlation-id")
    assert response.status_code == 422
    assert response.json() == error_envelope(
        "validation_error",
        "request validation failed",
        details=(
            {
                "type": "value_error",
                "loc": ["header", "X-Correlation-Id"],
                "msg": "correlation id must be a UUID",
            },
        ),
    )


@pytest.mark.asyncio
async def test_configuration_error_maps_to_503(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/configuration-error")
    assert response.status_code == 503
    assert response.json() == error_envelope(
        "service_unavailable",
        "service is unavailable",
        details=(
            {
                "type": "configuration_error",
                "loc": [],
                "msg": "memory module is disabled",
                "code": "memory_disabled",
            },
        ),
    )


@pytest.mark.asyncio
async def test_readiness_error_maps_to_503_with_reason(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/readiness-error")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "runtime_not_started",
    }


@pytest.mark.asyncio
async def test_unhandled_exception_maps_to_500(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/unhandled")
    assert response.status_code == 500
    assert response.json() == error_envelope("internal_error", "internal server error")
