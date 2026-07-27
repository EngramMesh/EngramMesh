"""Async, framework-neutral ports for durable multi-Agent execution."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from engrammesh.modules.memory.public import EvidencePacket, MemoryScope
from engrammesh.modules.runtime.domain.model import (
    AgentInvocation,
    AgentOutcome,
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
    Plan,
    PlanDelta,
    ToolCall,
    ToolDescriptor,
    ToolResult,
)
from engrammesh.shared.kernel.ids import ArtifactId, ExecutionId


@runtime_checkable
class OrchestratorPort(Protocol):
    """Durable orchestration boundary intended for a Temporal adapter."""

    async def start(self, spec: ExecutionSpec) -> ExecutionSnapshot: ...

    async def get_snapshot(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
    ) -> ExecutionSnapshot: ...

    async def cancel(
        self,
        scope: MemoryScope,
        execution_id: ExecutionId,
        idempotency_key: str,
    ) -> ExecutionSnapshot: ...


@runtime_checkable
class PlannerPort(Protocol):
    """Pure planning-engine boundary; durable authority remains orchestration."""

    async def plan(
        self,
        spec: ExecutionSpec,
        evidence: EvidencePacket,
    ) -> Plan: ...

    async def revise(
        self,
        plan: Plan,
        delta: PlanDelta,
        evidence: EvidencePacket,
    ) -> Plan: ...


@runtime_checkable
class AgentEnginePort(Protocol):
    """One isolated Agent invocation, suitable for an Agent-engine adapter."""

    async def invoke(self, invocation: AgentInvocation) -> AgentOutcome: ...


@runtime_checkable
class ModelProviderPort(Protocol):
    """Provider-neutral model generation boundary."""

    async def generate(
        self,
        input_ref: ArtifactId,
        expected_output_schema: Mapping[str, object],
        budget: Budget,
    ) -> ArtifactId: ...


@runtime_checkable
class ToolRegistryPort(Protocol):
    """Typed registry boundary, with MCP confined to an adapter."""

    async def resolve(
        self,
        name: str,
        version: str,
    ) -> ToolDescriptor | None: ...

    async def list_allowed(
        self,
        grants: tuple[str, ...],
    ) -> tuple[ToolDescriptor, ...]: ...


@runtime_checkable
class ToolExecutorPort(Protocol):
    """Logical tool-effect boundary, with MCP confined to an adapter."""

    async def execute(self, call: ToolCall) -> ToolResult: ...


@runtime_checkable
class PolicyPort(Protocol):
    """Authorization boundary for Agent and tool actions."""

    async def authorize_agent(self, invocation: AgentInvocation) -> bool: ...

    async def authorize_tool(self, call: ToolCall) -> bool: ...


@runtime_checkable
class ArtifactStorePort(Protocol):
    """Referenced content boundary; storage details belong to adapters."""

    async def put(
        self,
        scope: MemoryScope,
        content: bytes,
        media_type: str,
    ) -> ArtifactId: ...

    async def get(
        self,
        scope: MemoryScope,
        artifact_id: ArtifactId,
    ) -> bytes: ...


@runtime_checkable
class RemoteAgentPort(Protocol):
    """Remote Agent boundary, with A2A confined to an adapter."""

    async def invoke(self, invocation: AgentInvocation) -> AgentOutcome: ...
