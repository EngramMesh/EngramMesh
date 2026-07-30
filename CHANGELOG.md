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
