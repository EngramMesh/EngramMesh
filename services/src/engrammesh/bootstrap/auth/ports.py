"""Authentication ports for bootstrap-layer OIDC integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from engrammesh.shared.kernel.ids import SubjectId, TenantId


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Verified actor and tenant identity from a JWT."""

    actor_id: SubjectId
    tenant_id: TenantId


@runtime_checkable
class TokenVerifierPort(Protocol):
    """JWT verification boundary."""

    async def verify(self, token: str) -> AuthenticatedPrincipal: ...
