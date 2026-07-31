"""Unit tests for Temporal execution spec/snapshot mappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import pytest

from engrammesh.modules.memory.public import MemoryQuery, MemoryScope
from engrammesh.modules.runtime.adapters.temporal.mappers import (
    payload_to_snapshot,
    snapshot_to_payload,
    spec_to_payload,
)
from engrammesh.modules.runtime.domain.model import (
    Budget,
    ExecutionSnapshot,
    ExecutionSpec,
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
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
TENANT = TenantId(UUID("108440a7-5e06-49b0-ae10-42323fe84860"))
SUBJECT = SubjectId(UUID("dc63fae9-dcc3-4f2d-93ee-b573b89693d7"))
AGENT = AgentInstanceId(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))


def _budget() -> Budget:
    return Budget(
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=NOW + timedelta(hours=1),
    )


def _scope() -> MemoryScope:
    return MemoryScope(TENANT, SUBJECT, workspace_id="ws-1", agent_id=AGENT)


def _memory_query() -> MemoryQuery:
    return MemoryQuery(
        query_id="q-1",
        scope=_scope(),
        text="find related episodes",
        valid_at=NOW,
        recorded_at=NOW + timedelta(minutes=5),
        limit=25,
    )


def _spec() -> ExecutionSpec:
    return ExecutionSpec(
        id=ExecutionId(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
        scope=_scope(),
        objective_ref=ArtifactId(UUID("d3d34bf3-6ce6-475b-b960-3097cc3f639f")),
        root_agent_id=AgentDefinitionId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        memory_query=_memory_query(),
        budget=_budget(),
        idempotency_key="start-1",
    )


def _snapshot() -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
        scope=_scope(),
        revision=3,
        status=ExecutionStatus.RUNNING,
        plan_revision=1,
        node_statuses=MappingProxyType(
            {
                NodeId(UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")): NodeStatus.READY,
            }
        ),
        suspension=None,
        result_ref=ArtifactId(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")),
        failure=None,
        updated_at=NOW,
    )


def test_spec_to_payload_round_trips_required_fields() -> None:
    spec = _spec()
    payload = spec_to_payload(spec)

    assert payload["id"] == str(spec.id)
    assert payload["idempotency_key"] == "start-1"
    assert payload["objective_ref"] == str(spec.objective_ref)
    assert payload["root_agent_id"] == str(spec.root_agent_id)

    scope_payload = payload["scope"]
    assert isinstance(scope_payload, dict)
    assert scope_payload["tenant_id"] == str(TENANT)
    assert scope_payload["subject_id"] == str(SUBJECT)
    assert scope_payload["workspace_id"] == "ws-1"
    assert scope_payload["agent_id"] == str(AGENT)

    budget_payload = payload["budget"]
    assert isinstance(budget_payload, dict)
    assert budget_payload["max_input_tokens"] == 1_000
    assert budget_payload["deadline"] == (NOW + timedelta(hours=1)).isoformat()

    memory_query_payload = payload["memory_query"]
    assert isinstance(memory_query_payload, dict)
    assert memory_query_payload["query_id"] == "q-1"
    assert memory_query_payload["text"] == "find related episodes"
    assert memory_query_payload["limit"] == 25


def test_spec_to_payload_allows_missing_memory_query() -> None:
    spec = ExecutionSpec(
        id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT),
        objective_ref=ArtifactId.new(),
        root_agent_id=AgentDefinitionId.new(),
        memory_query=None,
        budget=_budget(),
        idempotency_key="start-2",
    )

    payload = spec_to_payload(spec)

    assert payload["memory_query"] is None


def test_snapshot_payload_round_trip() -> None:
    snapshot = _snapshot()

    restored = payload_to_snapshot(snapshot_to_payload(snapshot))

    assert restored == snapshot


def test_snapshot_payload_round_trip_minimal_pending() -> None:
    snapshot = ExecutionSnapshot(
        execution_id=ExecutionId.new(),
        scope=MemoryScope(TENANT, SUBJECT),
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses=MappingProxyType({}),
        suspension=None,
        result_ref=None,
        failure=None,
        updated_at=NOW,
    )

    restored = payload_to_snapshot(snapshot_to_payload(snapshot))

    assert restored == snapshot


def test_payload_to_snapshot_rejects_invalid_status() -> None:
    payload = snapshot_to_payload(_snapshot())
    payload["status"] = "not-a-status"

    with pytest.raises(ValueError, match="status"):
        payload_to_snapshot(payload)
