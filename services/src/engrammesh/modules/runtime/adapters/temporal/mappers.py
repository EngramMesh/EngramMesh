"""JSON-serializable mappers between domain execution types and Temporal payloads."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from engrammesh.modules.memory.public import MemoryQuery
from engrammesh.modules.runtime.adapters.shared.snapshot_codec import (
    _parse_datetime,
    _parse_optional_datetime,
    _require_int,
    _require_mapping,
    _require_str,
    _scope_from_payload,
    scope_to_payload,
    snapshot_from_json,
    snapshot_to_json,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
    ExecutionStatus,
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
        "scope": scope_to_payload(memory_query.scope),
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
        "scope": scope_to_payload(spec.scope),
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
    return snapshot_to_json(snapshot)


def payload_to_snapshot(payload: dict[str, object]) -> ExecutionSnapshot:
    """Deserialize a Temporal workflow snapshot payload into domain state."""
    return snapshot_from_json(payload)


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
