from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.modules.runtime.domain.model import (
    AgentInvocation,
    Budget,
    Decision,
    ExecutionSpec,
    JoinKind,
    NodeKind,
    Plan,
    PlanDelta,
    PlanEdge,
    PlanNode,
    PlanOperation,
    SideEffectClass,
    Suspension,
    SuspensionKind,
    derive_effect_id,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    AttemptId,
    ExecutionId,
    NodeId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


def _budget() -> Budget:
    return Budget(
        max_input_tokens=2_000,
        max_output_tokens=1_000,
        max_cost_micros=500_000,
        deadline=NOW + timedelta(hours=1),
    )


def _node(node_id: NodeId | None = None) -> PlanNode:
    return PlanNode(
        id=node_id or NodeId.new(),
        kind=NodeKind.AGENT,
        objective_ref=ArtifactId.new(),
        agent_definition_id=AgentDefinitionId.new(),
        join_kind=JoinKind.ALL,
        input_refs=(),
        expected_output_schema={"type": "object"},
        tool_grants=("web.read",),
        budget=_budget(),
        side_effect_class=SideEffectClass.NONE,
        acceptance_criteria=("schema-valid",),
    )


def test_execution_spec_rejects_memory_query_for_another_scope() -> None:
    scope = MemoryScope(TenantId.new(), SubjectId.new())
    other_scope = MemoryScope(TenantId.new(), SubjectId.new())

    with pytest.raises(ValueError, match="memory_query.scope"):
        ExecutionSpec(
            id=ExecutionId.new(),
            scope=scope,
            objective_ref=ArtifactId.new(),
            root_agent_id=AgentDefinitionId.new(),
            memory_query=MemoryQuery(
                query_id="query-1",
                scope=other_scope,
                text="tea",
            ),
            budget=_budget(),
            idempotency_key="execution-1",
        )


def test_plan_rejects_duplicate_node_ids() -> None:
    node = _node()

    with pytest.raises(ValueError, match="duplicate node"):
        Plan(
            execution_id=ExecutionId.new(),
            revision=1,
            nodes=(node, node),
            edges=(),
        )


def test_plan_rejects_dangling_edges() -> None:
    node = _node()

    with pytest.raises(ValueError, match="dangling edge"):
        Plan(
            execution_id=ExecutionId.new(),
            revision=1,
            nodes=(node,),
            edges=(PlanEdge(source=node.id, target=NodeId.new()),),
        )


def test_plan_rejects_self_edges() -> None:
    node = _node()

    with pytest.raises(ValueError, match="self edge"):
        Plan(
            execution_id=ExecutionId.new(),
            revision=1,
            nodes=(node,),
            edges=(PlanEdge(source=node.id, target=node.id),),
        )


def test_plan_rejects_cycles() -> None:
    first = _node()
    second = _node()
    third = _node()

    with pytest.raises(ValueError, match="cycle"):
        Plan(
            execution_id=ExecutionId.new(),
            revision=1,
            nodes=(first, second, third),
            edges=(
                PlanEdge(source=first.id, target=second.id),
                PlanEdge(source=second.id, target=third.id),
                PlanEdge(source=third.id, target=first.id),
            ),
        )


def test_plan_accepts_an_immutable_dag() -> None:
    first = _node()
    second = _node()
    nodes = [first, second]
    edges = [PlanEdge(source=first.id, target=second.id)]

    plan = Plan(
        execution_id=ExecutionId.new(),
        revision=1,
        nodes=nodes,  # type: ignore[arg-type]
        edges=edges,  # type: ignore[arg-type]
    )
    nodes.clear()
    edges.clear()

    assert plan.nodes == (first, second)
    assert plan.edges == (PlanEdge(source=first.id, target=second.id),)
    with pytest.raises(FrozenInstanceError):
        plan.revision = 2


def test_plan_delta_requires_an_expected_revision_and_operation() -> None:
    with pytest.raises(ValueError, match="expected_revision"):
        PlanDelta(expected_revision=-1, operations=(PlanOperation.remove_node(NodeId.new()),))
    with pytest.raises(ValueError, match="operation"):
        PlanDelta(expected_revision=1, operations=())


def test_plan_operation_requires_the_exact_target_for_its_kind() -> None:
    node = _node()

    assert PlanOperation.add_node(node).node is node
    assert PlanOperation.remove_node(node.id).node_id == node.id
    with pytest.raises(ValueError, match="target"):
        PlanOperation(kind="add_node", edge=PlanEdge(node.id, NodeId.new()))


def test_effect_id_is_stable_across_attempts_and_mapping_order() -> None:
    execution_id = ExecutionId(UUID("00000000-0000-0000-0000-000000000001"))
    node_id = NodeId(UUID("00000000-0000-0000-0000-000000000002"))
    first_attempt = AttemptId.new()
    second_attempt = AttemptId.new()

    first = derive_effect_id(
        execution_id=execution_id,
        node_id=node_id,
        logical_operation="send-email",
        payload={"subject": "hello", "recipients": ["a@example.com"]},
    )
    second = derive_effect_id(
        execution_id=execution_id,
        node_id=node_id,
        logical_operation="send-email",
        payload={"recipients": ["a@example.com"], "subject": "hello"},
    )

    assert first_attempt != second_attempt
    assert first == second
    assert str(first) == "7358851b-076c-79f5-43b9-dfb5c9e5bc86"


def test_effect_id_changes_with_the_canonical_logical_operation() -> None:
    execution_id = ExecutionId.new()
    node_id = NodeId.new()

    original = derive_effect_id(
        execution_id,
        node_id,
        "send-email",
        {"recipient": "a@example.com"},
    )
    changed_action = derive_effect_id(
        execution_id,
        node_id,
        "delete-email",
        {"recipient": "a@example.com"},
    )
    changed_payload = derive_effect_id(
        execution_id,
        node_id,
        "send-email",
        {"recipient": "b@example.com"},
    )

    assert len({original, changed_action, changed_payload}) == 3


def test_agent_invocation_carries_only_isolated_context_contracts() -> None:
    invocation = AgentInvocation(
        attempt_id=AttemptId.new(),
        execution_id=ExecutionId.new(),
        node_id=NodeId.new(),
        agent_definition_id=AgentDefinitionId.new(),
        input_refs=(ArtifactId.new(),),
        evidence_ref=ArtifactId.new(),
        tool_grants=("web.read",),
        expected_output_schema={"type": "object", "required": ["answer"]},
        scope=MemoryScope(TenantId.new(), SubjectId.new()),
        budget=_budget(),
    )

    assert isinstance(invocation.expected_output_schema, Mapping)
    assert tuple(invocation.expected_output_schema["required"]) == ("answer",)
    forbidden_fields = {
        "chat_history",
        "conversation",
        "messages",
        "prompt",
        "reasoning",
        "scratchpad",
    }
    assert forbidden_fields.isdisjoint(invocation.__dataclass_fields__)


def test_suspension_requires_stable_ids_and_aware_ordered_expiry() -> None:
    values = {
        "request_id": "approval-42",
        "idempotency_key": "approval-42:v1",
        "execution_id": ExecutionId.new(),
        "node_id": NodeId.new(),
        "kind": SuspensionKind.APPROVAL,
        "request_ref": ArtifactId.new(),
        "requested_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }

    assert Suspension(**values).request_id == "approval-42"
    with pytest.raises(ValueError, match="request_id"):
        Suspension(**(values | {"request_id": " "}))
    with pytest.raises(ValueError, match="idempotency_key"):
        Suspension(**(values | {"idempotency_key": ""}))
    with pytest.raises(ValueError, match="expires_at"):
        Suspension(**(values | {"expires_at": NOW.replace(tzinfo=None)}))
    with pytest.raises(ValueError, match="later"):
        Suspension(**(values | {"expires_at": NOW}))


def test_decision_requires_stable_ids_and_aware_decision_time() -> None:
    values = {
        "request_id": "approval-42",
        "idempotency_key": "decision-42:v1",
        "approved": True,
        "decided_by": SubjectId.new(),
        "decision_ref": ArtifactId.new(),
        "decided_at": NOW,
    }

    assert Decision(**values).approved
    with pytest.raises(ValueError, match="request_id"):
        Decision(**(values | {"request_id": ""}))
    with pytest.raises(ValueError, match="idempotency_key"):
        Decision(**(values | {"idempotency_key": " "}))
    with pytest.raises(ValueError, match="decided_at"):
        Decision(**(values | {"decided_at": NOW.replace(tzinfo=None)}))
