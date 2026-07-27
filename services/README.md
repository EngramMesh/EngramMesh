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
│   │   │   ├── adapters/     # in-memory test/development transaction adapter
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

- PostgreSQL is the future authority for memory facts, versioned records,
  append-only events, and durable structured snapshots.
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
injected clock and identity ports. The only concrete persistence implementation
is `InMemoryMemoryUnitOfWorkFactory`, backed by
`InMemoryMemoryDatabase`, for deterministic tests and local development.

The slice deliberately excludes HTTP, dependency-injection wiring, PostgreSQL,
ORMs and migrations, Temporal, object upload, Claim extraction, retrieval,
correction and deletion, projections, and external Outbox dispatch. It makes no
cross-process durability or delivery guarantee.

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
translation is outside this slice.

## Idempotency and transaction semantics

Idempotency is scoped to `(tenant_id, idempotency_key)`. The first append
returns `created=True`; a replay in the same tenant returns the original Episode
ID with `created=False` and stages no second event. A different tenant may reuse
the same key.

The in-memory adapter serializes transactions with one process-local lock and
uses copy-on-write state. `commit()` stages the new committed snapshot, while
successful context exit completes the transaction. Exit without `commit()`, an
exception, or cancellation discards staged Episode, idempotency, and Outbox
changes. An exception or cancellation after `commit()` but before successful
context exit restores the pre-transaction snapshot. This behavior is an atomic
local test/development model, not a production concurrency or durability model.

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
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite" || exit
done
```

Configuration is read from `ENGRAMMESH__` variables with `__` between nested
fields, for example `ENGRAMMESH__TEMPORAL__NAMESPACE`. There is no implicit
`.env` loading. Production validation fails closed for sensitive telemetry
capture, requires PostgreSQL `sslmode=verify-full`, and requires Temporal TLS.

## Next adapter obligation

A future PostgreSQL Episode adapter must bind every assertion in
`tests/contract/memory_adapter_contract.py` through its own typed harness without
changing the reusable assertion bodies. It must also add PostgreSQL-specific
integration coverage for migrations, constraints, transaction isolation,
tenant enforcement, and failure behavior. Claim persistence and cursor support
remain unavailable in this slice; changing those behaviors requires a separately
reviewed contract revision.

After separate design review, later phases may add an explicit composition root,
PostgreSQL or Temporal adapters, migrations, APIs, workers, and external event
dispatch. They must preserve the dependency and authority boundaries above;
this guide does not pre-authorize any vendor or deployable product feature.
