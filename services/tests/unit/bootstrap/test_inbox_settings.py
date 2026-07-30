import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.settings import (
    AppSettings,
    Environment,
    InboxSettings,
)


def test_inbox_settings_defaults() -> None:
    settings = InboxSettings()

    assert settings.enabled is True
    assert settings.consumer_name == "episode-recorded-v1"


@pytest.mark.parametrize("value", ["", "   "])
def test_inbox_settings_reject_blank_consumer_name(value: str) -> None:
    with pytest.raises(ValidationError, match="consumer_name"):
        InboxSettings(consumer_name=value)


def test_app_settings_includes_inbox_with_defaults() -> None:
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

    assert settings.inbox == InboxSettings()
