"""HTTP error envelopes and FastAPI exception mapping."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from engrammesh.bootstrap.auth.errors import (
    AuthenticationRequiredError,
    InvalidTokenError,
    TenantAccessDeniedError,
)
from engrammesh.bootstrap.composition import ReadinessError
from engrammesh.bootstrap.http.mappers import (
    ActorIdNotAllowedError,
    ActorIdRequiredError,
    InvalidCorrelationIdError,
    LimitOutOfRangeError,
    TenantMismatchError,
)
from engrammesh.bootstrap.settings import ConfigurationError
from engrammesh.modules.memory.application.errors import (
    EpisodeAuthorizationDenied,
    EpisodeNotFound,
    EpisodeReadAuthorizationDenied,
)
from engrammesh.modules.memory.domain.errors import (
    EpisodeIdempotencyConflict,
    InvalidEpisodeCursor,
)

_EPISODE_AUTHORIZATION_DENIED_MESSAGE = "episode recording is not authorized"
_EPISODE_READ_AUTHORIZATION_DENIED_MESSAGE = "episode reading is not authorized"
_EPISODE_NOT_FOUND_MESSAGE = "episode not found"
_INVALID_EPISODE_CURSOR_MESSAGE = "episode list cursor is invalid"
_EPISODE_IDEMPOTENCY_CONFLICT_MESSAGE = (
    "idempotency key conflicts with an existing episode"
)
_AUTHENTICATION_REQUIRED_MESSAGE = "authentication is required"
_INVALID_TOKEN_MESSAGE = "invalid token"
_TENANT_ACCESS_DENIED_MESSAGE = "tenant access is denied"
_VALIDATION_ERROR_MESSAGE = "request validation failed"
_SERVICE_UNAVAILABLE_MESSAGE = "service is unavailable"
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

    @app.exception_handler(AuthenticationRequiredError)
    async def authentication_required_handler(
        _request: Request,
        _exc: AuthenticationRequiredError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_envelope(
                "authentication_required",
                _AUTHENTICATION_REQUIRED_MESSAGE,
            ),
        )

    @app.exception_handler(InvalidTokenError)
    async def invalid_token_handler(
        _request: Request,
        _exc: InvalidTokenError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content=error_envelope("invalid_token", _INVALID_TOKEN_MESSAGE),
        )

    @app.exception_handler(TenantAccessDeniedError)
    async def tenant_access_denied_handler(
        _request: Request,
        _exc: TenantAccessDeniedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "tenant_access_denied",
                _TENANT_ACCESS_DENIED_MESSAGE,
            ),
        )

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

    @app.exception_handler(EpisodeReadAuthorizationDenied)
    async def episode_read_authorization_denied_handler(
        _request: Request,
        _exc: EpisodeReadAuthorizationDenied,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=error_envelope(
                "episode_read_authorization_denied",
                _EPISODE_READ_AUTHORIZATION_DENIED_MESSAGE,
            ),
        )

    @app.exception_handler(EpisodeNotFound)
    async def episode_not_found_handler(
        _request: Request,
        _exc: EpisodeNotFound,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=error_envelope(
                "episode_not_found",
                _EPISODE_NOT_FOUND_MESSAGE,
            ),
        )

    @app.exception_handler(InvalidEpisodeCursor)
    async def invalid_episode_cursor_handler(
        _request: Request,
        _exc: InvalidEpisodeCursor,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "invalid_episode_cursor",
                _INVALID_EPISODE_CURSOR_MESSAGE,
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

    @app.exception_handler(ActorIdNotAllowedError)
    async def actor_id_not_allowed_handler(
        _request: Request,
        exc: ActorIdNotAllowedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope("actor_id_not_allowed", str(exc)),
        )

    @app.exception_handler(ActorIdRequiredError)
    async def actor_id_required_handler(
        _request: Request,
        exc: ActorIdRequiredError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope("actor_id_required", str(exc)),
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

    @app.exception_handler(LimitOutOfRangeError)
    async def limit_out_of_range_handler(
        _request: Request,
        exc: LimitOutOfRangeError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error",
                _VALIDATION_ERROR_MESSAGE,
                details=(
                    {
                        "type": "value_error",
                        "loc": ["query", "limit"],
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
                _SERVICE_UNAVAILABLE_MESSAGE,
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
