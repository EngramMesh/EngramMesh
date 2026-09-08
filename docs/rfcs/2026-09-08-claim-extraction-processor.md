# RFC: Claim Extraction Processor (Phase 2 entry)

- **Status**: Implemented
- **Date**: 2026-09-08
- **Type**: Application / storage interface
- **Authority**: `docs/superpowers/specs/2026-09-08-claim-extraction-processor-design.md`
- **Related roadmap**: Phase 2 — episodic and semantic long-term memory
- **Prerequisites**: Episode ingest, Outbox Relay, Inbox consumer (`EpisodeRecordedProcessor`)

## Summary

Extends inbox processing for `memory.episode-recorded` events to extract deterministic
claim proposals and persist them in PostgreSQL `memory_claim_proposals`. Introduces
`DeterministicMemoryExtractor`, `ExtractClaimsFromEpisodeHandler`, and
`ClaimExtractionSettings` with `claim_extraction.enabled` rollback switch.

## Non-goals

- LLM, Model Gateway, or prompt-based extraction
- Artifact content fetch or object-storage reads (episodes remain reference-only)
- Claim read HTTP APIs, semantic search, vector/graph projections
- Entity resolution, reranking, admission workflow (`ACCEPTED` / dispute lifecycle)
- Runtime Inbox consumer for `runtime.execution-status-changed` (future slice)
- New outbox event types (`memory.claim-proposed`) — deferred to a follow-up slice
- Kafka/Redpanda, multi-consumer `SKIP LOCKED`, or inbox schema changes
- Changing `RecordEpisodeHandler` or episode ingest HTTP semantics

## Follow-up

- `memory.claim-proposed` outbox events
- LLM-backed `MemoryExtractorPort` adapter
- Claim read HTTP API
