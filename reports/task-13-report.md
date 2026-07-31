# Task 13 Report: Documentation and RFC

## Summary

Added the Temporal runtime adapter RFC and bilingual Runtime execution documentation to `services/README.md` and `services/README.zh-CN.md`. Updated purpose/non-goals and module tree to reflect the delivered runtime slice.

## Changes

| File | Purpose |
|------|---------|
| `docs/rfcs/2026-07-31-temporal-runtime-adapter.md` | RFC summary linking to design spec; enablement matrix, workflow ID, testing, follow-ups ④a/④b |
| `services/README.md` | Runtime execution slice section (handlers, ExecutionIndex, workflow ID, enablement matrix, in-memory vs Temporal, worker startup, temporal tests, non-goals) |
| `services/README.zh-CN.md` | Chinese equivalent of Runtime section |

## Documentation highlights

- **Handlers:** `StartExecutionHandler`, `GetExecutionSnapshotHandler`, `CancelExecutionHandler` via `AppRuntime` accessors.
- **ExecutionIndex:** singleton `InMemoryRuntimeDatabase` for `(tenant_id, idempotency_key) → execution_id`.
- **Workflow ID:** `{tenant_id}:{execution_id}`; `created` inferred by `snapshot.execution_id ==` newly generated id.
- **Enablement matrix:** `runtime_enabled` × `temporal.enabled` (spec §7.1).
- **Worker:** `python -m engrammesh.bootstrap.worker` (separate from HTTP).
- **Temporal tests:** `pytest services/tests -m temporal -q` (default CI excludes via `addopts`).
- **Non-goals:** execution HTTP API (④a), PostgreSQL snapshot store (④b).

## Verification

```bash
uv run --python 3.14 --project services pytest services/tests -q          # 636 passed
uv run --python 3.14 --project services pytest services/tests -m temporal -q  # 4 passed
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
```

All checks passed.
