"""PostgreSQL end-to-end integration tests for episode read HTTP API."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.settings import Environment

_helpers_path = (
    Path(__file__).resolve().parent.parent / "http" / "episode_http_helpers.py"
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


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_http_postgres_read_lifecycle(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    settings = make_test_settings(
        postgres={"dsn": postgres_dsn},
        environment=Environment.TEST,
    )
    runtime = create_runtime(settings)
    await runtime.startup()
    try:
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            yield

        app = create_app(runtime, lifespan=lifespan)
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
            got = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
                params={
                    "subject_id": str(SUBJECT_ID),
                    "workspace_id": "workspace-42",
                    "actor_id": str(ACTOR_ID),
                },
            )
            assert got.status_code == 200
            assert got.json()["episode_id"] == episode_id
            listed = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes",
                params={
                    "subject_id": str(SUBJECT_ID),
                    "workspace_id": "workspace-42",
                    "actor_id": str(ACTOR_ID),
                    "limit": 10,
                },
            )
            assert listed.status_code == 200
            assert len(listed.json()["items"]) == 1
    finally:
        await runtime.shutdown()
