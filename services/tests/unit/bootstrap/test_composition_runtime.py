from unittest.mock import AsyncMock, patch

import pytest

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.settings import (
    AppSettings,
    ConfigurationError,
    Environment,
    ModuleSettings,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
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
from engrammesh.modules.runtime.application.start_execution import StartExecutionHandler


def _test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


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
async def test_runtime_handlers_before_startup_raise() -> None:
    runtime = create_runtime(_test_settings())
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.start_execution_handler()
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.get_execution_snapshot_handler()
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.cancel_execution_handler()


@pytest.mark.asyncio
async def test_startup_wires_in_memory_orchestrator_when_temporal_disabled() -> None:
    runtime = create_runtime(
        _test_settings(
            modules=ModuleSettings(memory_enabled=False),
            temporal={"enabled": False, "namespace": "ns", "task_queue": "q"},
        )
    )
    with patch(
        "engrammesh.bootstrap.composition.connect_temporal_client",
        new_callable=AsyncMock,
    ) as connect_mock:
        await runtime.startup()
        connect_mock.assert_not_awaited()
    handler = runtime.start_execution_handler()
    assert isinstance(handler, StartExecutionHandler)
    assert isinstance(handler._orchestrator, InMemoryOrchestratorPort)


@pytest.mark.asyncio
async def test_startup_wires_temporal_orchestrator_when_temporal_enabled() -> None:
    runtime = create_runtime(
        _test_settings(
            modules=ModuleSettings(memory_enabled=False),
            temporal={"enabled": True, "namespace": "ns", "task_queue": "q"},
        )
    )
    client = object()
    with patch(
        "engrammesh.bootstrap.composition.connect_temporal_client",
        new_callable=AsyncMock,
        return_value=client,
    ) as connect_mock:
        await runtime.startup()
        connect_mock.assert_awaited_once_with(runtime.settings.temporal)
    handler = runtime.start_execution_handler()
    assert isinstance(handler, StartExecutionHandler)
    assert isinstance(handler._orchestrator, TemporalOrchestratorPort)
    assert handler._orchestrator._client is client


@pytest.mark.asyncio
async def test_runtime_handlers_return_cached_instances() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
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


@pytest.mark.asyncio
async def test_shutdown_clears_runtime_handlers() -> None:
    runtime = create_runtime(
        _test_settings(modules=ModuleSettings(memory_enabled=False))
    )
    await runtime.startup()
    start_handler = runtime.start_execution_handler()
    await runtime.shutdown()
    with pytest.raises(RuntimeError, match="application runtime is not started"):
        runtime.start_execution_handler()
    del start_handler
