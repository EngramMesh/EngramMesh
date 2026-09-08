"""Application orchestration for claim extraction from episode-recorded events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, final
from uuid import UUID

from engrammesh.modules.memory.domain.model import Claim, MemoryScope
from engrammesh.modules.memory.ports import (
    ClaimProposal,
    MemoryExtractorPort,
    MemoryIdentityPort,
    MemoryUnitOfWorkFactory,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import AgentInstanceId, MemoryId, SubjectId

_CLAIM_PROPOSED = "memory.claim-proposed"


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


def claim_proposed_payload(claim: Claim, *, episode_id: MemoryId) -> dict[str, Any]:
    """Build memory.claim-proposed event payload from a persisted claim."""
    evidence = claim.evidence[0]
    if evidence.episode_id != episode_id:
        msg = "episode_id must match claim evidence episode_id"
        raise ValueError(msg)
    payload: dict[str, Any] = {
        "claim_id": str(claim.id),
        "episode_id": str(episode_id),
        "scope": {
            "subject_id": str(claim.scope.subject_id),
            "workspace_id": claim.scope.workspace_id,
            "agent_id": (
                str(claim.scope.agent_id)
                if claim.scope.agent_id is not None
                else None
            ),
        },
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object_value": claim.object_value,
        "polarity": claim.polarity,
        "epistemic_kind": claim.epistemic_kind.value,
        "confidence": claim.confidence,
        "valid_from": claim.valid_from.isoformat(),
        "valid_to": claim.valid_to.isoformat() if claim.valid_to is not None else None,
        "recorded_from": claim.recorded_from.isoformat(),
        "status": claim.status.value,
        "extractor_version": evidence.extractor_version,
        "evidence": [
            {
                "episode_id": str(evidence.episode_id),
                "source_span": evidence.source_span,
                "extractor_version": evidence.extractor_version,
            }
        ],
    }
    return payload


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
                result = await unit_of_work.claims.add_proposal(
                    ClaimProposal(claim=claim)
                )
                if result.created:
                    outbox_event_id = await self._identities.new_event_id()
                    await unit_of_work.outbox.publish(
                        EventEnvelope(
                            event_id=outbox_event_id,
                            event_type=_CLAIM_PROPOSED,
                            schema_version=1,
                            tenant_id=claim.scope.tenant_id,
                            aggregate_id=result.claim_id,
                            aggregate_version=1,
                            correlation_id=event.correlation_id,
                            causation_id=event.event_id,
                            occurred_at=claim.recorded_from,
                            payload=claim_proposed_payload(
                                claim,
                                episode_id=episode_id,
                            ),
                        )
                    )
            await unit_of_work.commit()
