"""Application runtime composition from typed settings."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Self, final

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedMemoryAuthorization,
    LoggingOutboxEventPublisher,
    SystemUtcClock,
    UuidMemoryIdentityPort,
)
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError
from engrammesh.modules.memory.adapters.postgres import (
    PostgresMemoryDatabase,
    PostgresMemoryUnitOfWorkFactory,
    PostgresOutboxRelayStore,
)
from engrammesh.modules.memory.application.contracts import (
    RelayOutboxCommand,
    RelayOutboxResult,
)
from engrammesh.modules.memory.application.record_episode import RecordEpisodeHandler
from engrammesh.modules.memory.application.relay_outbox import RelayOutboxEventsHandler


def load_settings() -> AppSettings:
    return AppSettings.model_validate({})


def create_runtime(settings: AppSettings | None = None) -> AppRuntime:
    return AppRuntime(settings if settings is not None else load_settings())


@final
class ReadinessError(Exception):
    """Raised when AppRuntime is not ready to serve memory traffic."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@final
class AppRuntime:
    __slots__ = (
        "_database",
        "_handler",
        "_outbox_publisher",
        "_relay_handler",
        "_settings",
        "_started",
        "_unit_of_work_factory",
    )

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._database: PostgresMemoryDatabase | None = None
        self._unit_of_work_factory: PostgresMemoryUnitOfWorkFactory | None = None
        self._handler: RecordEpisodeHandler | None = None
        self._outbox_publisher = LoggingOutboxEventPublisher()
        self._relay_handler: RelayOutboxEventsHandler | None = None
        self._started = False

    @property
    def settings(self) -> AppSettings:
        return self._settings

    async def check_ready(self) -> None:
        if not self._settings.modules.memory_enabled:
            raise ReadinessError("memory_disabled")
        if not self._started or self._database is None:
            raise ReadinessError("runtime_not_started")
        try:
            async with self._database.connection() as conn:
                await conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 -- readiness must not leak database errors
            raise ReadinessError("database_unavailable") from None

    async def startup(self) -> None:
        if not self._settings.modules.memory_enabled:
            return
        if self._started:
            return
        database = PostgresMemoryDatabase(
            self._settings.postgres.dsn.get_secret_value()
        )
        await database.open()
        self._database = database
        self._unit_of_work_factory = PostgresMemoryUnitOfWorkFactory(database)
        self._started = True

    async def shutdown(self) -> None:
        database = self._database
        self._database = None
        self._unit_of_work_factory = None
        self._handler = None
        self._relay_handler = None
        self._outbox_publisher = LoggingOutboxEventPublisher()
        self._started = False
        if database is not None:
            await database.close()

    @property
    def outbox_event_publisher(self) -> LoggingOutboxEventPublisher:
        return self._outbox_publisher

    def record_episode_handler(self) -> RecordEpisodeHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._unit_of_work_factory is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._handler is None:
            self._handler = RecordEpisodeHandler(
                authorization=EnvironmentGatedMemoryAuthorization(
                    self._settings.environment
                ),
                clock=SystemUtcClock(),
                identities=UuidMemoryIdentityPort(),
                unit_of_work_factory=self._unit_of_work_factory,
            )
        return self._handler

    def relay_outbox_handler(self) -> RelayOutboxEventsHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._database is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if not self._settings.outbox_relay.enabled:
            msg = "outbox relay is disabled"
            raise ConfigurationError("outbox_relay_disabled", msg)
        if self._relay_handler is None:
            self._relay_handler = RelayOutboxEventsHandler(
                clock=SystemUtcClock(),
                store=PostgresOutboxRelayStore(self._database),
                publisher=self._outbox_publisher,
            )
        return self._relay_handler

    async def relay_outbox_once(
        self,
        *,
        batch_size: int | None = None,
    ) -> RelayOutboxResult:
        handler = self.relay_outbox_handler()
        size = (
            batch_size
            if batch_size is not None
            else self._settings.outbox_relay.batch_size
        )
        return await handler.handle(RelayOutboxCommand(batch_size=size))

    async def run_outbox_relay_loop(
        self,
        *,
        batch_size: int | None = None,
        interval_seconds: float | None = None,
        stop_event: asyncio.Event,
    ) -> None:
        size = (
            batch_size
            if batch_size is not None
            else self._settings.outbox_relay.batch_size
        )
        interval = (
            interval_seconds
            if interval_seconds is not None
            else self._settings.outbox_relay.poll_interval_seconds
        )
        while not stop_event.is_set():
            result = await self.relay_outbox_once(batch_size=size)
            if result.fetched < size:
                await asyncio.sleep(interval)

    async def __aenter__(self) -> Self:
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        await self.shutdown()
