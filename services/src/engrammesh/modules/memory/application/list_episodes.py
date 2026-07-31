"""Application orchestration for listing cognitive-memory episodes."""

from typing import final

from engrammesh.modules.memory.application.contracts import (
    ListEpisodesQuery,
    ListEpisodesResult,
)
from engrammesh.modules.memory.application.errors import (
    EpisodeReadAuthorizationDenied,
)
from engrammesh.modules.memory.domain.episode_cursor import encode_episode_cursor
from engrammesh.modules.memory.domain.model import Sensitivity
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    MemoryAuthorizationPort,
    MemoryUnitOfWorkFactory,
)


@final
class ListEpisodesHandler:
    def __init__(
        self,
        *,
        authorization: MemoryAuthorizationPort,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
    ) -> None:
        self._authorization = authorization
        self._unit_of_work_factory = unit_of_work_factory

    async def handle(self, query: ListEpisodesQuery) -> ListEpisodesResult:
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
        # InvalidEpisodeCursor from decode_episode_cursor propagates to HTTP layer (spec §6.5).
        async with self._unit_of_work_factory.create() as unit_of_work:
            rows = await unit_of_work.episodes.stream(
                query.scope,
                limit=query.limit + 1,
                cursor=query.cursor,
            )
        if len(rows) > query.limit:
            items = rows[: query.limit]
            next_cursor = encode_episode_cursor(
                ingested_at=items[-1].ingested_at,
                episode_id=items[-1].id,
            )
            return ListEpisodesResult(items=items, next_cursor=next_cursor)
        return ListEpisodesResult(items=rows, next_cursor=None)
