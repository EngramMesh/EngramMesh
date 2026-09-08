# RFC: Execution List API with Snapshot Projection

- **Status**: Implemented
- **Date**: 2026-09-07
- **Type**: HTTP API / projection slice summary
- **Authority**: `docs/superpowers/specs/2026-09-07-execution-list-api-design.md`
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Execution snapshot store (④b), Temporal runtime adapter (④), Runtime outbox (④c)

## Summary

Delivers `GET /v1/tenants/{tenant_id}/executions` backed by a unified PostgreSQL
snapshot projection. Temporal activities and orchestrator start upsert into
`runtime_execution_snapshots`; list reads use `ExecutionSnapshotStore.stream()`.
Single-execution reads remain on `GET /executions/{id}` via `OrchestratorPort`.

## Follow-up

- ⑤ Claim extraction
