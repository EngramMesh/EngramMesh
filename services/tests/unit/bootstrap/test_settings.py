from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    HttpSettings,
    InboxSettings,
    ModuleSettings,
    OidcSettings,
    OutboxRelaySettings,
    PostgresSettings,
    TelemetrySettings,
    TemporalSettings,
)

EXPECTED_MODEL_FIELDS: Mapping[type[object], tuple[str, ...]] = {
    PostgresSettings: ("dsn",),
    TemporalSettings: ("address", "namespace", "task_queue", "tls"),
    TelemetrySettings: ("otlp_endpoint", "capture_sensitive_content"),
    ModuleSettings: ("memory_enabled", "runtime_enabled"),
    HttpSettings: ("enabled", "host", "port"),
    OutboxRelaySettings: ("enabled", "batch_size", "poll_interval_seconds"),
    InboxSettings: ("enabled", "consumer_name"),
    OidcSettings: (
        "enabled",
        "issuer",
        "jwks_uri",
        "audience",
        "actor_claim",
        "tenant_claim",
        "dev_signing_key",
    ),
    AppSettings: (
        "configuration_schema_version",
        "environment",
        "postgres",
        "temporal",
        "telemetry",
        "modules",
        "http",
        "inbox",
        "outbox_relay",
        "oidc",
    ),
}


def _settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.DEVELOPMENT,
        "postgres": {"dsn": "postgresql://engrammesh:secret@localhost/engrammesh"},
        "temporal": {
            "namespace": "engrammesh-dev",
            "task_queue": "engrammesh-dev",
        },
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_settings_models_have_the_exact_architecture_boundary_fields() -> None:
    for model, expected_fields in EXPECTED_MODEL_FIELDS.items():
        assert tuple(model.model_fields) == expected_fields


def test_settings_parse_prefixed_nested_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variables = {
        "ENGRAMMESH__ENVIRONMENT": "test",
        "ENGRAMMESH__POSTGRES__DSN": (
            "postgresql://engrammesh:secret@postgres.test/engrammesh"
        ),
        "ENGRAMMESH__TEMPORAL__ADDRESS": "temporal.test:7233",
        "ENGRAMMESH__TEMPORAL__NAMESPACE": "engrammesh-test",
        "ENGRAMMESH__TEMPORAL__TASK_QUEUE": "engrammesh-test",
        "ENGRAMMESH__TEMPORAL__TLS": "true",
        "ENGRAMMESH__TELEMETRY__OTLP_ENDPOINT": "https://otel.test/v1/traces",
        "ENGRAMMESH__MODULES__RUNTIME_ENABLED": "false",
    }
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    settings = AppSettings()

    assert settings.environment is Environment.TEST
    assert settings.postgres.dsn.get_secret_value().endswith(
        "@postgres.test/engrammesh"
    )
    assert settings.temporal == TemporalSettings(
        address="temporal.test:7233",
        namespace="engrammesh-test",
        task_queue="engrammesh-test",
        tls=True,
    )
    assert settings.telemetry.otlp_endpoint == "https://otel.test/v1/traces"
    assert settings.modules.runtime_enabled is False


def test_settings_and_nested_models_are_frozen() -> None:
    settings = _settings()

    with pytest.raises(ValidationError, match="frozen"):
        settings.environment = Environment.PRODUCTION
    with pytest.raises(ValidationError, match="frozen"):
        settings.temporal.namespace = "another-namespace"


def test_postgres_secret_is_redacted_from_representations_and_snapshots() -> None:
    secret = "do-not-expose-this-password"
    settings = _settings(
        postgres={"dsn": f"postgresql://engrammesh:{secret}@localhost/engrammesh"}
    )

    assert secret not in repr(settings)
    assert secret not in str(settings.model_dump(mode="json"))
    assert settings.postgres.dsn.get_secret_value().find(secret) >= 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"telemetry": {"capture_sensitive_content": True}},
            "capture sensitive content",
        ),
        (
            {
                "postgres": {
                    "dsn": "postgresql://engrammesh:secret@postgres/engrammesh"
                }
            },
            "PostgreSQL TLS",
        ),
        (
            {
                "postgres": {
                    "dsn": "https://postgres/engrammesh?sslmode=verify-full"
                }
            },
            "PostgreSQL DSN",
        ),
        (
            {
                "postgres": {
                    "dsn": (
                        "postgresql://engrammesh:secret@postgres/engrammesh"
                        "?sslmode=verify-full"
                    )
                },
                "temporal": {
                    "namespace": "engrammesh-prod",
                    "task_queue": "engrammesh-prod",
                    "tls": False,
                },
            },
            "Temporal TLS",
        ),
    ],
)
def test_production_rejects_plaintext_or_insecure_configuration(
    overrides: Mapping[str, object],
    message: str,
) -> None:
    production: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "postgres": {
            "dsn": (
                "postgresql://engrammesh:secret@postgres/engrammesh"
                "?sslmode=verify-full"
            )
        },
        "temporal": {
            "namespace": "engrammesh-prod",
            "task_queue": "engrammesh-prod",
            "tls": True,
        },
    }
    production.update(overrides)

    with pytest.raises(ConfigurationError, match=message):
        AppSettings.model_validate(production)


def test_invalid_production_configuration_never_exposes_postgres_secret() -> None:
    secret = "review-sentinel-password"
    dsn = f"postgresql://engrammesh:{secret}@postgres/engrammesh"
    production: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "postgres": {"dsn": dsn},
        "temporal": {
            "namespace": "engrammesh-prod",
            "task_queue": "engrammesh-prod",
            "tls": True,
        },
    }

    with pytest.raises(ConfigurationError) as raised:
        AppSettings.model_validate(production)

    renderings = (
        str(raised.value),
        repr(raised.value),
        repr(raised.value.errors()),
        raised.value.json(),
    )
    for rendering in renderings:
        assert secret not in rendering
        assert dsn not in rendering


@pytest.mark.parametrize(
    ("password", "dsn"),
    [
        (
            "nfkc-password-sentinel",
            (
                "postgresql://engrammesh:nfkc-password-sentinel"
                "@postgres／nfkc-dsn-sentinel/engrammesh?sslmode=verify-full"
            ),
        ),
        (
            "ipv6-password-sentinel",
            (
                "postgresql://engrammesh:ipv6-password-sentinel"
                "@[2001:db8::1/ipv6-dsn-sentinel?sslmode=verify-full"
            ),
        ),
        (
            "port-password-sentinel",
            (
                "postgresql://engrammesh:port-password-sentinel"
                "@postgres:port-dsn-sentinel/engrammesh?sslmode=verify-full"
            ),
        ),
    ],
)
def test_malformed_production_dsn_raises_only_sanitized_configuration_error(
    password: str,
    dsn: str,
) -> None:
    production: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "postgres": {"dsn": dsn},
        "temporal": {
            "namespace": "engrammesh-prod",
            "task_queue": "engrammesh-prod",
            "tls": True,
        },
    }

    with pytest.raises(ConfigurationError) as raised:
        AppSettings.model_validate(production)

    assert raised.value.code == "invalid_postgres_dsn"
    renderings = (
        str(raised.value),
        repr(raised.value),
        repr(raised.value.errors()),
        raised.value.json(),
    )
    for rendering in renderings:
        assert password not in rendering
        assert dsn not in rendering


@pytest.mark.parametrize(
    "sslmode",
    [
        None,
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full&sslmode=",
    ],
)
def test_production_rejects_postgres_without_full_certificate_verification(
    sslmode: str | None,
) -> None:
    query = "" if sslmode is None else f"?sslmode={sslmode}"

    with pytest.raises(ConfigurationError, match="PostgreSQL TLS"):
        AppSettings.model_validate(
            {
                "environment": Environment.PRODUCTION,
                "postgres": {
                    "dsn": (
                        "postgresql://engrammesh:secret@postgres/engrammesh"
                        f"{query}"
                    )
                },
                "temporal": {
                    "namespace": "engrammesh-prod",
                    "task_queue": "engrammesh-prod",
                    "tls": True,
                },
            }
        )


def test_production_accepts_postgres_with_full_certificate_verification() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": Environment.PRODUCTION,
            "postgres": {
                "dsn": (
                    "postgresql://engrammesh:secret@postgres/engrammesh"
                    "?sslmode=verify-full"
                )
            },
            "temporal": {
                "namespace": "engrammesh-prod",
                "task_queue": "engrammesh-prod",
                "tls": True,
            },
        }
    )

    assert settings.environment is Environment.PRODUCTION


@pytest.mark.parametrize("field", ["namespace", "task_queue"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_temporal_namespace_and_task_queue_are_required_and_non_blank(
    field: str,
    value: str | None,
) -> None:
    temporal: dict[str, object] = {
        "namespace": "engrammesh-dev",
        "task_queue": "engrammesh-dev",
    }
    if value is None:
        temporal.pop(field)
    else:
        temporal[field] = value

    with pytest.raises(ValidationError):
        _settings(temporal=temporal)


def test_http_settings_defaults() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://localhost/test"},
            "temporal": {"namespace": "demo", "task_queue": "demo"},
        }
    )
    assert settings.http.port == 8080
    assert settings.http.enabled is True


def test_configuration_snapshot_has_an_explicit_semantic_version() -> None:
    snapshot = _settings().model_dump(mode="json")

    assert snapshot["configuration_schema_version"] == "1.0.0"


def test_dotenv_files_are_never_loaded_implicitly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        """ENGRAMMESH__ENVIRONMENT=production
ENGRAMMESH__POSTGRES__DSN=postgresql://user:secret@postgres/db?sslmode=verify-full
ENGRAMMESH__TEMPORAL__NAMESPACE=production
ENGRAMMESH__TEMPORAL__TASK_QUEUE=production
ENGRAMMESH__TEMPORAL__TLS=true
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        AppSettings()
