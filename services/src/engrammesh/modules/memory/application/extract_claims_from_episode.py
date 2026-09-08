"""Application orchestration for claim extraction from episode-recorded events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import final
from uuid import UUID

from engrammesh.modules.memory.domain.model import MemoryScope
from engrammesh.modules.memory.ports import (
    ClaimProposal,
    MemoryExtractorPort,
    MemoryIdentityPort,
    MemoryUnitOfWorkFactory,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import AgentInstanceId, MemoryId, SubjectId


def scope_from_episode_recorded_event(
    event: EventEnvelope,
) -> tuple[MemoryScope, MemoryId]:
    """Reconstruct scope and episode id from a memory.episode-recorded envelope."""
    payload = event.payload
    scope_raw = payload["scope"]
    if not isinstance(scope_raw, Mapping):
        msg = "payload.scope must be an object"
        raise TypeError(msg)
    if "tenant_id" in scope_raw:
        msg = "payload.scope must not contain tenant_id"
        raise ValueError(msg)
    scope = MemoryScope(
        tenant_id=event.tenant_id,
        subject_id=SubjectId(UUID(str(scope_raw["subject_id"]))),
        workspace_id=scope_raw.get("workspace_id"),
        agent_id=(
            AgentInstanceId(UUID(str(scope_raw["agent_id"])))
            if scope_raw.get("agent_id") is not None
            else None
        ),
    )
    episode_id = MemoryId(UUID(str(payload["episode_id"])))
    return scope, episode_id


@final
class ExtractClaimsFromEpisodeHandler:
    """Load episode, extract claims, and persist proposals."""

    def __init__(
        self,
        *,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
        extractor: MemoryExtractorPort,
        identities: MemoryIdentityPort,
        enabled: bool,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._extractor = extractor
        self._identities = identities
        self._enabled = enabled

    async def handle(self, event: EventEnvelope) -> None:
        if not self._enabled:
            return
        scope, episode_id = scope_from_episode_recorded_event(event)
        async with self._unit_of_work_factory.create() as unit_of_work:
            episode = await unit_of_work.episodes.get(scope, episode_id)
            if episode is None:
                msg = f"episode {episode_id} not found for claim extraction"
                raise ValueError(msg)
            proposals = await self._extractor.propose(episode)
            for proposal in proposals:
                claim_id = await self._identities.new_memory_id()
                claim = replace(proposal.claim, id=claim_id)
                await unit_of_work.claims.add_proposal(ClaimProposal(claim=claim))
            await unit_of_work.commit()
