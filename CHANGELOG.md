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
- Bilingual services architecture and Episode ingest guides (`services/README.md`,
  `services/README.zh-CN.md`).

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
