"""JWT token verifiers for bootstrap-layer OIDC integration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
from jwt.types import Options

from engrammesh.bootstrap.auth.errors import InvalidTokenError
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.shared.kernel.ids import SubjectId, TenantId

_decode_options: Options = {"require": ["exp", "sub"]}


def _claim_uuid(payload: dict[str, Any], claim: str) -> UUID:
    try:
        return UUID(str(payload[claim]))
    except (KeyError, ValueError, AttributeError) as exc:
        raise InvalidTokenError() from exc


class StaticDevTokenVerifier:
    """HS256 JWT verifier for development and test environments."""

    def __init__(
        self,
        *,
        issuer: str,
        signing_key: str,
        actor_claim: str = "sub",
        tenant_claim: str = "tenant_id",
        audience: str | None = None,
    ) -> None:
        self._issuer = issuer
        self._signing_key = signing_key
        self._actor_claim = actor_claim
        self._tenant_claim = tenant_claim
        self._audience = audience

    async def verify(self, token: str) -> AuthenticatedPrincipal:
        options: Options = (
            {**_decode_options, "verify_aud": False}
            if self._audience is None
            else _decode_options
        )
        try:
            payload = jwt.decode(
                token,
                self._signing_key,
                algorithms=["HS256"],
                issuer=self._issuer,
                audience=self._audience,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError() from exc
        return AuthenticatedPrincipal(
            actor_id=SubjectId(_claim_uuid(payload, self._actor_claim)),
            tenant_id=TenantId(_claim_uuid(payload, self._tenant_claim)),
        )
