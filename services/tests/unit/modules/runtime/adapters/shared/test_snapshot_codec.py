"""Unit tests for shared runtime snapshot codec."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    _spec_fingerprint,
)
from engrammesh.modules.runtime.adapters.shared.snapshot_codec import (
    fingerprint_from_json,
    fingerprint_to_json,
    snapshot_from_json,
    snapshot_to_json,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
    ExecutionStatus,
)
from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    ArtifactId,
    ExecutionId,
    SubjectId,
    TenantId,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
SCOPE = MemoryScope(TENANT, SUBJECT, workspace_id="ws-1")


def _snapshot() -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        scope=SCOPE,
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )


def test_snapshot_json_round_trip() -> None:
    original = _snapshot()
    assert snapshot_from_json(snapshot_to_json(original)) == original


def test_fingerprint_json_round_trips_orchestrator_spec_fingerprint() -> None:
    spec = ExecutionSpec(
        id=ExecutionId(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        scope=SCOPE,
        objective_ref=ArtifactId(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
        root_agent_id=AgentDefinitionId(UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")),
        memory_query=None,
        budget=Budget(1000, 500, 100_000, NOW + timedelta(hours=1)),
        idempotency_key="start-1",
    )
    fingerprint = _spec_fingerprint(spec)
    assert fingerprint_from_json(fingerprint_to_json(fingerprint)) == fingerprint
