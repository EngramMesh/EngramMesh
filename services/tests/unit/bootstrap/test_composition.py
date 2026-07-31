import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from engrammesh.bootstrap.auth.token_verifiers import StaticDevTokenVerifier
from engrammesh.bootstrap.composition import (
    ReadinessError,
    create_runtime,
    load_settings,
)
from engrammesh.bootstrap.infrastructure import InboxOutboxEventPublisher
from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    ModuleSettings,
)
from engrammesh.modules.memory.application.get_episode import GetEpisodeHandler
from engrammesh.modules.memory.application.list_episodes import ListEpisodesHandler
from engrammesh.modules.memory.application.record_episode import RecordEpisodeHandler
from engrammesh.modules.memory.application.relay_outbox import RelayOutboxEventsHandler


def _test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_runtime_exposes_static_dev_verifier_in_test_environment() -> None:
    settings = _test_settings(
        oidc={
            "enabled": True,
            "issuer": "https://dev.engrammesh.test",
            "dev_signing_key": "dev-only-signing-key-not-for-production",
        },
    )
    runtime = create_runtime(settings)
    verifier = runtime.token_verifier()
    assert isinstance(verifier, StaticDevTokenVerifier)


def test_staging_without_jwks_raises_at_runtime_construction() -> None:
    settings = _test_settings(
        environment=Environment.STAGING,
        oidc={"enabled": True, "issuer": "https://auth.example.com/"},
    )
    with pytest.raises(ConfigurationError) as exc_info:
        create_runtime(settings)
    assert exc_info.value.code == "oidc_misconfigured"


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
async def test_runtime_async_context_manager_lifecycle() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database = database_cls.return_value
        database.open = AsyncMock()
        database.close = AsyncMock()
        async with runtime:
            database.open.assert_awaited_once()
            runtime.record_episode_handler()
        database.close.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_get_episode_handler_returns_cached_handler() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        first = runtime.get_episode_handler()
        second = runtime.get_episode_handler()
        assert isinstance(first, GetEpisodeHandler)
        assert first is second


def test_get_episode_handler_when_memory_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.get_episode_handler()
    assert exc_info.value.code == "memory_disabled"


@pytest.mark.asyncio
async def test_list_episodes_handler_returns_cached_handler() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        first = runtime.list_episodes_handler()
        second = runtime.list_episodes_handler()
        assert isinstance(first, ListEpisodesHandler)
        assert first is second


def test_list_episodes_handler_when_memory_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.list_episodes_handler()
    assert exc_info.value.code == "memory_disabled"


def test_relay_outbox_handler_when_memory_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(
            modules=ModuleSettings(memory_enabled=False),
            outbox_relay={"enabled": False},
        )
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.relay_outbox_handler()
    assert exc_info.value.code == "memory_disabled"


@pytest.mark.asyncio
async def test_relay_outbox_handler_when_outbox_relay_disabled_raises() -> None:
    runtime = create_runtime(_test_settings(outbox_relay={"enabled": False}))
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        with pytest.raises(ConfigurationError) as exc_info:
            runtime.relay_outbox_handler()
        assert exc_info.value.code == "outbox_relay_disabled"


@pytest.mark.asyncio
async def test_relay_outbox_handler_before_startup_raises() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.relay_outbox_handler()


@pytest.mark.asyncio
async def test_outbox_event_publisher_is_inbox_wrapper_when_inbox_enabled() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        assert isinstance(runtime.outbox_event_publisher, InboxOutboxEventPublisher)


@pytest.mark.asyncio
async def test_outbox_event_publisher_is_logging_when_inbox_disabled() -> None:
    runtime = create_runtime(_test_settings(inbox={"enabled": False}))
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        assert runtime.outbox_event_publisher is runtime.logging_outbox_event_publisher


def test_process_inbox_handler_when_memory_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.process_inbox_handler()
    assert exc_info.value.code == "memory_disabled"


@pytest.mark.asyncio
async def test_process_inbox_handler_before_startup_raises() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.process_inbox_handler()


@pytest.mark.asyncio
async def test_relay_outbox_handler_returns_cached_handler() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        first = runtime.relay_outbox_handler()
        second = runtime.relay_outbox_handler()
        assert isinstance(first, RelayOutboxEventsHandler)
        assert first is second
        publisher = runtime.outbox_event_publisher
        assert first._publisher is publisher
        assert second._publisher is publisher


@pytest.mark.asyncio
async def test_shutdown_clears_outbox_publisher() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        publisher = runtime.outbox_event_publisher
        logging_publisher = runtime.logging_outbox_event_publisher
        inbox_handler = runtime.process_inbox_handler()
        await runtime.shutdown()
        assert runtime.outbox_event_publisher is not publisher
        assert runtime.logging_outbox_event_publisher is not logging_publisher
        with pytest.raises(RuntimeError, match="application runtime is not started"):
            runtime.process_inbox_handler()
        del inbox_handler


@pytest.mark.asyncio
async def test_run_outbox_relay_loop_exits_immediately_when_stopped() -> None:
    runtime = create_runtime(_test_settings())
    stop_event = asyncio.Event()
    stop_event.set()

    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database_cls.return_value.open = AsyncMock()
        database_cls.return_value.close = AsyncMock()
        await runtime.startup()
        with patch(
            "engrammesh.bootstrap.composition.AppRuntime.relay_outbox_once",
            new_callable=AsyncMock,
        ) as relay_mock:
            await runtime.run_outbox_relay_loop(
                batch_size=10,
                interval_seconds=0.01,
                stop_event=stop_event,
            )
            relay_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_ready_raises_runtime_not_started() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(ReadinessError) as exc:
        await runtime.check_ready()
    assert exc.value.code == "runtime_not_started"


@pytest.mark.asyncio
async def test_check_ready_raises_memory_disabled() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ReadinessError) as exc:
        await runtime.check_ready()
    assert exc.value.code == "memory_disabled"


@pytest.mark.asyncio
async def test_check_ready_raises_database_unavailable() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database = database_cls.return_value
        database.open = AsyncMock()
        database.close = AsyncMock()

        @asynccontextmanager
        async def failing_connection():
            raise RuntimeError("database unavailable")
            yield  # pragma: no cover

        database.connection = failing_connection
        await runtime.startup()
        with pytest.raises(ReadinessError) as exc:
            await runtime.check_ready()
        assert exc.value.code == "database_unavailable"


@pytest.mark.asyncio
async def test_check_ready_succeeds_when_database_is_available() -> None:
    runtime = create_runtime(_test_settings())
    with patch(
        "engrammesh.bootstrap.composition.PostgresMemoryDatabase"
    ) as database_cls:
        database = database_cls.return_value
        database.open = AsyncMock()
        database.close = AsyncMock()

        @asynccontextmanager
        async def healthy_connection():
            connection = AsyncMock()
            connection.execute = AsyncMock()
            yield connection

        database.connection = healthy_connection
        await runtime.startup()
        await runtime.check_ready()
