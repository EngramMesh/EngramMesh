"""Immutable durable multi-Agent execution contracts and pure invariants."""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Self
from uuid import UUID

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    AttemptId,
    EffectId,
    ExecutionId,
    NodeId,
    SubjectId,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} must not be blank"
        raise ValueError(msg)


def _freeze_json_value(value: object, path: str) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                msg = f"{path} keys must be strings"
                raise TypeError(msg)
            frozen[key] = _freeze_json_value(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list | tuple):
        return tuple(
            _freeze_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{path} must contain only finite numbers"
        raise ValueError(msg)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    msg = f"{path} contains unsupported value type {type(value).__name__}"
    raise TypeError(msg)


def _freeze_schema(schema: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    frozen = _freeze_json_value(schema, field_name)
    if not isinstance(frozen, Mapping):
        msg = f"{field_name} must be a mapping"
        raise TypeError(msg)
    return frozen


class ExecutionStatus(StrEnum):
    """Durable execution lifecycle state."""

    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    CANCELLING = "cancelling"
    COMPENSATING = "compensating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(StrEnum):
    """Durable plan-node lifecycle state."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    CANCELLING = "cancelling"
    COMPENSATING = "compensating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    COMPENSATED = "compensated"


class FailureCategory(StrEnum):
    """Stable failure taxonomy interpreted by durable orchestration."""

    TRANSIENT = "transient"
    INTERMITTENT = "intermittent"
    PERMANENT = "permanent"
    USER_FIXABLE = "user_fixable"
    POLICY_BLOCKED = "policy_blocked"
    SYSTEM_DEFECT = "system_defect"


class NodeKind(StrEnum):
    """Architectural kind of work represented by a plan node."""

    AGENT = "agent"
    TOOL = "tool"
    JOIN = "join"
    DECISION = "decision"


class JoinKind(StrEnum):
    """Dependency condition for a node with multiple predecessors."""

    ALL = "all"
    ANY = "any"


class SideEffectClass(StrEnum):
    """Side-effect semantics declared before execution."""

    NONE = "none"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"


class SuspensionKind(StrEnum):
    """Reason durable execution is waiting for an external decision or fact."""

    APPROVAL = "approval"
    INPUT = "input"
    EXTERNAL_EVENT = "external_event"


@dataclass(frozen=True, slots=True)
class Budget:
    """Hard invocation limits, expressed without provider-specific concepts."""

    max_input_tokens: int
    max_output_tokens: int
    max_cost_micros: int
    deadline: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "max_input_tokens",
            "max_output_tokens",
            "max_cost_micros",
        ):
            if getattr(self, field_name) < 0:
                msg = f"{field_name} must not be negative"
                raise ValueError(msg)
        _require_aware(self.deadline, "deadline")


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Pinned input for one durable execution."""

    id: ExecutionId
    scope: MemoryScope
    objective_ref: ArtifactId
    root_agent_id: AgentDefinitionId
    memory_query: MemoryQuery | None
    budget: Budget
    idempotency_key: str

    def __post_init__(self) -> None:
        _require_non_blank(self.idempotency_key, "idempotency_key")
        if self.memory_query is not None and self.memory_query.scope != self.scope:
            msg = "memory_query.scope must match execution scope"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Versioned Agent identity and capability declaration."""

    id: AgentDefinitionId
    version: int
    role: str
    instruction_ref: ArtifactId
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version <= 0:
            msg = "version must be positive"
            raise ValueError(msg)
        _require_non_blank(self.role, "role")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))


@dataclass(frozen=True, slots=True)
class AgentInvocation:
    """Isolated Agent input containing references, grants, scope, and limits."""

    attempt_id: AttemptId
    execution_id: ExecutionId
    node_id: NodeId
    agent_definition_id: AgentDefinitionId
    input_refs: tuple[ArtifactId, ...]
    evidence_ref: ArtifactId | None
    tool_grants: tuple[str, ...]
    expected_output_schema: Mapping[str, object]
    scope: MemoryScope
    budget: Budget

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        object.__setattr__(self, "tool_grants", tuple(self.tool_grants))
        object.__setattr__(
            self,
            "expected_output_schema",
            _freeze_schema(
                self.expected_output_schema,
                "expected_output_schema",
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanNode:
    """One immutable unit of planned work."""

    id: NodeId
    kind: NodeKind
    objective_ref: ArtifactId
    agent_definition_id: AgentDefinitionId | None
    join_kind: JoinKind | None
    input_refs: tuple[ArtifactId, ...]
    expected_output_schema: Mapping[str, object]
    tool_grants: tuple[str, ...]
    budget: Budget
    side_effect_class: SideEffectClass
    acceptance_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_refs", tuple(self.input_refs))
        object.__setattr__(self, "tool_grants", tuple(self.tool_grants))
        object.__setattr__(
            self,
            "acceptance_criteria",
            tuple(self.acceptance_criteria),
        )
        object.__setattr__(
            self,
            "expected_output_schema",
            _freeze_schema(
                self.expected_output_schema,
                "expected_output_schema",
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanEdge:
    """Directed dependency from one plan node to another."""

    source: NodeId
    target: NodeId


def _validate_dag(nodes: tuple[PlanNode, ...], edges: tuple[PlanEdge, ...]) -> None:
    node_ids = tuple(node.id for node in nodes)
    known_ids = set(node_ids)
    if len(known_ids) != len(node_ids):
        msg = "plan contains duplicate node ids"
        raise ValueError(msg)

    successors: dict[NodeId, list[NodeId]] = {
        node_id: [] for node_id in node_ids
    }
    indegree = dict.fromkeys(node_ids, 0)
    for edge in edges:
        if edge.source == edge.target:
            msg = "plan contains a self edge"
            raise ValueError(msg)
        if edge.source not in known_ids or edge.target not in known_ids:
            msg = "plan contains a dangling edge"
            raise ValueError(msg)
        successors[edge.source].append(edge.target)
        indegree[edge.target] += 1

    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        node_id = ready.pop()
        visited += 1
        for successor in successors[node_id]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    if visited != len(node_ids):
        msg = "plan contains a cycle"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Plan:
    """Revisioned immutable directed acyclic execution plan."""

    execution_id: ExecutionId
    revision: int
    nodes: tuple[PlanNode, ...]
    edges: tuple[PlanEdge, ...]

    def __post_init__(self) -> None:
        if self.revision < 0:
            msg = "revision must not be negative"
            raise ValueError(msg)
        nodes = tuple(self.nodes)
        edges = tuple(self.edges)
        _validate_dag(nodes, edges)
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)


@dataclass(frozen=True, slots=True)
class PlanOperation:
    """One explicitly targeted structural change to a plan."""

    kind: Literal["add_node", "remove_node", "add_edge", "remove_edge"]
    node: PlanNode | None = None
    node_id: NodeId | None = None
    edge: PlanEdge | None = None

    def __post_init__(self) -> None:
        expected_target = {
            "add_node": (self.node is not None, self.node_id is None, self.edge is None),
            "remove_node": (
                self.node is None,
                self.node_id is not None,
                self.edge is None,
            ),
            "add_edge": (self.node is None, self.node_id is None, self.edge is not None),
            "remove_edge": (
                self.node is None,
                self.node_id is None,
                self.edge is not None,
            ),
        }
        if self.kind not in expected_target or not all(expected_target[self.kind]):
            msg = "plan operation must carry exactly the target required by its kind"
            raise ValueError(msg)

    @classmethod
    def add_node(cls, node: PlanNode) -> Self:
        """Create an add-node operation."""
        return cls(kind="add_node", node=node)

    @classmethod
    def remove_node(cls, node_id: NodeId) -> Self:
        """Create a remove-node operation."""
        return cls(kind="remove_node", node_id=node_id)

    @classmethod
    def add_edge(cls, edge: PlanEdge) -> Self:
        """Create an add-edge operation."""
        return cls(kind="add_edge", edge=edge)

    @classmethod
    def remove_edge(cls, edge: PlanEdge) -> Self:
        """Create a remove-edge operation."""
        return cls(kind="remove_edge", edge=edge)


@dataclass(frozen=True, slots=True)
class PlanDelta:
    """Optimistic, non-empty set of plan changes."""

    expected_revision: int
    operations: tuple[PlanOperation, ...]

    def __post_init__(self) -> None:
        if self.expected_revision < 0:
            msg = "expected_revision must not be negative"
            raise ValueError(msg)
        operations = tuple(self.operations)
        if not operations:
            msg = "operations must contain at least one operation"
            raise ValueError(msg)
        object.__setattr__(self, "operations", operations)


@dataclass(frozen=True, slots=True)
class Suspension:
    """Durable request that pauses execution until expiry or a decision."""

    request_id: str
    idempotency_key: str
    execution_id: ExecutionId
    node_id: NodeId | None
    kind: SuspensionKind
    request_ref: ArtifactId
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.request_id, "request_id")
        _require_non_blank(self.idempotency_key, "idempotency_key")
        _require_aware(self.requested_at, "requested_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.requested_at:
            msg = "expires_at must be later than requested_at"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Decision:
    """Idempotent answer to a stable suspension request."""

    request_id: str
    idempotency_key: str
    approved: bool
    decided_by: SubjectId
    decision_ref: ArtifactId | None
    decided_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.request_id, "request_id")
        _require_non_blank(self.idempotency_key, "idempotency_key")
        _require_aware(self.decided_at, "decided_at")


@dataclass(frozen=True, slots=True)
class Failure:
    """Framework-neutral classified failure."""

    category: FailureCategory
    code: str
    message: str
    details_ref: ArtifactId | None

    def __post_init__(self) -> None:
        _require_non_blank(self.code, "code")
        _require_non_blank(self.message, "message")


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """Versioned tool contract exposed by a registry adapter."""

    name: str
    version: str
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    required_grants: tuple[str, ...]
    side_effect_class: SideEffectClass

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        _require_non_blank(self.version, "version")
        object.__setattr__(
            self,
            "input_schema",
            _freeze_schema(self.input_schema, "input_schema"),
        )
        object.__setattr__(
            self,
            "output_schema",
            _freeze_schema(self.output_schema, "output_schema"),
        )
        object.__setattr__(self, "required_grants", tuple(self.required_grants))


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Authorized logical tool effect, separate from its execution attempt."""

    effect_id: EffectId
    attempt_id: AttemptId
    tool_name: str
    tool_version: str
    input_ref: ArtifactId
    grants: tuple[str, ...]
    scope: MemoryScope

    def __post_init__(self) -> None:
        _require_non_blank(self.tool_name, "tool_name")
        _require_non_blank(self.tool_version, "tool_version")
        object.__setattr__(self, "grants", tuple(self.grants))


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Referenced result or classified failure of a tool effect."""

    effect_id: EffectId
    output_ref: ArtifactId | None
    failure: Failure | None

    def __post_init__(self) -> None:
        if (self.output_ref is None) == (self.failure is None):
            msg = "tool result must contain exactly one of output_ref or failure"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    """Referenced output or classified failure of one Agent invocation."""

    attempt_id: AttemptId
    output_ref: ArtifactId | None
    failure: Failure | None

    def __post_init__(self) -> None:
        if (self.output_ref is None) == (self.failure is None):
            msg = "agent outcome must contain exactly one of output_ref or failure"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    """Small durable state snapshot; large values remain artifact references."""

    execution_id: ExecutionId
    scope: MemoryScope
    revision: int
    status: ExecutionStatus
    plan_revision: int | None
    node_statuses: Mapping[NodeId, NodeStatus]
    suspension: Suspension | None
    result_ref: ArtifactId | None
    failure: Failure | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.revision < 0:
            msg = "revision must not be negative"
            raise ValueError(msg)
        if self.plan_revision is not None and self.plan_revision < 0:
            msg = "plan_revision must not be negative"
            raise ValueError(msg)
        _require_aware(self.updated_at, "updated_at")
        object.__setattr__(
            self,
            "node_statuses",
            MappingProxyType(dict(self.node_statuses)),
        )


def _canonical_effect_value(value: object, path: str = "payload") -> object:
    if isinstance(value, Mapping):
        canonical: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                msg = f"{path} keys must be strings"
                raise TypeError(msg)
            canonical[key] = _canonical_effect_value(item, f"{path}.{key}")
        return canonical
    if isinstance(value, list | tuple):
        return [
            _canonical_effect_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{path} must contain only finite numbers"
        raise ValueError(msg)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    msg = f"{path} contains unsupported value type {type(value).__name__}"
    raise TypeError(msg)


def derive_effect_id(
    execution_id: ExecutionId,
    node_id: NodeId,
    logical_operation: str,
    payload: Mapping[str, object],
) -> EffectId:
    """Derive a retry-independent effect ID from one canonical logical action."""
    _require_non_blank(logical_operation, "logical_operation")
    canonical = {
        "execution_id": str(execution_id),
        "logical_operation": logical_operation,
        "node_id": str(node_id),
        "payload": _canonical_effect_value(payload),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(encoded).digest()
    return EffectId(UUID(bytes=digest[:16]))
