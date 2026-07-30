"""PostgreSQL end-to-end integration tests for episode ingest HTTP API."""

from __future__ import annotations

import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope
from engrammesh.bootstrap.settings import AppSettings, Environment

_helpers_path = (
    Path(__file__).resolve().parent.parent / "http" / "episode_http_helpers.py"
)
_spec = importlib.util.spec_from_file_location("episode_http_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

CORRELATION_ID = _helpers.CORRELATION_ID
TENANT_A = _helpers.TENANT_A
make_episode_payload = _helpers.make_episode_payload


def _make_settings(postgres_dsn: str) -> AppSettings:
    return AppSettings.model_validate(
        {
            "environment": Environment.TEST,
            "postgres": {"dsn": postgres_dsn},
            "temporal": {"namespace": "test", "task_queue": "test"},
        }
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_http_postgres_record_episode_lifecycle(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> None:
    settings = _make_settings(postgres_dsn)
    payload = make_episode_payload()

    async with create_runtime(settings) as runtime:
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            yield

        app = create_app(runtime, lifespan=lifespan)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
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
            conflict = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=make_episode_payload(content_hash="sha256:deadbeef"),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )

    assert first.status_code == 201
    first_body = first.json()
    assert first_body["created"] is True
    assert isinstance(first_body["episode_id"], str)

    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["created"] is False
    assert replay_body["episode_id"] == first_body["episode_id"]

    assert conflict.status_code == 409
    assert conflict.json() == error_envelope(
        "episode_idempotency_conflict",
        "idempotency key conflicts with an existing episode",
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM memory_episodes")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM memory_outbox_events")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT payload FROM memory_outbox_events LIMIT 1"
        )
        outbox_payload = cursor.fetchone()[0]

    scope = outbox_payload["scope"]
    if isinstance(scope, str):
        scope = json.loads(scope)
    assert "tenant_id" not in scope
