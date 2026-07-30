"""Integration tests for episode ingest HTTP API."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope
from engrammesh.bootstrap.settings import Environment, ModuleSettings

_helpers_path = Path(__file__).resolve().with_name("episode_http_helpers.py")
_spec = importlib.util.spec_from_file_location("episode_http_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

CORRELATION_ID = _helpers.CORRELATION_ID
SUBJECT_ID = _helpers.SUBJECT_ID
TENANT_A = _helpers.TENANT_A
TENANT_B = _helpers.TENANT_B
make_episode_payload = _helpers.make_episode_payload
make_test_settings = _helpers.make_test_settings
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory


@pytest.mark.asyncio
async def test_post_first_write_returns_201(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert isinstance(body["episode_id"], str)


@pytest.mark.asyncio
async def test_post_idempotent_replay_returns_200(client: httpx.AsyncClient) -> None:
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

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["episode_id"] == first.json()["episode_id"]


@pytest.mark.asyncio
async def test_post_idempotency_conflict_returns_409(
    client: httpx.AsyncClient,
) -> None:
    await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(content_hash="sha256:deadbeef"),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 409
    assert response.json() == error_envelope(
        "episode_idempotency_conflict",
        "idempotency key conflicts with an existing episode",
    )


@pytest.mark.asyncio
async def test_post_staging_environment_returns_403() -> None:
    runtime = await start_runtime_with_in_memory(
        make_test_settings(environment=Environment.STAGING)
    )
    try:
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            yield

        app = create_app(runtime, lifespan=lifespan)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=make_episode_payload(),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 403
    assert response.json() == error_envelope(
        "episode_authorization_denied",
        "episode recording is not authorized",
    )


@pytest.mark.asyncio
async def test_post_tenant_mismatch_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(
            scope={
                "tenant_id": str(TENANT_B),
                "subject_id": str(SUBJECT_ID),
                "workspace_id": "workspace-42",
            }
        ),
    )

    assert response.status_code == 422
    assert response.json() == error_envelope(
        "validation_error",
        "request validation failed",
        details=(
            {
                "type": "value_error",
                "loc": ["scope", "tenant_id"],
                "msg": "path tenant_id does not match body scope.tenant_id",
            },
        ),
    )


@pytest.mark.asyncio
async def test_post_invalid_correlation_id_returns_422(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": "not-uuid"},
    )

    assert response.status_code == 422
    assert response.json() == error_envelope(
        "validation_error",
        "request validation failed",
        details=(
            {
                "type": "value_error",
                "loc": ["header", "X-Correlation-Id"],
                "msg": "correlation id must be a UUID",
            },
        ),
    )


@pytest.mark.asyncio
async def test_ready_before_startup_returns_503_runtime_not_started() -> None:
    runtime = create_runtime(make_test_settings())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "runtime_not_started",
    }


@pytest.mark.asyncio
async def test_post_memory_disabled_returns_503() -> None:
    runtime = create_runtime(
        make_test_settings(modules=ModuleSettings(memory_enabled=False))
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = create_app(runtime, lifespan=lifespan)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/v1/tenants/{TENANT_A}/episodes",
            json=make_episode_payload(),
        )

    assert response.status_code == 503
    assert response.json() == error_envelope(
        "service_unavailable",
        "memory module is disabled",
        details=(
            {
                "type": "configuration_error",
                "loc": [],
                "msg": "memory module is disabled",
                "code": "memory_disabled",
            },
        ),
    )


@pytest.mark.asyncio
async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_when_started_returns_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
