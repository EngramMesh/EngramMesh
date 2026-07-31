from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest

from engrammesh.bootstrap.auth.errors import InvalidTokenError
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.auth.token_verifiers import StaticDevTokenVerifier
from engrammesh.shared.kernel.ids import SubjectId, TenantId

ISSUER = "https://dev.engrammesh.test"
SIGNING_KEY = "dev-only-signing-key-not-for-production"
ACTOR_ID = UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6")
TENANT_ID = UUID("53dad495-7915-439a-b03a-379452a1aa86")


def _mint_token(
    *,
    signing_key: str = SIGNING_KEY,
    issuer: str = ISSUER,
    actor_id: UUID = ACTOR_ID,
    tenant_id: UUID = TENANT_ID,
    audience: str | None = None,
    expired: bool = False,
    omit_tenant_claim: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload: dict[str, object] = {
        "sub": str(actor_id),
        "iss": issuer,
        "exp": exp,
    }
    if not omit_tenant_claim:
        payload["tenant_id"] = str(tenant_id)
    if audience is not None:
        payload["aud"] = audience
    return jwt.encode(payload, signing_key, algorithm="HS256")


def _make_verifier(*, audience: str | None = None) -> StaticDevTokenVerifier:
    return StaticDevTokenVerifier(
        issuer=ISSUER,
        signing_key=SIGNING_KEY,
        actor_claim="sub",
        tenant_claim="tenant_id",
        audience=audience,
    )


@pytest.mark.asyncio
async def test_verify_valid_token_returns_principal() -> None:
    verifier = _make_verifier()
    token = _mint_token()

    principal = await verifier.verify(token)

    assert principal == AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )


@pytest.mark.asyncio
async def test_verify_expired_token_raises_invalid_token_error() -> None:
    verifier = _make_verifier()
    token = _mint_token(expired=True)

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_verify_token_without_audience_when_audience_not_configured() -> None:
    verifier = _make_verifier(audience=None)
    token = _mint_token(audience=None)

    principal = await verifier.verify(token)

    assert principal.tenant_id == TenantId(TENANT_ID)


@pytest.mark.asyncio
async def test_verify_token_requires_matching_audience_when_configured() -> None:
    verifier = _make_verifier(audience="engrammesh-api")
    token = _mint_token(audience="engrammesh-api")

    principal = await verifier.verify(token)

    assert principal.actor_id == SubjectId(ACTOR_ID)


@pytest.mark.asyncio
async def test_verify_token_rejects_wrong_audience_when_configured() -> None:
    verifier = _make_verifier(audience="engrammesh-api")
    token = _mint_token(audience="other-audience")

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_verify_token_rejects_invalid_signature() -> None:
    verifier = _make_verifier()
    token = _mint_token(signing_key="different-signing-key")

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_verify_token_rejects_missing_tenant_claim() -> None:
    verifier = _make_verifier()
    token = _mint_token(omit_tenant_claim=True)

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)
