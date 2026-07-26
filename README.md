# EngramMesh

> Open-source cognitive memory and durable multi-agent runtime.

## Status

Architecture approved; product implementation has not started.

## Why EngramMesh

Chat history is ephemeral, difficult to inspect, and prone to losing the context
needed across long-running work. Vector-only RAG can retrieve similar text, but
does not by itself model evidence, time, corrections, access boundaries, or the
authority of task execution. EngramMesh is designed around durable memory that
can be explained, versioned, corrected, and governed by permissions while
supporting reliable multi-agent work.

## Core Principles

- Explainable, versioned and correctable memory, with evidence and provenance.
- Temporal as the durable execution authority for task lifecycle and retries.
- PostgreSQL as the memory fact source, with append-only events and versioned records.
- Rebuildable vector and graph projections rather than unrecoverable primary state.
- Zero-trust tools and permission-preserving derived memory.
- Provider-neutral models and storage adapters to avoid coupling core behavior to one vendor.

## Architecture

See the [production architecture](docs/architecture/engrammesh-production-architecture.md).

## Roadmap

See the [non-binding roadmap](ROADMAP.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
and [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 for code; CC BY 4.0 for documentation.
