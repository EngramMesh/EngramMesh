"""Integration tests for claim read HTTP API."""

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
SUBJECT_ID = _helpers.SUBJECT_ID
TENANT_A = _helpers.TENANT_A
TENANT_B = _helpers.TENANT_B
make_test_settings = _helpers.make_test_settings
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory

READ_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
    "actor_id": str(ACTOR_ID),
}

UNKNOWN_CLAIM_ID = "00000000-0000-4000-8000-000000000099"


@pytest.mark.asyncio
async def test_get_claims_returns_503_claims_unavailable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/claims",
        params=READ_PARAMS,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "claims_unavailable"


@pytest.mark.asyncio
async def test_get_claim_by_id_returns_503_claims_unavailable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/claims/{UNKNOWN_CLAIM_ID}",
        params=READ_PARAMS,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "claims_unavailable"


@pytest.mark.asyncio
async def test_list_claims_limit_101_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/claims",
        params={**READ_PARAMS, "limit": 101},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_claim_cross_tenant_still_unavailable_in_memory(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_B}/claims/{UNKNOWN_CLAIM_ID}",
        params=READ_PARAMS,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "claims_unavailable"


@pytest.mark.asyncio
async def test_get_claim_staging_environment_returns_403() -> None:
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
                f"/v1/tenants/{TENANT_A}/claims/{UNKNOWN_CLAIM_ID}",
                params=READ_PARAMS,
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 403
    assert response.json() == error_envelope(
        "claim_read_authorization_denied",
        "claim reading is not authorized",
    )


@pytest.mark.asyncio
async def test_get_claim_memory_disabled_returns_503() -> None:
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
            f"/v1/tenants/{TENANT_A}/claims/{UNKNOWN_CLAIM_ID}",
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
