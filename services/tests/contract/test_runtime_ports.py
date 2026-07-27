import inspect
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, get_protocol_members, get_type_hints

from engrammesh.modules.memory.public import (
    EvidencePacket,
    MemoryQuery,
    MemoryScope,
)
from engrammesh.modules.runtime import ports
from engrammesh.modules.runtime.domain.model import (
    AgentDefinition,
    AgentInvocation,
    AgentOutcome,
    Budget,
    Decision,
    ExecutionSnapshot,
    ExecutionSpec,
    ExecutionStatus,
    Failure,
    FailureCategory,
    JoinKind,
    NodeKind,
    NodeStatus,
    Plan,
    PlanDelta,
    PlanEdge,
    PlanNode,
    PlanOperation,
    SideEffectClass,
    Suspension,
    SuspensionKind,
    ToolCall,
    ToolDescriptor,
    ToolResult,
)
from engrammesh.modules.runtime.ports import (
    AgentEnginePort,
    ArtifactStorePort,
    ModelProviderPort,
    OrchestratorPort,
    PlannerPort,
    PolicyPort,
    RemoteAgentPort,
    ToolExecutorPort,
    ToolRegistryPort,
)
from engrammesh.modules.runtime.public import __all__ as public_exports
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    AttemptId,
    EffectId,
    ExecutionId,
    NodeId,
    SubjectId,
)

PROTOCOLS = (
    OrchestratorPort,
    PlannerPort,
    AgentEnginePort,
    ModelProviderPort,
    ToolRegistryPort,
    ToolExecutorPort,
    PolicyPort,
    ArtifactStorePort,
    RemoteAgentPort,
)

EXPECTED_METHODS = {
    OrchestratorPort: ("start", "get_snapshot", "cancel"),
    PlannerPort: ("plan", "revise"),
    AgentEnginePort: ("invoke",),
    ModelProviderPort: ("generate",),
    ToolRegistryPort: ("resolve", "list_allowed"),
    ToolExecutorPort: ("execute",),
    PolicyPort: ("authorize_agent", "authorize_tool"),
    ArtifactStorePort: ("put", "get"),
    RemoteAgentPort: ("invoke",),
}

DATACLASS_SHAPES = {
    Budget: (
        ("max_input_tokens", int, MISSING),
        ("max_output_tokens", int, MISSING),
        ("max_cost_micros", int, MISSING),
        ("deadline", datetime, MISSING),
    ),
    ExecutionSpec: (
        ("id", ExecutionId, MISSING),
        ("scope", MemoryScope, MISSING),
        ("objective_ref", ArtifactId, MISSING),
        ("root_agent_id", AgentDefinitionId, MISSING),
        ("memory_query", MemoryQuery | None, MISSING),
        ("budget", Budget, MISSING),
        ("idempotency_key", str, MISSING),
    ),
    ExecutionSnapshot: (
        ("execution_id", ExecutionId, MISSING),
        ("revision", int, MISSING),
        ("status", ExecutionStatus, MISSING),
        ("plan_revision", int | None, MISSING),
        ("node_statuses", Mapping[NodeId, NodeStatus], MISSING),
        ("suspension", Suspension | None, MISSING),
        ("result_ref", ArtifactId | None, MISSING),
        ("failure", Failure | None, MISSING),
        ("updated_at", datetime, MISSING),
    ),
    AgentDefinition: (
        ("id", AgentDefinitionId, MISSING),
        ("version", int, MISSING),
        ("role", str, MISSING),
        ("instruction_ref", ArtifactId, MISSING),
        ("capabilities", tuple[str, ...], MISSING),
    ),
    AgentInvocation: (
        ("attempt_id", AttemptId, MISSING),
        ("execution_id", ExecutionId, MISSING),
        ("node_id", NodeId, MISSING),
        ("agent_definition_id", AgentDefinitionId, MISSING),
        ("input_refs", tuple[ArtifactId, ...], MISSING),
        ("evidence_ref", ArtifactId | None, MISSING),
        ("tool_grants", tuple[str, ...], MISSING),
        ("expected_output_schema", Mapping[str, object], MISSING),
        ("scope", MemoryScope, MISSING),
        ("budget", Budget, MISSING),
    ),
    PlanNode: (
        ("id", NodeId, MISSING),
        ("kind", NodeKind, MISSING),
        ("objective_ref", ArtifactId, MISSING),
        ("agent_definition_id", AgentDefinitionId | None, MISSING),
        ("join_kind", JoinKind | None, MISSING),
        ("input_refs", tuple[ArtifactId, ...], MISSING),
        ("expected_output_schema", Mapping[str, object], MISSING),
        ("tool_grants", tuple[str, ...], MISSING),
        ("budget", Budget, MISSING),
        ("side_effect_class", SideEffectClass, MISSING),
        ("acceptance_criteria", tuple[str, ...], MISSING),
    ),
    PlanEdge: (
        ("source", NodeId, MISSING),
        ("target", NodeId, MISSING),
    ),
    Plan: (
        ("execution_id", ExecutionId, MISSING),
        ("revision", int, MISSING),
        ("nodes", tuple[PlanNode, ...], MISSING),
        ("edges", tuple[PlanEdge, ...], MISSING),
    ),
    PlanOperation: (
        (
            "kind",
            Literal["add_node", "remove_node", "add_edge", "remove_edge"],
            MISSING,
        ),
        ("node", PlanNode | None, None),
        ("node_id", NodeId | None, None),
        ("edge", PlanEdge | None, None),
    ),
    PlanDelta: (
        ("expected_revision", int, MISSING),
        ("operations", tuple[PlanOperation, ...], MISSING),
    ),
    Suspension: (
        ("request_id", str, MISSING),
        ("idempotency_key", str, MISSING),
        ("execution_id", ExecutionId, MISSING),
        ("node_id", NodeId | None, MISSING),
        ("kind", SuspensionKind, MISSING),
        ("request_ref", ArtifactId, MISSING),
        ("requested_at", datetime, MISSING),
        ("expires_at", datetime, MISSING),
    ),
    Decision: (
        ("request_id", str, MISSING),
        ("idempotency_key", str, MISSING),
        ("approved", bool, MISSING),
        ("decided_by", SubjectId, MISSING),
        ("decision_ref", ArtifactId | None, MISSING),
        ("decided_at", datetime, MISSING),
    ),
    ToolDescriptor: (
        ("name", str, MISSING),
        ("version", str, MISSING),
        ("input_schema", Mapping[str, object], MISSING),
        ("output_schema", Mapping[str, object], MISSING),
        ("required_grants", tuple[str, ...], MISSING),
        ("side_effect_class", SideEffectClass, MISSING),
    ),
    ToolCall: (
        ("effect_id", EffectId, MISSING),
        ("attempt_id", AttemptId, MISSING),
        ("tool_name", str, MISSING),
        ("tool_version", str, MISSING),
        ("input_ref", ArtifactId, MISSING),
        ("grants", tuple[str, ...], MISSING),
        ("scope", MemoryScope, MISSING),
    ),
    ToolResult: (
        ("effect_id", EffectId, MISSING),
        ("output_ref", ArtifactId | None, MISSING),
        ("failure", Failure | None, MISSING),
    ),
    Failure: (
        ("category", FailureCategory, MISSING),
        ("code", str, MISSING),
        ("message", str, MISSING),
        ("details_ref", ArtifactId | None, MISSING),
    ),
    AgentOutcome: (
        ("attempt_id", AttemptId, MISSING),
        ("output_ref", ArtifactId | None, MISSING),
        ("failure", Failure | None, MISSING),
    ),
}

EMPTY = inspect.Signature.empty
PARAMETER = inspect.Parameter.POSITIONAL_OR_KEYWORD
PROTOCOL_SIGNATURES = {
    OrchestratorPort.start: (
        (("self", EMPTY, EMPTY), ("spec", ExecutionSpec, EMPTY)),
        ExecutionSnapshot,
    ),
    OrchestratorPort.get_snapshot: (
        (("self", EMPTY, EMPTY), ("execution_id", ExecutionId, EMPTY)),
        ExecutionSnapshot,
    ),
    OrchestratorPort.cancel: (
        (
            ("self", EMPTY, EMPTY),
            ("execution_id", ExecutionId, EMPTY),
            ("idempotency_key", str, EMPTY),
        ),
        ExecutionSnapshot,
    ),
    PlannerPort.plan: (
        (
            ("self", EMPTY, EMPTY),
            ("spec", ExecutionSpec, EMPTY),
            ("evidence", EvidencePacket, EMPTY),
        ),
        Plan,
    ),
    PlannerPort.revise: (
        (
            ("self", EMPTY, EMPTY),
            ("plan", Plan, EMPTY),
            ("delta", PlanDelta, EMPTY),
            ("evidence", EvidencePacket, EMPTY),
        ),
        Plan,
    ),
    AgentEnginePort.invoke: (
        (("self", EMPTY, EMPTY), ("invocation", AgentInvocation, EMPTY)),
        AgentOutcome,
    ),
    ModelProviderPort.generate: (
        (
            ("self", EMPTY, EMPTY),
            ("input_ref", ArtifactId, EMPTY),
            ("expected_output_schema", Mapping[str, object], EMPTY),
            ("budget", Budget, EMPTY),
        ),
        ArtifactId,
    ),
    ToolRegistryPort.resolve: (
        (
            ("self", EMPTY, EMPTY),
            ("name", str, EMPTY),
            ("version", str, EMPTY),
        ),
        ToolDescriptor | None,
    ),
    ToolRegistryPort.list_allowed: (
        (("self", EMPTY, EMPTY), ("grants", tuple[str, ...], EMPTY)),
        tuple[ToolDescriptor, ...],
    ),
    ToolExecutorPort.execute: (
        (("self", EMPTY, EMPTY), ("call", ToolCall, EMPTY)),
        ToolResult,
    ),
    PolicyPort.authorize_agent: (
        (("self", EMPTY, EMPTY), ("invocation", AgentInvocation, EMPTY)),
        bool,
    ),
    PolicyPort.authorize_tool: (
        (("self", EMPTY, EMPTY), ("call", ToolCall, EMPTY)),
        bool,
    ),
    ArtifactStorePort.put: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("content", bytes, EMPTY),
            ("media_type", str, EMPTY),
        ),
        ArtifactId,
    ),
    ArtifactStorePort.get: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("artifact_id", ArtifactId, EMPTY),
        ),
        bytes,
    ),
    RemoteAgentPort.invoke: (
        (("self", EMPTY, EMPTY), ("invocation", AgentInvocation, EMPTY)),
        AgentOutcome,
    ),
}


def test_enums_have_exact_stable_values() -> None:
    assert {item.value for item in ExecutionStatus} == {
        "pending",
        "planning",
        "running",
        "waiting",
        "retrying",
        "cancelling",
        "compensating",
        "succeeded",
        "failed",
        "cancelled",
    }
    assert {item.value for item in NodeStatus} == {
        "pending",
        "ready",
        "running",
        "waiting",
        "retrying",
        "cancelling",
        "compensating",
        "succeeded",
        "failed",
        "cancelled",
        "skipped",
        "compensated",
    }
    assert {item.value for item in FailureCategory} == {
        "transient",
        "intermittent",
        "permanent",
        "user_fixable",
        "policy_blocked",
        "system_defect",
    }
    assert {item.value for item in NodeKind} == {
        "agent",
        "tool",
        "join",
        "decision",
    }
    assert {item.value for item in JoinKind} == {"all", "any"}
    assert {item.value for item in SideEffectClass} == {
        "none",
        "idempotent",
        "non_idempotent",
    }
    assert {item.value for item in SuspensionKind} == {
        "approval",
        "input",
        "external_event",
    }


def test_dataclasses_have_exact_public_shapes() -> None:
    for contract, expected_fields in DATACLASS_SHAPES.items():
        assert is_dataclass(contract)
        assert contract.__dataclass_params__.frozen  # type: ignore[attr-defined]
        assert "__slots__" in contract.__dict__
        actual_fields = fields(contract)
        type_hints = get_type_hints(contract)
        assert tuple(field.name for field in actual_fields) == tuple(
            name for name, _, _ in expected_fields
        )
        for field, (_, expected_type, expected_default) in zip(
            actual_fields,
            expected_fields,
            strict=True,
        ):
            assert type_hints[field.name] == expected_type
            assert field.default is expected_default or field.default == expected_default
            assert field.default_factory is MISSING


def test_ports_are_runtime_checkable_protocols_with_exact_async_methods() -> None:
    for protocol, expected_methods in EXPECTED_METHODS.items():
        assert protocol._is_protocol  # type: ignore[attr-defined]
        assert protocol._is_runtime_protocol  # type: ignore[attr-defined]
        assert get_protocol_members(protocol) == frozenset(expected_methods)
        assert all(
            inspect.iscoroutinefunction(getattr(protocol, method))
            for method in expected_methods
        )


def test_port_methods_have_exact_framework_neutral_signatures() -> None:
    for method, (expected_parameters, expected_return) in PROTOCOL_SIGNATURES.items():
        signature = inspect.signature(method, eval_str=True)
        assert tuple(
            (
                parameter.name,
                parameter.annotation,
                parameter.default,
                parameter.kind,
            )
            for parameter in signature.parameters.values()
        ) == tuple(
            (name, annotation, default, PARAMETER)
            for name, annotation, default in expected_parameters
        )
        assert signature.return_annotation == expected_return


def test_runtime_contracts_import_memory_only_through_its_public_api() -> None:
    runtime_root = Path(ports.__file__).parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(runtime_root.rglob("*.py"))
    )

    assert "engrammesh.modules.memory.public" in source
    assert "engrammesh.modules.memory.domain" not in source
    assert "engrammesh.modules.memory.ports" not in source


def test_runtime_signatures_do_not_leak_framework_or_sdk_types() -> None:
    forbidden = ("temporal", "langgraph", "mcp", "a2a", "openai", "anthropic")
    for method in PROTOCOL_SIGNATURES:
        rendered = str(inspect.signature(method, eval_str=True)).lower()
        assert all(name not in rendered for name in forbidden)


def test_public_surface_exports_only_supported_domain_contracts() -> None:
    assert set(public_exports) == {
        "AgentDefinition",
        "AgentInvocation",
        "AgentOutcome",
        "Budget",
        "Decision",
        "ExecutionSnapshot",
        "ExecutionSpec",
        "ExecutionStatus",
        "Failure",
        "FailureCategory",
        "JoinKind",
        "NodeKind",
        "NodeStatus",
        "Plan",
        "PlanDelta",
        "PlanEdge",
        "PlanNode",
        "PlanOperation",
        "SideEffectClass",
        "Suspension",
        "SuspensionKind",
        "ToolCall",
        "ToolDescriptor",
        "ToolResult",
        "can_transition_execution",
        "can_transition_node",
        "derive_effect_id",
    }
    assert not {protocol.__name__ for protocol in PROTOCOLS} & set(public_exports)
