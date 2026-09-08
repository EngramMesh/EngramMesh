from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Never, Self
from uuid import UUID

import pytest

from engrammesh.modules.memory.application.contracts import ListClaimsQuery
from engrammesh.modules.memory.application.errors import ClaimReadAuthorizationDenied
from engrammesh.modules.memory.application.list_claims import ListClaimsHandler
from engrammesh.modules.memory.domain.claim_cursor import encode_claim_cursor
from engrammesh.modules.memory.domain.errors import InvalidClaimCursor
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
CLAIM_IDS = (
    MemoryId(UUID("840ddfba-f834-486b-b918-bbb87a6bf9db")),
    MemoryId(UUID("940ddfba-f834-486b-b918-bbb87a6bf9db")),
    MemoryId(UUID("a40ddfba-f834-486b-b918-bbb87a6bf9db")),
)
EPISODE_ID = MemoryId(UUID("b40ddfba-f834-486b-b918-bbb87a6bf9db"))
BASE_RECORDED_AT = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


@dataclass
class RecordingAuthorization:
    calls: list[str] = field(default_factory=list)
    allowed: bool = True

    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append(request.action)
        return self.allowed


@dataclass
class FakeClaimStore:
    stream_rows: tuple[Claim, ...] = ()
    last_limit: int | None = None
    last_cursor: str | None = None

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
        return ()

    async def stream(
        self,
        scope: MemoryScope,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> tuple[Claim, ...]:
        del scope
        self.last_limit = limit
        self.last_cursor = cursor
        if cursor == "bad":
            raise InvalidClaimCursor()
        if limit is None:
            return self.stream_rows
        return self.stream_rows[:limit]


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


def make_claim(index: int) -> Claim:
    recorded_from = BASE_RECORDED_AT + timedelta(minutes=index)
    return Claim(
        id=CLAIM_IDS[index],
        scope=make_scope(),
        subject=str(SUBJECT),
        predicate="observed_content_hash",
        object_value=f"sha256:{index}",
        polarity=True,
        epistemic_kind=EpistemicKind.EXTRACTED,
        confidence=1.0,
        valid_from=recorded_from,
        valid_to=None,
        recorded_from=recorded_from,
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
async def test_list_returns_items_and_next_cursor() -> None:
    claims = tuple(make_claim(i) for i in range(3))
    claim_store = FakeClaimStore(stream_rows=claims)
    handler = ListClaimsHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=FakeUnitOfWorkFactory(claims=claim_store),
    )
    first_page = await handler.handle(
        ListClaimsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=2,
        )
    )
    assert first_page.items == claims[:2]
    assert first_page.next_cursor == encode_claim_cursor(
        recorded_from=claims[1].recorded_from,
        claim_id=claims[1].id,
    )
    assert claim_store.last_limit == 3


@pytest.mark.asyncio
async def test_list_empty_scope_returns_empty() -> None:
    handler = ListClaimsHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=FakeUnitOfWorkFactory(claims=FakeClaimStore()),
    )
    result = await handler.handle(
        ListClaimsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=10,
        )
    )
    assert result.items == ()
    assert result.next_cursor is None


def test_list_rejects_limit_over_100() -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        ListClaimsQuery(
            actor_id=ACTOR,
            scope=make_scope(),
            limit=101,
        )


@pytest.mark.asyncio
async def test_list_denial_authorizes_read_claim_only() -> None:
    authorization = RecordingAuthorization(allowed=False)
    handler = ListClaimsHandler(
        authorization=authorization,
        unit_of_work_factory=MustNotBeUsed(),
    )
    with pytest.raises(ClaimReadAuthorizationDenied):
        await handler.handle(
            ListClaimsQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
            )
        )
    assert authorization.calls == ["read_claim"]


@pytest.mark.asyncio
async def test_list_invalid_cursor_propagates() -> None:
    handler = ListClaimsHandler(
        authorization=RecordingAuthorization(),
        unit_of_work_factory=FakeUnitOfWorkFactory(
            claims=FakeClaimStore(stream_rows=(make_claim(0),)),
        ),
    )
    with pytest.raises(InvalidClaimCursor):
        await handler.handle(
            ListClaimsQuery(
                actor_id=ACTOR,
                scope=make_scope(),
                limit=10,
                cursor="bad",
            )
        )
