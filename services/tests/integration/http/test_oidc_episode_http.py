"""Integration tests for OIDC-protected episode HTTP API."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope
from engrammesh.bootstrap.settings import Environment

_helpers_path = Path(__file__).resolve().with_name("episode_http_helpers.py")
_spec = importlib.util.spec_from_file_location("episode_http_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

TENANT_A = _helpers.TENANT_A
TENANT_B = _helpers.TENANT_B
SUBJECT_ID = _helpers.SUBJECT_ID
CORRELATION_ID = _helpers.CORRELATION_ID
auth_headers = _helpers.auth_headers
make_episode_payload_oidc = _helpers.make_episode_payload_oidc
make_oidc_test_settings = _helpers.make_oidc_test_settings
make_static_dev_verifier = _helpers.make_static_dev_verifier
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory


@pytest.mark.asyncio
async def test_post_without_bearer_returns_401() -> None:
    runtime = await start_runtime_with_in_memory(make_oidc_test_settings())
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
                json=make_episode_payload_oidc(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )


@pytest.mark.asyncio
async def test_post_with_valid_bearer_returns_201() -> None:
    runtime = await start_runtime_with_in_memory(make_oidc_test_settings())
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
                json=make_episode_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 201
    assert response.json()["created"] is True


@pytest.mark.asyncio
async def test_post_wrong_path_tenant_returns_403() -> None:
    runtime = await start_runtime_with_in_memory(make_oidc_test_settings())
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
                f"/v1/tenants/{TENANT_B}/episodes",
                json=make_episode_payload_oidc(
                    scope={
                        "tenant_id": str(TENANT_B),
                        "subject_id": str(SUBJECT_ID),
                        "workspace_id": "workspace-42",
                    }
                ),
                headers=auth_headers(tenant_id=TENANT_A),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 403
    assert response.json() == error_envelope(
        "tenant_access_denied",
        "tenant access is denied",
    )


@pytest.mark.asyncio
async def test_get_with_query_actor_id_returns_422() -> None:
    runtime = await start_runtime_with_in_memory(make_oidc_test_settings())
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
                json=make_episode_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            episode_id = post.json()["episode_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
                params={
                    "subject_id": str(SUBJECT_ID),
                    "workspace_id": "workspace-42",
                    "actor_id": str(_helpers.ACTOR_ID),
                },
                headers=auth_headers(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "actor_id_not_allowed"


@pytest.mark.asyncio
async def test_staging_with_injected_verifier_allows_write() -> None:
    runtime = await start_runtime_with_in_memory(
        make_oidc_test_settings(
            environment=Environment.STAGING,
            oidc={
                "enabled": True,
                "issuer": _helpers.DEV_ISSUER,
                "jwks_uri": "https://auth.example.com/jwks",
            },
        )
    )
    injected = make_static_dev_verifier()
    try:
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            yield

        app = create_app(runtime, lifespan=lifespan, token_verifier=injected)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/v1/tenants/{TENANT_A}/episodes",
                json=make_episode_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_get_episode_with_bearer_after_post() -> None:
    runtime = await start_runtime_with_in_memory(make_oidc_test_settings())
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
                json=make_episode_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            episode_id = post.json()["episode_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/episodes/{episode_id}",
                params={
                    "subject_id": str(SUBJECT_ID),
                    "workspace_id": "workspace-42",
                },
                headers=auth_headers(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 200
    assert response.json()["episode_id"] == episode_id
