"""FastAPI dependencies for Bearer JWT authentication."""

from __future__ import annotations

from contextvars import Token
from types import TracebackType
from typing import final
from uuid import UUID

from engrammesh.bootstrap.auth.context import bind_principal, reset_principal
from engrammesh.bootstrap.auth.errors import (
    AuthenticationRequiredError,
    InvalidTokenError,
    TenantAccessDeniedError,
)
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal, TokenVerifierPort
from engrammesh.shared.kernel.ids import TenantId

_BEARER_PREFIX = "Bearer "


def parse_bearer_token(authorization: str | None) -> str:
    """Extract the JWT from the Authorization header."""
    if authorization is None or not authorization.strip():
        raise AuthenticationRequiredError()
    if not authorization.startswith(_BEARER_PREFIX):
        raise InvalidTokenError()
    token = authorization[len(_BEARER_PREFIX) :]
    if not token:
        raise InvalidTokenError()
    return token


async def authenticate_tenant_request(
    *,
    path_tenant_id: UUID,
    authorization: str | None,
    verifier: TokenVerifierPort,
) -> AuthenticatedPrincipal:
    """Verify Bearer credentials and ensure tenant scope matches the path."""
    token = parse_bearer_token(authorization)
    principal = await verifier.verify(token)
    if principal.tenant_id != TenantId(path_tenant_id):
        raise TenantAccessDeniedError()
    return principal


@final
class PrincipalBinding:
    """Context manager that binds *principal* for the duration of a request handler."""

    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self._principal = principal
        self._token: Token[AuthenticatedPrincipal | None] | None = None

    def __enter__(self) -> AuthenticatedPrincipal:
        self._token = bind_principal(self._principal)
        return self._principal

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            reset_principal(self._token)
