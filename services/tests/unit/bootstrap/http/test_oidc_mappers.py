from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from engrammesh.bootstrap.auth.ports import AuthenticatedPrincipal
from engrammesh.bootstrap.http.mappers import (
    ActorIdNotAllowedError,
    ActorIdRequiredError,
    resolve_query_actor_id,
    to_command,
)
from engrammesh.bootstrap.http.schemas import RecordEpisodeRequest, ScopeRequest
from engrammesh.shared.kernel.ids import CorrelationId, SubjectId, TenantId

TENANT = TenantId.new()
ACTOR = SubjectId.new()
PRINCIPAL = AuthenticatedPrincipal(actor_id=ACTOR, tenant_id=TENANT)
OBSERVED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)
CONTENT_REF = uuid4()


def _minimal_body(*, actor_id: UUID | None = None) -> RecordEpisodeRequest:
    return RecordEpisodeRequest(
        actor_id=actor_id,
        scope=ScopeRequest(
            tenant_id=TENANT.value,
            subject_id=SubjectId.new().value,
            workspace_id="ws",
        ),
        source_type="user",
        content_ref=CONTENT_REF,
        observed_at=OBSERVED_AT,
        content_hash="sha256:abc",
        idempotency_key="k1",
        sensitivity="confidential",
        retention_class="standard",
        consent_basis="user_request",
    )


def test_to_command_uses_principal_actor() -> None:
    command = to_command(
        path_tenant_id=TENANT,
        correlation_id=CorrelationId.new(),
        body=_minimal_body(actor_id=None),
        principal=PRINCIPAL,
    )
    assert command.actor_id == ACTOR


def test_to_command_rejects_body_actor_id_with_principal() -> None:
    with pytest.raises(ActorIdNotAllowedError):
        to_command(
            path_tenant_id=TENANT,
            correlation_id=CorrelationId.new(),
            body=_minimal_body(actor_id=SubjectId.new().value),
            principal=PRINCIPAL,
        )


def test_to_command_requires_body_actor_id_without_principal() -> None:
    with pytest.raises(ActorIdRequiredError):
        to_command(
            path_tenant_id=TENANT,
            correlation_id=CorrelationId.new(),
            body=_minimal_body(actor_id=None),
            principal=None,
        )


def test_resolve_query_actor_id_rejects_query_param_with_principal() -> None:
    with pytest.raises(ActorIdNotAllowedError):
        resolve_query_actor_id(principal=PRINCIPAL, query_actor_id=ACTOR.value)
