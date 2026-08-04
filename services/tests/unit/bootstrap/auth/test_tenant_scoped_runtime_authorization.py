from __future__ import annotations

from uuid import UUID

import pytest

from engrammesh.bootstrap.auth.context import bind_principal, reset_principal
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.infrastructure import (
    EnvironmentGatedRuntimeAuthorization,
    TenantScopedRuntimeAuthorization,
    create_runtime_authorization,
)
from engrammesh.bootstrap.settings import AppSettings
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.ports import RuntimeAuthorizationRequest
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ACTOR_ID = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
TENANT_ID = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
OTHER_TENANT_ID = TenantId(UUID("e63173e8-8f03-4f34-beac-2020676684c0"))


def _runtime_auth_request(
    *,
    tenant_id: TenantId = TENANT_ID,
    action: str = "start_execution",
) -> RuntimeAuthorizationRequest:
    return RuntimeAuthorizationRequest(
        actor_id=ACTOR_ID,
        scope=MemoryScope(tenant_id=tenant_id, subject_id=SubjectId(UUID(int=1))),
        action=action,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_tenant_scoped_runtime_authorization_allows_matching_principal() -> None:
    authorization = TenantScopedRuntimeAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(_runtime_auth_request())
    finally:
        reset_principal(token)
    assert allowed is True


@pytest.mark.asyncio
async def test_tenant_scoped_runtime_authorization_denies_other_tenant() -> None:
    authorization = TenantScopedRuntimeAuthorization()
    token = bind_principal(
        AuthenticatedPrincipal(actor_id=ACTOR_ID, tenant_id=TENANT_ID)
    )
    try:
        allowed = await authorization.authorize(
            _runtime_auth_request(tenant_id=OTHER_TENANT_ID)
        )
    finally:
        reset_principal(token)
    assert allowed is False


def test_create_runtime_authorization_selects_tenant_scoped_when_oidc_enabled() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
            "oidc": {
                "enabled": True,
                "issuer": "https://dev.engrammesh.test",
                "dev_signing_key": "dev-only-signing-key-not-for-production",
            },
        }
    )
    authorization = create_runtime_authorization(settings)
    assert isinstance(authorization, TenantScopedRuntimeAuthorization)


def test_create_runtime_authorization_selects_environment_gate_when_oidc_disabled() -> None:
    settings = AppSettings.model_validate(
        {
            "environment": "test",
            "postgres": {"dsn": "postgresql://u:p@localhost/db"},
            "temporal": {"namespace": "ns", "task_queue": "q"},
        }
    )
    authorization = create_runtime_authorization(settings)
    assert isinstance(authorization, EnvironmentGatedRuntimeAuthorization)
