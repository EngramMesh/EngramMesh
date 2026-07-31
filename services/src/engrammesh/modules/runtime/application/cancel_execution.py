"""Application orchestration for cancelling durable executions."""

from typing import final

from engrammesh.modules.runtime.application.contracts import (
    CancelExecutionCommand,
    CancelExecutionResult,
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
class CancelExecutionHandler:
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
        command: CancelExecutionCommand,
    ) -> CancelExecutionResult:
        authorized = await self._authorization.authorize(
            RuntimeAuthorizationRequest(
                actor_id=command.actor_id,
                scope=command.scope,
                action="cancel_execution",
            )
        )
        if not authorized:
            raise ExecutionAuthorizationDenied()

        snapshot = await self._orchestrator.cancel(
            command.scope,
            command.execution_id,
            command.idempotency_key,
        )
        return CancelExecutionResult(snapshot=snapshot)
