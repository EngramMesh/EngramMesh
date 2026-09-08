# RFC: memory.claim-proposed Outbox Events

- **Status**: Draft
- **Date**: 2026-09-08
- **Type**: Application / event contract
- **Authority**: `docs/rfcs/2026-09-08-claim-proposed-outbox-design.md`
- **Related roadmap**: Phase 2 — episodic and semantic long-term memory (⑥)
- **Prerequisites**: Claim extraction processor (⑤), Outbox Relay

## Summary

After claim extraction persists a new proposal, emit `memory.claim-proposed` via
the memory outbox in the same transaction. Adds JSON Schema v1 contract,
`AddProposalResult` on `ClaimStore.add_proposal`, and outbox aggregate validation.

## Non-goals

- Claim read HTTP API, LLM extraction, Kafka/inbox schema changes
- Downstream consumers of `memory.claim-proposed` (projection workers are follow-up)

## Follow-up

- Qdrant claim projection worker
- Claim read HTTP API
- LLM-backed `MemoryExtractorPort` adapter
