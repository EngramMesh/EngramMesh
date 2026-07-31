# RFC: Inbox Consumer and episode-recorded Processor

- **Status**: Approved
- **Date**: 2026-07-31
- **Type**: Application / storage interface
- **Authority**: `docs/superpowers/specs/2026-07-31-inbox-episode-recorded-consumer-design.md` (this RFC is a summary; the spec is the single source of truth)
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Episode ingest, PostgreSQL adapter, Outbox Relay, Episode Ingest HTTP API

## 1. Background

EngramMesh closes the write path through `RecordEpisodeHandler`, transactional Outbox,
and `RelayOutboxEventsHandler`. Relay dispatch uses `OutboxEventPublisher`, which today
is an in-process `LoggingOutboxEventPublisher` for tests. Downstream consumers have no
durable deduplication boundary yet.

This slice adds the first Inbox consumer and an `memory.episode-recorded` processor to
close the Phase 1 event loop without vector/graph projections.

## 2. Goals

1. `InboxStore` with `event_id` deduplication for at-least-once relay delivery.
2. `ProcessInboxEventHandler` routing supported events to pluggable processors.
3. `EpisodeRecordedProcessor` validating `memory.episode-recorded` v1 structural invariants.
4. Inbox-aware `OutboxEventPublisher` when inbox is enabled.
5. PostgreSQL migration, tests, and bilingual services documentation.

## 3. Non-goals

- Projections, Claim extraction, Kafka, inbox HTTP API, multi-consumer `SKIP LOCKED`
- Full JSON Schema validation (enums, datetime regex) in v1

## 4. Design summary

### 4.1 Flow

```text
Relay → InboxOutboxEventPublisher
          → ProcessInboxEventHandler (dedup + validate)
          → LoggingOutboxEventPublisher (test visibility)
        → mark_published
```

### 4.2 Dedup

- Primary key: `event_id` (v1 single consumer per database).
- Processor failure after record: `remove_record`, relay retries.
- Unsupported `event_type`: skip without inbox write.
- Logging delegate always runs; `memory_inbox_events` is the processed authority.

### 4.3 Storage

Migration `003_inbox_events.sql` — see spec for full DDL and index.

### 4.4 Configuration

`InboxSettings`: `enabled=True`, `consumer_name="episode-recorded-v1"`.

`inbox.enabled=False` restores pre-inbox relay behavior.

### 4.5 Processor (v1)

Structural validation: required fields, `aggregate_id == episode_id`, scope without
`tenant_id`. No projection side effects.

## 5. Testing

- Full `test_memory_ports.py` protocol registration for new ports
- Unit: handler, processor, settings
- Integration: postgres store, composed record→relay→inbox
- Dedup via double `publish` or relay retry after publish failure (not double relay after `mark_published`)
- Regression: `inbox.enabled=False`

## 6. Acceptance

See spec acceptance criteria (7 items).

## 7. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅
③ OIDC tenant context
④ Temporal runtime adapter
```
