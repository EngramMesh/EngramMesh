"""Application orchestration for reading one cognitive-memory claim."""

from typing import final

from engrammesh.modules.memory.application.contracts import (
    GetClaimQuery,
    GetClaimResult,
)
from engrammesh.modules.memory.application.errors import (
    ClaimNotFound,
    ClaimReadAuthorizationDenied,
)
from engrammesh.modules.memory.domain.model import Sensitivity
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    MemoryAuthorizationPort,
    MemoryUnitOfWorkFactory,
)


@final
class GetClaimHandler:
    def __init__(
        self,
        *,
        authorization: MemoryAuthorizationPort,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
    ) -> None:
        self._authorization = authorization
        self._unit_of_work_factory = unit_of_work_factory

    async def handle(self, query: GetClaimQuery) -> GetClaimResult:
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
            claims = await unit_of_work.claims.history(query.scope, query.claim_id)
        if not claims:
            raise ClaimNotFound()
        return GetClaimResult(claim=claims[0])
