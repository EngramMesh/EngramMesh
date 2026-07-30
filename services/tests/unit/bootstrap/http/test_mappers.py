from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.bootstrap.http.mappers import (
    InvalidCorrelationIdError,
    TenantMismatchError,
    parse_correlation_id,
    to_command,
    to_response,
)
from engrammesh.bootstrap.http.schemas import RecordEpisodeRequest, ScopeRequest
from engrammesh.modules.memory.application.contracts import RecordEpisodeResult
from engrammesh.modules.memory.domain.model import (
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT_A = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-000000000002"))
ACTOR_ID = UUID("29ee5d4a-8988-48b9-bd24-e65ba7eb3de5")
AGENT_ID = UUID("b93676a1-4671-47da-a32e-cd4615588188")
CONTENT_REF = UUID("a49f42ec-453a-46ba-98d7-32dda8d6ad7e")
CORRELATION_ID = CorrelationId(UUID("223fdcf1-87da-43f4-b453-02bded156035"))
EPISODE_ID = MemoryId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
SUBJECT_ID = UUID("436b95a8-df23-4d6e-8200-d2058ad62d86")
OBSERVED_AT = datetime(2026, 7, 27, 8, 29, 58, tzinfo=UTC)


def make_body(
    *,
    tenant_id: UUID = TENANT_A.value,
    subject_id: UUID = SUBJECT_ID,
    workspace_id: str | None = "workspace-42",
    agent_id: UUID | None = AGENT_ID,
) -> RecordEpisodeRequest:
    return RecordEpisodeRequest(
        actor_id=ACTOR_ID,
        scope=ScopeRequest(
            tenant_id=tenant_id,
            subject_id=subject_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
        ),
        source_type=SourceType.USER,
        content_ref=CONTENT_REF,
        observed_at=OBSERVED_AT,
        content_hash="sha256:88c7355c",
        idempotency_key="episode-42",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


def test_to_command_rejects_tenant_mismatch() -> None:
    with pytest.raises(TenantMismatchError):
        to_command(
            path_tenant_id=TENANT_A,
            correlation_id=CorrelationId.new(),
            body=make_body(tenant_id=TENANT_B.value),
        )


def test_to_command_maps_all_fields() -> None:
    command = to_command(
        path_tenant_id=TENANT_A,
        correlation_id=CORRELATION_ID,
        body=make_body(),
    )

    assert command.correlation_id == CORRELATION_ID
    assert command.actor_id == SubjectId(ACTOR_ID)
    assert command.scope.tenant_id == TENANT_A
    assert command.scope.subject_id == SubjectId(SUBJECT_ID)
    assert command.scope.workspace_id == "workspace-42"
    assert command.scope.agent_id == AgentInstanceId(AGENT_ID)
    assert command.source_type is SourceType.USER
    assert command.content_ref == ArtifactId(CONTENT_REF)
    assert command.observed_at == OBSERVED_AT
    assert command.content_hash == "sha256:88c7355c"
    assert command.idempotency_key == "episode-42"
    assert command.sensitivity is Sensitivity.CONFIDENTIAL
    assert command.retention_class is RetentionClass.STANDARD
    assert command.consent_basis == "user_request"


def test_to_response_serializes_episode_id_as_uuid_string() -> None:
    response = to_response(
        RecordEpisodeResult(episode_id=EPISODE_ID, created=True)
    )

    assert response.episode_id == str(EPISODE_ID.value)
    assert response.created is True


def test_parse_correlation_id_generates_new_id_when_header_missing() -> None:
    correlation_id = parse_correlation_id(None)

    assert isinstance(correlation_id, CorrelationId)


def test_parse_correlation_id_rejects_invalid_uuid() -> None:
    with pytest.raises(InvalidCorrelationIdError):
        parse_correlation_id("not-a-uuid")
