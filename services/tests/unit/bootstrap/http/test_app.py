"""Unit tests for HTTP application factory."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.http.app import create_app

_helpers_path = (
    Path(__file__).resolve().parents[3] / "integration" / "http" / "episode_http_helpers.py"
)
_spec = importlib.util.spec_from_file_location("episode_http_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

ACTOR_ID = _helpers.ACTOR_ID
CORRELATION_ID = _helpers.CORRELATION_ID
SUBJECT_ID = _helpers.SUBJECT_ID
TENANT_A = _helpers.TENANT_A
make_episode_payload = _helpers.make_episode_payload
make_test_settings = _helpers.make_test_settings
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory


@pytest.mark.asyncio
async def test_create_app_exposes_health_and_ready() -> None:
    runtime = await start_runtime_with_in_memory(make_test_settings())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            health = await client.get("/health")
            ready = await client.get("/ready")
    finally:
        await runtime.shutdown()

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_record_episode_replay_returns_200() -> None:
    runtime = await start_runtime_with_in_memory()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = make_episode_payload()
            first = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=payload,
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
            replay = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=payload,
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["created"] is False


@pytest.mark.asyncio
async def test_get_episode_returns_200_after_post() -> None:
    runtime = await start_runtime_with_in_memory()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            post = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=make_episode_payload(),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
            assert post.status_code == 201
            episode_id = post.json()["episode_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
                params={
                    "subject_id": str(SUBJECT_ID),
                    "workspace_id": "workspace-42",
                    "actor_id": str(ACTOR_ID),
                },
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 200
    assert response.json()["episode_id"] == episode_id
