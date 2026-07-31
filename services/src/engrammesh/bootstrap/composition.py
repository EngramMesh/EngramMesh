"""Application runtime composition from typed settings."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, Self, final

from engrammesh.bootstrap.auth.ports import TokenVerifierPort
from engrammesh.bootstrap.infrastructure import (
    InboxOutboxEventPublisher,
    LoggingOutboxEventPublisher,
    SystemUtcClock,
    UuidMemoryIdentityPort,
    UuidRuntimeIdentityPort,
    create_memory_authorization,
    create_runtime_authorization,
    create_token_verifier,
)
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError
from engrammesh.modules.memory.adapters.postgres import (
    PostgresInboxStore,
    PostgresMemoryDatabase,
    PostgresMemoryUnitOfWorkFactory,
    PostgresOutboxRelayStore,
)
from engrammesh.modules.memory.application.contracts import (
    RelayOutboxCommand,
    RelayOutboxResult,
)
from engrammesh.modules.memory.application.episode_recorded_processor import (
    EpisodeRecordedProcessor,
)
from engrammesh.modules.memory.application.get_episode import GetEpisodeHandler
from engrammesh.modules.memory.application.list_episodes import ListEpisodesHandler
from engrammesh.modules.memory.application.process_inbox_event import (
    ProcessInboxEventHandler,
)
from engrammesh.modules.memory.application.record_episode import RecordEpisodeHandler
from engrammesh.modules.memory.application.relay_outbox import RelayOutboxEventsHandler
from engrammesh.modules.memory.ports import OutboxEventPublisher
from engrammesh.modules.runtime.adapters.in_memory.database import (
    InMemoryRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.adapters.temporal.connection import (
    TemporalConnectionSettings,
    connect_temporal_client,
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
from engrammesh.modules.runtime.ports import OrchestratorPort


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
        "_cancel_execution_handler",
        "_database",
        "_execution_index",
        "_get_episode_handler",
        "_get_execution_snapshot_handler",
        "_handler",
        "_inbox_handler",
        "_list_episodes_handler",
        "_logging_publisher",
        "_orchestrator",
        "_outbox_publisher",
        "_relay_handler",
        "_settings",
        "_start_execution_handler",
        "_started",
        "_temporal_client",
        "_token_verifier",
        "_unit_of_work_factory",
    )

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._token_verifier = create_token_verifier(settings)
        self._database: PostgresMemoryDatabase | None = None
        self._unit_of_work_factory: PostgresMemoryUnitOfWorkFactory | None = None
        self._handler: RecordEpisodeHandler | None = None
        self._get_episode_handler: GetEpisodeHandler | None = None
        self._list_episodes_handler: ListEpisodesHandler | None = None
        self._inbox_handler: ProcessInboxEventHandler | None = None
        self._logging_publisher = LoggingOutboxEventPublisher()
        self._outbox_publisher: OutboxEventPublisher = self._logging_publisher
        self._relay_handler: RelayOutboxEventsHandler | None = None
        self._execution_index: InMemoryRuntimeDatabase | None = None
        self._orchestrator: OrchestratorPort | None = None
        self._temporal_client: Any = None
        self._start_execution_handler: StartExecutionHandler | None = None
        self._get_execution_snapshot_handler: GetExecutionSnapshotHandler | None = None
        self._cancel_execution_handler: CancelExecutionHandler | None = None
        self._started = False

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def token_verifier(self) -> TokenVerifierPort | None:
        return self._token_verifier

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
        if self._settings.modules.memory_enabled and not self._started:
            database = PostgresMemoryDatabase(
                self._settings.postgres.dsn.get_secret_value()
            )
            await database.open()
            self._database = database
            self._unit_of_work_factory = PostgresMemoryUnitOfWorkFactory(database)
            self._started = True
            self._logging_publisher = LoggingOutboxEventPublisher()
            if self._settings.inbox.enabled:
                self._outbox_publisher = InboxOutboxEventPublisher(
                    inbox_handler=self.process_inbox_handler(),
                    delegate=self._logging_publisher,
                )
            else:
                self._outbox_publisher = self._logging_publisher

        if self._settings.modules.runtime_enabled and self._orchestrator is None:
            self._execution_index = InMemoryRuntimeDatabase()
            if self._settings.temporal.enabled:
                temporal = self._settings.temporal
                self._temporal_client = await connect_temporal_client(
                    TemporalConnectionSettings(
                        address=temporal.address,
                        namespace=temporal.namespace,
                        tls=temporal.tls,
                    )
                )
            self._orchestrator = self._create_orchestrator()

    def _create_orchestrator(self) -> OrchestratorPort:
        assert self._execution_index is not None
        clock = SystemUtcClock()
        if not self._settings.temporal.enabled:
            return InMemoryOrchestratorPort(clock, self._execution_index)
        assert self._temporal_client is not None
        return TemporalOrchestratorPort(
            self._temporal_client,
            task_queue=self._settings.temporal.task_queue,
            index=self._execution_index,
            clock=clock,
        )

    async def shutdown(self) -> None:
        database = self._database
        self._database = None
        self._unit_of_work_factory = None
        self._handler = None
        self._get_episode_handler = None
        self._list_episodes_handler = None
        self._inbox_handler = None
        self._relay_handler = None
        self._execution_index = None
        self._orchestrator = None
        self._temporal_client = None
        self._start_execution_handler = None
        self._get_execution_snapshot_handler = None
        self._cancel_execution_handler = None
        self._logging_publisher = LoggingOutboxEventPublisher()
        self._outbox_publisher = LoggingOutboxEventPublisher()
        self._started = False
        if database is not None:
            await database.close()

    @property
    def outbox_event_publisher(self) -> OutboxEventPublisher:
        return self._outbox_publisher

    @property
    def logging_outbox_event_publisher(self) -> LoggingOutboxEventPublisher:
        return self._logging_publisher

    def process_inbox_handler(self) -> ProcessInboxEventHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._database is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._inbox_handler is None:
            self._inbox_handler = ProcessInboxEventHandler(
                store=PostgresInboxStore(self._database),
                processors=(EpisodeRecordedProcessor(),),
                consumer_name=self._settings.inbox.consumer_name,
                clock=SystemUtcClock(),
            )
        return self._inbox_handler

    def record_episode_handler(self) -> RecordEpisodeHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._unit_of_work_factory is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._handler is None:
            self._handler = RecordEpisodeHandler(
                authorization=create_memory_authorization(self._settings),
                clock=SystemUtcClock(),
                identities=UuidMemoryIdentityPort(),
                unit_of_work_factory=self._unit_of_work_factory,
            )
        return self._handler

    def get_episode_handler(self) -> GetEpisodeHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._unit_of_work_factory is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._get_episode_handler is None:
            self._get_episode_handler = GetEpisodeHandler(
                authorization=create_memory_authorization(self._settings),
                unit_of_work_factory=self._unit_of_work_factory,
            )
        return self._get_episode_handler

    def list_episodes_handler(self) -> ListEpisodesHandler:
        if not self._settings.modules.memory_enabled:
            msg = "memory module is disabled"
            raise ConfigurationError("memory_disabled", msg)
        if not self._started or self._unit_of_work_factory is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._list_episodes_handler is None:
            self._list_episodes_handler = ListEpisodesHandler(
                authorization=create_memory_authorization(self._settings),
                unit_of_work_factory=self._unit_of_work_factory,
            )
        return self._list_episodes_handler

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
                publisher=self.outbox_event_publisher,
            )
        return self._relay_handler

    def start_execution_handler(self) -> StartExecutionHandler:
        if not self._settings.modules.runtime_enabled:
            msg = "runtime module is disabled"
            raise ConfigurationError("runtime_disabled", msg)
        if self._orchestrator is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._start_execution_handler is None:
            self._start_execution_handler = StartExecutionHandler(
                authorization=create_runtime_authorization(self._settings),
                identities=UuidRuntimeIdentityPort(),
                orchestrator=self._orchestrator,
            )
        return self._start_execution_handler

    def get_execution_snapshot_handler(self) -> GetExecutionSnapshotHandler:
        if not self._settings.modules.runtime_enabled:
            msg = "runtime module is disabled"
            raise ConfigurationError("runtime_disabled", msg)
        if self._orchestrator is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._get_execution_snapshot_handler is None:
            self._get_execution_snapshot_handler = GetExecutionSnapshotHandler(
                authorization=create_runtime_authorization(self._settings),
                orchestrator=self._orchestrator,
            )
        return self._get_execution_snapshot_handler

    def cancel_execution_handler(self) -> CancelExecutionHandler:
        if not self._settings.modules.runtime_enabled:
            msg = "runtime module is disabled"
            raise ConfigurationError("runtime_disabled", msg)
        if self._orchestrator is None:
            msg = "application runtime is not started"
            raise RuntimeError(msg)
        if self._cancel_execution_handler is None:
            self._cancel_execution_handler = CancelExecutionHandler(
                authorization=create_runtime_authorization(self._settings),
                orchestrator=self._orchestrator,
            )
        return self._cancel_execution_handler

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
