"""HTTP transport boundaries for bootstrap."""

from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope, register_exception_handlers
from engrammesh.bootstrap.http.mappers import (
    InvalidCorrelationIdError,
    TenantMismatchError,
    parse_correlation_id,
    to_command,
    to_response,
)
from engrammesh.bootstrap.http.schemas import (
    RecordEpisodeRequest,
    RecordEpisodeResponse,
    ScopeRequest,
)

__all__ = [
    "InvalidCorrelationIdError",
    "RecordEpisodeRequest",
    "RecordEpisodeResponse",
    "ScopeRequest",
    "TenantMismatchError",
    "create_app",
    "error_envelope",
    "parse_correlation_id",
    "register_exception_handlers",
    "to_command",
    "to_response",
]
