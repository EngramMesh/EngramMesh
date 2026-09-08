# Design: Claim Extraction Processor (Phase 2 entry)

- **Status**: Draft
- **Date**: 2026-09-08
- **Type**: Application / storage interface
- **Related RFC follow-up**: ⑤ Claim extraction processor (Phase 2 entry)
- **Related roadmap**: Phase 2 — episodic and semantic long-term memory
- **Prerequisites**: Episode ingest, PostgreSQL memory adapter, Outbox Relay, Inbox consumer (`EpisodeRecordedProcessor`)
- **Event contract**: `packages/contracts/jsonschema/memory/v1/episode-recorded.schema.json` (v1.0.0)

## 1. Problem

EngramMesh closes the Phase 1 write path through `RecordEpisodeHandler`, transactional
Outbox, Outbox Relay, and `EpisodeRecordedProcessor` structural validation. The domain
already models bitemporal `Claim` values, `ClaimProposal`, and `MemoryExtractorPort`,
but:

1. `ClaimStore` is explicitly unavailable in both in-memory and PostgreSQL adapters.
2. No `MemoryExtractorPort` implementation exists.
3. Inbox processing validates `memory.episode-recorded` events without persisting
   semantic memory.

Phase 2 requires PostgreSQL as the authority for durable memory facts, including
claims derived from episodes. Item **⑤** is the minimal vertical slice that turns
episode-recorded events into persisted claim proposals without LLM integration,
vector/graph projections, or Claim read APIs.

## 2. Goals

1. Add `ExtractClaimsFromEpisodeHandler` application orchestration: load episode,
   invoke extractor, persist proposals atomically in the same unit of work.
2. Implement `DeterministicMemoryExtractor` (`MemoryExtractorPort`) — rule-based,
   reproducible proposals from episode metadata (no model calls).
3. Implement PostgreSQL `ClaimStore` with versioned SQL migration on the shared
   memory DSN.
4. Extend inbox processing so validated `memory.episode-recorded` events trigger
   claim extraction (same consumer, same dedup semantics).
5. Wire `AppRuntime` composition root, settings (extractor version string),
   contract tests, postgres integration tests, architecture import-boundary tests,
   and bilingual `services/README.md` updates.

## 3. Non-goals

- LLM, Model Gateway, or prompt-based extraction
- Artifact content fetch or object-storage reads (episodes remain reference-only)
- Claim read HTTP APIs, semantic search, vector/graph projections
- Entity resolution, reranking, admission workflow (`ACCEPTED` / dispute lifecycle)
- Runtime Inbox consumer for `runtime.execution-status-changed` (future slice)
- New outbox event types (`memory.claim-proposed`) — deferred to a follow-up slice
- Kafka/Redpanda, multi-consumer `SKIP LOCKED`, or inbox schema changes
- Changing `RecordEpisodeHandler` or episode ingest HTTP semantics

## 4. Design decisions

### 4.1 Extend inbox processor, not parallel consumer (recommended)

Keep a single `InboxEventProcessor` registration for `memory.episode-recorded`.
Refactor `EpisodeRecordedProcessor` to:

1. Run existing structural validation (unchanged rules).
2. Delegate to `ExtractClaimsFromEpisodeHandler.handle(event)`.

Alternatives rejected:

| Alternative | Why rejected |
|---|---|
| Second processor for same `event_type` | `ProcessInboxEventHandler` selects one processor per type |
| Processor chain in `ProcessInboxEventHandler` | Broader refactor outside slice scope |
| Synchronous extraction inside `RecordEpisodeHandler` | Violates event-driven boundary; blocks ingest latency |

### 4.2 Deterministic extractor v1 and claim ID assignment

`DeterministicMemoryExtractor` (`adapters/deterministic/extractor.py`) implements
`MemoryExtractorPort.propose(episode)`:

- Returns exactly **one** `ClaimProposal` per episode.
- Uses a **sentinel claim ID** `MemoryId(UUID(int=0))` as placeholder; the
  handler **must** replace it with `await identities.new_memory_id()` before
  calling `add_proposal`. The extractor never calls `MemoryIdentityPort`.
- Sets `Claim.scope = episode.scope` (full `MemoryScope`, including optional
  `workspace_id` and `agent_id`).
- Builds a subject–predicate–object triple from episode metadata:
  - `subject`: `str(episode.scope.subject_id)`
  - `predicate`: `"observed_content_hash"`
  - `object_value`: `episode.content_hash`
- Sets `epistemic_kind=EXTRACTED`, `status=PROPOSED`, `polarity=True`,
  `confidence=1.0`.
- Bitemporal intervals: `valid_from=episode.observed_at`, `valid_to=None`,
  `recorded_from=episode.ingested_at`, `recorded_to=None`.
- Evidence: one `EvidenceRef` with `episode_id=episode.id`, `source_span="metadata"`,
  `extractor_version` from settings (default `"deterministic-v1"`),
  `model_ref=None`, `prompt_version=None`.

Handler ID assignment flow:

```text
proposals = await extractor.propose(episode)
for proposal in proposals:
    claim = replace(proposal.claim, id=await identities.new_memory_id())
    await unit_of_work.claims.add_proposal(ClaimProposal(claim=claim))
```

This yields testable, idempotent semantics without external I/O.

### 4.3 Idempotency and inbox replay

Inbox dedup by `event_id` ensures extraction runs once per relay delivery.
Additionally, `ClaimStore.add_proposal` must be idempotent for the same
`(tenant_id, episode_id, extractor_version)` tuple so manual inbox replays or
future multi-consumer migrations do not duplicate rows.

Enforce with a unique index:

```text
UNIQUE (tenant_id, episode_id, extractor_version)
```

`add_proposal` uses `INSERT ... ON CONFLICT DO NOTHING` on the unique index.
Conflict is **silent**: no exception, no return value; the first persisted row
wins. Contract tests assert row count unchanged on duplicate `add_proposal`.

### 4.4 Transaction boundary

`ExtractClaimsFromEpisodeHandler` opens a **new** unit of work (separate from
the original episode ingest transaction). Flow:

```text
EpisodeRecordedProcessor.process(event)
  → validate envelope (existing)
  → ExtractClaimsFromEpisodeHandler.handle(event)
      → reconstruct MemoryScope + episode_id from payload
      → unit_of_work.episodes.get(scope, episode_id)
      → if episode missing: raise ValueError (processor failure → inbox remove_record → relay retry)
      → proposals = extractor.propose(episode)
      → assign claim IDs via MemoryIdentityPort (§4.2)
      → for each proposal: unit_of_work.claims.add_proposal(proposal)
      → unit_of_work.commit()
```

Episode must exist before extraction (written in the same relay path prior to
inbox). Missing episode is treated as a **transient** ordering bug in v1;
the processor fails so relay retries. Permanent data loss would poison-retry
until manual intervention — acceptable for v1; a dead-letter path is follow-up.

**Settings interaction:** extraction runs only when `inbox.enabled=true` and
`claim_extraction.enabled=true`. When `inbox.enabled=false`, relay skips inbox
entirely (pre-slice behavior); `claim_extraction.enabled` has no effect.

### 4.5 Adapter capability matrix

| Adapter | Episode store | Claim store | Extraction in inbox |
|---|---|---|---|
| PostgreSQL | durable | **enabled** (this slice) | yes when `inbox.enabled` |
| In-memory | process-local | remains **unavailable** | unit tests mock `ClaimStore` at handler level |

PostgreSQL becomes the reference implementation. In-memory `ClaimStore` stays
unavailable to avoid implying cross-process claim durability. Handler unit tests
use fakes; postgres integration tests cover the full record→relay→inbox→claim
path.

Remove `claims_unavailable` from `POSTGRES_EPISODE_CAPABILITY_CONTRACTS`.
Add new `CLAIM_ADAPTER_CONTRACTS` in `memory_adapter_contract.py`, bound only
to the postgres harness (see §8.1). Delete or rewrite
`test_unit_of_work.py::test_claims_unavailable_matches_in_memory_message`.
Update `test_settings.py::EXPECTED_MODEL_FIELDS` with `claim_extraction` nested
fields on `AppSettings`.

## 5. Architecture

```text
RelayOutboxEventsHandler
  → InboxOutboxEventPublisher
      → ProcessInboxEventHandler
          → EpisodeRecordedProcessor.process(event)
              → structural validation
              → ExtractClaimsFromEpisodeHandler.handle(event)
                  → DeterministicMemoryExtractor.propose(episode)
                  → PostgresClaimStore.add_proposal(...)
          → LoggingOutboxEventPublisher
```

Module boundaries (unchanged rules):

- Domain/application code must not import adapters or third-party packages
- `psycopg` confined to `modules/memory/adapters/postgres/`
- `DeterministicMemoryExtractor` lives at `adapters/deterministic/extractor.py`
- Composition root wiring (see §5.1)

### 5.1 Composition root

`AppRuntime.process_inbox_handler()` constructs:

```python
EpisodeRecordedProcessor(
    extraction=ExtractClaimsFromEpisodeHandler(
        unit_of_work_factory=self._unit_of_work_factory,
        extractor=DeterministicMemoryExtractor(
            extractor_version=self._settings.claim_extraction.extractor_version,
        ),
        identities=UuidMemoryIdentityPort(),
        enabled=self._settings.claim_extraction.enabled,
    ),
)
```

`ExtractClaimsFromEpisodeHandler` constructor:

| Parameter | Type |
|---|---|
| `unit_of_work_factory` | `MemoryUnitOfWorkFactory` |
| `extractor` | `MemoryExtractorPort` |
| `identities` | `MemoryIdentityPort` |
| `enabled` | `bool` |

`EpisodeRecordedProcessor` holds optional `ExtractClaimsFromEpisodeHandler | None`;
when `enabled=false`, only validation runs.

## 6. Storage

### 6.1 Migration `004_claim_proposals.sql`

```sql
CREATE TABLE IF NOT EXISTS memory_claim_proposals (
    tenant_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    episode_id uuid NOT NULL,
    subject_id uuid NOT NULL,
    workspace_id text,
    agent_id uuid,
    subject text NOT NULL,
    predicate text NOT NULL,
    object_value text NOT NULL,
    polarity boolean NOT NULL,
    epistemic_kind text NOT NULL,
    confidence double precision NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    recorded_from timestamptz NOT NULL,
    recorded_to timestamptz,
    status text NOT NULL,
    evidence jsonb NOT NULL,
    extractor_version text NOT NULL,
    PRIMARY KEY (tenant_id, claim_id),
    CONSTRAINT memory_claim_proposals_episode_fkey
        FOREIGN KEY (tenant_id, episode_id)
        REFERENCES memory_episodes (tenant_id, episode_id),
    CONSTRAINT memory_claim_proposals_epistemic_kind_check CHECK (
        epistemic_kind IN ('observed', 'extracted', 'inferred', 'human_confirmed')
    ),
    CONSTRAINT memory_claim_proposals_status_check CHECK (
        status IN ('proposed', 'accepted', 'disputed', 'retracted', 'superseded')
    ),
    CONSTRAINT memory_claim_proposals_confidence_check CHECK (
        confidence >= 0 AND confidence <= 1
    ),
    UNIQUE (tenant_id, episode_id, extractor_version)
);

CREATE INDEX IF NOT EXISTS memory_claim_proposals_scope_recorded_idx
    ON memory_claim_proposals (
        tenant_id,
        subject_id,
        recorded_from DESC,
        claim_id DESC
    );
```

Table stores one row per proposed claim (v1). Status transitions update rows in
place in future slices; v1 only inserts `status='proposed'`.

**Evidence JSONB** — array of objects mirroring `EvidenceRef`:

```json
[{
  "episode_id": "<uuid>",
  "source_span": "metadata",
  "extractor_version": "deterministic-v1",
  "model_ref": null,
  "prompt_version": null
}]
```

### 6.2 Scope reconstruction from event payload

Algorithm (symmetric with `record_episode.py` publish format):

```python
scope = MemoryScope(
    tenant_id=event.tenant_id,
    subject_id=SubjectId(UUID(payload["scope"]["subject_id"])),
    workspace_id=payload["scope"].get("workspace_id"),
    agent_id=(
        AgentInstanceId(UUID(payload["scope"]["agent_id"]))
        if payload["scope"].get("agent_id") is not None
        else None
    ),
)
episode_id = MemoryId(UUID(payload["episode_id"]))
```

Reject `tenant_id` inside `payload.scope` (existing `EpisodeRecordedProcessor`
invariant). `episodes.get(scope, episode_id)` uses `IS NOT DISTINCT FROM` for
optional scope columns — reconstruction must match ingest scope exactly.

### 6.3 ClaimStore read semantics (v1)

**`add_proposal(proposal)`** — insert row mapped from `Claim` + `episode_id`
derived from `proposal.claim.evidence[0].episode_id`. Silent no-op on unique
conflict (§4.3).

**`current(query)`** — return proposed claims in scope:

| Filter | Rule |
|---|---|
| Scope | `tenant_id`, `subject_id` match; `workspace_id` and `agent_id` use `IS NOT DISTINCT FROM` |
| Status | `status = 'proposed'` |
| Recorded interval | `recorded_to IS NULL` |
| `text` | **ignored** in v1 |
| `valid_at`, `recorded_at` | **ignored** in v1 |
| Order | `recorded_from DESC`, `claim_id DESC` |
| Limit | `query.limit` (default 10) |

**`history(scope, claim_id)`** — return all rows for `(tenant_id, claim_id)`
where scope columns match. v1 has at most one row per `claim_id`; returns
`(claim,)` or `()` if not found or scope mismatch.

## 7. Configuration

```python
class ClaimExtractionSettings:
    enabled: bool = True
    extractor_version: str = "deterministic-v1"
```

| Environment variable | Default |
|---|---|
| `ENGRAMMESH__CLAIM_EXTRACTION__ENABLED` | `true` |
| `ENGRAMMESH__CLAIM_EXTRACTION__EXTRACTOR_VERSION` | `deterministic-v1` |

When `claim_extraction.enabled=false`, `EpisodeRecordedProcessor` performs
validation only (rollback switch matching pre-slice behavior).

Add `claim_extraction: ClaimExtractionSettings` to `AppSettings` in
`bootstrap/settings.py` (existing Pydantic boundary).

## 8. Testing

| Layer | Coverage |
|---|---|
| Unit | `DeterministicMemoryExtractor` proposal shape and invariants |
| Unit | `ExtractClaimsFromEpisodeHandler` — missing episode, happy path with fake ports |
| Unit | `EpisodeRecordedProcessor` — extraction skipped when disabled |
| Contract | `CLAIM_ADAPTER_CONTRACTS` on postgres harness (§8.1) |
| Integration | postgres: record → relay → inbox → row in `memory_claim_proposals` |
| Integration | postgres: duplicate inbox delivery does not duplicate claims |
| Architecture | existing import-boundary scans pass; no domain→adapter leaks |
| Regression | `claim_extraction.enabled=false` preserves validation-only inbox |

Existing `assert_claim_operations_are_unavailable` remains for **in-memory**
capability contracts only.

### 8.1 `CLAIM_ADAPTER_CONTRACTS` assertions

Add to `memory_adapter_contract.py` and bind in
`test_postgres_claim_adapter_contract.py`:

| Name | Assertion |
|---|---|
| `add_proposal_persists` | After `add_proposal`, `current` returns the claim in scope |
| `add_proposal_idempotent` | Second `add_proposal` with same `(episode_id, extractor_version)` leaves row count unchanged |
| `current_respects_limit` | Three proposals in scope; `current(limit=2)` returns 2 newest by `recorded_from` |
| `history_returns_claim` | `history(scope, claim_id)` returns the persisted claim |
| `history_scope_mismatch` | `history` with wrong `subject_id` returns empty tuple |

## 9. Documentation

- Update `services/README.md` and `services/README.zh-CN.md` Inbox section with
  claim extraction flow, settings table, and migration `004`.
- Add RFC summary at `docs/rfcs/2026-09-08-claim-extraction-processor.md`
  pointing to `docs/rfcs/2026-09-08-claim-extraction-processor-design.md` as authority.

## 10. Acceptance criteria

1. `uv run --python 3.14 --project services pytest services/tests -q` passes.
2. `uv run --python 3.14 --project services ruff check services/src services/tests` passes.
3. `uv run --python 3.14 --project services mypy services/src` passes.
4. PostgreSQL integration test proves one claim proposal per new episode after
   relay + inbox.
5. `CLAIM_ADAPTER_CONTRACTS` pass on postgres harness (§8.1).
6. Idempotent `add_proposal` for same `(tenant_id, episode_id, extractor_version)`.
7. `claim_extraction.enabled=false` disables extraction without breaking inbox
   validation.
8. Bilingual README and RFC summary (`docs/rfcs/2026-09-08-claim-extraction-processor.md`)
   document the slice and explicitly list non-goals above.
9. `test_settings.py` includes `claim_extraction` in `EXPECTED_MODEL_FIELDS`.

## 11. Follow-up (out of scope)

```text
⑤ Claim extraction processor (deterministic)     ← this slice
⑥ memory.claim-proposed outbox events
⑦ LLM-backed MemoryExtractorPort adapter
⑧ Claim read HTTP API
⑨ Runtime execution-status-changed consumer
```
