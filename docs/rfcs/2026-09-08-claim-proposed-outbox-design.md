# Design: memory.claim-proposed Outbox Events

- **Status**: Draft
- **Date**: 2026-09-08
- **Type**: Application / event contract
- **Related roadmap**: Phase 2 — episodic and semantic long-term memory (⑥)
- **Prerequisites**: Claim extraction processor (⑤), Outbox Relay, Inbox consumer
- **Authority for prior slice**: `docs/rfcs/2026-09-08-claim-extraction-processor-design.md`

## 1. Problem

Slice ⑤ persists claim proposals in `memory_claim_proposals` when
`ExtractClaimsFromEpisodeHandler` processes `memory.episode-recorded` inbox events,
but emits **no outbox event**. Downstream consumers (Qdrant projection, admission
workflows, cross-module integrations) cannot observe new proposals without polling
PostgreSQL.

Phase 2 item **⑥** closes this gap: after a **new** proposal is persisted,
emit `memory.claim-proposed` through the existing memory outbox in the **same
transaction**, then relay via the unchanged `RelayOutboxEventsHandler`.

## 2. Goals

1. Define JSON Schema v1 for `memory.claim-proposed` at
   `packages/contracts/jsonschema/memory/v1/claim-proposed.schema.json`.
2. Extend `ExtractClaimsFromEpisodeHandler` to publish outbox events atomically
   with claim persistence.
3. Return `AddProposalResult(created: bool)` from `ClaimStore.add_proposal` so
   the handler can skip outbox publish on idempotent replay.
4. Extend PostgreSQL outbox validation for `memory.claim-proposed` aggregate
   integrity (mirror `memory.episode-recorded` pattern).
5. Contract tests, unit tests, postgres integration tests, and bilingual README
   updates documenting the new event type.

## 3. Non-goals

- Claim read HTTP API
- LLM extraction or Model Gateway
- Kafka, inbox schema changes, or new relay mechanics
- Consumers that **process** `memory.claim-proposed` (projection workers are follow-up)
- Changing `RecordEpisodeHandler` or episode ingest HTTP semantics
- Admission workflow (`ACCEPTED` / dispute lifecycle)

## 4. Design decisions

### 4.1 Emit in extraction transaction (recommended)

`ExtractClaimsFromEpisodeHandler` already opens a unit of work for claim
persistence. Publish the outbox event in that same transaction before `commit()`.

Alternatives rejected:

| Alternative | Why rejected |
|---|---|
| Separate UoW after extraction | Two transactions; claim could exist without event on partial failure |
| Synchronous publish in relay path | Violates outbox pattern; no durability guarantee |
| Polling `memory_claim_proposals` | Bypasses outbox; couples consumers to table schema |

### 4.2 Outbox only on `created=True`

`add_proposal` uses `INSERT ... ON CONFLICT DO NOTHING` on
`(tenant_id, episode_id, extractor_version)`. Change the port signature to return
`AddProposalResult(created: bool)`:

- `created=True` → publish `memory.claim-proposed`
- `created=False` → silent skip (idempotent inbox replay)

This mirrors `RecordEpisodeHandler` + `AppendResult.created`.

### 4.3 Event envelope fields

| Field | Value |
|---|---|
| `event_type` | `"memory.claim-proposed"` |
| `schema_version` | `1` |
| `tenant_id` | `claim.scope.tenant_id` |
| `aggregate_id` | `claim.id` (claim_id) |
| `aggregate_version` | `1` |
| `correlation_id` | propagated from triggering `memory.episode-recorded` event |
| `causation_id` | `event_id` of triggering `memory.episode-recorded` event |
| `occurred_at` | `claim.recorded_from` (canonical UTC) |
| `event_id` | `await identities.new_event_id()` before publish (same as `RecordEpisodeHandler`) |

### 4.4 JSON Schema (full envelope)

File: `packages/contracts/jsonschema/memory/v1/claim-proposed.schema.json`

Structure mirrors `episode-recorded.schema.json`: full envelope with top-level
`event_id`, `event_type` const `"memory.claim-proposed"`, `schema_version` const
`1`, and `payload` `$ref`. Register in contract test `SCHEMA_PATHS` alongside
`episode-recorded.schema.json`.

### 4.5 Payload shape (v1)

Scope in payload follows `episode-recorded` convention: **no `tenant_id` inside
`scope`** (tenant is on the envelope).

```json
{
  "claim_id": "<uuid>",
  "episode_id": "<uuid>",
  "scope": {
    "subject_id": "<uuid>",
    "workspace_id": "<string|null>",
    "agent_id": "<uuid|null>"
  },
  "subject": "<string>",
  "predicate": "<string>",
  "object_value": "<string>",
  "polarity": true,
  "epistemic_kind": "extracted",
  "confidence": 1.0,
  "valid_from": "<iso8601>",
  "valid_to": null,
  "recorded_from": "<iso8601>",
  "status": "proposed",
  "extractor_version": "deterministic-v1",
  "evidence": [
    {
      "episode_id": "<uuid>",
      "source_span": "metadata",
      "extractor_version": "deterministic-v1"
    }
  ]
}
```

`recorded_to` is omitted (always null at proposal time). `model_ref` and
`prompt_version` are omitted when null (deterministic extractor).

### 4.6 Outbox aggregate validation

Extend `_PostgresOutboxPort.publish` and `_InMemoryOutbox.publish`:

- For `memory.claim-proposed`, verify `aggregate_id` (claim_id) exists in
  `memory_claim_proposals` / in-memory claim store with matching `tenant_id`.
- PostgreSQL query: `WHERE tenant_id = %(tenant_id)s AND claim_id = %(aggregate_id)s`.
- Reuse error messages pattern: `_EVENT_AGGREGATE_UNKNOWN`, `_EVENT_TENANT_MISMATCH`.

### 4.7 Payload builder location

Add `claim_proposed_payload(claim: Claim, *, episode_id: MemoryId) -> dict`
in application layer (`extract_claims_from_episode.py` or a small
`claim_proposed_event.py` helper) — **not** in adapters. Keeps domain/application
free of adapter imports; handler constructs `EventEnvelope`.

## 5. Architecture

```text
ExtractClaimsFromEpisodeHandler.handle(episode_recorded_event)
  → unit_of_work.episodes.get(...)
  → proposals = extractor.propose(episode)
  → for each proposal:
      → claim = replace(proposal.claim, id=await identities.new_memory_id())
      → result = unit_of_work.claims.add_proposal(ClaimProposal(claim=claim))
      → if result.created:
          → event_id = await identities.new_event_id()
          → unit_of_work.outbox.publish(memory.claim-proposed envelope)
            (correlation_id=event.correlation_id, causation_id=event.event_id)
  → unit_of_work.commit()

RelayOutboxEventsHandler (unchanged)
  → publishes to LoggingOutboxEventPublisher / future Kafka
```

Module boundaries unchanged: domain/application must not import adapters.

## 6. Port changes

```python
@dataclass(frozen=True, slots=True)
class AddProposalResult:
    claim_id: MemoryId
    created: bool
```

`ClaimStore.add_proposal` returns `AddProposalResult` instead of `None`.

Update implementations:

| Adapter | Behavior |
|---|---|
| PostgreSQL | `INSERT ... RETURNING claim_id`; on conflict `SELECT claim_id` for existing row → `created=False` with canonical `claim_id` |
| In-memory unavailable | unchanged `NotImplementedError` |
| Test fakes | return `AddProposalResult(claim_id=..., created=True/False)` |

On `created=False`, `claim_id` must be the **persisted** canonical ID (mirror
`AppendResult.episode_id` on idempotent replay), not the attempted new ID.

Update `CLAIM_ADAPTER_CONTRACTS.add_proposal_idempotent` to assert
`created=False` and unchanged canonical `claim_id`.

## 7. Testing

| Layer | Test |
|---|---|
| Contract | `claim-proposed.schema.json` validates sample envelope |
| Unit | `ExtractClaimsFromEpisodeHandler` publishes outbox when `created=True` |
| Unit | Handler skips outbox when `created=False` |
| Unit | `claim_proposed_payload` shape matches schema |
| Integration | postgres: record → relay → inbox → 1 claim + 1 unpublished `memory.claim-proposed` outbox row (`published_at IS NULL`); second relay publishes it |
| Integration | postgres: duplicate inbox → 1 claim, 1 `memory.claim-proposed` outbox row (no duplicate) |
| Regression | `claim_extraction.enabled=false` → no outbox claim-proposed events |

## 8. Documentation

- RFC summary: `docs/rfcs/2026-09-08-claim-proposed-outbox.md`
- Update `services/README.md` and `services/README.zh-CN.md` Outbox section with
  `memory.claim-proposed` event type and flow diagram extension.
- Update claim extraction processor RFC follow-up to mark ⑥ as in progress.

## 9. Acceptance criteria

1. `uv run --python 3.14 --project services pytest services/tests -q` passes.
2. `uv run --python 3.14 --project services ruff check services/src services/tests` passes.
3. `uv run --python 3.14 --project services mypy services/src` passes.
4. JSON Schema contract at `packages/contracts/jsonschema/memory/v1/claim-proposed.schema.json`.
5. PostgreSQL integration proves one `memory.claim-proposed` outbox row per new claim.
6. Idempotent `add_proposal` does not emit duplicate outbox events.
7. Bilingual README documents the new event type and explicitly lists non-goals.

## 10. Follow-up (out of scope)

```text
⑥ memory.claim-proposed outbox events     ← this slice
⑦ LLM-backed MemoryExtractorPort adapter
⑧ Claim read HTTP API
⑨ Runtime execution-status-changed consumer
⑩ Qdrant claim projection worker
```
