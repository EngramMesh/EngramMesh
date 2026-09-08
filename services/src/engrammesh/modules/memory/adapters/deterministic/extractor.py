"""Deterministic rule-based claim extraction adapter."""

from __future__ import annotations

from typing import final
from uuid import UUID

from engrammesh.modules.memory.domain.model import (
    Claim,
    ClaimStatus,
    Episode,
    EpistemicKind,
    EvidenceRef,
)
from engrammesh.modules.memory.ports import ClaimProposal
from engrammesh.shared.kernel.ids import MemoryId

SENTINEL_CLAIM_ID = MemoryId(UUID(int=0))


@final
class DeterministicMemoryExtractor:
    """Produce reproducible claim proposals from episode metadata."""

    def __init__(self, *, extractor_version: str) -> None:
        self._extractor_version = extractor_version

    async def propose(self, episode: Episode) -> tuple[ClaimProposal, ...]:
        claim = Claim(
            id=SENTINEL_CLAIM_ID,
            scope=episode.scope,
            subject=str(episode.scope.subject_id),
            predicate="observed_content_hash",
            object_value=episode.content_hash,
            polarity=True,
            epistemic_kind=EpistemicKind.EXTRACTED,
            confidence=1.0,
            valid_from=episode.observed_at,
            valid_to=None,
            recorded_from=episode.ingested_at,
            recorded_to=None,
            status=ClaimStatus.PROPOSED,
            evidence=(
                EvidenceRef(
                    episode_id=episode.id,
                    source_span="metadata",
                    extractor_version=self._extractor_version,
                ),
            ),
        )
        return (ClaimProposal(claim=claim),)
