# RFC: Execution Snapshot Store (PostgreSQL)

- **Status**: Implemented
- **Date**: 2026-08-04
- **Type**: Storage / adapter summary
- **Authority**: `docs/superpowers/specs/2026-08-04-execution-snapshot-store-design.md`
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Temporal runtime adapter, Execution HTTP API

## 1. Background

`InMemoryRuntimeDatabase` (`ExecutionIndex`) is process-local. Restarts lose start
idempotency and in-memory orchestrator snapshots. Phase 1 item **④b** introduces a
PostgreSQL-backed `RuntimeDatabasePort` as the durable replacement.

## 2. Goals

1. `RuntimeDatabasePort` with existing `read` / `write` callback semantics.
2. `PostgresRuntimeDatabase` with versioned SQL migrations (shared DSN with memory).
3. Idempotency + fingerprints for **both** orchestrators; full snapshots when
   `temporal.enabled=false`.
4. Contract tests + postgres integration tests.
5. Composition-root wiring and bilingual documentation.

## 3. Non-goals

- Execution list HTTP API (④d)
- Temporal → PostgreSQL snapshot projection (④e)
- Handler, HTTP, or `OrchestratorPort` semantic changes

## 4. Design summary

```text
OrchestratorPort (InMemory | Temporal)
  → RuntimeDatabasePort
      ├── InMemoryRuntimeDatabase   (unit tests)
      └── PostgresRuntimeDatabase   (production; shared postgres.dsn)
```

| `temporal.enabled` | PG stores | Snapshot authority |
|--------------------|-----------|-------------------|
| `false` | idempotency + fingerprints + snapshots | PostgreSQL |
| `true` | idempotency + fingerprints | Temporal workflow query |

Tables: `runtime_start_idempotency`, `runtime_execution_snapshots` (JSONB via shared
`snapshot_codec`; scope columns for future list API). `CommittedRuntimeState` lives in
`modules/runtime/runtime_state.py`. Postgres and Temporal adapters share the codec;
Postgres does not import Temporal.

## 5. Testing

- `RUNTIME_DATABASE_CONTRACTS` (in-memory + postgres bindings)
- `@pytest.mark.postgres` handler E2E with adapter restart
- Temporal orchestrator + Postgres: idempotency rows only (no snapshot table writes)
- Architecture: `psycopg` confined to `adapters/postgres/`; no postgres→temporal imports

## 6. Acceptance

See spec §9.

## 7. Follow-up

```text
④b Execution snapshot store (PostgreSQL)      ✅
④c Runtime Outbox + execution lifecycle events   ✅
④d Execution list HTTP API
④e Temporal snapshot projection to PostgreSQL
⑤ Claim extraction processor                  ← Phase 2 entry
```
