"""Typed, immutable process configuration boundary."""

from enum import StrEnum
from typing import Literal, Self
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Fail closed when production transport or telemetry is unsafe."""
        if self.environment is not Environment.PRODUCTION:
            return self

        if self.telemetry.capture_sensitive_content:
            msg = "production must not capture sensitive content in plaintext telemetry"
            raise ValueError(msg)

        dsn = urlsplit(self.postgres.dsn.get_secret_value())
        if dsn.scheme not in {"postgres", "postgresql"} or dsn.hostname is None:
            msg = "production requires a PostgreSQL DSN with an explicit host"
            raise ValueError(msg)
        sslmode = parse_qs(dsn.query).get("sslmode", [""])[-1]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            msg = "production requires PostgreSQL TLS"
            raise ValueError(msg)

        if not self.temporal.tls:
            msg = "production requires Temporal TLS"
            raise ValueError(msg)

        return self
