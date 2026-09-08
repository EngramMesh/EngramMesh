"""Integration tests for OIDC-protected claim read HTTP API."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope

_helpers_path = Path(__file__).resolve().with_name("episode_http_helpers.py")
_spec = importlib.util.spec_from_file_location("episode_http_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)

TENANT_A = _helpers.TENANT_A
SUBJECT_ID = _helpers.SUBJECT_ID
make_oidc_test_settings = _helpers.make_oidc_test_settings
start_runtime_with_in_memory = _helpers.start_runtime_with_in_memory

READ_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
}


@pytest.mark.asyncio
async def test_get_claim_without_bearer_returns_401() -> None:
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
            response = await client.get(
                f"/v1/tenants/{TENANT_A}/claims",
                params=READ_PARAMS,
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 401
    assert response.json() == error_envelope(
        "authentication_required",
        "authentication is required",
    )
