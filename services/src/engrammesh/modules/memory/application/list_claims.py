"""Application orchestration for listing cognitive-memory claims."""

from typing import final

from engrammesh.modules.memory.application.contracts import (
    ListClaimsQuery,
    ListClaimsResult,
)
from engrammesh.modules.memory.application.errors import ClaimReadAuthorizationDenied
from engrammesh.modules.memory.domain.claim_cursor import encode_claim_cursor
from engrammesh.modules.memory.domain.model import Sensitivity
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    MemoryAuthorizationPort,
    MemoryUnitOfWorkFactory,
)


@final
class ListClaimsHandler:
    def __init__(
        self,
        *,
        authorization: MemoryAuthorizationPort,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
    ) -> None:
        self._authorization = authorization
        self._unit_of_work_factory = unit_of_work_factory

    async def handle(self, query: ListClaimsQuery) -> ListClaimsResult:
        authorized = await self._authorization.authorize(
            AuthorizationRequest(
                actor_id=query.actor_id,
                scope=query.scope,
                action="read_claim",
                sensitivity=Sensitivity.INTERNAL,
            )
        )
        if not authorized:
            raise ClaimReadAuthorizationDenied()
        async with self._unit_of_work_factory.create() as unit_of_work:
            rows = await unit_of_work.claims.stream(
                query.scope,
                limit=query.limit + 1,
                cursor=query.cursor,
            )
        if len(rows) > query.limit:
            items = rows[: query.limit]
            next_cursor = encode_claim_cursor(
                recorded_from=items[-1].recorded_from,
                claim_id=items[-1].id,
            )
            return ListClaimsResult(items=items, next_cursor=next_cursor)
        return ListClaimsResult(items=rows, next_cursor=None)
