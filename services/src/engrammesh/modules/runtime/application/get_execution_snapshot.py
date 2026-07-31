"""Application orchestration for reading one durable execution snapshot."""

from typing import final

from engrammesh.modules.runtime.application.contracts import (
    GetExecutionSnapshotQuery,
    GetExecutionSnapshotResult,
)
from engrammesh.modules.runtime.application.errors import (
    ExecutionAuthorizationDenied,
)
from engrammesh.modules.runtime.ports import (
    OrchestratorPort,
    RuntimeAuthorizationPort,
    RuntimeAuthorizationRequest,
)


@final
class GetExecutionSnapshotHandler:
    def __init__(
        self,
        *,
        authorization: RuntimeAuthorizationPort,
        orchestrator: OrchestratorPort,
    ) -> None:
        self._authorization = authorization
        self._orchestrator = orchestrator

    async def handle(
        self,
        query: GetExecutionSnapshotQuery,
    ) -> GetExecutionSnapshotResult:
        authorized = await self._authorization.authorize(
            RuntimeAuthorizationRequest(
                actor_id=query.actor_id,
                scope=query.scope,
                action="get_execution",
            )
        )
        if not authorized:
            raise ExecutionAuthorizationDenied()

        snapshot = await self._orchestrator.get_snapshot(
            query.scope,
            query.execution_id,
        )
        return GetExecutionSnapshotResult(snapshot=snapshot)
