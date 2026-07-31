from __future__ import annotations

from uuid import UUID

import pytest

from engrammesh.bootstrap.auth.context import bind_principal, reset_principal
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedMemoryAuthorization,
    TenantScopedMemoryAuthorization,
    create_memory_authorization,
)
from engrammesh.bootstrap.settings import AppSettings, Environment
from engrammesh.modules.memory.domain.model import MemoryScope, Sensitivity
from engrammesh.modules.memory.ports import AuthorizationRequest
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
TENANT_ID = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
OTHER_TENANT_ID = TenantId(UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))


def _test_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "postgres": {"dsn": "postgresql://u:p@localhost/db"},
        "temporal": {"namespace": "ns", "task_queue": "q"},
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def _auth_request(
    *,
    actor_id: SubjectId = ACTOR_ID,
    tenant_id: TenantId = TENANT_ID,
) -> AuthorizationRequest:
    return AuthorizationRequest(
        actor_id=actor_id,
        scope=MemoryScope(
            tenant_id=tenant_id,
            subject_id=SubjectId(UUID(int=1)),
        ),
        action="read_episode",
        sensitivity=Sensitivity.INTERNAL,
    )


@pytest.mark.asyncio
async def test_tenant_scoped_authorization_allows_matching_principal() -> None:
    authorization = TenantScopedMemoryAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(_auth_request())
    finally:
        reset_principal(token)
    assert allowed is True


@pytest.mark.asyncio
async def test_tenant_scoped_authorization_denies_other_tenant() -> None:
    authorization = TenantScopedMemoryAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(
            _auth_request(tenant_id=OTHER_TENANT_ID)
        )
    finally:
        reset_principal(token)
    assert allowed is False


def test_create_memory_authorization_selects_tenant_scoped_when_oidc_enabled() -> None:
    settings = _test_settings(oidc={"enabled": True})
    authorization = create_memory_authorization(settings)
    assert isinstance(authorization, TenantScopedMemoryAuthorization)


def test_create_memory_authorization_selects_environment_gated_when_oidc_disabled() -> (
    None
):
    settings = _test_settings()
    authorization = create_memory_authorization(settings)
    assert isinstance(authorization, EnvironmentGatedMemoryAuthorization)
