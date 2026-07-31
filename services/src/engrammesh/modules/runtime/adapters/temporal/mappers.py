"""JSON-serializable mappers between domain execution types and Temporal payloads."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import cast
from uuid import UUID

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
    ExecutionStatus,
    NodeStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    ExecutionId,
    NodeId,
    SubjectId,
    TenantId,
)


def _require_mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{field_name} must be a mapping"
        raise TypeError(msg)
    return cast(dict[str, object], value)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    return value


def _parse_uuid_value[T](value_type: type[T], value: object, field_name: str) -> T:
    text = _require_str(value, field_name)
    return value_type(UUID(text))  # type: ignore[call-arg]


def _parse_optional_uuid_value[T](
    value_type: type[T],
    value: object,
    field_name: str,
) -> T | None:
    if value is None:
        return None
    return _parse_uuid_value(value_type, value, field_name)


def _parse_datetime(value: object, field_name: str) -> datetime:
    text = _require_str(value, field_name)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)
    return parsed


def _parse_optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, field_name)


def _scope_to_payload(scope: MemoryScope) -> dict[str, object]:
    payload: dict[str, object] = {
        "tenant_id": str(scope.tenant_id),
        "subject_id": str(scope.subject_id),
        "workspace_id": scope.workspace_id,
        "agent_id": None if scope.agent_id is None else str(scope.agent_id),
    }
    return payload


def _scope_from_payload(payload: object) -> MemoryScope:
    mapping = _require_mapping(payload, "scope")
    return MemoryScope(
        tenant_id=_parse_uuid_value(TenantId, mapping["tenant_id"], "scope.tenant_id"),
        subject_id=_parse_uuid_value(
            SubjectId,
            mapping["subject_id"],
            "scope.subject_id",
        ),
        workspace_id=cast(str | None, mapping.get("workspace_id")),
        agent_id=_parse_optional_uuid_value(
            AgentInstanceId,
            mapping.get("agent_id"),
            "scope.agent_id",
        ),
    )


def _budget_to_payload(budget: Budget) -> dict[str, object]:
    return {
        "max_input_tokens": budget.max_input_tokens,
        "max_output_tokens": budget.max_output_tokens,
        "max_cost_micros": budget.max_cost_micros,
        "deadline": budget.deadline.isoformat(),
    }


def _budget_from_payload(payload: object) -> Budget:
    mapping = _require_mapping(payload, "budget")
    return Budget(
        max_input_tokens=_require_int(
            mapping["max_input_tokens"],
            "budget.max_input_tokens",
        ),
        max_output_tokens=_require_int(
            mapping["max_output_tokens"],
            "budget.max_output_tokens",
        ),
        max_cost_micros=_require_int(
            mapping["max_cost_micros"],
            "budget.max_cost_micros",
        ),
        deadline=_parse_datetime(mapping["deadline"], "budget.deadline"),
    )


def _memory_query_to_payload(memory_query: MemoryQuery) -> dict[str, object]:
    return {
        "query_id": memory_query.query_id,
        "scope": _scope_to_payload(memory_query.scope),
        "text": memory_query.text,
        "valid_at": (
            None
            if memory_query.valid_at is None
            else memory_query.valid_at.isoformat()
        ),
        "recorded_at": (
            None
            if memory_query.recorded_at is None
            else memory_query.recorded_at.isoformat()
        ),
        "limit": memory_query.limit,
    }


def _memory_query_from_payload(payload: object) -> MemoryQuery | None:
    if payload is None:
        return None
    mapping = _require_mapping(payload, "memory_query")
    return MemoryQuery(
        query_id=_require_str(mapping["query_id"], "memory_query.query_id"),
        scope=_scope_from_payload(mapping["scope"]),
        text=_require_str(mapping["text"], "memory_query.text"),
        valid_at=_parse_optional_datetime(mapping.get("valid_at"), "memory_query.valid_at"),
        recorded_at=_parse_optional_datetime(
            mapping.get("recorded_at"),
            "memory_query.recorded_at",
        ),
        limit=_require_int(mapping["limit"], "memory_query.limit"),
    )


def spec_to_payload(spec: ExecutionSpec) -> dict[str, object]:
    """Serialize an execution spec for Temporal workflow input."""
    return {
        "id": str(spec.id),
        "scope": _scope_to_payload(spec.scope),
        "objective_ref": str(spec.objective_ref),
        "root_agent_id": str(spec.root_agent_id),
        "memory_query": (
            None
            if spec.memory_query is None
            else _memory_query_to_payload(spec.memory_query)
        ),
        "budget": _budget_to_payload(spec.budget),
        "idempotency_key": spec.idempotency_key,
    }


def snapshot_to_payload(snapshot: ExecutionSnapshot) -> dict[str, object]:
    """Serialize an execution snapshot for Temporal workflow state."""
    node_statuses = {
        str(node_id): status.value
        for node_id, status in snapshot.node_statuses.items()
    }
    return {
        "execution_id": str(snapshot.execution_id),
        "scope": _scope_to_payload(snapshot.scope),
        "revision": snapshot.revision,
        "status": snapshot.status.value,
        "plan_revision": snapshot.plan_revision,
        "node_statuses": node_statuses,
        "suspension": None,
        "result_ref": (
            None if snapshot.result_ref is None else str(snapshot.result_ref)
        ),
        "failure": None,
        "updated_at": snapshot.updated_at.isoformat(),
    }


def payload_to_snapshot(payload: dict[str, object]) -> ExecutionSnapshot:
    """Deserialize a Temporal workflow snapshot payload into domain state."""
    status_text = _require_str(payload["status"], "status")
    try:
        status = ExecutionStatus(status_text)
    except ValueError as exc:
        msg = "status must be a valid execution status"
        raise ValueError(msg) from exc

    node_statuses_payload = _require_mapping(
        payload.get("node_statuses", {}),
        "node_statuses",
    )
    node_statuses: dict[NodeId, NodeStatus] = {}
    for node_id_text, node_status_text in node_statuses_payload.items():
        try:
            node_status = NodeStatus(_require_str(node_status_text, "node_statuses.value"))
        except ValueError as exc:
            msg = "node_statuses values must be valid node statuses"
            raise ValueError(msg) from exc
        node_statuses[NodeId(UUID(node_id_text))] = node_status

    return ExecutionSnapshot(
        execution_id=_parse_uuid_value(
            ExecutionId,
            payload["execution_id"],
            "execution_id",
        ),
        scope=_scope_from_payload(payload["scope"]),
        revision=_require_int(payload["revision"], "revision"),
        status=status,
        plan_revision=cast(int | None, payload.get("plan_revision")),
        node_statuses=MappingProxyType(node_statuses),
        suspension=None,
        result_ref=_parse_optional_uuid_value(
            ArtifactId,
            payload.get("result_ref"),
            "result_ref",
        ),
        failure=None,
        updated_at=_parse_datetime(payload["updated_at"], "updated_at"),
    )


def initial_snapshot_payload(
    spec_payload: dict[str, object],
    *,
    updated_at: datetime,
) -> dict[str, object]:
    """Build the initial pending snapshot payload from a workflow spec payload."""
    scope_payload = spec_payload["scope"]
    if not isinstance(scope_payload, dict):
        msg = "scope must be a mapping"
        raise TypeError(msg)
    return {
        "execution_id": _require_str(spec_payload["id"], "id"),
        "scope": dict(cast(dict[str, object], scope_payload)),
        "revision": 1,
        "status": ExecutionStatus.PENDING.value,
        "plan_revision": None,
        "node_statuses": {},
        "suspension": None,
        "result_ref": None,
        "failure": None,
        "updated_at": updated_at.isoformat(),
    }
