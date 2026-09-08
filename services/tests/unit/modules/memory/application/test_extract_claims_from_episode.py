"""Unit tests for ExtractClaimsFromEpisodeHandler."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.extract_claims_from_episode import (
    ExtractClaimsFromEpisodeHandler,
    claim_proposed_payload,
    scope_from_episode_recorded_event,
)
from engrammesh.modules.memory.domain.model import Episode, MemoryScope
from engrammesh.modules.memory.ports import (
    AddProposalResult,
    ClaimProposal,
    MemoryExtractorPort,
    MemoryIdentityPort,
)
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

TENANT_ID = TenantId(UUID(int=1))
SUBJECT_ID = SubjectId(UUID(int=2))
EPISODE_ID = MemoryId(UUID(int=3))
CLAIM_ID = MemoryId(UUID(int=99))
EVENT_ID = EventId(UUID(int=10))
CORRELATION_ID = CorrelationId(UUID(int=11))
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


def _episode() -> Episode:
    from engrammesh.modules.memory.domain.model import (
        RetentionClass,
        Sensitivity,
        SourceType,
    )

    return Episode(
        id=EPISODE_ID,
        scope=MemoryScope(TENANT_ID, SUBJECT_ID, workspace_id="ws"),
        actor_id=SUBJECT_ID,
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


def _event() -> EventEnvelope:
    return EventEnvelope(
        event_id=EVENT_ID,
        event_type="memory.episode-recorded",
        schema_version=1,
        tenant_id=TENANT_ID,
        aggregate_id=EPISODE_ID,
        aggregate_version=1,
        correlation_id=CORRELATION_ID,
        causation_id=None,
        occurred_at=NOW,
        payload={
            "episode_id": str(EPISODE_ID),
            "scope": {
                "subject_id": str(SUBJECT_ID),
                "workspace_id": "ws",
                "agent_id": None,
            },
            "actor_id": str(SUBJECT_ID),
            "source_type": "user",
            "content_ref": str(ArtifactId(UUID(int=4))),
            "observed_at": NOW.isoformat(),
            "ingested_at": NOW.isoformat(),
            "content_hash": "abc123",
            "idempotency_key": "key-1",
            "sensitivity": "internal",
            "retention_class": "standard",
            "consent_basis": "test",
        },
    )


@dataclass
class FakeClaimStore:
    proposals: list[ClaimProposal] = field(default_factory=list)
    created_on_next: bool = True

    async def add_proposal(self, proposal: ClaimProposal) -> AddProposalResult:
        self.proposals.append(proposal)
        return AddProposalResult(
            claim_id=proposal.claim.id,
            created=self.created_on_next,
        )

    async def current(self, query: object) -> tuple[object, ...]:
        del query
        return ()

    async def history(self, scope: object, claim_id: object) -> tuple[object, ...]:
        del scope, claim_id
        return ()


@dataclass
class FakeUnitOfWork:
    episode: Episode | None
    claims: FakeClaimStore = field(default_factory=FakeClaimStore)
    outbox_events: list[EventEnvelope] = field(default_factory=list)
    committed: bool = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    @property
    def episodes(self) -> FakeUnitOfWork:
        return self

    async def get(self, scope: MemoryScope, episode_id: MemoryId) -> Episode | None:
        if self.episode is None:
            return None
        if self.episode.id == episode_id and self.episode.scope == scope:
            return self.episode
        return None

    @property
    def outbox(self) -> FakeUnitOfWork:
        return self

    async def publish(self, event: EventEnvelope) -> None:
        self.outbox_events.append(event)

    async def commit(self) -> None:
        self.committed = True


class FakeUnitOfWorkFactory:
    def __init__(self, episode: Episode | None) -> None:
        self._episode = episode
        self.last_unit_of_work: FakeUnitOfWork | None = None

    def create(self) -> FakeUnitOfWork:
        unit_of_work = FakeUnitOfWork(self._episode)
        self.last_unit_of_work = unit_of_work
        return unit_of_work


class FakeExtractor(MemoryExtractorPort):
    def __init__(self, proposals: tuple[ClaimProposal, ...]) -> None:
        self._proposals = proposals

    async def propose(self, episode: Episode) -> tuple[ClaimProposal, ...]:
        del episode
        return self._proposals


class FixedIdentityPort(MemoryIdentityPort):
    async def new_memory_id(self) -> MemoryId:
        return CLAIM_ID

    async def new_event_id(self) -> EventId:
        return EVENT_ID


@pytest.mark.asyncio
async def test_handle_persists_proposals_with_assigned_ids() -> None:
    from engrammesh.modules.memory.adapters.deterministic.extractor import (
        DeterministicMemoryExtractor,
    )

    episode = _episode()
    extractor = DeterministicMemoryExtractor(extractor_version="deterministic-v1")
    proposals = await extractor.propose(episode)
    factory = FakeUnitOfWorkFactory(episode)
    handler = ExtractClaimsFromEpisodeHandler(
        unit_of_work_factory=factory,
        extractor=FakeExtractor(proposals),
        identities=FixedIdentityPort(),
        enabled=True,
    )
    await handler.handle(_event())
    assert factory.last_unit_of_work is not None
    assert factory.last_unit_of_work.committed is True
    assert len(factory.last_unit_of_work.claims.proposals) == 1
    assert factory.last_unit_of_work.claims.proposals[0].claim.id == CLAIM_ID
    assert len(factory.last_unit_of_work.outbox_events) == 1
    published = factory.last_unit_of_work.outbox_events[0]
    assert published.event_type == "memory.claim-proposed"
    assert published.aggregate_id == CLAIM_ID
    assert published.causation_id == EVENT_ID
    assert published.correlation_id == CORRELATION_ID


@pytest.mark.asyncio
async def test_handle_skips_outbox_when_proposal_not_created() -> None:
    from engrammesh.modules.memory.adapters.deterministic.extractor import (
        DeterministicMemoryExtractor,
    )

    episode = _episode()
    extractor = DeterministicMemoryExtractor(extractor_version="deterministic-v1")
    proposals = await extractor.propose(episode)
    factory = FakeUnitOfWorkFactory(episode)
    assert factory.last_unit_of_work is None
    unit_of_work = factory.create()
    unit_of_work.claims.created_on_next = False
    handler = ExtractClaimsFromEpisodeHandler(
        unit_of_work_factory=factory,
        extractor=FakeExtractor(proposals),
        identities=FixedIdentityPort(),
        enabled=True,
    )
    await handler.handle(_event())
    assert len(unit_of_work.outbox_events) == 0


def test_claim_proposed_payload_matches_schema() -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    from engrammesh.modules.memory.adapters.deterministic.extractor import (
        DeterministicMemoryExtractor,
    )

    episode = _episode()
    extractor = DeterministicMemoryExtractor(extractor_version="deterministic-v1")
    import asyncio

    proposals = asyncio.run(extractor.propose(episode))
    claim = replace(proposals[0].claim, id=CLAIM_ID)
    payload = claim_proposed_payload(claim, episode_id=EPISODE_ID)
    schema_path = (
        Path(__file__).parents[6]
        / "packages"
        / "contracts"
        / "jsonschema"
        / "memory"
        / "v1"
        / "claim-proposed.schema.json"
    )
    with schema_path.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    event = {
        "event_id": str(EVENT_ID),
        "event_type": "memory.claim-proposed",
        "schema_version": 1,
        "tenant_id": str(TENANT_ID),
        "aggregate_id": str(CLAIM_ID),
        "aggregate_version": 1,
        "correlation_id": str(CORRELATION_ID),
        "causation_id": str(EVENT_ID),
        "occurred_at": NOW.isoformat(),
        "payload": payload,
    }
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(event)


@pytest.mark.asyncio
async def test_handle_raises_when_episode_missing() -> None:
    handler = ExtractClaimsFromEpisodeHandler(
        unit_of_work_factory=FakeUnitOfWorkFactory(None),
        extractor=FakeExtractor(()),
        identities=FixedIdentityPort(),
        enabled=True,
    )
    with pytest.raises(ValueError, match="not found"):
        await handler.handle(_event())


@pytest.mark.asyncio
async def test_handle_noop_when_disabled() -> None:
    factory = FakeUnitOfWorkFactory(_episode())
    handler = ExtractClaimsFromEpisodeHandler(
        unit_of_work_factory=factory,
        extractor=FakeExtractor(()),
        identities=FixedIdentityPort(),
        enabled=False,
    )
    await handler.handle(_event())
    assert factory.last_unit_of_work is None


def test_scope_from_episode_recorded_event() -> None:
    scope, episode_id = scope_from_episode_recorded_event(_event())
    assert episode_id == EPISODE_ID
    assert scope.tenant_id == TENANT_ID
    assert scope.subject_id == SUBJECT_ID
    assert scope.workspace_id == "ws"
