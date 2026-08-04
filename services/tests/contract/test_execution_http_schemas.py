"""Contract tests for execution HTTP JSON Schemas and mapper round-trips."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from engrammesh.bootstrap.http.mappers import snapshot_to_response, start_result_to_response
from engrammesh.modules.memory.public import MemoryScope
from engrammesh.modules.runtime.application.contracts import StartExecutionResult
from engrammesh.modules.runtime.domain.model import (
    ExecutionSnapshot,
    ExecutionStatus,
    Failure,
    FailureCategory,
    NodeStatus,
    Suspension,
    SuspensionKind,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    ExecutionId,
    NodeId,
    SubjectId,
    TenantId,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_ROOT = REPOSITORY_ROOT / "packages" / "contracts" / "jsonschema" / "runtime" / "v1"
START_REQUEST_SCHEMA_PATH = SCHEMA_ROOT / "start-execution-request.schema.json"
CANCEL_REQUEST_SCHEMA_PATH = SCHEMA_ROOT / "cancel-execution-request.schema.json"
SNAPSHOT_RESPONSE_SCHEMA_PATH = SCHEMA_ROOT / "execution-snapshot-response.schema.json"
START_RESPONSE_SCHEMA_PATH = SCHEMA_ROOT / "start-execution-response.schema.json"

UUIDS = {
    "tenant": "53dad495-7915-439a-b03a-379452a1aa86",
    "subject": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
    "actor": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
    "objective": "a2e57fc9-d07d-45dc-a647-76d195985d86",
    "root_agent": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "execution": "0ee41388-bc30-4477-b6fe-e9e16e731f5f",
    "node": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "result": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "details": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "request_ref": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
}


def _load_schema(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict)
    return value



def _snapshot_validator() -> Draft202012Validator:
    return Draft202012Validator(
        _load_schema(SNAPSHOT_RESPONSE_SCHEMA_PATH),
        format_checker=FormatChecker(),
    )


def _start_response_validator() -> Draft202012Validator:
    return Draft202012Validator(
        _load_schema(START_RESPONSE_SCHEMA_PATH),
        format_checker=FormatChecker(),
    )


def _http_scope() -> dict[str, object]:
    return {
        "tenant_id": UUIDS["tenant"],
        "subject_id": UUIDS["subject"],
        "workspace_id": "workspace-42",
        "agent_id": None,
    }


def sample_start_execution_request_dict() -> dict[str, object]:
    return {
        "actor_id": UUIDS["actor"],
        "scope": _http_scope(),
        "objective_ref": UUIDS["objective"],
        "root_agent_id": UUIDS["root_agent"],
        "memory_query": None,
        "budget": {
            "max_input_tokens": 1000,
            "max_output_tokens": 500,
            "max_cost_micros": 100_000,
            "deadline": "2026-08-04T12:00:00+00:00",
        },
        "idempotency_key": "exec-1",
    }


def sample_cancel_execution_request_dict() -> dict[str, object]:
    return {
        "actor_id": UUIDS["actor"],
        "scope": _http_scope(),
        "idempotency_key": "cancel-1",
    }


def sample_execution_snapshot_response_dict() -> dict[str, object]:
    return {
        "execution_id": UUIDS["execution"],
        "scope": _http_scope(),
        "revision": 1,
        "status": "pending",
        "plan_revision": None,
        "node_statuses": {
            UUIDS["node"]: "running",
        },
        "suspension": {
            "request_id": "suspend-1",
            "idempotency_key": "suspend-key-1",
            "execution_id": UUIDS["execution"],
            "node_id": UUIDS["node"],
            "kind": "approval",
            "request_ref": UUIDS["request_ref"],
            "requested_at": "2026-08-04T12:00:00+00:00",
            "expires_at": "2026-08-04T13:00:00+00:00",
        },
        "result_ref": None,
        "failure": {
            "category": "transient",
            "code": "upstream_timeout",
            "message": "upstream timed out",
            "details_ref": UUIDS["details"],
        },
        "updated_at": "2026-08-04T12:00:00+00:00",
    }


def sample_start_execution_response_dict() -> dict[str, object]:
    body = sample_execution_snapshot_response_dict()
    body["created"] = True
    return body


def _minimal_execution_snapshot() -> ExecutionSnapshot:
    return ExecutionSnapshot(
        execution_id=ExecutionId(UUID(UUIDS["execution"])),
        scope=MemoryScope(
            tenant_id=TenantId(UUID(UUIDS["tenant"])),
            subject_id=SubjectId(UUID(UUIDS["subject"])),
            workspace_id="workspace-42",
        ),
        revision=1,
        status=ExecutionStatus.PENDING,
        plan_revision=None,
        node_statuses={
            NodeId(UUID(UUIDS["node"])): NodeStatus.RUNNING,
        },
        suspension=Suspension(
            request_id="suspend-1",
            idempotency_key="suspend-key-1",
            execution_id=ExecutionId(UUID(UUIDS["execution"])),
            node_id=NodeId(UUID(UUIDS["node"])),
            kind=SuspensionKind.APPROVAL,
            request_ref=ArtifactId(UUID(UUIDS["request_ref"])),
            requested_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 4, 13, 0, tzinfo=UTC),
        ),
        result_ref=None,
        failure=Failure(
            category=FailureCategory.TRANSIENT,
            code="upstream_timeout",
            message="upstream timed out",
            details_ref=ArtifactId(UUID(UUIDS["details"])),
        ),
        updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("path", "title"),
    [
        (START_REQUEST_SCHEMA_PATH, "Runtime Start Execution HTTP Request"),
        (CANCEL_REQUEST_SCHEMA_PATH, "Runtime Cancel Execution HTTP Request"),
        (SNAPSHOT_RESPONSE_SCHEMA_PATH, "Runtime Execution Snapshot HTTP Response"),
        (START_RESPONSE_SCHEMA_PATH, "Runtime Start Execution HTTP Response"),
    ],
)
def test_schema_is_valid_draft_2020_12_with_explicit_metadata(
    path: Path,
    title: str,
) -> None:
    schema = _load_schema(path)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["version"] == "1.0.0"
    assert schema["$id"] == f"https://engrammesh.org/contracts/runtime/v1/{path.name}"
    assert schema["title"] == title
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False


def test_start_execution_request_schema_accepts_representative_body() -> None:
    Draft202012Validator(
        _load_schema(START_REQUEST_SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(sample_start_execution_request_dict())


def test_start_execution_request_without_actor_id_is_valid() -> None:
    body = sample_start_execution_request_dict()
    del body["actor_id"]
    Draft202012Validator(
        _load_schema(START_REQUEST_SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(body)


def test_start_execution_request_with_memory_query_is_valid() -> None:
    body = sample_start_execution_request_dict()
    body["memory_query"] = {
        "query_id": "q-1",
        "scope": _http_scope(),
        "text": "find context",
        "valid_at": None,
        "recorded_at": None,
        "limit": 10,
    }
    Draft202012Validator(
        _load_schema(START_REQUEST_SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(body)


def test_cancel_execution_request_schema_accepts_representative_body() -> None:
    Draft202012Validator(
        _load_schema(CANCEL_REQUEST_SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(sample_cancel_execution_request_dict())


def test_execution_snapshot_response_schema_accepts_representative_body() -> None:
    _snapshot_validator().validate(sample_execution_snapshot_response_dict())


def test_start_execution_response_schema_accepts_representative_body() -> None:
    _start_response_validator().validate(sample_start_execution_response_dict())


@pytest.mark.parametrize(
    ("path", "body_factory", "missing_path"),
    [
        (START_REQUEST_SCHEMA_PATH, sample_start_execution_request_dict, ("scope",)),
        (START_REQUEST_SCHEMA_PATH, sample_start_execution_request_dict, ("budget",)),
        (START_REQUEST_SCHEMA_PATH, sample_start_execution_request_dict, ("idempotency_key",)),
        (CANCEL_REQUEST_SCHEMA_PATH, sample_cancel_execution_request_dict, ("scope",)),
        (CANCEL_REQUEST_SCHEMA_PATH, sample_cancel_execution_request_dict, ("idempotency_key",)),
        (
            SNAPSHOT_RESPONSE_SCHEMA_PATH,
            sample_execution_snapshot_response_dict,
            ("execution_id",),
        ),
        (
            START_RESPONSE_SCHEMA_PATH,
            sample_start_execution_response_dict,
            ("created",),
        ),
    ],
)
def test_schema_rejects_missing_required_fields(
    path: Path,
    body_factory: object,
    missing_path: tuple[str, ...],
) -> None:
    assert callable(body_factory)
    body = copy.deepcopy(body_factory())
    target = body
    for component in missing_path[:-1]:
        target = target[component]
    del target[missing_path[-1]]

    validator = Draft202012Validator(
        _load_schema(path),
        format_checker=FormatChecker(),
    )
    with pytest.raises(ValidationError):
        validator.validate(body)


def test_snapshot_mapper_output_matches_response_schema() -> None:
    payload = snapshot_to_response(_minimal_execution_snapshot()).model_dump(mode="json")
    _snapshot_validator().validate(payload)


def test_start_result_mapper_output_matches_start_response_schema() -> None:
    result = StartExecutionResult(snapshot=_minimal_execution_snapshot(), created=True)
    payload = start_result_to_response(result).model_dump(mode="json")
    _start_response_validator().validate(payload)
