from datetime import UTC
from uuid import UUID

import pytest

from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedMemoryAuthorization,
    SystemUtcClock,
    UuidMemoryIdentityPort,
)
from engrammesh.bootstrap.settings import Environment
from engrammesh.modules.memory.domain.model import MemoryScope, Sensitivity
from engrammesh.modules.memory.ports import AuthorizationRequest
from engrammesh.shared.kernel.ids import MemoryId, SubjectId, TenantId


@pytest.mark.asyncio
async def test_system_utc_clock_returns_timezone_aware_utc() -> None:
    clock = SystemUtcClock()
    now = await clock.now()
    assert now.tzinfo is UTC


@pytest.mark.asyncio
async def test_uuid_identity_port_returns_unique_ids() -> None:
    identities = UuidMemoryIdentityPort()
    memory_id = await identities.new_memory_id()
    event_id = await identities.new_event_id()
    assert isinstance(memory_id, MemoryId)
    assert isinstance(event_id.value, UUID)
    assert memory_id != await identities.new_memory_id()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (Environment.DEVELOPMENT, True),
        (Environment.TEST, True),
        (Environment.STAGING, False),
        (Environment.PRODUCTION, False),
    ],
)
async def test_environment_gated_authorization(
    environment: Environment,
    expected: bool,
) -> None:
    authorization = EnvironmentGatedMemoryAuthorization(environment)
    allowed = await authorization.authorize(
        AuthorizationRequest(
            actor_id=SubjectId(UUID(int=1)),
            scope=MemoryScope(
                tenant_id=TenantId(UUID(int=2)),
                subject_id=SubjectId(UUID(int=3)),
            ),
            action="record_episode",
            sensitivity=Sensitivity.INTERNAL,
        )
    )
    assert allowed is expected
