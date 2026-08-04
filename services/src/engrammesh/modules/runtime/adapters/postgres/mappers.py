"""Row mappers between PostgreSQL records and runtime domain types."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from engrammesh.modules.runtime.adapters.shared.snapshot_codec import (
    fingerprint_from_json,
    fingerprint_to_json,
    snapshot_from_json,
    snapshot_to_json,
)
from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.shared.kernel.ids import ExecutionId, TenantId


def snapshot_to_row(snapshot: ExecutionSnapshot) -> dict[str, object]:
    """Serialize an execution snapshot into runtime_execution_snapshots columns."""
    scope = snapshot.scope
    return {
        "tenant_id": scope.tenant_id.value,
        "execution_id": snapshot.execution_id.value,
        "subject_id": scope.subject_id.value,
        "workspace_id": scope.workspace_id,
        "agent_id": scope.agent_id.value if scope.agent_id is not None else None,
        "revision": snapshot.revision,
        "status": snapshot.status.value,
        "snapshot": snapshot_to_json(snapshot),
        "updated_at": snapshot.updated_at,
    }


def row_to_snapshot(row: Mapping[str, object]) -> ExecutionSnapshot:
    """Deserialize a runtime_execution_snapshots row into an execution snapshot."""
    snapshot_payload = row["snapshot"]
    if not isinstance(snapshot_payload, Mapping):
        msg = "snapshot must be a mapping"
        raise TypeError(msg)
    return snapshot_from_json(cast(dict[str, object], snapshot_payload))


def idempotency_to_row(
    tenant_id: TenantId,
    idempotency_key: str,
    execution_id: ExecutionId,
    fingerprint: tuple[object, ...],
    *,
    created_at: datetime,
) -> dict[str, object]:
    """Serialize a start-idempotency entry into runtime_start_idempotency columns."""
    return {
        "tenant_id": tenant_id.value,
        "idempotency_key": idempotency_key,
        "execution_id": execution_id.value,
        "fingerprint": fingerprint_to_json(fingerprint),
        "created_at": created_at,
    }


def row_to_fingerprint(row: Mapping[str, object]) -> tuple[object, ...]:
    """Deserialize the fingerprint JSON stored on a start-idempotency row."""
    fingerprint_payload = row["fingerprint"]
    if not isinstance(fingerprint_payload, list):
        msg = "fingerprint must be a list"
        raise TypeError(msg)
    return fingerprint_from_json(cast(list[object], fingerprint_payload))


def _as_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    msg = f"expected UUID or UUID text, got {type(value).__name__}"
    raise TypeError(msg)


def _to_json_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json_value(item) for item in value]
    return value
