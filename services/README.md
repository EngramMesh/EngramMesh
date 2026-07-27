# EngramMesh Services Architecture Scaffold

[简体中文](README.zh-CN.md) | English

## Purpose and exact non-goals

This directory contains the tested Python 3.14 architecture scaffold for
EngramMesh services. It defines immutable shared identifiers and event metadata,
the public memory and durable-runtime contracts, dependency rules, typed process
configuration, and versioned JSON Schema event contracts.

It does **not** contain a running service, dependency-injection container,
database or Temporal client, API, worker, persistence implementation, model or
tool integration, projection pipeline, or product feature. Passing tests prove
the architecture contracts; they do not imply that a deployable runtime exists.

## Module tree

```text
services/
├── src/engrammesh/
│   ├── bootstrap/
│   │   └── settings.py       # typed, immutable configuration boundary
│   ├── modules/
│   │   ├── memory/
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
    ├── contract/             # public contracts and JSON Schemas
    └── unit/                 # pure invariant and configuration tests

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
bootstrap/configuration        module public contracts
           |                            |
           v                            v
 future composition root -> future application services -> ports
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
- The contracts and schemas in this scaffold define shapes and invariants only;
  they do not persist, schedule, publish, or project state.

## Third-party adapter policy

PostgreSQL drivers, Temporal SDKs, model providers, tool protocols, object
stores, vector databases, graph databases, and telemetry exporters must be
implemented behind the existing or separately reviewed ports. Vendor types,
clients, exceptions, and retry policies must not leak into domain models or
public module contracts. An adapter owns translation to and from the stable
EngramMesh types, enforces tenant and authorization context, and is tested with
deterministic contract tests. Adding a provider library also requires a concrete
adapter use case; it is not added speculatively.

## Run tests and static checks

From the repository root, use the locked Python 3.14 environment:

```bash
uv lock --python 3.14 --project services
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
for suite in tools dco history links workflow orchestration external baseline yaml; do
  ./scripts/test-repository-policy.sh "$suite"
done
```

Configuration is read from `ENGRAMMESH__` variables with `__` between nested
fields, for example `ENGRAMMESH__TEMPORAL__NAMESPACE`. There is no implicit
`.env` loading. Production validation fails closed for sensitive telemetry
capture, requires PostgreSQL `sslmode=verify-full`, and requires Temporal TLS.

## What the next implementation phase may add

After separate design review, the next phase may add application services that
orchestrate the existing ports, a small explicit composition root, concrete
PostgreSQL and Temporal adapters, migrations, APIs, workers, and deterministic
adapter contract tests. It may extend public contracts only through reviewed,
versioned changes. It must preserve the dependency and authority boundaries
above; this guide does not pre-authorize any vendor or product feature.
