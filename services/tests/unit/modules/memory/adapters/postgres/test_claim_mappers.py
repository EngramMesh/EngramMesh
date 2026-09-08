"""Unit tests for claim row mappers."""

from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.adapters.postgres.mappers import (
    claim_to_row,
    row_to_claim,
)
from engrammesh.modules.memory.domain.model import (
    Claim,
    ClaimStatus,
    EpistemicKind,
    EvidenceRef,
    MemoryScope,
)
from engrammesh.shared.kernel.ids import MemoryId, SubjectId, TenantId

TENANT = TenantId(UUID(int=1))
SUBJECT = SubjectId(UUID(int=2))
EPISODE_ID = MemoryId(UUID(int=3))
CLAIM_ID = MemoryId(UUID(int=4))
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def _claim() -> Claim:
    return Claim(
        id=CLAIM_ID,
        scope=MemoryScope(TENANT, SUBJECT, workspace_id="ws", agent_id=None),
        subject=str(SUBJECT.value),
        predicate="observed_content_hash",
        object_value="abc123",
        polarity=True,
        epistemic_kind=EpistemicKind.EXTRACTED,
        confidence=1.0,
        valid_from=NOW,
        valid_to=None,
        recorded_from=NOW,
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


def test_claim_to_row_round_trip() -> None:
    claim = _claim()
    row = claim_to_row(claim, episode_id=EPISODE_ID)
    assert row["extractor_version"] == "deterministic-v1"
    assert row["episode_id"] == EPISODE_ID.value
    restored = row_to_claim(row)
    assert restored == claim
