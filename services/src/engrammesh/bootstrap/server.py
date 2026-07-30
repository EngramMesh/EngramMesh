"""Uvicorn entry point for the EngramMesh HTTP control API."""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from engrammesh.bootstrap.composition import create_runtime, load_settings
from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.settings import ConfigurationError


def main() -> None:
    settings = load_settings()
    if not settings.http.enabled:
        raise ConfigurationError("http_disabled", "HTTP server is disabled")
    runtime = create_runtime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await runtime.startup()
        try:
            yield
        finally:
            await runtime.shutdown()

    app = create_app(runtime, lifespan=lifespan)
    uvicorn.run(app, host=settings.http.host, port=settings.http.port)


if __name__ == "__main__":
    main()
