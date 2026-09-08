from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.bootstrap.http.mappers import (
    LimitOutOfRangeError,
    claim_to_response,
    to_get_claim_query,
    to_list_claims_query,
)
from engrammesh.modules.memory.domain.model import (
    Claim,
    ClaimStatus,
    EpistemicKind,
    EvidenceRef,
    MemoryScope,
)
from engrammesh.shared.kernel.ids import MemoryId, SubjectId, TenantId

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
CLAIM_ID = MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db"))
EPISODE_ID = MemoryId(UUID("940ddfba-f834-486b-b918-bbb87a6bf9db"))
RECORDED_AT = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def make_domain_claim() -> Claim:
    return Claim(
        id=CLAIM_ID,
        scope=MemoryScope(
            tenant_id=TENANT,
            subject_id=SUBJECT,
            workspace_id="workspace-42",
        ),
        subject=str(SUBJECT),
        predicate="observed_content_hash",
        object_value="sha256:abc",
        polarity=True,
        epistemic_kind=EpistemicKind.EXTRACTED,
        confidence=1.0,
        valid_from=RECORDED_AT,
        valid_to=None,
        recorded_from=RECORDED_AT,
        recorded_to=None,
        status=ClaimStatus.PROPOSED,
        evidence=(
            EvidenceRef(
                episode_id=EPISODE_ID,
                source_span="metadata",
                extractor_version="deterministic-v1",
            ),
        ),
    )


def test_claim_to_response_maps_episode_id_from_evidence() -> None:
    claim = make_domain_claim()
    response = claim_to_response(claim)
    assert response.claim_id == str(CLAIM_ID.value)
    assert response.episode_id == EPISODE_ID.value
    assert response.scope.tenant_id == TENANT.value
    assert response.extractor_version == "deterministic-v1"
    assert len(response.evidence) == 1


def test_to_get_claim_query_builds_scope() -> None:
    query = to_get_claim_query(
        path_tenant_id=TENANT,
        claim_id=CLAIM_ID,
        actor_id=ACTOR,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
        agent_id=None,
    )
    assert query.claim_id == CLAIM_ID
    assert query.scope.tenant_id == TENANT
    assert query.scope.subject_id == SUBJECT


def test_to_list_claims_query_rejects_limit_over_100() -> None:
    with pytest.raises(LimitOutOfRangeError):
        to_list_claims_query(
            path_tenant_id=TENANT,
            actor_id=ACTOR,
            subject_id=SUBJECT,
            workspace_id="workspace-42",
            agent_id=None,
            limit=101,
            cursor=None,
        )
