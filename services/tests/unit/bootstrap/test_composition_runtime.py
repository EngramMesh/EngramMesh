import asyncio
from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    ModuleSettings,
)
from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase as PostgresMemoryDatabaseType,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase as PostgresRuntimeDatabaseType,
)
from engrammesh.modules.runtime.adapters.temporal.connection import (
    TemporalConnectionSettings,
)
from engrammesh.modules.runtime.adapters.temporal.orchestrator import (
    TemporalOrchestratorPort,
)
from engrammesh.modules.runtime.application.cancel_execution import (
    CancelExecutionHandler,
)
from engrammesh.modules.runtime.application.get_execution_snapshot import (
    GetExecutionSnapshotHandler,
)
from engrammesh.modules.runtime.application.relay_outbox import (
    RelayRuntimeOutboxEventsHandler,
)
from engrammesh.modules.runtime.application.start_execution import StartExecutionHandler


def _test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def _mock_postgres_memory_database() -> PostgresMemoryDatabaseType:
    database = create_autospec(PostgresMemoryDatabaseType, instance=True)
    database.open = AsyncMock()
    database.close = AsyncMock()
    return database


def _mock_postgres_runtime_database() -> PostgresRuntimeDatabaseType:
    database = create_autospec(PostgresRuntimeDatabaseType, instance=True)
    database.open = AsyncMock()
    database.close = AsyncMock()
    return database


def test_start_execution_handler_when_runtime_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(runtime_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.start_execution_handler()
    assert exc_info.value.code == "runtime_disabled"


def test_get_execution_snapshot_handler_when_runtime_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(runtime_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.get_execution_snapshot_handler()
    assert exc_info.value.code == "runtime_disabled"


def test_cancel_execution_handler_when_runtime_disabled_raises() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(runtime_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        runtime.cancel_execution_handler()
    assert exc_info.value.code == "runtime_disabled"


@pytest.mark.asyncio
async def test_relay_runtime_outbox_handler_when_relay_disabled_raises() -> None:
    runtime = create_runtime(_test_settings(runtime_outbox_relay={"enabled": False}))
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
    ):
        memory_cls.return_value = _mock_postgres_memory_database()
        runtime_cls.return_value = _mock_postgres_runtime_database()
        await runtime.startup()
        with pytest.raises(ConfigurationError) as exc_info:
            runtime.relay_runtime_outbox_handler()
        assert exc_info.value.code == "runtime_outbox_relay_disabled"
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_relay_runtime_outbox_handler_before_startup_raises() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.relay_runtime_outbox_handler()


@pytest.mark.asyncio
async def test_relay_runtime_outbox_handler_returns_cached_handler() -> None:
    runtime = create_runtime(_test_settings())
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
    ):
        memory_cls.return_value = _mock_postgres_memory_database()
        runtime_cls.return_value = _mock_postgres_runtime_database()
        await runtime.startup()
        first = runtime.relay_runtime_outbox_handler()
        second = runtime.relay_runtime_outbox_handler()
        assert isinstance(first, RelayRuntimeOutboxEventsHandler)
        assert first is second
        publisher = runtime.logging_runtime_outbox_event_publisher
        assert first._publisher is publisher
        assert second._publisher is publisher
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_run_runtime_outbox_relay_loop_exits_immediately_when_stopped() -> None:
    runtime = create_runtime(_test_settings())
    stop_event = asyncio.Event()
    stop_event.set()

    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
    ):
        memory_cls.return_value = _mock_postgres_memory_database()
        runtime_cls.return_value = _mock_postgres_runtime_database()
        await runtime.startup()
        with patch(
            "engrammesh.bootstrap.composition.AppRuntime.relay_runtime_outbox_once",
            new_callable=AsyncMock,
        ) as relay_mock:
            await runtime.run_runtime_outbox_relay_loop(
                batch_size=10,
                interval_seconds=0.01,
                stop_event=stop_event,
            )
            relay_mock.assert_not_awaited()
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_handlers_before_startup_raise() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.start_execution_handler()
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.get_execution_snapshot_handler()
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.cancel_execution_handler()


@pytest.mark.asyncio
async def test_startup_raises_when_runtime_enabled_without_memory_storage() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    with pytest.raises(ConfigurationError) as exc_info:
        await runtime.startup()
    assert exc_info.value.code == "runtime_storage_unconfigured"


@pytest.mark.asyncio
async def test_startup_wires_in_memory_orchestrator_when_temporal_disabled() -> None:
    runtime = create_runtime(
        _test_settings(
            temporal={"enabled": False, "namespace": "ns", "task_queue": "q"},
        )
    )
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
        patch(
            "engrammesh.bootstrap.composition.connect_temporal_client",
            new_callable=AsyncMock,
        ) as connect_mock,
    ):
        memory_cls.return_value.open = AsyncMock()
        memory_cls.return_value.close = AsyncMock()
        runtime_cls.return_value.open = AsyncMock()
        runtime_cls.return_value.close = AsyncMock()
        await runtime.startup()
        connect_mock.assert_not_awaited()
        handler = runtime.start_execution_handler()
        assert isinstance(handler, StartExecutionHandler)
        assert isinstance(handler._orchestrator, InMemoryOrchestratorPort)
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_startup_wires_temporal_orchestrator_when_temporal_enabled() -> None:
    runtime = create_runtime(
        _test_settings(
            temporal={"enabled": True, "namespace": "ns", "task_queue": "q"},
        )
    )
    client = object()
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
        patch(
            "engrammesh.bootstrap.composition.connect_temporal_client",
            new_callable=AsyncMock,
            return_value=client,
        ) as connect_mock,
    ):
        memory_cls.return_value.open = AsyncMock()
        memory_cls.return_value.close = AsyncMock()
        runtime_cls.return_value.open = AsyncMock()
        runtime_cls.return_value.close = AsyncMock()
        await runtime.startup()
        temporal = runtime.settings.temporal
        connect_mock.assert_awaited_once_with(
            TemporalConnectionSettings(
                address=temporal.address,
                namespace=temporal.namespace,
                tls=temporal.tls,
            )
        )
        handler = runtime.start_execution_handler()
        assert isinstance(handler, StartExecutionHandler)
        assert isinstance(handler._orchestrator, TemporalOrchestratorPort)
        assert handler._orchestrator._client is client
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_runtime_handlers_return_cached_instances() -> None:
    runtime = create_runtime(_test_settings())
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
    ):
        memory_cls.return_value.open = AsyncMock()
        memory_cls.return_value.close = AsyncMock()
        runtime_cls.return_value.open = AsyncMock()
        runtime_cls.return_value.close = AsyncMock()
        await runtime.startup()
        start_first = runtime.start_execution_handler()
        start_second = runtime.start_execution_handler()
        get_first = runtime.get_execution_snapshot_handler()
        get_second = runtime.get_execution_snapshot_handler()
        cancel_first = runtime.cancel_execution_handler()
        cancel_second = runtime.cancel_execution_handler()
        assert isinstance(start_first, StartExecutionHandler)
        assert start_first is start_second
        assert isinstance(get_first, GetExecutionSnapshotHandler)
        assert get_first is get_second
        assert isinstance(cancel_first, CancelExecutionHandler)
        assert cancel_first is cancel_second
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_shutdown_clears_runtime_handlers() -> None:
    runtime = create_runtime(_test_settings())
    with (
        patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as memory_cls,
        patch("engrammesh.bootstrap.composition.PostgresRuntimeDatabase") as runtime_cls,
    ):
        memory_cls.return_value = _mock_postgres_memory_database()
        runtime_cls.return_value = _mock_postgres_runtime_database()
        await runtime.startup()
        start_handler = runtime.start_execution_handler()
        relay_handler = runtime.relay_runtime_outbox_handler()
        logging_publisher = runtime.logging_runtime_outbox_event_publisher
        await runtime.shutdown()
        with pytest.raises(RuntimeError, match="application runtime is not started"):
            runtime.start_execution_handler()
        with pytest.raises(RuntimeError, match="application runtime is not started"):
            runtime.relay_runtime_outbox_handler()
        assert runtime.logging_runtime_outbox_event_publisher is not logging_publisher
        del start_handler, relay_handler
