from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Never, Self
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.contracts import GetClaimQuery
from engrammesh.modules.memory.application.errors import (
    ClaimNotFound,
    ClaimReadAuthorizationDenied,
)
from engrammesh.modules.memory.application.get_claim import GetClaimHandler
from engrammesh.modules.memory.domain.model import (
    Claim,
    ClaimStatus,
    EpistemicKind,
    EvidenceRef,
    MemoryScope,
)
from engrammesh.modules.memory.ports import (
    AddProposalResult,
    AuthorizationRequest,
    ClaimProposal,
    MemoryQuery,
)
from engrammesh.shared.kernel.ids import MemoryId, SubjectId, TenantId

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))
CLAIM_ID = MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db"))
EPISODE_ID = MemoryId(UUID("940ddfba-f834-486b-b918-bbb87a6bf9db"))
RECORDED_AT = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


@dataclass
class RecordingAuthorization:
    calls: list[AuthorizationRequest] = field(default_factory=list)
    allowed: bool = True

    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append(request)
        return self.allowed


@dataclass
class FakeClaimStore:
    history_result: tuple[Claim, ...] = ()

    async def add_proposal(self, proposal: ClaimProposal) -> AddProposalResult:
        del proposal
        raise AssertionError("add_proposal must not be called")

    async def current(self, query: MemoryQuery) -> tuple[Claim, ...]:
        del query
        return ()

    async def history(
        self,
        scope: MemoryScope,
        claim_id: MemoryId,
    ) -> tuple[Claim, ...]:
        del scope, claim_id
        return self.history_result

    async def stream(
        self,
        scope: MemoryScope,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> tuple[Claim, ...]:
        del scope, limit, cursor
        return ()


@dataclass
class FakeUnitOfWork:
    claims: FakeClaimStore

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        return None


@dataclass
class FakeUnitOfWorkFactory:
    claims: FakeClaimStore

    def create(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(claims=self.claims)


def make_scope() -> MemoryScope:
    return MemoryScope(
        tenant_id=TENANT,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
    )


def make_claim() -> Claim:
    return Claim(
        id=CLAIM_ID,
        scope=make_scope(),
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


@pytest.mark.asyncio
async def test_get_claim_returns_claim_when_found() -> None:
    claim = make_claim()
    factory = FakeUnitOfWorkFactory(
        claims=FakeClaimStore(history_result=(claim,)),
    )
    handler = GetClaimHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    result = await handler.handle(
        GetClaimQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            claim_id=CLAIM_ID,
        )
    )
    assert result.claim == claim


@pytest.mark.asyncio
async def test_get_claim_raises_not_found() -> None:
    factory = FakeUnitOfWorkFactory(claims=FakeClaimStore())
    handler = GetClaimHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=factory,
    )
    with pytest.raises(ClaimNotFound):
        await handler.handle(
            GetClaimQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                claim_id=CLAIM_ID,
            )
        )


@pytest.mark.asyncio
async def test_get_claim_denial_authorizes_read_claim_only() -> None:
    authorization = RecordingAuthorization(allowed=False)
    handler = GetClaimHandler(
        authorization=authorization,
        unit_of_work_factory=MustNotBeUsed(),
    )
    with pytest.raises(ClaimReadAuthorizationDenied):
        await handler.handle(
            GetClaimQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                claim_id=CLAIM_ID,
            )
        )
    assert len(authorization.calls) == 1
    assert authorization.calls[0].action == "read_claim"
