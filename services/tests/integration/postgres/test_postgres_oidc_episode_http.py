"""PostgreSQL end-to-end integration tests for OIDC episode HTTP API."""

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

CORRELATION_ID = _helpers.CORRELATION_ID
SUBJECT_ID = _helpers.SUBJECT_ID
TENANT_A = _helpers.TENANT_A
auth_headers = _helpers.auth_headers
make_episode_payload_oidc = _helpers.make_episode_payload_oidc
make_oidc_test_settings = _helpers.make_oidc_test_settings

READ_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
}


async def _postgres_oidc_http_client(
    postgres_dsn: str,
) -> tuple[httpx.AsyncClient, AppRuntime]:
    settings = make_oidc_test_settings(
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
async def test_http_postgres_oidc_episode_lifecycle(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    del postgres_connection
    client, runtime = await _postgres_oidc_http_client(postgres_dsn)
    try:
        post = await client.post(
            f"/v1/tenants/{TENANT_A}/episodes",
            json=make_episode_payload_oidc(),
            headers={
                **auth_headers(),
                "X-Correlation-Id": str(CORRELATION_ID),
            },
        )
        assert post.status_code == 201
        episode_id = post.json()["episode_id"]
        got = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
            params=READ_PARAMS,
            headers=auth_headers(),
        )
        assert got.status_code == 200
        assert got.json()["episode_id"] == episode_id
        listed = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes",
            params={**READ_PARAMS, "limit": 10},
            headers=auth_headers(),
        )
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
    finally:
        await client.aclose()
        await runtime.shutdown()
