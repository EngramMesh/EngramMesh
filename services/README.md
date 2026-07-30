# EngramMesh Services Architecture Scaffold

[简体中文](README.zh-CN.md) | English

## Purpose and exact non-goals

This directory contains the tested Python 3.14 architecture scaffold for
EngramMesh services and one tested Episode ingest application slice. It defines
immutable shared identifiers and event metadata, public memory and
durable-runtime contracts, dependency rules, typed process configuration,
versioned JSON Schema event contracts, and a transactional in-memory adapter
for test and development use.

It does **not** contain a running service, dependency-injection container,
production database or Temporal client, API, worker, external event dispatcher,
model or tool integration, projection pipeline, or deployable product feature.
The in-memory adapter is process-local and non-durable. Passing tests prove the
documented application and architecture contracts; they do not imply that a
deployable runtime exists.

## Module tree

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   └── settings.py       # typed, immutable configuration boundary
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
 future composition root -> application services -> ports
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

The slice deliberately excludes HTTP, dependency-injection wiring,
`PostgresSettings` composition-root binding, Temporal, object upload, Claim
extraction, retrieval, correction and deletion, projections, and external
Outbox dispatch. The in-memory adapter makes no cross-process durability or
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
production-hardening slice. `PostgresSettings` exists in
`bootstrap/settings.py` but is not wired into the adapter here; a future
composition root will read `ENGRAMMESH__POSTGRES__DSN` and construct
`PostgresMemoryDatabase`.

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

Follow-up work for production PostgreSQL includes row-level security policies,
`PostgresSettings` wiring through an explicit composition root, and broader
memory surfaces beyond Episode ingest. New shared capability behavior requires
a separately reviewed contract profile rather than edits to the portable
Episode assertion bodies.

After separate design review, later phases may add Temporal adapters, APIs,
workers, and external event dispatch. They must preserve the dependency and
authority boundaries above; this guide does not pre-authorize any vendor or
deployable product feature.
