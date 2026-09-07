# Execution List API with Snapshot Projection

**Status:** Implemented  
**Authority:** [`docs/superpowers/specs/2026-09-07-execution-list-api-design.md`](../superpowers/specs/2026-09-07-execution-list-api-design.md)

## Summary

Delivers `GET /v1/tenants/{tenant_id}/executions` backed by a unified PostgreSQL
snapshot projection. Temporal activities and orchestrator start upsert into
`runtime_execution_snapshots`; list reads use `ExecutionSnapshotStore.stream()`.
Single-execution reads remain on `GET /executions/{id}` via `OrchestratorPort`.

## Follow-up

- ⑤ Claim extraction
