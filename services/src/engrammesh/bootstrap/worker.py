"""Temporal worker entry point for durable execution workflows."""

from __future__ import annotations

import asyncio
import signal

from temporalio.worker import Worker

from engrammesh.bootstrap.composition import load_settings
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError
from engrammesh.modules.runtime.adapters.postgres.outbox_writer import (
    PostgresRuntimeOutboxWriter,
)
from engrammesh.modules.runtime.adapters.postgres.snapshot_writer import (
    PostgresRuntimeSnapshotWriter,
)
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
    apply_execution_cancel,
    configure_runtime_outbox_writer,
    configure_runtime_snapshot_writer,
)
from engrammesh.modules.runtime.adapters.temporal.connection import (
    TemporalConnectionSettings,
    connect_temporal_client,
)
from engrammesh.modules.runtime.adapters.temporal.workflows import (
    ExecutionLifecycleWorkflow,
)


async def run_worker(settings: AppSettings) -> None:
    if not settings.temporal.enabled:
        msg = "Temporal worker requires temporal.enabled"
        raise ConfigurationError("temporal_disabled", msg)

    temporal = settings.temporal
    client = await connect_temporal_client(
        TemporalConnectionSettings(
            address=temporal.address,
            namespace=temporal.namespace,
            tls=temporal.tls,
        )
    )
    outbox_writer = PostgresRuntimeOutboxWriter(
        settings.postgres.dsn.get_secret_value(),
    )
    await outbox_writer.open()
    configure_runtime_outbox_writer(outbox_writer)
    snapshot_writer = PostgresRuntimeSnapshotWriter(
        settings.postgres.dsn.get_secret_value(),
    )
    await snapshot_writer.open()
    configure_runtime_snapshot_writer(snapshot_writer)

    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=[ExecutionLifecycleWorkflow],
        activities=[
            advance_to_planning,
            advance_to_running,
            advance_to_succeeded,
            apply_execution_cancel,
        ],
    )

    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    try:
        async with worker:
            await shutdown_event.wait()
    finally:
        configure_runtime_outbox_writer(None)
        configure_runtime_snapshot_writer(None)
        await outbox_writer.close()
        await snapshot_writer.close()


def main() -> None:
    settings = load_settings()
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
