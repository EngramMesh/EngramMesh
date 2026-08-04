"""JSON-serializable codec for execution snapshots and spec fingerprints."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import cast
from uuid import UUID

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.domain.model import (
    ExecutionSnapshot,
    ExecutionStatus,
    NodeStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    AgentInstanceId,
    ArtifactId,
    ExecutionId,
    NodeId,
    SubjectId,
    TenantId,
    UUIDValue,
)

_ID_TYPES: dict[str, type[UUIDValue]] = {
    "TenantId": TenantId,
    "SubjectId": SubjectId,
    "AgentDefinitionId": AgentDefinitionId,
    "AgentInstanceId": AgentInstanceId,
    "ExecutionId": ExecutionId,
    "NodeId": NodeId,
    "ArtifactId": ArtifactId,
}


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


def scope_to_payload(scope: MemoryScope) -> dict[str, object]:
    return {
        "tenant_id": str(scope.tenant_id),
        "subject_id": str(scope.subject_id),
        "workspace_id": scope.workspace_id,
        "agent_id": None if scope.agent_id is None else str(scope.agent_id),
    }


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


def snapshot_to_json(snapshot: ExecutionSnapshot) -> dict[str, object]:
    """Serialize an execution snapshot to a JSON-compatible mapping."""
    node_statuses = {
        str(node_id): status.value
        for node_id, status in snapshot.node_statuses.items()
    }
    return {
        "execution_id": str(snapshot.execution_id),
        "scope": scope_to_payload(snapshot.scope),
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


def snapshot_from_json(payload: dict[str, object]) -> ExecutionSnapshot:
    """Deserialize a JSON mapping into an execution snapshot."""
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


def _fingerprint_encode_value(value: object) -> object:
    if isinstance(value, UUIDValue):
        return {"$": type(value).__name__, "v": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "fingerprint datetime must be timezone-aware"
            raise ValueError(msg)
        return {"$": "datetime", "v": value.isoformat()}
    if isinstance(value, tuple):
        return [_fingerprint_encode_value(item) for item in value]
    if value is None or isinstance(value, (int, str, bool)):
        return value
    msg = f"unsupported fingerprint value type: {type(value)!r}"
    raise TypeError(msg)


def _fingerprint_decode_value(value: object) -> object:
    if isinstance(value, list):
        return tuple(_fingerprint_decode_value(item) for item in value)
    if isinstance(value, dict) and "$" in value:
        tag = _require_str(value["$"], "fingerprint tag")
        raw = value["v"]
        if tag == "datetime":
            return _parse_datetime(raw, "fingerprint datetime")
        id_type = _ID_TYPES.get(tag)
        if id_type is not None:
            return id_type(UUID(_require_str(raw, "fingerprint id")))
        msg = f"unknown fingerprint tag: {tag}"
        raise ValueError(msg)
    return value


def fingerprint_to_json(fingerprint: tuple[object, ...]) -> list[object]:
    """Serialize a spec fingerprint tuple for JSON storage."""
    return [_fingerprint_encode_value(item) for item in fingerprint]


def fingerprint_from_json(payload: list[object]) -> tuple[object, ...]:
    """Deserialize a JSON list into a spec fingerprint tuple."""
    return tuple(_fingerprint_decode_value(item) for item in payload)
