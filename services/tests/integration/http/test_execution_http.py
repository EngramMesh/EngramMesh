"""Integration tests for execution HTTP API (non-OIDC)."""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from engrammesh.bootstrap.composition import create_runtime
from engrammesh.bootstrap.http.app import create_app
from engrammesh.bootstrap.http.errors import error_envelope
from engrammesh.bootstrap.settings import Environment, ModuleSettings
from engrammesh.shared.kernel.ids import ExecutionId

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
OBJECTIVE_REF = _execution_helpers.OBJECTIVE_REF
SUBJECT_ID = _episode_helpers.SUBJECT_ID
TENANT_A = _episode_helpers.TENANT_A
TENANT_B = _episode_helpers.TENANT_B
make_cancel_execution_payload = _execution_helpers.make_cancel_execution_payload
make_start_execution_payload = _execution_helpers.make_start_execution_payload
make_test_settings = _episode_helpers.make_test_settings
seed_succeeded_execution = _execution_helpers.seed_succeeded_execution
start_runtime_with_in_memory = _episode_helpers.start_runtime_with_in_memory

GET_PARAMS = {
    "subject_id": str(SUBJECT_ID),
    "workspace_id": "workspace-42",
    "actor_id": str(ACTOR_ID),
}

OTHER_OBJECTIVE = UUID("00000000-0000-4000-8000-000000000099")


@pytest.mark.asyncio
async def test_post_start_returns_201(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert isinstance(body["execution_id"], str)


@pytest.mark.asyncio
async def test_post_start_idempotent_replay_returns_200(
    client: httpx.AsyncClient,
) -> None:
    payload = make_start_execution_payload()
    first = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=payload,
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    replay = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=payload,
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["execution_id"] == first.json()["execution_id"]


@pytest.mark.asyncio
async def test_post_start_idempotency_conflict_returns_409(
    client: httpx.AsyncClient,
) -> None:
    await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(objective_ref=str(OTHER_OBJECTIVE)),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 409
    assert response.json() == error_envelope(
        "execution_idempotency_conflict",
        "idempotency key conflicts with an existing execution",
    )


@pytest.mark.asyncio
async def test_post_start_naive_deadline_returns_422(client: httpx.AsyncClient) -> None:
    payload = make_start_execution_payload()
    payload["budget"] = {
        **payload["budget"],  # type: ignore[dict-item]
        "deadline": "2026-08-04T12:00:00",
    }
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_post_start_invalid_correlation_id_returns_422(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
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
async def test_get_execution_after_start_returns_200(
    client: httpx.AsyncClient,
) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = start.json()["execution_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
        params=GET_PARAMS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["scope"]["tenant_id"] == str(TENANT_A)


@pytest.mark.asyncio
async def test_get_unknown_execution_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/executions/00000000-0000-4000-8000-000000000099",
        params=GET_PARAMS,
    )

    assert response.status_code == 404
    assert response.json() == error_envelope(
        "execution_not_found",
        "execution not found",
    )


@pytest.mark.asyncio
async def test_get_wrong_subject_returns_404(client: httpx.AsyncClient) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = start.json()["execution_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
        params={
            **GET_PARAMS,
            "subject_id": "00000000-0000-4000-8000-000000000099",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "execution_not_found"


@pytest.mark.asyncio
async def test_get_missing_actor_id_returns_422(client: httpx.AsyncClient) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = start.json()["execution_id"]
    response = await client.get(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
        params={
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "actor_id_required"


@pytest.mark.asyncio
async def test_post_cancel_returns_200_cancelled(client: httpx.AsyncClient) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = start.json()["execution_id"]
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}/cancel",
        json=make_cancel_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_post_cancel_body_tenant_mismatch_returns_422(
    client: httpx.AsyncClient,
) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = start.json()["execution_id"]
    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}/cancel",
        json=make_cancel_execution_payload(
            scope={
                "tenant_id": str(TENANT_B),
                "subject_id": str(SUBJECT_ID),
                "workspace_id": "workspace-42",
            }
        ),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
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
async def test_post_cancel_succeeded_execution_returns_409(
    client: httpx.AsyncClient,
    runtime,
) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    execution_id = ExecutionId(UUID(start.json()["execution_id"]))
    await seed_succeeded_execution(runtime, execution_id)

    response = await client.post(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id.value}/cancel",
        json=make_cancel_execution_payload(),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )

    assert response.status_code == 409
    assert response.json() == error_envelope(
        "invalid_execution_transition",
        "execution transition is not allowed",
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
                f"/v1/tenants/{TENANT_A}/executions",
                json=make_start_execution_payload(),
                headers={"X-Correlation-Id": str(CORRELATION_ID)},
            )
    finally:
        await runtime.shutdown()

    assert response.status_code == 403
    assert response.json() == error_envelope(
        "execution_authorization_denied",
        "execution is not authorized",
    )


@pytest.mark.asyncio
async def test_runtime_disabled_returns_503() -> None:
    runtime = create_runtime(
        make_test_settings(modules=ModuleSettings(runtime_enabled=False))
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
            f"/v1/tenants/{TENANT_A}/executions",
            json=make_start_execution_payload(),
        )

    assert response.status_code == 503
    assert response.json() == error_envelope(
        "service_unavailable",
        "service is unavailable",
        details=(
            {
                "type": "configuration_error",
                "loc": [],
                "msg": "runtime module is disabled",
                "code": "runtime_disabled",
            },
        ),
    )


@pytest.mark.asyncio
async def test_start_get_cancel_composed_flow(client: httpx.AsyncClient) -> None:
    start = await client.post(
        f"/v1/tenants/{TENANT_A}/executions",
        json=make_start_execution_payload(idempotency_key="composed-exec"),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    assert start.status_code == 201
    execution_id = start.json()["execution_id"]

    snapshot = await client.get(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}",
        params=GET_PARAMS,
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["execution_id"] == execution_id
    assert snapshot.json()["status"] == "pending"

    cancel = await client.post(
        f"/v1/tenants/{TENANT_A}/executions/{execution_id}/cancel",
        json=make_cancel_execution_payload(idempotency_key="composed-cancel"),
        headers={"X-Correlation-Id": str(CORRELATION_ID)},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
