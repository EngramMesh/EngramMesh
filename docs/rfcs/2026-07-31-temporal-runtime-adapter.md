# RFC: Temporal Runtime Adapter

- **Status**: Approved
- **Date**: 2026-07-31
- **Type**: Application / storage interface
- **Authority**: `docs/superpowers/specs/2026-07-31-temporal-runtime-adapter-design.md` (this RFC is a summary; the spec is the single source of truth)
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Episode ingest, Outbox Relay, Inbox consumer, Episode read HTTP API, OIDC tenant context

## 1. Background

EngramMesh has a tested memory vertical slice but no durable execution layer. `OrchestratorPort`
existed as a contract with no adapter. Phase 1 requires a Temporal-backed execution foundation
before Agent tasks, Claim extraction, or multi-Agent orchestration.

This slice delivers Slice 1 (in-memory `OrchestratorPort` + application handlers) and Slice 2
(Temporal adapter + worker entry) so execution is testable end-to-end without an HTTP surface.

## 2. Goals

1. `InMemoryOrchestratorPort` implementing `OrchestratorPort` with idempotency and legal state transitions.
2. Shared `ExecutionIndex` (`InMemoryRuntimeDatabase`) for `(tenant_id, idempotency_key) → execution_id` lookups used by both adapters.
3. Application handlers: `StartExecutionHandler`, `GetExecutionSnapshotHandler`, `CancelExecutionHandler`.
4. `TemporalOrchestratorPort` with a minimal lifecycle workflow (`PENDING → PLANNING → RUNNING → SUCCEEDED`).
5. Independent worker entry point (`bootstrap/worker.py`).
6. Contract, unit, integration, and `@pytest.mark.temporal` tests.
7. Composition-root wiring with `runtime_enabled` gate and bilingual services documentation.

## 3. Non-goals

- PostgreSQL execution snapshot store / Outbox events (Slice 4 — follow-up ④b)
- LangGraph, PlannerPort, AgentEnginePort, ArtifactStore
- Full Plan DAG execution
- Claim extraction (Phase 2 entry)

## 4. Design summary

### 4.1 Flow

```text
StartExecutionHandler / GetExecutionSnapshotHandler / CancelExecutionHandler
  → RuntimeAuthorizationPort
  → OrchestratorPort
      ├── InMemoryOrchestratorPort      (temporal.enabled=false; full snapshots in ExecutionIndex)
      └── TemporalOrchestratorPort      (temporal.enabled=true; snapshots from Workflow query)
            └── ExecutionIndex          (shared idempotency + execution_id resolution)
  → Temporal Worker (bootstrap/worker.py, separate from HTTP)
```

Temporal SDK is confined to `modules/runtime/adapters/temporal/` and `bootstrap/worker.py`.
Domain and application layers remain framework-neutral. `AppRuntime` owns a **single**
`InMemoryRuntimeDatabase` instance for the process lifetime.

### 4.2 Workflow identity and idempotency

- **Workflow ID:** `{tenant_id}:{execution_id}` — enables `get_snapshot` lookup without a reverse index.
- **Start idempotency:** `ExecutionIndex` maps `(tenant_id, idempotency_key) → execution_id` before
  `start_workflow`. Replay describes the existing workflow instead of starting a new one.
- **`created` inference:** `StartExecutionHandler` sets `created=True` when
  `snapshot.execution_id ==` the newly generated id; idempotent replay returns the stored
  `execution_id` → `created=False`.

### 4.3 OrchestratorPort semantics (summary)

| Operation | Key behavior |
|-----------|--------------|
| `start` | Idempotency on `(tenant_id, idempotency_key)`; fingerprint mismatch → `ExecutionIdempotencyConflict` |
| `get_snapshot` | Tenant-scoped; unknown or scope mismatch → `ExecutionNotFound` |
| `cancel` | Cancel-scoped `idempotency_key`; terminal states return as-is; illegal transition → `InvalidExecutionTransition` |

### 4.4 Enablement matrix (spec §7.1)

| `runtime_enabled` | `temporal.enabled` | Behavior |
|-------------------|-------------------|----------|
| `false` | any | Handlers raise `ConfigurationError(runtime_disabled)` |
| `true` | `false` | `InMemoryOrchestratorPort` (default; CI/dev) |
| `true` | `true` | `TemporalOrchestratorPort`; requires running worker |

### 4.5 Configuration

| Field | Default | Env var |
|-------|---------|---------|
| `modules.runtime_enabled` | `true` | `ENGRAMMESH__MODULES__RUNTIME_ENABLED` |
| `temporal.enabled` | `false` | `ENGRAMMESH__TEMPORAL__ENABLED` |
| `temporal.address` | `localhost:7233` | `ENGRAMMESH__TEMPORAL__ADDRESS` |
| `temporal.namespace` | required | `ENGRAMMESH__TEMPORAL__NAMESPACE` |
| `temporal.task_queue` | required | `ENGRAMMESH__TEMPORAL__TASK_QUEUE` |
| `temporal.tls` | `false` | `ENGRAMMESH__TEMPORAL__TLS` |

### 4.6 Authorization (v1)

`EnvironmentGatedRuntimeAuthorization`: `development` and `test` allow all; `staging` and
`production` deny (mirrors pre-OIDC memory gate). OIDC extension deferred to Slice 3 HTTP work.

## 5. Testing

- `ORCHESTRATOR_PORT_CONTRACTS` reusable assertions (in-memory binding first).
- Unit: state machine, idempotency, authorization, settings, mappers.
- Integration: in-memory handler E2E start → get → cancel.
- `@pytest.mark.temporal`: WorkflowEnvironment time-skipping tests; **excluded from default CI**
  via `addopts = "-m 'not temporal'"` in `services/pyproject.toml`.
- Architecture: `test_temporal_imports.py` — `temporalio` only in `adapters/temporal/` and
  `bootstrap/worker.py`.

Run temporal tests explicitly:

```bash
uv run --python 3.14 --project services pytest services/tests -m temporal -q
```

## 6. Acceptance

See spec acceptance criteria (8 items), including:

1. Default `pytest services/tests` passes (temporal excluded).
2. `pytest services/tests -m temporal` passes when temporalio is available.
3. `ruff` and `mypy` pass.
4. Bilingual services README documents runtime slice.

## 7. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅
③ OIDC tenant context                            ✅
④ Temporal runtime adapter                       ✅
   ④a Execution HTTP API                         ✅
   ④b Execution snapshot store (PostgreSQL)      ← Slice 4; replaces in-process ExecutionIndex
⑤ Claim extraction processor                     ← Phase 2 entry
```
