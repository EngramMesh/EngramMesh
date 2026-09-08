# RFC: Claim Read HTTP API

- **Status**: Draft
- **Date**: 2026-09-08
- **Type**: Public API / implementation design summary
- **Authority**: `docs/superpowers/specs/2026-09-08-claim-read-http-api-design.md` (spec is source of truth)
- **Related roadmap**: Phase 2 — episodic and semantic long-term memory (⑧)
- **Prerequisites**: Claim extraction processor (⑤), `memory.claim-proposed` outbox (⑥), Episode read HTTP API, OIDC tenant context

## Summary

Adds `GET /v1/tenants/{tenant_id}/claims` and
`GET /v1/tenants/{tenant_id}/claims/{claim_id}` backed by `ClaimStore.stream` and
`ClaimStore.history`. Mirrors episode read patterns: OIDC tenant binding, keyset cursor
pagination (`recorded_from DESC`, `claim_id DESC`), `read_claim` authorization, and
`503 claims_unavailable` when the in-memory claim store is used.

## Non-goals

- Semantic search or vector projections
- Claim correction/deletion or admission workflow
- PostgreSQL RLS
- In-memory claim store

## Follow-up

- Claim correction and soft-deletion lifecycle
- Qdrant claim projection worker
- PostgreSQL row-level security for memory tables
