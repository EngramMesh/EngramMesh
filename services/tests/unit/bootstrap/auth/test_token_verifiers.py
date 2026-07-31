from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import jwt
import pytest

from engrammesh.bootstrap.auth.errors import InvalidTokenError
from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.auth.token_verifiers import (
    JwksTokenVerifier,
    StaticDevTokenVerifier,
)
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


def _make_jwks_verifier(
    *,
    jwks_client: MagicMock,
    audience: str | None = None,
) -> JwksTokenVerifier:
    return JwksTokenVerifier(
        issuer=ISSUER,
        jwks_client=jwks_client,
        actor_claim="sub",
        tenant_claim="tenant_id",
        audience=audience,
    )


@pytest.mark.asyncio
async def test_jwks_verifier_uses_pyjwt_client(monkeypatch: pytest.MonkeyPatch) -> None:
    signing_key = MagicMock()
    signing_key.key = "rsa-public-key"

    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key

    decode_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_decode(*args: Any, **kwargs: Any) -> dict[str, str]:
        decode_calls.append((args, kwargs))
        return {
            "sub": str(ACTOR_ID),
            "tenant_id": str(TENANT_ID),
        }

    monkeypatch.setattr(
        "engrammesh.bootstrap.auth.token_verifiers.jwt.decode",
        fake_decode,
    )

    to_thread_calls: list[tuple[Any, tuple[Any, ...]]] = []

    async def fake_to_thread(func: Any, /, *args: Any) -> Any:
        to_thread_calls.append((func, args))
        return func(*args)

    monkeypatch.setattr(
        "engrammesh.bootstrap.auth.token_verifiers.asyncio.to_thread",
        fake_to_thread,
    )

    verifier = _make_jwks_verifier(jwks_client=jwks_client, audience=None)
    token = "fake.jwt.token"

    principal = await verifier.verify(token)

    assert principal == AuthenticatedPrincipal(
        actor_id=SubjectId(ACTOR_ID),
        tenant_id=TenantId(TENANT_ID),
    )
    jwks_client.get_signing_key_from_jwt.assert_called_once_with(token)
    assert len(to_thread_calls) == 1
    assert to_thread_calls[0][0] == jwks_client.get_signing_key_from_jwt
    assert to_thread_calls[0][1] == (token,)
    assert len(decode_calls) == 1
    args, kwargs = decode_calls[0]
    assert args == (token, "rsa-public-key")
    assert kwargs["algorithms"] == ["RS256", "ES256", "EdDSA"]
    assert kwargs["issuer"] == ISSUER
    assert kwargs["audience"] is None
    assert kwargs["options"] == {"require": ["exp", "sub"], "verify_aud": False}
