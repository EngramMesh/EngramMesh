# Agents Guide

Instructions for AI coding agents working in the EngramMesh repository.

## Project

EngramMesh is an open-source cognitive memory and durable multi-agent runtime.
The current codebase is a tested Python 3.14 architecture scaffold with one
Episode ingest application slice. Production API, worker, Temporal, and most
product features are not implemented yet.

## Layout

```text
services/src/engrammesh/   # Python services scaffold
packages/contracts/        # JSON Schema event contracts
docs/                      # Architecture and design docs
```

Key modules:

- `modules/memory/` — Episode ingest, ports, domain, adapters (`in_memory`, `postgres`)
- `modules/runtime/` — Durable-execution contracts (no adapters yet)
- `shared/kernel/` — Typed IDs and event envelope
- `bootstrap/settings.py` — Typed configuration boundary

## Architecture Rules

- Domain and application code must not import adapters or third-party packages.
- Adapters implement ports and depend inward only.
- PostgreSQL is the authority for durable memory facts; vector/graph stores are rebuildable projections.
- Import PostgreSQL types from `engrammesh.modules.memory.adapters.postgres`, not the top-level `adapters` package.
- Keep changes minimal and scoped. Match existing naming, layering, and test style.

## Verification

From the repository root:

```bash
uv run --python 3.14 --project services pytest services/tests -q
uv run --python 3.14 --project services ruff check services/src services/tests
uv run --python 3.14 --project services mypy services/src
```

PostgreSQL tests require `ENGRAMMESH__POSTGRES__DSN` and are marked `@pytest.mark.postgres`.

## Git

- Write commit messages in **English**.
- Use [Conventional Commits](https://www.conventionalcommits.org/) subjects (e.g. `fix:`, `feat:`, `docs:`).
- Keep subjects concise and imperative.
- Include DCO sign-off: `git commit -s`.
- Do not commit unless explicitly asked.

## References

- [services/README.md](services/README.md) — architecture and Episode ingest details
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution and review expectations
- [docs/architecture/](docs/architecture/) — production architecture
