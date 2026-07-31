from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedRuntimeAuthorization,
    UuidRuntimeIdentityPort,
    create_runtime_authorization,
)
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
from engrammesh.shared.kernel.ids import ExecutionId, SubjectId, TenantId


@pytest.mark.asyncio
async def test_runtime_authorization_allows_development() -> None:
    auth = EnvironmentGatedRuntimeAuthorization(Environment.DEVELOPMENT)
    scope = MemoryScope(TenantId(UUID(int=1)), SubjectId(UUID(int=2)))
    allowed = await auth.authorize(
        RuntimeAuthorizationRequest(
            actor_id=SubjectId(UUID(int=3)),
            scope=scope,
            action="start_execution",
        )
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_runtime_authorization_denies_production() -> None:
    auth = EnvironmentGatedRuntimeAuthorization(Environment.PRODUCTION)
    scope = MemoryScope(TenantId(UUID(int=1)), SubjectId(UUID(int=2)))
    allowed = await auth.authorize(
        RuntimeAuthorizationRequest(
            actor_id=SubjectId(UUID(int=3)),
            scope=scope,
            action="start_execution",
        )
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_uuid_runtime_identity_port_generates_execution_id() -> None:
    port = UuidRuntimeIdentityPort()
    first = await port.new_execution_id()
    second = await port.new_execution_id()
    assert isinstance(first, ExecutionId)
    assert first != second


def test_create_runtime_authorization_uses_environment_gate() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
        }
    )
    auth = create_runtime_authorization(settings)
    assert isinstance(auth, EnvironmentGatedRuntimeAuthorization)
