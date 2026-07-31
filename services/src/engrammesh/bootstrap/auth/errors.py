"""Authentication errors for bootstrap-layer OIDC integration."""

from typing import final


class AuthenticationError(Exception):
    """Base class for authentication failures."""


@final
class AuthenticationRequiredError(AuthenticationError):
    """Raised when a protected request lacks Bearer credentials."""

    def __init__(self) -> None:
        super().__init__("authentication is required")


@final
class InvalidTokenError(AuthenticationError):
    """Raised when Bearer credentials cannot be verified."""

    def __init__(self) -> None:
        super().__init__("invalid token")


@final
class TenantAccessDeniedError(AuthenticationError):
    """Raised when the JWT tenant does not match the path tenant."""

    def __init__(self) -> None:
        super().__init__("tenant access is denied")
