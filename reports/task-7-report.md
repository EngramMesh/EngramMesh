# Task 7 Report: GetExecutionSnapshotHandler and CancelExecutionHandler

**Status:** Complete  
**Base:** `ec1fe2b`  
**Commit:** `feat: add runtime get and cancel handlers` (`0fadf07`)

## Summary

Added `GetExecutionSnapshotHandler` and `CancelExecutionHandler` following the `GetEpisodeHandler` pattern. Both handlers authorize via `RuntimeAuthorizationPort` with actions `get_execution` and `cancel_execution`, then delegate to `OrchestratorPort`. `ExecutionNotFound` propagates unchanged from the orchestrator.

## Changes

| File | Change |
|------|--------|
| `services/src/engrammesh/modules/runtime/application/get_execution_snapshot.py` | New `GetExecutionSnapshotHandler` |
| `services/src/engrammesh/modules/runtime/application/cancel_execution.py` | New `CancelExecutionHandler` |
| `services/tests/unit/modules/runtime/application/test_get_execution_snapshot.py` | Unit tests for get handler |
| `services/tests/unit/modules/runtime/application/test_cancel_execution.py` | Unit tests for cancel handler |

## Design Notes

- Authorization uses `RuntimeAuthorizationRequest` with `get_execution` / `cancel_execution` actions.
- Denied authorization raises `ExecutionAuthorizationDenied` before touching the orchestrator.
- Get handler calls `orchestrator.get_snapshot(scope, execution_id)`.
- Cancel handler calls `orchestrator.cancel(scope, execution_id, idempotency_key)`.
- Domain errors (`ExecutionNotFound`, `InvalidExecutionTransition`, etc.) propagate unchanged.

## Verification

```bash
uv run --python 3.14 --project services pytest services/tests/unit/modules/runtime/application/ -v
# 13 passed

uv run --python 3.14 --project services ruff check services/src/engrammesh/modules/runtime/application/get_execution_snapshot.py services/src/engrammesh/modules/runtime/application/cancel_execution.py services/tests/unit/modules/runtime/application/test_get_execution_snapshot.py services/tests/unit/modules/runtime/application/test_cancel_execution.py
# All checks passed

uv run --python 3.14 --project services mypy services/src/engrammesh/modules/runtime/application/get_execution_snapshot.py services/src/engrammesh/modules/runtime/application/cancel_execution.py
# Success
```

## Tests Added

### GetExecutionSnapshotHandler

1. `test_get_execution_snapshot_returns_snapshot_when_found` — returns snapshot after start
2. `test_get_execution_snapshot_raises_not_found` — missing execution raises `ExecutionNotFound`
3. `test_get_execution_snapshot_denial_authorizes_first_and_accesses_nothing_else` — denial skips orchestrator

### CancelExecutionHandler

1. `test_cancel_execution_returns_cancelled_snapshot` — cancel transitions to `CANCELLED`
2. `test_cancel_execution_raises_not_found` — missing execution raises `ExecutionNotFound`
3. `test_cancel_execution_denial_authorizes_first_and_accesses_nothing_else` — denial skips orchestrator
