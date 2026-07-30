"""Shared helpers for HTTP integration tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

from engrammesh.bootstrap.composition import AppRuntime, create_runtime
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)

TENANT_A = UUID("53dad495-7915-439a-b03a-379452a1aa86")
TENANT_B = UUID("e63173e8-8f03-4f34-beac-2020676684c0")
SUBJECT_ID = UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45")
ACTOR_ID = UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6")
CONTENT_REF = UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")
CORRELATION_ID = UUID("02ffae84-2764-41f3-a22a-4d4652a7c139")
OBSERVED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


def make_test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def mock_postgres_connection() -> Any:
    @asynccontextmanager
    async def healthy_connection():
        connection = AsyncMock()
        connection.execute = AsyncMock()
        yield connection

    return healthy_connection


async def start_runtime_with_in_memory(
    settings: AppSettings | None = None,
) -> AppRuntime:
    runtime = create_runtime(settings if settings is not None else make_test_settings())
    with patch("engrammesh.bootstrap.composition.PostgresMemoryDatabase") as cls:
        database = cls.return_value
        database.open = AsyncMock()
        database.close = AsyncMock()
        database.connection = mock_postgres_connection()
        await runtime.startup()
        runtime._unit_of_work_factory = InMemoryMemoryUnitOfWorkFactory(
            InMemoryMemoryDatabase()
        )
    return runtime


def make_episode_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor_id": str(ACTOR_ID),
        "scope": {
            "tenant_id": str(TENANT_A),
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
        },
        "source_type": "user",
        "content_ref": str(CONTENT_REF),
        "observed_at": OBSERVED_AT.isoformat(),
        "content_hash": "sha256:88c7355c",
        "idempotency_key": "episode-42",
        "sensitivity": "confidential",
        "retention_class": "standard",
        "consent_basis": "user_request",
    }
    payload.update(overrides)
    return payload
