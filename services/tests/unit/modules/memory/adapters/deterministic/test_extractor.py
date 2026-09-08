"""Unit tests for DeterministicMemoryExtractor."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from engrammesh.modules.memory.adapters.deterministic.extractor import (
    SENTINEL_CLAIM_ID,
    DeterministicMemoryExtractor,
)
from engrammesh.modules.memory.domain.model import (
    ClaimStatus,
    Episode,
    EpistemicKind,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import ArtifactId, MemoryId, SubjectId, TenantId

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
TENANT = TenantId(UUID(int=1))
SUBJECT = SubjectId(UUID(int=2))


def _episode() -> Episode:
    return Episode(
        id=MemoryId(UUID(int=3)),
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws"),
        actor_id=SUBJECT,
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID(int=4)),
        observed_at=NOW,
        ingested_at=NOW,
        content_hash="abc123",
        idempotency_key="key-1",
        sensitivity=Sensitivity.INTERNAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="test",
    )


@pytest.mark.asyncio
async def test_propose_returns_one_proposal_with_sentinel_id() -> None:
    episode = _episode()
    extractor = DeterministicMemoryExtractor(extractor_version="deterministic-v1")
    proposals = await extractor.propose(episode)
    assert len(proposals) == 1
    claim = proposals[0].claim
    assert claim.id == SENTINEL_CLAIM_ID
    assert claim.scope == episode.scope
    assert claim.predicate == "observed_content_hash"
    assert claim.object_value == episode.content_hash
    assert claim.status is ClaimStatus.PROPOSED
    assert claim.epistemic_kind is EpistemicKind.EXTRACTED
    assert claim.evidence[0].extractor_version == "deterministic-v1"
