# RFC: Runtime Outbox and Execution Lifecycle Events

- **Status**: Implemented
- **Date**: 2026-09-07
- **Type**: Storage interface / application slice summary
- **Authority**: `docs/superpowers/specs/2026-09-07-runtime-outbox-design.md`
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Temporal runtime adapter (④), Execution HTTP API (④a), Execution snapshot store (④b)

## 1. Background

Memory events flow through a transactional Outbox, Outbox Relay, and optional Inbox
consumer. Runtime execution status changes were observable only via polling
`GET /executions/{id}` or Temporal workflow queries. Phase 1 item **④c** adds a
durable, relayable `runtime.execution-status-changed` event stream.

## 2. Goals

1. Publish `runtime.execution-status-changed` atomically with committed runtime
   state writes on the PostgreSQL path.
2. `runtime_outbox_events` table with versioned SQL migrations (shared DSN).
3. `RuntimeOutboxPort`, `RuntimeOutboxRelayStore`, `RuntimeOutboxEventPublisher`,
   and `RelayRuntimeOutboxEventsHandler` mirroring memory Outbox Relay semantics.
4. Emit from `InMemoryOrchestratorPort` (start/cancel) and Temporal lifecycle
   activities plus `apply_execution_cancel`.
5. Composition root wiring, contract/postgres/temporal tests, architecture import
   boundaries, and bilingual services documentation.

## 3. Non-goals

- Runtime Inbox consumer or Claim extraction (Phase 2)
- External broker adapters beyond the logging test publisher
- Handler, HTTP, or `OrchestratorPort` public semantic changes

## 4. Design summary

```text
OrchestratorPort / Temporal activities
  → status transition committed
  → RuntimeOutboxPort.publish(EventEnvelope)
  → runtime_outbox_events (PostgreSQL)

RelayRuntimeOutboxEventsHandler
  → RuntimeOutboxRelayStore.fetch_unpublished
  → RuntimeOutboxEventPublisher.publish
  → RuntimeOutboxRelayStore.mark_published

AppRuntime
  → relay_runtime_outbox_once()
  → run_runtime_outbox_relay_loop()
```

| Path | Emission |
|------|----------|
| InMemory `start` (new) | 1 event (`null → pending`) |
| InMemory `start` (idempotent replay) | 0 |
| InMemory `cancel` | 1–2 events |
| Temporal lifecycle | 3 events (`planning → running → succeeded`) |
| Temporal cancel | 1–2 events |

**Naming:** `RuntimeOutboxPort.publish` (transactional write) and
`RuntimeOutboxEventPublisher.publish` (relay dispatch) are distinct responsibilities.

Relay semantics match memory Outbox Relay: at-least-once delivery, global poll
order `occurred_at ASC, event_id ASC`, `published_at` set only after every
`publish` in the batch succeeds, downstream dedupe by `event_id`.

Event contract: `packages/contracts/jsonschema/runtime/v1/execution-status-changed.schema.json` (v1.0.0).

## 5. Testing

- `RUNTIME_OUTBOX_CONTRACTS` (in-memory + postgres bindings)
- `@pytest.mark.postgres` composed start/cancel relay, restart, mid-batch failure
- `@pytest.mark.temporal` lifecycle and cancel outbox writer tests
- Architecture: `psycopg` confined to `modules/runtime/adapters/postgres/`
- JSON Schema round-trip for `build_execution_status_changed_event(...)`

## 6. Acceptance

See spec §13.

## 7. Follow-up

```text
④b Execution snapshot store (PostgreSQL)           ✅
④c Runtime Outbox + execution lifecycle events     ✅
④d Execution list HTTP API                         ✅ (see `docs/rfcs/2026-09-07-execution-list-api.md`)
④e Temporal snapshot projection to PostgreSQL      ✅ (see `docs/rfcs/2026-09-07-execution-list-api.md`)
⑤ Runtime Inbox consumer + Claim extraction        ← Phase 2 entry
```
