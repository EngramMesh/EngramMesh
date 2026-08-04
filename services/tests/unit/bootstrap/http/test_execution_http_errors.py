import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from engrammesh.bootstrap.http.errors import (
    error_envelope,
    register_exception_handlers,
)
from engrammesh.bootstrap.http.mappers import MemoryQueryScopeMismatchError
from engrammesh.modules.runtime.application.errors import (
    ExecutionAuthorizationDenied,
    OrchestrationUnavailable,
)
from engrammesh.modules.runtime.domain.errors import (
    ExecutionIdempotencyConflict,
    ExecutionNotFound,
    InvalidExecutionTransition,
)


@pytest.fixture
def execution_error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/execution-authorization-denied")
    async def execution_authorization_denied() -> None:
        raise ExecutionAuthorizationDenied()

    @app.get("/execution-not-found")
    async def execution_not_found() -> None:
        raise ExecutionNotFound()

    @app.get("/execution-idempotency-conflict")
    async def execution_idempotency_conflict() -> None:
        raise ExecutionIdempotencyConflict()

    @app.get("/invalid-execution-transition")
    async def invalid_execution_transition() -> None:
        raise InvalidExecutionTransition()

    @app.get("/orchestration-unavailable")
    async def orchestration_unavailable() -> None:
        raise OrchestrationUnavailable()

    @app.get("/memory-query-scope-mismatch")
    async def memory_query_scope_mismatch() -> None:
        raise MemoryQueryScopeMismatchError(
            "memory_query.scope must match execution scope"
        )

    return app


@pytest.mark.asyncio
async def test_execution_authorization_denied_maps_to_403(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/execution-authorization-denied")
    assert response.status_code == 403
    assert response.json() == error_envelope(
        "execution_authorization_denied",
        "execution is not authorized",
    )


@pytest.mark.asyncio
async def test_execution_not_found_maps_to_404(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/execution-not-found")
    assert response.status_code == 404
    assert response.json() == error_envelope(
        "execution_not_found",
        "execution not found",
    )


@pytest.mark.asyncio
async def test_execution_idempotency_conflict_maps_to_409(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/execution-idempotency-conflict")
    assert response.status_code == 409
    assert response.json() == error_envelope(
        "execution_idempotency_conflict",
        "idempotency key conflicts with an existing execution",
    )


@pytest.mark.asyncio
async def test_invalid_execution_transition_maps_to_409(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/invalid-execution-transition")
    assert response.status_code == 409
    assert response.json() == error_envelope(
        "invalid_execution_transition",
        "execution transition is not allowed",
    )


@pytest.mark.asyncio
async def test_orchestration_unavailable_maps_to_503(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/orchestration-unavailable")
    assert response.status_code == 503
    assert response.json() == error_envelope(
        "orchestration_unavailable",
        "orchestration backend is unavailable",
    )


@pytest.mark.asyncio
async def test_memory_query_scope_mismatch_maps_to_422(
    execution_error_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=execution_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/memory-query-scope-mismatch")
    assert response.status_code == 422
    assert response.json() == error_envelope(
        "validation_error",
        "request validation failed",
        details=(
            {
                "type": "value_error",
                "loc": ["memory_query", "scope"],
                "msg": "memory_query.scope must match execution scope",
            },
        ),
    )
