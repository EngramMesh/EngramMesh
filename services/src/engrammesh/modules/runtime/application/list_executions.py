"""Application orchestration for listing durable execution snapshots."""

from typing import final

from engrammesh.modules.runtime.application.contracts import (
    ExecutionListItem,
    ListExecutionsQuery,
    ListExecutionsResult,
)
from engrammesh.modules.runtime.application.errors import (
    ExecutionAuthorizationDenied,
)
from engrammesh.modules.runtime.domain.execution_cursor import encode_execution_cursor
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.modules.runtime.ports import (
    ExecutionSnapshotStore,
    RuntimeAuthorizationPort,
    RuntimeAuthorizationRequest,
)


@final
class ListExecutionsHandler:
    def __init__(
        self,
        *,
        authorization: RuntimeAuthorizationPort,
        snapshot_store: ExecutionSnapshotStore,
    ) -> None:
        self._authorization = authorization
        self._snapshot_store = snapshot_store

    async def handle(self, query: ListExecutionsQuery) -> ListExecutionsResult:
        authorized = await self._authorization.authorize(
            RuntimeAuthorizationRequest(
                actor_id=query.actor_id,
                scope=query.scope,
                action="get_execution",
            )
        )
        if not authorized:
            raise ExecutionAuthorizationDenied()
        rows = await self._snapshot_store.stream(
            query.scope,
            limit=query.limit + 1,
            cursor=query.cursor,
        )
        if len(rows) > query.limit:
            page = rows[: query.limit]
            next_cursor = encode_execution_cursor(
                updated_at=page[-1].updated_at,
                execution_id=page[-1].execution_id,
            )
            return ListExecutionsResult(
                items=tuple(self._to_item(snapshot) for snapshot in page),
                next_cursor=next_cursor,
            )
        return ListExecutionsResult(
            items=tuple(self._to_item(snapshot) for snapshot in rows),
            next_cursor=None,
        )

    @staticmethod
    def _to_item(snapshot: ExecutionSnapshot) -> ExecutionListItem:
        return ExecutionListItem(
            execution_id=snapshot.execution_id,
            scope=snapshot.scope,
            revision=snapshot.revision,
            status=snapshot.status,
            updated_at=snapshot.updated_at,
        )
