"""Temporal worker entry point for durable execution workflows."""

from __future__ import annotations

import asyncio
import signal

from temporalio.worker import Worker

from engrammesh.bootstrap.composition import load_settings
from engrammesh.bootstrap.settings import AppSettings, ConfigurationError
from engrammesh.modules.runtime.adapters.temporal.activities import (
    advance_to_planning,
    advance_to_running,
    advance_to_succeeded,
)
from engrammesh.modules.runtime.adapters.temporal.client import connect_temporal_client
from engrammesh.modules.runtime.adapters.temporal.workflows import (
    ExecutionLifecycleWorkflow,
)


async def run_worker(settings: AppSettings) -> None:
    if not settings.temporal.enabled:
        msg = "Temporal worker requires temporal.enabled"
        raise ConfigurationError("temporal_disabled", msg)

    client = await connect_temporal_client(settings.temporal)
    worker = Worker(
        client,
        task_queue=settings.temporal.task_queue,
        workflows=[ExecutionLifecycleWorkflow],
        activities=[
            advance_to_planning,
            advance_to_running,
            advance_to_succeeded,
        ],
    )

    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    async with worker:
        await shutdown_event.wait()


def main() -> None:
    settings = load_settings()
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
