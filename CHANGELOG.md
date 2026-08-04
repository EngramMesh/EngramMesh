# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to
Semantic Versioning after its first public release.

## [Unreleased]

### Added

- Initial production architecture and open-source governance baseline.
- Python 3.14 services architecture scaffold: shared kernel, cognitive memory
  and durable runtime domain contracts, async ports, typed configuration
  boundary, JSON Schema event contracts, and architecture dependency tests.
- Episode ingest application slice: `RecordEpisodeHandler` with authorization,
  idempotency, atomic Episode/Outbox commit, and `memory.episode-recorded`
  event publication.
- Transactional in-memory memory adapter with reusable
  `EPISODE_ADAPTER_CONTRACTS` and capability-profile contract coverage.
- PostgreSQL Episode adapter: versioned SQL migrations, psycopg3 async pool,
  transactional `PostgresMemoryUnitOfWork`, portable `EPISODE_ADAPTER_CONTRACTS`
  binding, `POSTGRES_EPISODE_CAPABILITY_CONTRACTS`, integration coverage for
  tenant isolation and transaction failures, and CI workflow against PostgreSQL
  16. Import from `engrammesh.modules.memory.adapters.postgres`; the top-level
  `adapters` package exports only the in-memory adapter.
- Bilingual services architecture and Episode ingest guides (`services/README.md`,
  `services/README.zh-CN.md`).
- Composition root (`bootstrap/composition.py`, `bootstrap/infrastructure.py`):
  `load_settings`, `AppRuntime`, `create_runtime`, environment-gated authorization,
  PostgreSQL wiring and pool lifecycle, and composed Episode ingest integration
  coverage.
- Outbox Relay application slice: `RelayOutboxEventsHandler`,
  `PostgresOutboxRelayStore`, `LoggingOutboxEventPublisher`, partial index
  migration, `AppRuntime.relay_outbox_once` / `run_outbox_relay_loop`, composed
  relay integration coverage, and bilingual services documentation for relay
  semantics (`OutboxPort` vs `OutboxEventPublisher`, at-least-once delivery).
- Episode ingest HTTP API: FastAPI control API (`bootstrap/http/`,
  `bootstrap/server.py`) with `POST /v1/tenants/{tenant_id}/episodes`,
  `GET /health`, `GET /ready`, structured error envelopes (403 / 409 / 422 /
  503 / 500), stable `/ready` reason codes, `record-episode-request.schema.json`,
  HTTP scope vs Outbox event scope separation, unit and integration tests, and
  bilingual services documentation (endpoints, errors, staging/production write
  restriction, `curl` example, server start command).
- Inbox consumer and `memory.episode-recorded` processor: `InboxStore` with
  `event_id` deduplication, `ProcessInboxEventHandler`, `EpisodeRecordedProcessor`,
  `InboxOutboxEventPublisher`, migration `003_inbox_events.sql`,
  `inbox.enabled` rollback switch, composed record→relay→inbox integration
  coverage, and bilingual services documentation (delegate vs inbox authority,
  v1 single-consumer `event_id` primary key).
- Episode read HTTP API: `GET /v1/tenants/{tenant_id}/episodes/{episode_id}` and
  `GET /v1/tenants/{tenant_id}/episodes` with keyset cursor pagination,
  `GetEpisodeHandler` / `ListEpisodesHandler`, response JSON Schemas, and
  integration coverage.
- OIDC tenant context: Bearer JWT on episode routes when `oidc.enabled=true`,
  `StaticDevTokenVerifier` and `JwksTokenVerifier`, `TenantScopedMemoryAuthorization`,
  principal-aware HTTP mappers, `record-episode-request` schema v1.1.0 (optional
  `actor_id`), integration and PostgreSQL E2E coverage, and bilingual services
  documentation for OIDC settings and error codes.
- Temporal runtime adapter: `InMemoryOrchestratorPort` and `TemporalOrchestratorPort`
  with shared `ExecutionIndex`, `StartExecutionHandler` / `GetExecutionSnapshotHandler`
  / `CancelExecutionHandler`, lifecycle workflow and worker entry point
  (`bootstrap/worker.py`), contract and integration coverage (including
  `@pytest.mark.temporal`), and bilingual services documentation for runtime
  enablement and Temporal settings.

### Changed

- Root README status reflects the delivered scaffold and Episode ingest slice
  rather than an empty repository.

### Fixed

- Episode ingest semantics: exact idempotency replay, final commit behavior,
  Outbox aggregate integrity, and UTC timestamp canonicalization.
- Architecture scaffold hardening: module domain boundaries, configuration
  secret redaction, strict TLS validation, event parity, and malformed DSN
  rejection.

### Chore

- Ignore macOS `.DS_Store` and Python bytecode caches in `.gitignore`.
