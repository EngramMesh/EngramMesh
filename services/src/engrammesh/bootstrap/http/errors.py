"""HTTP error envelopes and FastAPI exception mapping."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from engrammesh.bootstrap.composition import ReadinessError
from engrammesh.bootstrap.http.mappers import (
    InvalidCorrelationIdError,
    TenantMismatchError,
)
from engrammesh.bootstrap.settings import ConfigurationError
from engrammesh.modules.memory.application.errors import EpisodeAuthorizationDenied
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict

_EPISODE_AUTHORIZATION_DENIED_MESSAGE = "episode recording is not authorized"
_EPISODE_IDEMPOTENCY_CONFLICT_MESSAGE = (
    "idempotency key conflicts with an existing episode"
)
_VALIDATION_ERROR_MESSAGE = "request validation failed"
_INTERNAL_ERROR_MESSAGE = "internal server error"


def error_envelope(
    code: str,
    message: str,
    details: tuple[dict[str, Any], ...] = (),
) -> dict[str, dict[str, Any]]:
    """Build the canonical HTTP error response envelope."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": list(details),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register HTTP exception handlers for episode ingest error mapping."""

    @app.exception_handler(EpisodeAuthorizationDenied)
    async def episode_authorization_denied_handler(
        _request: Request,
        _exc: EpisodeAuthorizationDenied,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "episode_authorization_denied",
                _EPISODE_AUTHORIZATION_DENIED_MESSAGE,
            ),
        )

    @app.exception_handler(EpisodeIdempotencyConflict)
    async def episode_idempotency_conflict_handler(
        _request: Request,
        _exc: EpisodeIdempotencyConflict,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_envelope(
                "episode_idempotency_conflict",
                _EPISODE_IDEMPOTENCY_CONFLICT_MESSAGE,
            ),
        )

    @app.exception_handler(TenantMismatchError)
    async def tenant_mismatch_handler(
        _request: Request,
        exc: TenantMismatchError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error",
                _VALIDATION_ERROR_MESSAGE,
                details=(
                    {
                        "type": "value_error",
                        "loc": ["scope", "tenant_id"],
                        "msg": str(exc),
                    },
                ),
            ),
        )

    @app.exception_handler(InvalidCorrelationIdError)
    async def invalid_correlation_id_handler(
        _request: Request,
        exc: InvalidCorrelationIdError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error",
                _VALIDATION_ERROR_MESSAGE,
                details=(
                    {
                        "type": "value_error",
                        "loc": ["header", "X-Correlation-Id"],
                        "msg": str(exc),
                    },
                ),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error",
                _VALIDATION_ERROR_MESSAGE,
                details=tuple(exc.errors()),
            ),
        )

    @app.exception_handler(ConfigurationError)
    async def configuration_error_handler(
        _request: Request,
        exc: ConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_envelope(
                "service_unavailable",
                str(exc),
                details=exc.errors(),
            ),
        )

    @app.exception_handler(ReadinessError)
    async def readiness_error_handler(
        _request: Request,
        exc: ReadinessError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": exc.code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_envelope("internal_error", _INTERNAL_ERROR_MESSAGE),
        )
