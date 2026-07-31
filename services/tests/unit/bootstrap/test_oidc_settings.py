import pytest

from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    OidcSettings,
)


def _base(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "environment": Environment.DEVELOPMENT,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return values


def _production_base(**overrides: object) -> dict[str, object]:
    return _base(
        environment=Environment.PRODUCTION,
        postgres={
            "dsn": "postgresql://u:p@postgres/db?sslmode=verify-full",
        },
        temporal={"namespace": "prod", "task_queue": "prod", "tls": True},
        **overrides,
    )


def test_oidc_settings_defaults() -> None:
    settings = AppSettings.model_validate(_base())
    assert settings.oidc == OidcSettings()


def test_production_requires_oidc_issuer_and_jwks_when_enabled() -> None:
    with pytest.raises(ConfigurationError, match="issuer"):
        AppSettings.model_validate(
            _production_base(oidc={"enabled": True, "issuer": "", "jwks_uri": ""})
        )


def test_production_forbids_dev_signing_key_when_oidc_enabled() -> None:
    with pytest.raises(ConfigurationError, match="dev_signing_key"):
        AppSettings.model_validate(
            _production_base(
                oidc={
                    "enabled": True,
                    "issuer": "https://auth.example.com/",
                    "jwks_uri": "https://auth.example.com/jwks",
                    "dev_signing_key": "must-not-appear-in-production",
                }
            )
        )


def test_oidc_dev_signing_key_is_redacted_from_representations() -> None:
    secret = "do-not-expose-dev-signing-key"
    settings = AppSettings.model_validate(
        _base(oidc={"dev_signing_key": secret}),
    )

    assert secret not in repr(settings)
    assert secret not in str(settings.model_dump(mode="json"))
    assert settings.oidc.dev_signing_key is not None
    assert settings.oidc.dev_signing_key.get_secret_value() == secret
