"""Request-scoped principal binding via ContextVar."""

from __future__ import annotations

from contextvars import ContextVar, Token

from engrammesh.bootstrap.auth.errors import AuthenticationRequiredError
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal

_principal: ContextVar[AuthenticatedPrincipal | None] = ContextVar(
    "principal",
    default=None,
)


def bind_principal(
    principal: AuthenticatedPrincipal,
) -> Token[AuthenticatedPrincipal | None]:
    """Bind *principal* to the current context and return the reset token."""
    return _principal.set(principal)


def reset_principal(token: Token[AuthenticatedPrincipal | None]) -> None:
    """Restore the previous principal binding."""
    _principal.reset(token)


def current_principal() -> AuthenticatedPrincipal:
    """Return the bound principal or raise when authentication is required."""
    principal = _principal.get()
    if principal is None:
        raise AuthenticationRequiredError()
    return principal
