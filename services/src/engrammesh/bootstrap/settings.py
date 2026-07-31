"""Typed, immutable process configuration boundary."""

import json
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import SplitResult, parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Sanitized public error for unsafe configuration combinations."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def errors(self) -> tuple[dict[str, object], ...]:
        """Return structured error details without preserving input values."""
        return (
            {
                "type": "configuration_error",
                "loc": (),
                "msg": str(self),
                "code": self.code,
            },
        )

    def json(self) -> str:
        """Serialize structured error details without preserving input values."""
        return json.dumps(self.errors(), separators=(",", ":"))


def _parse_postgres_dsn(value: str) -> tuple[SplitResult, str | None] | None:
    try:
        dsn = urlsplit(value)
        hostname = dsn.hostname
        _ = dsn.port
    except ValueError:
        return None
    return dsn, hostname


class Environment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class _FrozenSettingsModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PostgresSettings(_FrozenSettingsModel):
    """PostgreSQL connection boundary."""

    dsn: SecretStr


class TemporalSettings(_FrozenSettingsModel):
    """Temporal connection and worker routing boundary."""

    address: str = "localhost:7233"
    namespace: str
    task_queue: str
    tls: bool = False

    @field_validator("address", "namespace", "task_queue")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        """Reject ambiguous empty routing values."""
        if not value.strip():
            msg = "Temporal settings must not be blank"
            raise ValueError(msg)
        return value


class TelemetrySettings(_FrozenSettingsModel):
    """Telemetry export boundary with content capture disabled by default."""

    otlp_endpoint: str | None = None
    capture_sensitive_content: bool = False


class ModuleSettings(_FrozenSettingsModel):
    """Architectural module enablement switches."""

    memory_enabled: bool = True
    runtime_enabled: bool = True


class HttpSettings(_FrozenSettingsModel):
    """HTTP server binding and enablement boundary."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8080


class InboxSettings(_FrozenSettingsModel):
    """Inbox consumer dedup and processing boundary."""

    enabled: bool = True
    consumer_name: str = "episode-recorded-v1"

    @field_validator("consumer_name")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            msg = "consumer_name must not be blank"
            raise ValueError(msg)
        return value


class OutboxRelaySettings(_FrozenSettingsModel):
    """Outbox relay polling and batch dispatch boundary."""

    enabled: bool = True
    batch_size: int = 100
    poll_interval_seconds: float = 1.0

    @field_validator("batch_size")
    @classmethod
    def require_positive_batch_size(cls, value: int) -> int:
        if value <= 0:
            msg = "batch_size must be positive"
            raise ValueError(msg)
        return value

    @field_validator("poll_interval_seconds")
    @classmethod
    def require_positive_poll_interval(cls, value: float) -> float:
        if value <= 0:
            msg = "poll_interval_seconds must be positive"
            raise ValueError(msg)
        return value


class OidcSettings(_FrozenSettingsModel):
    """OIDC JWT verification boundary."""

    enabled: bool = False
    issuer: str = ""
    jwks_uri: str = ""
    audience: str | None = None
    actor_claim: str = "sub"
    tenant_claim: str = "tenant_id"
    dev_signing_key: str | None = None


class AppSettings(BaseSettings):
    """Immutable application configuration assembled from trusted sources."""

    model_config = SettingsConfigDict(
        env_prefix="ENGRAMMESH__",
        env_nested_delimiter="__",
        env_file=None,
        frozen=True,
        extra="forbid",
    )

    configuration_schema_version: Literal["1.0.0"] = "1.0.0"
    environment: Environment
    postgres: PostgresSettings
    temporal: TemporalSettings
    telemetry: TelemetrySettings = TelemetrySettings()
    modules: ModuleSettings = ModuleSettings()
    http: HttpSettings = HttpSettings()
    inbox: InboxSettings = InboxSettings()
    outbox_relay: OutboxRelaySettings = OutboxRelaySettings()
    oidc: OidcSettings = OidcSettings()

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Fail closed when production transport or telemetry is unsafe."""
        if self.environment is not Environment.PRODUCTION:
            return self

        if self.telemetry.capture_sensitive_content:
            msg = "production must not capture sensitive content in plaintext telemetry"
            raise ConfigurationError("plaintext_telemetry", msg)

        parsed_dsn = _parse_postgres_dsn(self.postgres.dsn.get_secret_value())
        if parsed_dsn is None:
            msg = "production requires a PostgreSQL DSN with an explicit host"
            raise ConfigurationError("invalid_postgres_dsn", msg)
        dsn, hostname = parsed_dsn
        if dsn.scheme not in {"postgres", "postgresql"} or hostname is None:
            msg = "production requires a PostgreSQL DSN with an explicit host"
            raise ConfigurationError("invalid_postgres_dsn", msg)
        sslmodes = parse_qs(dsn.query, keep_blank_values=True).get("sslmode", [])
        if sslmodes != ["verify-full"]:
            msg = "production requires PostgreSQL TLS with sslmode=verify-full"
            raise ConfigurationError("insecure_postgres_tls", msg)

        if not self.temporal.tls:
            msg = "production requires Temporal TLS"
            raise ConfigurationError("insecure_temporal_tls", msg)

        if self.oidc.enabled:
            if not self.oidc.issuer.strip():
                msg = "production requires OIDC issuer when OIDC is enabled"
                raise ConfigurationError("oidc_issuer_required", msg)
            if not self.oidc.jwks_uri.strip():
                msg = "production requires OIDC JWKS URI when OIDC is enabled"
                raise ConfigurationError("oidc_jwks_uri_required", msg)
            if self.oidc.dev_signing_key is not None:
                msg = "production must not configure OIDC dev_signing_key"
                raise ConfigurationError("oidc_dev_key_forbidden", msg)

        return self
