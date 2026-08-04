"""Integration tests for OIDC-protected execution HTTP API."""

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

_episode_helpers_path = Path(__file__).resolve().with_name("episode_http_helpers.py")
_episode_spec = importlib.util.spec_from_file_location(
    "episode_http_helpers", _episode_helpers_path
)
assert _episode_spec is not None and _episode_spec.loader is not None
_episode_helpers = importlib.util.module_from_spec(_episode_spec)
_episode_spec.loader.exec_module(_episode_helpers)

_execution_helpers_path = Path(__file__).resolve().with_name(
    "execution_http_helpers.py"
)
_execution_spec = importlib.util.spec_from_file_location(
    "execution_http_helpers", _execution_helpers_path
)
assert _execution_spec is not None and _execution_spec.loader is not None
_execution_helpers = importlib.util.module_from_spec(_execution_spec)
_execution_spec.loader.exec_module(_execution_helpers)

ACTOR_ID = _episode_helpers.ACTOR_ID
CORRELATION_ID = _episode_helpers.CORRELATION_ID
SUBJECT_ID = _episode_helpers.SUBJECT_ID
TENANT_A = _episode_helpers.TENANT_A
TENANT_B = _episode_helpers.TENANT_B
auth_headers = _episode_helpers.auth_headers
make_cancel_execution_payload = _execution_helpers.make_cancel_execution_payload
make_oidc_test_settings = _episode_helpers.make_oidc_test_settings
make_start_execution_payload = _execution_helpers.make_start_execution_payload
make_static_dev_verifier = _episode_helpers.make_static_dev_verifier
start_runtime_with_in_memory = _episode_helpers.start_runtime_with_in_memory

GET_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
}


def make_start_execution_payload_oidc(**overrides: object) -> dict[str, object]:
    payload = make_start_execution_payload(**overrides)
    payload.pop("actor_id", None)
    return payload


def make_cancel_execution_payload_oidc(**overrides: object) -> dict[str, object]:
    payload = make_cancel_execution_payload(**overrides)
    payload.pop("actor_id", None)
    return payload


@pytest.mark.asyncio
async def test_post_start_without_bearer_returns_401() -> None:
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
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )


@pytest.mark.asyncio
async def test_post_start_with_valid_bearer_returns_201() -> None:
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
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 201
    assert response.json()["created"] is True


@pytest.mark.asyncio
async def test_post_start_wrong_path_tenant_returns_403() -> None:
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
                f"/v1/tenants/{TENANT_B}/executions",
                json=make_start_execution_payload_oidc(
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
async def test_post_start_actor_id_in_body_returns_422() -> None:
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
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "actor_id_not_allowed"


@pytest.mark.asyncio
async def test_get_without_bearer_returns_401() -> None:
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
            start = await client.post(
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            execution_id = start.json()["execution_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
                params=GET_PARAMS,
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )


@pytest.mark.asyncio
async def test_get_with_valid_bearer_returns_200() -> None:
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
            start = await client.post(
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            execution_id = start.json()["execution_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
                params=GET_PARAMS,
                headers=auth_headers(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 200
    assert response.json()["execution_id"] == execution_id


@pytest.mark.asyncio
async def test_cancel_without_bearer_returns_401() -> None:
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
            start = await client.post(
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            execution_id = start.json()["execution_id"]
            response = await client.post(
                f"/v1/tenants/{TENANT_A}/executions/{execution_id}/cancel",
                json=make_cancel_execution_payload_oidc(),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )


@pytest.mark.asyncio
async def test_cancel_with_valid_bearer_returns_200() -> None:
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
            start = await client.post(
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            execution_id = start.json()["execution_id"]
            response = await client.post(
                f"/v1/tenants/{TENANT_A}/executions/{execution_id}/cancel",
                json=make_cancel_execution_payload_oidc(),
                headers={
                    **auth_headers(),
                    "X-Correlation-Id": str(CORRELATION_ID),
                },
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_get_actor_id_in_query_returns_422() -> None:
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
            start = await client.post(
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
            execution_id = start.json()["execution_id"]
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
                params={
                    **GET_PARAMS,
                    "actor_id": str(ACTOR_ID),
                },
                headers=auth_headers(),
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "actor_id_not_allowed"


@pytest.mark.asyncio
async def test_staging_with_injected_verifier_allows_start() -> None:
    runtime = await start_runtime_with_in_memory(
        make_oidc_test_settings(
            environment=Environment.STAGING,
            oidc={
                "enabled": True,
                "issuer": _episode_helpers.DEV_ISSUER,
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
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload_oidc(),
                headers={**auth_headers(), "X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 201
