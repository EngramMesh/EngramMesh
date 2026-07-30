"""Application runtime composition from typed settings."""

from __future__ import annotations

from types import TracebackType
from typing import Self, final

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedMemoryAuthorization,
    SystemUtcClock,
    UuidMemoryIdentityPort,
)
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError
from engrammesh.modules.memory.adapters.postgres import (
    PostgresMemoryDatabase,
    PostgresMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.record_episode import RecordEpisodeHandler


def load_settings() -> AppSettings:
    return AppSettings.model_validate({})


def create_runtime(settings: AppSettings | None = None) -> AppRuntime:
    return AppRuntime(settings if settings is not None else load_settings())


@final
class AppRuntime:
    __slots__ = (
        "_database",
        "_handler",
        "_settings",
        "_started",
        "_unit_of_work_factory",
    )

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._database: PostgresMemoryDatabase | None = None
        self._unit_of_work_factory: PostgresMemoryUnitOfWorkFactory | None = None
        self._handler: RecordEpisodeHandler | None = None
        self._started = False

    @property
    def settings(self) -> AppSettings:
        return self._settings

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
        self._started = False
        if database is not None:
            await database.close()

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
