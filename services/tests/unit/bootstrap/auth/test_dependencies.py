from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from engrammesh.bootstrap.auth.context import current_principal
from engrammesh.bootstrap.auth.dependencies import (
    PrincipalBinding,
    authenticate_tenant_request,
    parse_bearer_token,
)
from engrammesh.bootstrap.auth.errors import (
    AuthenticationRequiredError,
    InvalidTokenError,
    TenantAccessDeniedError,
)
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.http.errors import error_envelope, register_exception_handlers
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ISSUER = "https://dev.engrammesh.test"
SIGNING_KEY = "dev-only-signing-key-not-for-production"
ACTOR_ID = UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6")
TENANT_ID = UUID("53dad495-7915-439a-b03a-379452a1aa86")
OTHER_TENANT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _mint_token(*, tenant_id: UUID = TENANT_ID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(ACTOR_ID),
        "tenant_id": str(tenant_id),
        "iss": ISSUER,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, SIGNING_KEY, algorithm="HS256")


@pytest.mark.parametrize(
    "authorization",
    [None, "", "   "],
)
def test_parse_bearer_token_requires_authorization_header(
    authorization: str | None,
) -> None:
    with pytest.raises(AuthenticationRequiredError):
        parse_bearer_token(authorization)


@pytest.mark.parametrize(
    "authorization",
    ["Basic abc", "Bearer", "Bearer ", "bearer token", "Token abc"],
)
def test_parse_bearer_token_rejects_malformed_scheme(authorization: str) -> None:
    with pytest.raises(InvalidTokenError):
        parse_bearer_token(authorization)


def test_parse_bearer_token_extracts_jwt() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    assert parse_bearer_token(f"Bearer {token}") == token


@pytest.mark.asyncio
async def test_authenticate_tenant_request_returns_verified_principal() -> None:
    token = _mint_token()
    principal = AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )
    verifier = AsyncMock()
    verifier.verify.return_value = principal

    result = await authenticate_tenant_request(
        path_tenant_id=TENANT_ID,
        authorization=f"Bearer {token}",
        verifier=verifier,
    )

    assert result == principal
    verifier.verify.assert_awaited_once_with(token)


@pytest.mark.asyncio
async def test_authenticate_tenant_request_requires_authorization_header() -> None:
    verifier = AsyncMock()

    with pytest.raises(AuthenticationRequiredError):
        await authenticate_tenant_request(
            path_tenant_id=TENANT_ID,
            authorization=None,
            verifier=verifier,
        )

    verifier.verify.assert_not_called()


@pytest.mark.asyncio
async def test_authenticate_tenant_request_propagates_invalid_token() -> None:
    verifier = AsyncMock()
    verifier.verify.side_effect = InvalidTokenError()

    with pytest.raises(InvalidTokenError):
        await authenticate_tenant_request(
            path_tenant_id=TENANT_ID,
            authorization="Bearer invalid-token",
            verifier=verifier,
        )


@pytest.mark.asyncio
async def test_authenticate_tenant_request_denies_other_tenant() -> None:
    token = _mint_token()
    principal = AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )
    verifier = AsyncMock()
    verifier.verify.return_value = principal

    with pytest.raises(TenantAccessDeniedError):
        await authenticate_tenant_request(
            path_tenant_id=OTHER_TENANT_ID,
            authorization=f"Bearer {token}",
            verifier=verifier,
        )


def test_principal_binding_sets_and_resets_principal() -> None:
    principal = AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )

    with PrincipalBinding(principal):
        assert current_principal() == principal

    with pytest.raises(AuthenticationRequiredError):
        current_principal()


def test_principal_binding_resets_principal_when_handler_raises() -> None:
    principal = AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )

    with (
        pytest.raises(RuntimeError, match="handler failed"),
        PrincipalBinding(principal),
    ):
        raise RuntimeError("handler failed")

    with pytest.raises(AuthenticationRequiredError):
        current_principal()


@pytest.fixture
def auth_error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/authentication-required")
    async def authentication_required() -> None:
        raise AuthenticationRequiredError()

    @app.get("/invalid-token")
    async def invalid_token() -> None:
        raise InvalidTokenError()

    @app.get("/tenant-access-denied")
    async def tenant_access_denied() -> None:
        raise TenantAccessDeniedError()

    return app


@pytest.mark.asyncio
async def test_authentication_required_maps_to_401(auth_error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=auth_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/authentication-required")
    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )


@pytest.mark.asyncio
async def test_invalid_token_maps_to_401(auth_error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=auth_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/invalid-token")
    assert response.status_code == 401
    assert response.json() == error_envelope("invalid_token", "invalid token")


@pytest.mark.asyncio
async def test_tenant_access_denied_maps_to_403(auth_error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=auth_error_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/tenant-access-denied")
    assert response.status_code == 403
    assert response.json() == error_envelope(
        "tenant_access_denied",
        "tenant access is denied",
    )
