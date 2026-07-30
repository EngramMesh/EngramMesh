from unittest.mock import AsyncMock, patch

import pytest

from engrammesh.bootstrap.composition import create_runtime, load_settings
from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    ModuleSettings,
)
from engrammesh.modules.memory.application.record_episode import RecordEpisodeHandler


def _test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_load_settings_returns_app_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENGRAMMESH__ENVIRONMENT", "test")
    monkeypatch.setenv(
        "ENGRAMMESH__POSTGRES__DSN",
        "postgresql://u:p@localhost/db",
    )
    monkeypatch.setenv("ENGRAMMESH__TEMPORAL__NAMESPACE", "ns")
    monkeypatch.setenv("ENGRAMMESH__TEMPORAL__TASK_QUEUE", "q")
    settings = load_settings()
    assert settings.environment is Environment.TEST


@pytest.mark.asyncio
async def test_runtime_startup_shutdown_opens_and_closes_database() -> None:
    settings = _test_settings()
    runtime = create_runtime(settings)
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database = database_cls.return_value
        database.open = AsyncMock()
        database.close = AsyncMock()
        await runtime.startup()
        await runtime.shutdown()
        database.open.assert_awaited_once()
        database.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_startup_is_idempotent() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        await runtime.startup()
        database_cls.return_value.open.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_shutdown_is_idempotent() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        await runtime.shutdown()
        await runtime.shutdown()
        database_cls.return_value.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_episode_handler_before_startup_raises() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.record_episode_handler()


def test_record_episode_handler_when_memory_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.record_episode_handler()
    assert exc_info.value.code == "memory_disabled"


@pytest.mark.asyncio
async def test_record_episode_handler_returns_cached_handler() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        first = runtime.record_episode_handler()
        second = runtime.record_episode_handler()
        assert isinstance(first, RecordEpisodeHandler)
        assert first is second
