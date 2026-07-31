"""Application orchestration for reading one cognitive-memory episode."""

from typing import final

from engrammesh.modules.memory.application.contracts import (
    GetEpisodeQuery,
    GetEpisodeResult,
)
from engrammesh.modules.memory.application.errors import (
    EpisodeNotFound,
    EpisodeReadAuthorizationDenied,
)
from engrammesh.modules.memory.domain.model import Sensitivity
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    MemoryAuthorizationPort,
    MemoryUnitOfWorkFactory,
)


@final
class GetEpisodeHandler:
    def __init__(
        self,
        *,
        authorization: MemoryAuthorizationPort,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
    ) -> None:
        self._authorization = authorization
        self._unit_of_work_factory = unit_of_work_factory

    async def handle(self, query: GetEpisodeQuery) -> GetEpisodeResult:
        authorized = await self._authorization.authorize(
            AuthorizationRequest(
                actor_id=query.actor_id,
                scope=query.scope,
                action="read_episode",
                sensitivity=Sensitivity.INTERNAL,
            )
        )
        if not authorized:
            raise EpisodeReadAuthorizationDenied()
        # Read-only: no commit() — UoW rolls back read transaction on exit (see spec §6.4).
        async with self._unit_of_work_factory.create() as unit_of_work:
            episode = await unit_of_work.episodes.get(query.scope, query.episode_id)
        if episode is None:
            raise EpisodeNotFound()
        return GetEpisodeResult(episode=episode)
