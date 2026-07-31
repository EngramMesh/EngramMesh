"""PostgreSQL end-to-end integration tests for episode read HTTP API."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.composition import AppRuntime, create_runtime
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

READ_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
    "actor_id": str(ACTOR_ID),
}


async def _postgres_http_client(
    postgres_dsn: str,
) -> tuple[httpx.AsyncClient, AppRuntime]:
    settings = make_test_settings(
        postgres={"dsn": postgres_dsn},
        environment=Environment.TEST,
    )
    runtime = create_runtime(settings)
    await runtime.startup()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    return client, runtime


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_http_postgres_read_lifecycle(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    client, runtime = await _postgres_http_client(postgres_dsn)
    try:
        post = await client.post(
            f"/v1/tenants/{TENANT_A}/episodes",
            json=make_episode_payload(),
            headers={"X-Correlation-Id": str(CORRELATION_ID)},
        )
        assert post.status_code == 201
        episode_id = post.json()["episode_id"]
        got = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
            params=READ_PARAMS,
        )
        assert got.status_code == 200
        assert got.json()["episode_id"] == episode_id
        listed = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes",
            params={**READ_PARAMS, "limit": 10},
        )
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
    finally:
        await client.aclose()
        await runtime.shutdown()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_http_postgres_list_cursor_pagination(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    client, runtime = await _postgres_http_client(postgres_dsn)
    try:
        for index in range(3):
            response = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=make_episode_payload(idempotency_key=f"pg-cursor-{index}"),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
            assert response.status_code == 201

        first = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes",
            params={**READ_PARAMS, "limit": 2},
        )
        assert first.status_code == 200
        first_body = first.json()
        assert len(first_body["items"]) == 2
        assert first_body["next_cursor"] is not None

        second = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes",
            params={
                **READ_PARAMS,
                "limit": 2,
                "cursor": first_body["next_cursor"],
            },
        )
        assert second.status_code == 200
        second_body = second.json()
        first_ids = {item["episode_id"] for item in first_body["items"]}
        second_ids = {item["episode_id"] for item in second_body["items"]}
        assert first_ids.isdisjoint(second_ids)
        assert len(second_body["items"]) == 1
        assert second_body["next_cursor"] is None
    finally:
        await client.aclose()
        await runtime.shutdown()
