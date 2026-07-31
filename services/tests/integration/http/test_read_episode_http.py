"""Integration tests for episode read HTTP API."""

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

ACTOR_ID = _helpers.ACTOR_ID
CORRELATION_ID = _helpers.CORRELATION_ID
SUBJECT_ID = _helpers.SUBJECT_ID
TENANT_A = _helpers.TENANT_A
TENANT_B = _helpers.TENANT_B
make_episode_payload = _helpers.make_episode_payload
make_test_settings = _helpers.make_test_settings
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory

READ_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
    "actor_id": str(ACTOR_ID),
}


@pytest.mark.asyncio
async def test_get_after_post_returns_200(client: httpx.AsyncClient) -> None:
    post = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    episode_id = post.json()["episode_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
        params=READ_PARAMS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["episode_id"] == episode_id
    assert body["scope"]["tenant_id"] == str(TENANT_A)


@pytest.mark.asyncio
async def test_get_unknown_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes/00000000-0000-4000-8000-000000000099",
        params=READ_PARAMS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "episode_not_found"


@pytest.mark.asyncio
async def test_get_wrong_subject_returns_404(client: httpx.AsyncClient) -> None:
    post = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    episode_id = post.json()["episode_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
        params={
            **READ_PARAMS,
            "subject_id": "00000000-0000-4000-8000-000000000099",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_first_page_returns_next_cursor(client: httpx.AsyncClient) -> None:
    for index in range(3):
        await client.post(
            f"/v1/tenants/{TENANT_A}/episodes",
            json=make_episode_payload(idempotency_key=f"ep-{index}"),
            headers={"X-Correlation-Id": str(CORRELATION_ID)},
        )
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes",
        params={**READ_PARAMS, "limit": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None


@pytest.mark.asyncio
async def test_list_with_cursor_returns_remaining(client: httpx.AsyncClient) -> None:
    for index in range(3):
        await client.post(
            f"/v1/tenants/{TENANT_A}/episodes",
            json=make_episode_payload(idempotency_key=f"cursor-ep-{index}"),
            headers={"X-Correlation-Id": str(CORRELATION_ID)},
        )
    first = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes",
        params={**READ_PARAMS, "limit": 2},
    )
    second = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes",
        params={
            **READ_PARAMS,
            "limit": 2,
            "cursor": first.json()["next_cursor"],
        },
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_limit_101_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes",
        params={**READ_PARAMS, "limit": 101},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_invalid_cursor_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/episodes",
        params={**READ_PARAMS, "cursor": "not-valid"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_episode_cursor"


@pytest.mark.asyncio
async def test_get_cross_tenant_returns_404(client: httpx.AsyncClient) -> None:
    post = await client.post(
        f"/v1/tenants/{TENANT_A}/episodes",
        json=make_episode_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    episode_id = post.json()["episode_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_B}/episodes/{episode_id}",
        params=READ_PARAMS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "episode_not_found"


@pytest.mark.asyncio
async def test_get_staging_environment_returns_403() -> None:
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
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes/00000000-0000-4000-8000-000000000099",
                params=READ_PARAMS,
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 403
    assert response.json() == error_envelope(
        "episode_read_authorization_denied",
        "episode reading is not authorized",
    )


@pytest.mark.asyncio
async def test_get_memory_disabled_returns_503() -> None:
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
        response = await client.get(
            f"/v1/tenants/{TENANT_A}/episodes/00000000-0000-4000-8000-000000000099",
            params=READ_PARAMS,
        )

    assert response.status_code == 503
    assert response.json() == error_envelope(
        "service_unavailable",
        "service is unavailable",
        details=(
            {
                "type": "configuration_error",
                "loc": [],
                "msg": "memory module is disabled",
                "code": "memory_disabled",
            },
        ),
    )
