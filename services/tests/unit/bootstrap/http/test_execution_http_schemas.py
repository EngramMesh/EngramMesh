from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from engrammesh.bootstrap.http.schemas import (
    BudgetRequest,
    CancelExecutionRequest,
    ScopeRequest,
    StartExecutionRequest,
)

TENANT = UUID("53dad495-7915-439a-b03a-379452a1aa86")
SUBJECT = UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45")
OBJECTIVE = UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")
ROOT_AGENT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ACTOR = UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6")
DEADLINE = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _scope() -> ScopeRequest:
    return ScopeRequest(tenant_id=TENANT, subject_id=SUBJECT, workspace_id="ws-1")


def _budget() -> BudgetRequest:
    return BudgetRequest(
        max_input_tokens=1000,
        max_output_tokens=500,
        max_cost_micros=100_000,
        deadline=DEADLINE,
    )


def test_start_execution_request_accepts_valid_body() -> None:
    body = StartExecutionRequest(
        actor_id=ACTOR,
        scope=_scope(),
        objective_ref=OBJECTIVE,
        root_agent_id=ROOT_AGENT,
        memory_query=None,
        budget=_budget(),
        idempotency_key="exec-1",
    )
    assert body.idempotency_key == "exec-1"


def test_start_execution_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StartExecutionRequest.model_validate(
            {
                "actor_id": str(ACTOR),
                "scope": {"tenant_id": str(TENANT), "subject_id": str(SUBJECT)},
                "objective_ref": str(OBJECTIVE),
                "root_agent_id": str(ROOT_AGENT),
                "memory_query": None,
                "budget": {
                    "max_input_tokens": 1,
                    "max_output_tokens": 1,
                    "max_cost_micros": 1,
                    "deadline": DEADLINE.isoformat(),
                },
                "idempotency_key": "exec-1",
                "unexpected": True,
            }
        )


def test_cancel_execution_request_accepts_valid_body() -> None:
    body = CancelExecutionRequest(
        actor_id=ACTOR,
        scope=_scope(),
        idempotency_key="cancel-1",
    )
    assert body.idempotency_key == "cancel-1"


@pytest.mark.parametrize("idempotency_key", ("", " ", "\t"))
def test_start_execution_request_rejects_blank_idempotency_key(
    idempotency_key: str,
) -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        StartExecutionRequest(
            actor_id=ACTOR,
            scope=_scope(),
            objective_ref=OBJECTIVE,
            root_agent_id=ROOT_AGENT,
            memory_query=None,
            budget=_budget(),
            idempotency_key=idempotency_key,
        )


@pytest.mark.parametrize("idempotency_key", ("", " ", "\t"))
def test_cancel_execution_request_rejects_blank_idempotency_key(
    idempotency_key: str,
) -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        CancelExecutionRequest(
            actor_id=ACTOR,
            scope=_scope(),
            idempotency_key=idempotency_key,
        )


@pytest.mark.parametrize(
    "field_name",
    ("max_input_tokens", "max_output_tokens", "max_cost_micros"),
)
def test_budget_request_rejects_negative_values(field_name: str) -> None:
    values = {
        "max_input_tokens": 1000,
        "max_output_tokens": 500,
        "max_cost_micros": 100_000,
        "deadline": DEADLINE,
    }
    values[field_name] = -1
    with pytest.raises(ValidationError):
        BudgetRequest(**values)
