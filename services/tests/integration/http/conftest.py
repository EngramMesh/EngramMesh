"""Shared fixtures for HTTP integration tests."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest_asyncio
from fastapi import FastAPI

from engrammesh.bootstrap.composition import AppRuntime
from engrammesh.bootstrap.http.app import create_app


def _load_episode_http_helpers():
    path = Path(__file__).with_name("episode_http_helpers.py")
    spec = importlib.util.spec_from_file_location("episode_http_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helpers = _load_episode_http_helpers()
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory


@pytest_asyncio.fixture
async def runtime() -> AppRuntime:
    rt = await start_runtime_with_in_memory()
    yield rt
    await rt.shutdown()


@pytest_asyncio.fixture
async def client(runtime: AppRuntime) -> httpx.AsyncClient:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
