from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.bootstrap.http.mappers import (
    LimitOutOfRangeError,
    episode_to_response,
    to_list_episodes_query,
)
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))


def make_domain_episode() -> Episode:
    return Episode(
        id=MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db")),
        scope=MemoryScope(
            tenant_id=TENANT,
            subject_id=SUBJECT,
            workspace_id="workspace-42",
        ),
        actor_id=ACTOR,
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")),
        observed_at=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 7, 27, 10, 1, tzinfo=UTC),
        content_hash="sha256:88c7355c",
        idempotency_key="episode-42",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


def test_episode_to_response_includes_tenant_in_scope() -> None:
    episode = make_domain_episode()
    response = episode_to_response(episode)
    assert response.scope.tenant_id == episode.scope.tenant_id.value
    assert response.episode_id == str(episode.id.value)


def test_to_list_episodes_query_rejects_limit_over_100() -> None:
    with pytest.raises(LimitOutOfRangeError):
        to_list_episodes_query(
            path_tenant_id=TENANT,
            actor_id=ACTOR,
            subject_id=SUBJECT,
            workspace_id="workspace-42",
            agent_id=None,
            limit=101,
            cursor=None,
        )
