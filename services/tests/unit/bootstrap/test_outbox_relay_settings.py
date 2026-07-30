import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.settings import (
    AppSettings,
    Environment,
    OutboxRelaySettings,
)


def test_outbox_relay_settings_defaults() -> None:
    settings = OutboxRelaySettings()

    assert settings.enabled is True
    assert settings.batch_size == 100
    assert settings.poll_interval_seconds == 1.0


@pytest.mark.parametrize("value", [0, -1])
def test_outbox_relay_settings_reject_non_positive_batch_size(value: int) -> None:
    with pytest.raises(ValidationError, match="batch_size"):
        OutboxRelaySettings(batch_size=value)


@pytest.mark.parametrize("value", [0, -1.0])
def test_outbox_relay_settings_reject_non_positive_poll_interval(
    value: float,
) -> None:
    with pytest.raises(ValidationError, match="poll_interval_seconds"):
        OutboxRelaySettings(poll_interval_seconds=value)


def test_app_settings_includes_outbox_relay_with_defaults() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": Environment.DEVELOPMENT,
            "postgres": {
                "dsn": "postgresql://engrammesh:secret@localhost/engrammesh"
            },
            "temporal": {
                "namespace": "engrammesh-dev",
                "task_queue": "engrammesh-dev",
            },
        }
    )

    assert settings.outbox_relay == OutboxRelaySettings()
