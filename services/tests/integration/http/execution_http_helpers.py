"""Shared helpers for execution HTTP integration tests."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from engrammesh.bootstrap.composition import AppRuntime
from engrammesh.modules.runtime.adapters.in_memory.orchestrator import (
    InMemoryOrchestratorPort,
)
from engrammesh.modules.runtime.domain.model import ExecutionStatus
from engrammesh.shared.kernel.ids import ExecutionId

_episode_helpers_path = Path(__file__).resolve().with_name("episode_http_helpers.py")
_episode_spec = importlib.util.spec_from_file_location(
    "episode_http_helpers", _episode_helpers_path
)
assert _episode_spec is not None and _episode_spec.loader is not None
_episode_helpers = importlib.util.module_from_spec(_episode_spec)
_episode_spec.loader.exec_module(_episode_helpers)

ACTOR_ID = _episode_helpers.ACTOR_ID
SUBJECT_ID = _episode_helpers.SUBJECT_ID
TENANT_A = _episode_helpers.TENANT_A

OBJECTIVE_REF = UUID("a2e57fc9-d07d-45dc-a647-76d195985d86")
ROOT_AGENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def make_start_execution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor_id": str(ACTOR_ID),
        "scope": {
            "tenant_id": str(TENANT_A),
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
        },
        "objective_ref": str(OBJECTIVE_REF),
        "root_agent_id": str(ROOT_AGENT_ID),
        "memory_query": None,
        "budget": {
            "max_input_tokens": 1000,
            "max_output_tokens": 500,
            "max_cost_micros": 100_000,
            "deadline": "2026-08-04T12:00:00+00:00",
        },
        "idempotency_key": "exec-1",
    }
    payload.update(overrides)
    return payload


def make_cancel_execution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor_id": str(ACTOR_ID),
        "scope": {
            "tenant_id": str(TENANT_A),
            "subject_id": str(SUBJECT_ID),
            "workspace_id": "workspace-42",
        },
        "idempotency_key": "cancel-1",
    }
    payload.update(overrides)
    return payload


async def seed_succeeded_execution(runtime: AppRuntime, execution_id: ExecutionId) -> None:
    orchestrator = runtime.start_execution_handler()._orchestrator
    assert isinstance(orchestrator, InMemoryOrchestratorPort)

    def _mark_succeeded(state):
        snapshot = state.snapshots[execution_id]
        return replace(
            state,
            snapshots={
                **dict(state.snapshots),
                execution_id: replace(snapshot, status=ExecutionStatus.SUCCEEDED),
            },
        )

    await orchestrator.database.write(_mark_succeeded)
