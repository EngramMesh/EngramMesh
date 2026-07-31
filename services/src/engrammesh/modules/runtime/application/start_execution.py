"""Application orchestration for starting durable multi-agent executions."""

from typing import final

from engrammesh.modules.runtime.application.contracts import (
    StartExecutionCommand,
    StartExecutionResult,
)
from engrammesh.modules.runtime.application.errors import (
    ExecutionAuthorizationDenied,
)
from engrammesh.modules.runtime.domain.model import ExecutionSpec
from engrammesh.modules.runtime.ports import (
    OrchestratorPort,
    RuntimeAuthorizationPort,
    RuntimeAuthorizationRequest,
    RuntimeIdentityPort,
)


@final
class StartExecutionHandler:
    """Authorize and start one durable execution via the orchestrator port."""

    def __init__(
        self,
        *,
        authorization: RuntimeAuthorizationPort,
        identities: RuntimeIdentityPort,
        orchestrator: OrchestratorPort,
    ) -> None:
        self._authorization = authorization
        self._identities = identities
        self._orchestrator = orchestrator

    async def handle(
        self,
        command: StartExecutionCommand,
    ) -> StartExecutionResult:
        authorized = await self._authorization.authorize(
            RuntimeAuthorizationRequest(
                actor_id=command.actor_id,
                scope=command.scope,
                action="start_execution",
            )
        )
        if not authorized:
            raise ExecutionAuthorizationDenied()

        execution_id = await self._identities.new_execution_id()
        spec = ExecutionSpec(
            id=execution_id,
            scope=command.scope,
            objective_ref=command.objective_ref,
            root_agent_id=command.root_agent_id,
            memory_query=command.memory_query,
            budget=command.budget,
            idempotency_key=command.idempotency_key,
        )
        snapshot = await self._orchestrator.start(spec)
        created = snapshot.execution_id == execution_id
        return StartExecutionResult(snapshot=snapshot, created=created)
