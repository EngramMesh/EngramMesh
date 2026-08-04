# EngramMesh Services Architecture Scaffold

[简体中文](README.zh-CN.md) | English

## Purpose and exact non-goals

This directory contains the tested Python 3.14 architecture scaffold for
EngramMesh services, one tested Episode ingest application slice, and one
tested durable-execution runtime slice. It defines immutable shared identifiers
and event metadata, public memory and durable-runtime contracts, dependency
rules, typed process configuration, a composition root that wires
PostgreSQL-backed memory handlers and runtime orchestration from settings,
versioned JSON Schema event contracts, and transactional in-memory adapters for
test and development use.

It does **not** contain a PostgreSQL execution snapshot store, external event
dispatcher, dependency-injection framework, model or tool integration,
projection pipeline, or deployable product feature. A minimal HTTP control API
exposes Episode ingest, episode read, execution start/snapshot/cancel, health
probes, and optional OIDC Bearer JWT authentication; production hardening
remains follow-up work.
The in-memory adapters are process-local and non-durable. A separate Temporal
worker entry point exists for durable workflow execution when
`temporal.enabled=true`. Passing tests prove the documented application and
architecture contracts; they do not imply that a deployable runtime exists.

## Module tree

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   ├── composition.py    # AppRuntime composition root
│   │   ├── http/             # FastAPI control API (episode, execution, probes)
│   │   ├── infrastructure.py # default clock, identity, and authorization ports
│   │   ├── server.py         # uvicorn entry point
│   │   ├── settings.py       # typed, immutable configuration boundary
│   │   └── worker.py         # Temporal worker entry point
│   ├── modules/
│   │   ├── memory/
│   │   │   ├── adapters/     # in-memory and PostgreSQL transaction adapters
│   │   │   │   ├── in_memory/  # process-local test/development adapter
│   │   │   │   └── postgres/   # durable Episode/Outbox adapter (psycopg)
│   │   │   ├── application/  # framework-neutral Episode ingest orchestration
│   │   │   ├── domain/       # pure cognitive-memory values and invariants
│   │   │   ├── ports.py      # implementation-neutral boundaries
│   │   │   └── public.py     # cross-module public contract
│   │   └── runtime/
│   │       ├── adapters/     # in-memory and Temporal orchestrator adapters
│   │       │   ├── in_memory/  # ExecutionIndex + InMemoryOrchestratorPort
│   │       │   └── temporal/   # TemporalOrchestratorPort, workflow, activities
│   │       ├── application/  # framework-neutral execution orchestration
│   │       ├── domain/       # pure durable-execution values and transitions
│   │       ├── ports.py      # implementation-neutral boundaries
│   │       └── public.py     # cross-module public contract
│   └── shared/kernel/        # shared typed IDs and event envelope
└── tests/
    ├── architecture/         # dependency-policy tests
    ├── contract/             # public, schema, and reusable adapter contracts
    ├── integration/          # application plus concrete adapter tests
    └── unit/                 # invariants, applications, and adapter units

packages/contracts/jsonschema/
├── events/v1/               # generic event envelope
├── memory/v1/               # memory event payloads
└── runtime/v1/              # runtime event payloads
```

## Dependency direction

The shared kernel depends only on the Python standard library. A module domain
may depend on the standard library, the shared kernel, its own domain, and
another module's exact `public.py` contract. It must not import another module's
internals, its own public facade, adapters, or third-party packages. Ports and
public facades point inward to domain contracts. `bootstrap/settings.py` is the
only Pydantic Settings boundary in this scaffold; domain code remains
framework-independent.

```text
bootstrap/configuration       module public contracts
           |                           |
           v                           v
 bootstrap/composition.py -> application services -> ports
                                                 -> domain
                                                    |
                                                    v
                                              shared kernel
```

Future adapters will implement ports and depend inward. Domain and application
code must never depend outward on a concrete adapter.

## Authoritative-state boundaries

- PostgreSQL is the authority for durable memory facts, versioned records,
  append-only events, and durable structured snapshots. The PostgreSQL Episode
  adapter in this slice implements Episode ingest persistence; broader memory
  surfaces and row-level security policies remain follow-up work.
- Temporal Event History is the future authority for execution lifecycle,
  timers, retries, and durable workflow progress.
- Object storage is the future authority for large content addressed by
  immutable references.
- Vector indexes, graph stores, caches, search indexes, and telemetry are
  rebuildable projections or operational signals, never primary authority.
- The general contracts and schemas define stable shapes and invariants. The
  in-memory adapter retains committed Episode and Outbox state only inside one
  process; it does not provide durable authority, dispatch, or projection.

## Third-party adapter policy

PostgreSQL drivers, Temporal SDKs, model providers, tool protocols, object
stores, vector databases, graph databases, and telemetry exporters must be
implemented behind the existing or separately reviewed ports. Vendor types,
clients, exceptions, and retry policies must not leak into domain models or
public module contracts. An adapter owns translation to and from the stable
EngramMesh types, enforces tenant and authorization context, and is tested with
deterministic contract tests. Adding a provider library also requires a concrete
adapter use case; it is not added speculatively.

## Episode ingest slice

`RecordEpisodeHandler` is a framework-neutral application service. It records
one immutable `Episode` by artifact reference after authorization, using
injected clock and identity ports. Concrete persistence implementations are `InMemoryMemoryUnitOfWorkFactory`
(process-local) and `PostgresMemoryUnitOfWorkFactory` (durable PostgreSQL).
Import PostgreSQL types from `engrammesh.modules.memory.adapters.postgres`,
not from the top-level `engrammesh.modules.memory.adapters` package, which
exports only the in-memory adapter.

The slice deliberately excludes dependency-injection framework wiring,
Temporal, object upload, Claim extraction, retrieval, correction and deletion,
projections, and external Outbox dispatch. HTTP transport is provided separately
by `bootstrap/http/`; the in-memory adapter makes no cross-process durability or
delivery guarantee.

## Application flow

```text
RecordEpisodeCommand
  -> authorize(action="record_episode", actor, exact scope, sensitivity)
  -> build Episode with injected time and Memory ID
  -> create MemoryUnitOfWork
      -> EpisodeStore.append
      -> when created: OutboxPort.publish(memory.episode-recorded)
      -> commit
  -> RecordEpisodeResult(episode_id, created)
```

Authorization completes before the transaction opens. Invalid command or domain
values and adapter errors propagate unchanged because transport-specific error
translation is outside this slice. The handler rejects a naive clock value and
canonicalizes both the clock time and command `observed_at` to UTC before
constructing the Episode or event.

## Idempotency and transaction semantics

Idempotency is scoped to `(tenant_id, idempotency_key)`. The first append
returns `created=True`. A collision is an exact replay only when scope, actor,
source type, content reference, observed time, content hash, sensitivity,
retention class, and consent basis all match. Generated Episode ID and
`ingested_at` are excluded from that comparison. `correlation_id` is Outbox
tracing metadata, not an Episode-defining immutable field, so it is also
excluded. An exact replay returns the original Episode ID with `created=False`
and stages no second event; any difference in those compared Episode-defining
fields raises the zero-payload
`EpisodeIdempotencyConflict` without changing state. A different tenant may
reuse the same key.

The in-memory adapter serializes transactions with one process-local lock and
uses copy-on-write state. A successful `commit()` makes the new snapshot final
and globally visible; a later body exception, cancellation, or context exit does
not restore the old state. Exit without `commit()` still discards staged
Episode, idempotency, and Outbox changes.

For `memory.episode-recorded`, Outbox publication requires the aggregate Episode
to be visible in the transaction—whether committed earlier or newly staged—and
requires the envelope tenant to match the Episode tenant. Unknown and
cross-tenant Episode aggregates are rejected. Other event types are outside
this Episode correlation rule. Accepted aware timestamps are serialized in
canonical UTC. These behaviors are an atomic local test/development model, not
a production concurrency, durability, or external-delivery model.

## PostgreSQL Episode adapter

`PostgresMemoryDatabase` and `PostgresMemoryUnitOfWorkFactory` provide a
transaction-scoped Episode store, unavailable Claim store, and Outbox port
backed by versioned SQL migrations and a psycopg3 async connection pool. Only
`engrammesh.modules.memory.adapters.postgres` may import `psycopg`; domain,
application, and port modules remain provider-neutral.

```python
from engrammesh.modules.memory.adapters.postgres import (
    PostgresMemoryDatabase,
    PostgresMemoryUnitOfWorkFactory,
)
```

Portable Episode assertions in `EPISODE_ADAPTER_CONTRACTS` bind through a
PostgreSQL harness without changing the shared assertion bodies. PostgreSQL
capability contracts (`POSTGRES_EPISODE_CAPABILITY_CONTRACTS`) separately
describe unavailable Claim operations and rejected non-`None` stream cursors.

Tenant isolation is enforced in SQL predicates (`tenant_id` on every read and
write). PostgreSQL row-level security (RLS) policies are deferred to a later
production-hardening slice. `PostgresSettings` is read through `AppSettings` and
wired by `bootstrap/composition.py` when memory is enabled.

### Local PostgreSQL tests

Set a DSN and run postgres-marked tests. When `ENGRAMMESH__POSTGRES__DSN` is
unset, `@pytest.mark.postgres` tests skip. Tests that share one database run
serially via the `postgres_serial` xdist group:

```bash
export ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -m postgres -q
```

Run the full services suite (postgres and non-postgres) with the same DSN:

```bash
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -q
```

## Composition root

`bootstrap/composition.py` is the official composition root. It reads typed
`AppSettings`, opens a PostgreSQL connection pool on startup, and returns a
cached `RecordEpisodeHandler` wired to infrastructure ports. Only bootstrap may
import `engrammesh.modules.memory.adapters.postgres` and assemble application
services.

```python
from engrammesh.bootstrap.composition import create_runtime, load_settings
```

`load_settings()` is a thin wrapper around `AppSettings()` for a single
configuration entry point. `create_runtime()` accepts optional settings and
defaults to `load_settings()`; it does not call `startup()` until you use
explicit lifecycle methods or an async context manager.

```bash
export ENGRAMMESH__ENVIRONMENT=test
export ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh
export ENGRAMMESH__TEMPORAL__NAMESPACE=demo
export ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo
PYTHONPATH=services/src PYTHONDONTWRITEBYTECODE=1 \
  uv run --python 3.14 --project services python - <<'PY'
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.bootstrap.composition import create_runtime, load_settings
from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    SubjectId,
    TenantId,
)


async def main() -> None:
    async with create_runtime(load_settings()) as runtime:
        handler = runtime.record_episode_handler()
        command = RecordEpisodeCommand(
            correlation_id=CorrelationId(UUID(int=3)),
            actor_id=SubjectId(UUID(int=4)),
            scope=MemoryScope(
                tenant_id=TenantId(UUID(int=5)),
                subject_id=SubjectId(UUID(int=6)),
                workspace_id="demo",
            ),
            source_type=SourceType.USER,
            content_ref=ArtifactId(UUID(int=7)),
            observed_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
            content_hash="sha256:demo",
            idempotency_key="demo-composed-episode",
            sensitivity=Sensitivity.CONFIDENTIAL,
            retention_class=RetentionClass.STANDARD,
            consent_basis="user_request",
        )
        first = await handler.handle(command)
        replay = await handler.handle(command)
        print(f"first_created={first.created} replay_created={replay.created}")
        print(f"same_id={first.episode_id == replay.episode_id}")


asyncio.run(main())
PY
```

`record_episode_handler()` raises `ConfigurationError` with code
`memory_disabled` when `modules.memory_enabled` is `False`. It raises
`RuntimeError` with message `application runtime is not started` when memory is
enabled but `startup()` has not completed.

## Runtime execution slice

The runtime module provides durable multi-agent execution orchestration through
three application handlers wired by `AppRuntime`:

| Handler | Command / query | Action |
|---------|-----------------|--------|
| `StartExecutionHandler` | `StartExecutionCommand` | Authorize + start execution |
| `GetExecutionSnapshotHandler` | `GetExecutionSnapshotQuery` | Authorize + read snapshot |
| `CancelExecutionHandler` | `CancelExecutionCommand` | Authorize + cancel execution |

Accessors: `start_execution_handler()`, `get_execution_snapshot_handler()`,
`cancel_execution_handler()`. When `modules.runtime_enabled` is `False`, each
raises `ConfigurationError` with code `runtime_disabled`.

### ExecutionIndex and workflow identity

`AppRuntime` owns a **singleton** `InMemoryRuntimeDatabase` (alias
`ExecutionIndex`) for the process lifetime. The index maps
`(tenant_id, idempotency_key) → execution_id` and stores full snapshots when the
in-memory orchestrator is active.

**Workflow ID scheme:** `{tenant_id}:{execution_id}`. Both
`InMemoryOrchestratorPort` and `TemporalOrchestratorPort` use this format.
`get_snapshot` resolves workflows by tenant and execution id without a reverse
index. Start idempotency uses `ExecutionIndex` before `start_workflow`; replay
describes the existing workflow instead of creating a new one.

`StartExecutionHandler` infers `created` by comparing the returned snapshot's
`execution_id` to the newly generated id: first call → `created=True`; exact
idempotent replay returns the stored id → `created=False`.

### Enablement matrix

| `runtime_enabled` | `temporal.enabled` | Orchestrator | Notes |
|-------------------|-------------------|--------------|-------|
| `false` | any | none | Handlers raise `runtime_disabled` |
| `true` | `false` | `InMemoryOrchestratorPort` | Default; CI and local dev |
| `true` | `true` | `TemporalOrchestratorPort` | Requires running Temporal worker |

Memory and runtime startup are independent; runtime handlers can be used when
memory is disabled.

### In-memory vs Temporal

| Concern | `temporal.enabled=false` | `temporal.enabled=true` |
|---------|--------------------------|-------------------------|
| Snapshot authority | `ExecutionIndex` (process-local) | Temporal workflow query `current_snapshot` |
| Durability | None (process-local) | Temporal Event History |
| Worker | Not required | `bootstrap/worker.py` on configured task queue |
| SDK boundary | N/A | `temporalio` only in `adapters/temporal/` and `worker.py` |

`InMemoryOrchestratorPort` implements the full `OrchestratorPort` contract
including idempotency fingerprints, tenant-scoped reads, and cancel state
transitions. `TemporalOrchestratorPort` shares the same `ExecutionIndex` for
start idempotency and delegates lifecycle to `ExecutionLifecycleWorkflow` with
stub activities (`advance_to_planning`, `advance_to_running`,
`advance_to_succeeded`). SDK errors wrap as `OrchestrationUnavailable`.

Portable orchestrator assertions live in `ORCHESTRATOR_PORT_CONTRACTS`
(`tests/contract/orchestrator_adapter_contract.py`); the in-memory adapter
binds first.

### Start the Temporal worker

The worker runs separately from the HTTP server. It requires
`temporal.enabled=true` and a reachable Temporal server:

```bash
export ENGRAMMESH__TEMPORAL__ENABLED=true
export ENGRAMMESH__TEMPORAL__NAMESPACE=demo
export ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo
uv run --python 3.14 --project services \
  python -m engrammesh.bootstrap.worker
```

`worker.py` registers `ExecutionLifecycleWorkflow` and stub activities on the
configured task queue and shuts down gracefully on `SIGINT`/`SIGTERM`.

### Temporal tests

Default pytest excludes temporal-marked tests:

```toml
# services/pyproject.toml
addopts = "-m 'not temporal'"
```

Run temporal integration tests explicitly:

```bash
uv run --python 3.14 --project services pytest services/tests -m temporal -q
```

Temporal tests use `WorkflowEnvironment` time-skipping and prove workflow
completion, idempotent start replay, cancel, and worker-restart recovery.

### Runtime non-goals

This slice deliberately excludes:

- PostgreSQL execution snapshot store and runtime Outbox events (Slice 4 — follow-up ④b)
- LangGraph, PlannerPort, AgentEnginePort, full Plan DAG execution
- Claim extraction (Phase 2)

See `docs/rfcs/2026-07-31-temporal-runtime-adapter.md` and
`docs/superpowers/specs/2026-07-31-temporal-runtime-adapter-design.md`.

## Outbox Relay

`RelayOutboxEventsHandler` polls unpublished rows from `memory_outbox_events`,
dispatches them through `OutboxEventPublisher`, and sets `published_at` only
after every `publish` call in the batch succeeds. `AppRuntime` wires the relay
through `relay_outbox_handler()`, `relay_outbox_once()`, and
`run_outbox_relay_loop()`.

**Naming:** `OutboxPort.publish` (transactional write inside the Episode ingest
transaction) and `OutboxEventPublisher.publish` (relay dispatch outside the
store transaction) are distinct responsibilities. Documentation and code reviews
must keep this distinction explicit.

v1 assumes **one active relay worker per database** (no `SKIP LOCKED`). Rows
are fetched in global order `occurred_at ASC, event_id ASC`. Delivery is
**at-least-once**: if the process crashes after successful `publish` calls but
before `mark_published`, a retry may dispatch the same event again; downstream
consumers must dedupe by `event_id` (see [Inbox Consumer](#inbox-consumer)).
When any `publish`
fails, the handler re-raises immediately and does not call `mark_published`;
callers do not receive a `RelayOutboxResult` on failure. Events successfully
dispatched before the failure may have been delivered but remain unmarked
(`published_at` still NULL).

```python
async with create_runtime(load_settings()) as runtime:
    await runtime.record_episode_handler().handle(command)
    result = await runtime.relay_outbox_once()
    print(result.published, runtime.logging_outbox_event_publisher.published)
```

`relay_outbox_handler()` raises `ConfigurationError` with code `memory_disabled`
when memory is disabled (checked before relay-specific errors), then
`outbox_relay_disabled` when `outbox_relay.enabled` is `False`, and
`RuntimeError` when the runtime is not started. The default
`LoggingOutboxEventPublisher` records dispatched events in-process for tests;
production brokers implement the same port without changing the handler.

## Inbox Consumer

When `inbox.enabled` is `True` (default), relay dispatch flows through
`InboxOutboxEventPublisher`, which runs inbox processing before the logging
delegate. `ProcessInboxEventHandler` routes supported events to pluggable
processors; v1 registers `EpisodeRecordedProcessor` for
`memory.episode-recorded` structural validation (no projection side effects).

```text
RelayOutboxEventsHandler
  → InboxOutboxEventPublisher.publish(event)
      → ProcessInboxEventHandler.handle(event)
          → select InboxEventProcessor by event_type
          → InboxStore.try_record(event_id, ...)
          → EpisodeRecordedProcessor.process(event)
          → on failure: InboxStore.remove_record(event_id)
      → LoggingOutboxEventPublisher.publish(event)   # test visibility only
  → OutboxRelayStore.mark_published(...)
```

**Delegate vs inbox authority:** `InboxOutboxEventPublisher` always calls the
logging delegate after inbox handling, including when the handler returns
`skipped=True` (duplicate or unsupported event). Use
`logging_outbox_event_publisher.published` to assert dispatch visibility in
tests; use `memory_inbox_events` row counts as the processed authority.
`LoggingOutboxEventPublisher.published` is **not** a dedup authority.

| Outcome | `processed` | `skipped` | Inbox row |
|---------|-------------|-----------|-----------|
| Unsupported `event_type` | `False` | `True` | not written |
| Duplicate `event_id` | `False` | `True` | unchanged |
| New successful processing | `True` | `False` | written |

Processor failure after `try_record` calls `remove_record` and re-raises so
relay does not `mark_published` and can retry. Unsupported event types skip
without an inbox write.

Migration `003_inbox_events.sql` creates `memory_inbox_events` with
`event_id uuid PRIMARY KEY`. **v1 dedup key is `event_id` only** (global per
database, single consumer). `consumer_name` is stored for audit and future
multi-consumer migrations but does not participate in the primary key; multiple
consumers processing the same `event_id` would require a composite key migration.

### Configuration

```python
class InboxSettings:
    enabled: bool = True
    consumer_name: str = "episode-recorded-v1"
```

| Environment variable | Default |
|---------------------|---------|
| `ENGRAMMESH__INBOX__ENABLED` | `true` |
| `ENGRAMMESH__INBOX__CONSUMER_NAME` | `episode-recorded-v1` |

When `inbox.enabled=False`, `AppRuntime` uses `LoggingOutboxEventPublisher`
only and behavior matches the pre-inbox relay path (no inbox DB writes). This
is the rollback switch for regressions or environments that have not yet applied
migration `003`.

```python
async with create_runtime(load_settings()) as runtime:
    await runtime.record_episode_handler().handle(command)
    await runtime.relay_outbox_once()
    # Dispatch visibility (may include redeliveries):
    runtime.logging_outbox_event_publisher.published
    # Processed authority — query memory_inbox_events
```

`outbox_event_publisher` returns the wired publisher (`InboxOutboxEventPublisher`
or `LoggingOutboxEventPublisher`). `logging_outbox_event_publisher` always
exposes the inner delegate. `process_inbox_handler()` builds the handler when
inbox processing is needed.

### Authorization

Episode HTTP routes use one of two authorization strategies, selected by
`oidc.enabled` at composition time via `create_memory_authorization()`.
Execution HTTP routes use the same OIDC toggle via
`create_runtime_authorization()`: `EnvironmentGatedRuntimeAuthorization` when
OIDC is disabled, `TenantScopedRuntimeAuthorization` when OIDC is enabled.

#### When OIDC is disabled (`oidc.enabled=false`, default)

`EnvironmentGatedMemoryAuthorization` gates authorization by
`ENGRAMMESH__ENVIRONMENT`. Bearer tokens are not required. `actor_id` comes
from the request body (`POST`) or query parameters (`GET`).

| `Environment` | `authorize(...)` result |
|---------------|-------------------------|
| `development` | `True` for all requests |
| `test`        | `True` for all requests |
| `staging`     | `False` for all requests |
| `production`  | `False` for all requests |

Denied authorization surfaces as `EpisodeAuthorizationDenied` or
`EpisodeReadAuthorizationDenied`. On the HTTP API, `staging` and `production`
therefore return **403** with code `episode_authorization_denied` or
`episode_read_authorization_denied`; use `development` or `test` for local
exercises without OIDC.

#### OIDC authentication (`oidc.enabled=true`)

When OIDC is enabled, `POST` and `GET` episode routes require a valid
`Authorization: Bearer <jwt>` header. `/health` and `/ready` remain
unauthenticated. JWT verification and principal binding stay in
`bootstrap/auth/`; application handler signatures are unchanged.

`TenantScopedMemoryAuthorization` replaces the environment gate: the JWT
`actor_id` must equal the command/query `actor_id`, and the JWT `tenant_id`
must equal the request scope tenant. Path `{tenant_id}` must match the JWT
tenant claim; a mismatch returns **403** `tenant_access_denied` before the
handler runs.

**Verifier selection** (`create_token_verifier`):

| Condition | Verifier |
|-----------|----------|
| `environment` is `development` or `test`, and `dev_signing_key` is set | `StaticDevTokenVerifier` (HS256) |
| `jwks_uri` is set | `JwksTokenVerifier` (RS256 / ES256 / EdDSA via JWKS) |
| OIDC enabled but neither applies | startup `ConfigurationError` (`oidc_misconfigured`) |

`dev_signing_key` is for **development and test only**. Production rejects it
when OIDC is enabled (`oidc_dev_key_forbidden`) and requires non-blank `issuer`
and `jwks_uri`.

**JWT claim requirements** (defaults configurable via `actor_claim` /
`tenant_claim`):

| Claim | Default name | Requirement |
|-------|--------------|-------------|
| Actor | `sub` | Required; must be a UUID string |
| Tenant | `tenant_id` | Required; must be a UUID string |
| Expiry | `exp` | Required |
| Issuer | `iss` | Must match configured `issuer` |
| Audience | `aud` | Verified only when `audience` is configured |

When authenticated, `actor_id` is taken from the JWT. Supplying `actor_id` in
the request body or query returns **422** `actor_id_not_allowed`. When OIDC is
disabled, omitting `actor_id` returns **422** `actor_id_required`.

**Configuration** (`OidcSettings`):

| Field | Default | Environment variable |
|-------|---------|---------------------|
| `enabled` | `false` | `ENGRAMMESH__OIDC__ENABLED` |
| `issuer` | `""` | `ENGRAMMESH__OIDC__ISSUER` |
| `jwks_uri` | `""` | `ENGRAMMESH__OIDC__JWKS_URI` |
| `audience` | `null` | `ENGRAMMESH__OIDC__AUDIENCE` |
| `actor_claim` | `sub` | `ENGRAMMESH__OIDC__ACTOR_CLAIM` |
| `tenant_claim` | `tenant_id` | `ENGRAMMESH__OIDC__TENANT_CLAIM` |
| `dev_signing_key` | `null` | `ENGRAMMESH__OIDC__DEV_SIGNING_KEY` |

**Staging integration tests** can inject a verifier without changing handler
code:

```python
from engrammesh.bootstrap.http.app import create_app

app = create_app(
    runtime,
    lifespan=lifespan,
    token_verifier=my_test_verifier,  # overrides runtime.token_verifier()
)
```

**OIDC error codes** (in addition to ingest/read codes below):

| Status | `error.code` | Condition |
|--------|--------------|-----------|
| `401` | `authentication_required` | Missing or blank `Authorization` header |
| `401` | `invalid_token` | Malformed Bearer prefix, invalid JWT, or failed verification |
| `403` | `tenant_access_denied` | JWT tenant claim does not match path `{tenant_id}` |
| `422` | `actor_id_not_allowed` | `actor_id` in body or query when OIDC is enabled |
| `422` | `actor_id_required` | `actor_id` missing when OIDC is disabled |

## Episode ingest HTTP API

`bootstrap/http/` exposes the first Control API slice: `RecordEpisodeCommand`
over REST, wired through `create_app(runtime, lifespan=lifespan)` and
`AppRuntime.record_episode_handler()`. FastAPI and uvicorn stay in bootstrap;
domain and application modules remain framework-neutral.

```python
from engrammesh.bootstrap.http.app import create_app
```

### Endpoints

| Method | Path | Success | Description |
|--------|------|---------|-------------|
| `GET` | `/health` | `200` | Liveness probe; does not touch the database |
| `GET` | `/ready` | `200` or `503` | Readiness probe; checks runtime startup, memory enablement, and PostgreSQL |
| `POST` | `/v1/tenants/{tenant_id}/episodes` | `201` or `200` | Record one Episode; `201` when created, `200` on exact idempotent replay |
| `GET` | `/v1/tenants/{tenant_id}/episodes/{episode_id}` | `200` / `403` / `404` / `422` / `503` | Read one episode by exact scope |
| `GET` | `/v1/tenants/{tenant_id}/episodes` | `200` / `403` / `422` / `503` | List episodes with keyset cursor pagination |

`POST` accepts optional header `X-Correlation-Id` (UUID). When omitted, the
server generates a new correlation ID. Non-UUID values return **422**.

Path `tenant_id` must match body `scope.tenant_id`; a mismatch returns **422**.

**Success response bodies:**

| Endpoint | Status | Body |
|----------|--------|------|
| `GET /health` | `200` | `{ "status": "ok" }` |
| `GET /ready` | `200` | `{ "status": "ready" }` |
| `POST .../episodes` | `201` | `{ "episode_id": "<uuid>", "created": true }` |
| `POST .../episodes` | `200` | `{ "episode_id": "<uuid>", "created": false }` (idempotent replay) |

### HTTP scope vs event scope

HTTP request bodies use an independent transport schema
(`record-episode-request.schema.json`), not the Outbox event payload schema.

| Layer | Tenant location | `scope` fields |
|-------|---------------|----------------|
| HTTP request body | `scope.tenant_id` (required) plus path `tenant_id` (must match) | `tenant_id`, `subject_id`, `workspace_id?`, `agent_id?` |
| Outbox event envelope | `tenant_id` at envelope level | — |
| Outbox event `payload.scope` | **not included** | `subject_id`, `workspace_id?`, `agent_id?` |

The path/body `tenant_id` duplication supports gateway routing, audit logs, and
request validation. `RecordEpisodeHandler` still publishes events without
`tenant_id` inside `payload.scope`.

### Error responses

Episode ingest errors use a canonical envelope:

```json
{
  "error": {
    "code": "<machine_readable_code>",
    "message": "<human_readable_message>",
    "details": []
  }
}
```

| Status | `error.code` | Condition |
|--------|--------------|-----------|
| `401` | `authentication_required` | OIDC enabled; missing `Authorization` header |
| `401` | `invalid_token` | OIDC enabled; Bearer JWT verification failed |
| `403` | `tenant_access_denied` | OIDC enabled; JWT tenant ≠ path `{tenant_id}` |
| `403` | `episode_authorization_denied` | `EpisodeAuthorizationDenied` (including `staging` / `production` when OIDC off) |
| `409` | `episode_idempotency_conflict` | Same `(tenant_id, idempotency_key)` with differing Episode-defining fields |
| `422` | `actor_id_not_allowed` | OIDC enabled; `actor_id` supplied in body |
| `422` | `actor_id_required` | OIDC disabled; `actor_id` missing from body |
| `422` | `validation_error` | Pydantic validation, path/body `tenant_id` mismatch, invalid `X-Correlation-Id` |
| `503` | `service_unavailable` | `ConfigurationError` (for example `memory_disabled`, `http_disabled`) |
| `500` | `internal_error` | Unhandled exception (no stack trace in the response) |

### `/ready` reason codes

When not ready, `GET /ready` returns **503**:

```json
{ "status": "not_ready", "reason": "<stable_code>" }
```

| `reason` | Condition |
|----------|-----------|
| `runtime_not_started` | `AppRuntime.startup()` has not completed |
| `database_unavailable` | PostgreSQL pool unavailable or `SELECT 1` failed |
| `memory_disabled` | `modules.memory_enabled` is `False` |

`GET /ready` uses the `not_ready` body above. Episode `POST` does **not** call
`check_ready()`; `memory_disabled` on `POST` returns the `error` envelope with
`service_unavailable` (see the error table). If `POST` runs before
`AppRuntime.startup()` completes, `record_episode_handler()` raises
`RuntimeError`, which maps to **500** `internal_error`.

### Start the HTTP server

Configure via `ENGRAMMESH__HTTP__HOST`, `ENGRAMMESH__HTTP__PORT`, and
`ENGRAMMESH__HTTP__ENABLED`. Use `development` or `test` for authorized writes.

```bash
ENGRAMMESH__ENVIRONMENT=development \
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
ENGRAMMESH__TEMPORAL__NAMESPACE=demo \
ENGRAMMESH__TEMPORAL__TASK_QUEUE=demo \
uv run --python 3.14 --project services \
  python -m engrammesh.bootstrap.server
```

`server.py` calls `create_runtime`, defines lifespan `startup`/`shutdown`, and
passes that lifespan into `create_app`. Outbox relay is not started inside the
HTTP process; dispatch remains via `relay_outbox_once()` or a separate worker.

### Example `curl`

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: 02ffae84-2764-41f3-a22a-4d4652a7c139" \
  -d '{
    "actor_id": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
    "scope": {
      "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
      "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
      "workspace_id": "workspace-42"
    },
    "source_type": "user",
    "content_ref": "a2e57fc9-d07d-45dc-a647-76d195985d86",
    "observed_at": "2026-07-27T10:00:00+00:00",
    "content_hash": "sha256:88c7355c",
    "idempotency_key": "episode-42",
    "sensitivity": "confidential",
    "retention_class": "standard",
    "consent_basis": "user_request"
  }'
```

Expected first-write response (`201`):

```json
{ "episode_id": "<uuid>", "created": true }
```

Repeat the same request to observe an idempotent replay (`200`):

```json
{ "episode_id": "<same-uuid>", "created": false }
```

## Episode read HTTP API

`bootstrap/http/` exposes scope-accurate episode reads through
`AppRuntime.get_episode_handler()` and `AppRuntime.list_episodes_handler()`.
Read handlers use `read_episode` authorization via the same strategy as ingest
(see [Authorization](#authorization)).

### Read query parameters

Both read endpoints require query parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `subject_id` | yes | UUID subject within the tenant scope |
| `workspace_id` | no | Optional workspace narrowing |
| `agent_id` | no | Optional agent narrowing |
| `actor_id` | yes when OIDC off; omit when OIDC on | Authorization principal; from JWT when OIDC enabled |

List additionally accepts:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `limit` | `50` | Page size; min `1`, max `100` |
| `cursor` | omitted | Opaque cursor from prior `next_cursor`; omit on first page |

### Read success responses

| Endpoint | Status | Body |
|----------|--------|------|
| `GET .../episodes/{episode_id}` | `200` | Full `EpisodeResponse` (see `episode-response.schema.json`) |
| `GET .../episodes` | `200` | `{ "items": [ /* EpisodeResponse */ ], "next_cursor": "..." \| null }` |

`EpisodeResponse` includes `episode_id`, `scope` (with `tenant_id`), `actor_id`,
`source_type`, `content_ref`, `observed_at`, `ingested_at`, `content_hash`,
`idempotency_key`, `sensitivity`, `retention_class`, and `consent_basis`.
`content_ref` is opaque; object storage hydration is not implemented.

### Read error responses

Read errors reuse the canonical envelope. Additional codes beyond ingest:

| Status | `error.code` | Condition |
|--------|--------------|-----------|
| `401` | `authentication_required` | OIDC enabled; missing `Authorization` header |
| `401` | `invalid_token` | OIDC enabled; Bearer JWT verification failed |
| `403` | `tenant_access_denied` | OIDC enabled; JWT tenant ≠ path `{tenant_id}` |
| `403` | `episode_read_authorization_denied` | `EpisodeReadAuthorizationDenied` (including `staging` / `production` when OIDC off) |
| `404` | `episode_not_found` | Unknown id, wrong scope, or cross-tenant access (no existence leak) |
| `422` | `actor_id_not_allowed` | OIDC enabled; `actor_id` supplied in query |
| `422` | `actor_id_required` | OIDC disabled; `actor_id` missing from query |
| `422` | `invalid_episode_cursor` | Malformed list cursor |
| `422` | `validation_error` | Invalid UUIDs, `limit` out of range (`1`–`100`) |
| `503` | `service_unavailable` | `ConfigurationError` (for example `memory_disabled`) |

Wrong tenant, wrong `subject_id`, wrong optional scope narrowing, or unknown
`episode_id` all return **404** `episode_not_found`. Never **403** for cross-tenant
existence leaks.

### Example `curl` (record → get → list)

Record an episode (same as ingest example), then read it back:

```bash
EPISODE_ID="<uuid-from-post-response>"

curl -sS "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes/${EPISODE_ID}" \
  "?subject_id=3d65c071-ac55-4847-a8f1-e3cb859d3c45" \
  "&workspace_id=workspace-42" \
  "&actor_id=3ba213e4-3367-4e7c-9635-bcbfbad505e6"

curl -sS "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/episodes" \
  "?subject_id=3d65c071-ac55-4847-a8f1-e3cb859d3c45" \
  "&workspace_id=workspace-42" \
  "&actor_id=3ba213e4-3367-4e7c-9635-bcbfbad505e6" \
  "&limit=50"
```

List pagination: when `next_cursor` is non-null, pass it as the `cursor` query
parameter on the next request with the same scope and `limit`.

## Execution HTTP API

`bootstrap/http/` exposes durable execution control through
`AppRuntime.start_execution_handler()`, `get_execution_snapshot_handler()`, and
`cancel_execution_handler()`. Routes use `execution_auth_context` for OIDC (see
[Authorization](#authorization)). FastAPI and uvicorn stay in bootstrap; runtime
application handlers remain framework-neutral.

### Endpoints

| Method | Path | Success | Description |
|--------|------|---------|-------------|
| `POST` | `/v1/tenants/{tenant_id}/executions` | `201` or `200` | Start one execution; `201` when created, `200` on exact idempotent replay |
| `GET` | `/v1/tenants/{tenant_id}/executions/{execution_id}` | `200` / `403` / `404` / `422` / `503` | Read one execution snapshot by exact scope |
| `POST` | `/v1/tenants/{tenant_id}/executions/{execution_id}/cancel` | `200` / `403` / `404` / `409` / `422` / `503` | Cancel one execution |

`POST` start and cancel accept optional header `X-Correlation-Id` (UUID). When
omitted, the server generates a new correlation ID. Non-UUID values return
**422**.

Path `tenant_id` must match body `scope.tenant_id`; a mismatch returns **422**.
When `memory_query` is supplied on start, its `scope` must match the execution
`scope`; a mismatch returns **422** `validation_error`.

**Success response bodies:**

| Endpoint | Status | Body |
|----------|--------|------|
| `POST .../executions` | `201` | `ExecutionSnapshotResponse` + `created: true` |
| `POST .../executions` | `200` | `ExecutionSnapshotResponse` + `created: false` (idempotent replay) |
| `GET .../executions/{execution_id}` | `200` | `ExecutionSnapshotResponse` (see `execution-snapshot-response.schema.json`) |
| `POST .../executions/{execution_id}/cancel` | `200` | `ExecutionSnapshotResponse` |

`ExecutionSnapshotResponse` includes `execution_id`, `scope`, `revision`,
`status`, `plan_revision`, `node_statuses`, `suspension`, `result_ref`,
`failure`, and `updated_at`.

### Get and cancel query parameters

`GET` snapshot requires query parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `subject_id` | yes | UUID subject within the tenant scope |
| `workspace_id` | no | Optional workspace narrowing |
| `agent_id` | no | Optional agent narrowing |
| `actor_id` | yes when OIDC off; omit when OIDC on | Authorization principal; from JWT when OIDC enabled |

Cancel uses the same `actor_id` rules in the request body (or JWT when OIDC is
enabled).

### Error responses

Execution errors use the canonical envelope. Additional codes beyond shared
OIDC and validation errors:

| Status | `error.code` | Condition |
|--------|--------------|-----------|
| `403` | `execution_authorization_denied` | `ExecutionAuthorizationDenied` (including `staging` / `production` when OIDC off) |
| `404` | `execution_not_found` | Unknown id, wrong scope, or cross-tenant access (no existence leak) |
| `409` | `execution_idempotency_conflict` | Same `(tenant_id, idempotency_key)` with differing execution-defining fields |
| `409` | `invalid_execution_transition` | Cancel or transition rejected (for example already `succeeded`) |
| `422` | `actor_id_not_allowed` | OIDC enabled; `actor_id` supplied in body or query |
| `422` | `actor_id_required` | OIDC disabled; `actor_id` missing from body or query |
| `422` | `validation_error` | Pydantic validation, path/body `tenant_id` mismatch, `memory_query.scope` mismatch, invalid `X-Correlation-Id` |
| `503` | `service_unavailable` | `ConfigurationError` (for example `runtime_disabled`) |
| `503` | `orchestration_unavailable` | `OrchestrationUnavailable` (Temporal or orchestrator backend failure) |

Wrong tenant, wrong `subject_id`, wrong optional scope narrowing, or unknown
`execution_id` all return **404** `execution_not_found`. Never **403** for
cross-tenant existence leaks.

When `modules.runtime_enabled` is `False`, execution routes return **503**
`service_unavailable` with `runtime_disabled` in error details.

### Example `curl` (start → get → cancel)

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/executions" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: 02ffae84-2764-41f3-a22a-4d4652a7c139" \
  -d '{
    "actor_id": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
    "scope": {
      "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
      "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
      "workspace_id": "workspace-42"
    },
    "objective_ref": "a2e57fc9-d07d-45dc-a647-76d195985d86",
    "root_agent_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "memory_query": null,
    "budget": {
      "max_input_tokens": 1000,
      "max_output_tokens": 500,
      "max_cost_micros": 100000,
      "deadline": "2026-08-04T12:00:00+00:00"
    },
    "idempotency_key": "exec-1"
  }'
```

Expected first-write response (`201`):

```json
{ "execution_id": "<uuid>", "created": true, "status": "pending", "...": "..." }
```

Read the snapshot:

```bash
EXECUTION_ID="<uuid-from-post-response>"

curl -sS "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/executions/${EXECUTION_ID}" \
  "?subject_id=3d65c071-ac55-4847-a8f1-e3cb859d3c45" \
  "&workspace_id=workspace-42" \
  "&actor_id=3ba213e4-3367-4e7c-9635-bcbfbad505e6"
```

Cancel the execution:

```bash
curl -sS -X POST "http://127.0.0.1:8080/v1/tenants/53dad495-7915-439a-b03a-379452a1aa86/executions/${EXECUTION_ID}/cancel" \
  -H "Content-Type: application/json" \
  -d '{
    "actor_id": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
    "scope": {
      "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
      "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
      "workspace_id": "workspace-42"
    },
    "idempotency_key": "cancel-1"
  }'
```

Repeat the same start request to observe an idempotent replay (`200` with
`created: false`).

## Run the example

From the repository root, this deterministic example uses only standard-library
types and committed application/public modules:

```bash
PYTHONPATH=services/src PYTHONDONTWRITEBYTECODE=1 \
  uv run --python 3.14 --project services python - <<'PY'
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from engrammesh.modules.memory.adapters import (
    InMemoryMemoryDatabase,
    InMemoryMemoryUnitOfWorkFactory,
)
from engrammesh.modules.memory.application.record_episode import (
    RecordEpisodeHandler,
)
from engrammesh.modules.memory.public import (
    MemoryScope,
    RecordEpisodeCommand,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)


class Allow:
    async def authorize(self, request: object) -> bool:
        del request
        return True


class FixedClock:
    async def now(self) -> datetime:
        return datetime(2026, 7, 27, 9, 1, tzinfo=UTC)


class FixedIdentities:
    async def new_memory_id(self) -> MemoryId:
        return MemoryId(UUID(int=1))

    async def new_event_id(self) -> EventId:
        return EventId(UUID(int=2))


async def main() -> None:
    database = InMemoryMemoryDatabase()
    handler = RecordEpisodeHandler(
        authorization=Allow(),
        clock=FixedClock(),
        identities=FixedIdentities(),
        unit_of_work_factory=InMemoryMemoryUnitOfWorkFactory(database),
    )
    command = RecordEpisodeCommand(
        correlation_id=CorrelationId(UUID(int=3)),
        actor_id=SubjectId(UUID(int=4)),
        scope=MemoryScope(
            tenant_id=TenantId(UUID(int=5)),
            subject_id=SubjectId(UUID(int=6)),
            workspace_id="demo",
        ),
        source_type=SourceType.USER,
        content_ref=ArtifactId(UUID(int=7)),
        observed_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
        content_hash="sha256:demo",
        idempotency_key="demo-episode",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )
    first = await handler.handle(command)
    replay = await handler.handle(command)
    print(f"first_created={first.created} replay_created={replay.created}")
    print(
        f"same_id={first.episode_id == replay.episode_id} "
        f"episodes={len(database.episodes)} events={len(database.events)}"
    )


asyncio.run(main())
PY
```

Expected output:

```text
first_created=True replay_created=False
same_id=True episodes=1 events=1
```

## Verification

From the repository root, use the locked Python 3.14 environment:

```bash
uv lock --check --python 3.14 --project services
uv run --python 3.14 --project services pytest \
  services/tests/contract/test_in_memory_memory_adapter_contract.py -q
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite" || exit
done
```

PostgreSQL-only verification (serial when xdist loadgroup is enabled):

```bash
ENGRAMMESH__POSTGRES__DSN=postgresql://engrammesh:engrammesh@localhost:5432/engrammesh \
  uv run --python 3.14 --project services pytest services/tests -m postgres -q
```

Configuration is read from `ENGRAMMESH__` variables with `__` between nested
fields, for example `ENGRAMMESH__TEMPORAL__NAMESPACE`. There is no implicit
`.env` loading. Production validation fails closed for sensitive telemetry
capture, requires PostgreSQL `sslmode=verify-full`, and requires Temporal TLS.

## Adapter contract obligations

The PostgreSQL Episode adapter binds every assertion in
`EPISODE_ADAPTER_CONTRACTS` from `tests/contract/memory_adapter_contract.py`
through its typed harness without changing the reusable assertion bodies. The
core registry does not assume one global lock and does not require Claim
operations or cursors to be unavailable. Its reusable assertion module imports
only public memory ports, domain values, and shared contracts; application
orchestration is tested separately. `IN_MEMORY_CAPABILITY_CONTRACTS` and
`POSTGRES_EPISODE_CAPABILITY_CONTRACTS` separately describe each adapter's
unavailable Claims, rejected cursors, and synchronization model.

Follow-up work for production PostgreSQL includes row-level security policies
and broader memory surfaces beyond Episode ingest. HTTP follow-up includes
production observability. New shared capability behavior requires
a separately reviewed contract profile rather than edits to the portable Episode
assertion bodies.

After separate design review, later phases may add Temporal adapters, APIs,
workers, and external event dispatch. They must preserve the dependency and
authority boundaries above; this guide does not pre-authorize any vendor or
deployable product feature.
