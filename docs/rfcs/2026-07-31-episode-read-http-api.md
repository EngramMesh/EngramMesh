# RFC: Episode Read HTTP API

- **Status**: Approved
- **Date**: 2026-07-31
- **Type**: Public API / implementation design summary
- **Authority**: `docs/superpowers/specs/2026-07-31-episode-read-api-design.md` (this RFC is a summary; the spec is the single source of truth)
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Episode ingest, PostgreSQL adapter, Outbox Relay, Episode Ingest HTTP API, Inbox consumer + episode-recorded processor

## 1. Background

EngramMesh closes the write path through `RecordEpisodeHandler`, transactional Outbox,
Relay, and Inbox processing. External integrators can record episodes via HTTP but could
not read them back until this slice.

This RFC summarizes the Episode Read HTTP API: scope-accurate fact retrieval with keyset
cursor pagination over PostgreSQL episode facts (not semantic search, not content hydration).

## 2. Goals

1. `GET /v1/tenants/{tenant_id}/episodes/{episode_id}` — read one episode by exact scope
2. `GET /v1/tenants/{tenant_id}/episodes` — list episodes by scope with keyset cursor pagination
3. `GetEpisodeHandler` and `ListEpisodesHandler` with `read_episode` authorization
4. Keyset cursor support in `EpisodeStore.stream` for in-memory and PostgreSQL adapters
5. `episode-response.schema.json` and `episode-list-response.schema.json` under `packages/contracts/jsonschema/memory/v1/`
6. Unit, integration, contract, and PostgreSQL E2E tests
7. Bilingual services documentation

## 3. Non-goals

- OIDC / JWT (actor from query until OIDC slice)
- Semantic search, Claim read APIs, vector/graph projections
- Object storage content resolution (`content_ref` returned as-is)
- SSE or WebSocket streaming
- PostgreSQL RLS policies
- Full JSON Schema validation of datetime patterns in handlers (match ingest v1)

## 4. API summary

### 4.1 Get episode

```http
GET /v1/tenants/{tenant_id}/episodes/{episode_id}
    ?subject_id={uuid}
    &workspace_id={string}     # optional
    &agent_id={uuid}           # optional
    &actor_id={uuid}           # authorization principal
```

| Status | Condition |
|---|---|
| `200` | Episode found in exact scope |
| `403` | `EpisodeReadAuthorizationDenied` (staging/production) |
| `404` | Episode not found or scope mismatch (no cross-tenant leakage) |
| `422` | Invalid UUIDs or scope parameters |
| `503` | `memory_disabled` via `ConfigurationError` |

**404 policy**: wrong tenant, wrong subject, wrong optional scope narrowing, or unknown
`episode_id` all return `404 episode_not_found`. Never `403` for existence leaks across
tenants or scopes.

### 4.2 List episodes

```http
GET /v1/tenants/{tenant_id}/episodes
    ?subject_id={uuid}
    &workspace_id={string}
    &agent_id={uuid}
    &actor_id={uuid}
    &limit={int}               # default 50, min 1, max 100
    &cursor={opaque}           # optional; omit on first page
```

Response `200`:

```json
{
  "items": [ /* EpisodeResponse */ ],
  "next_cursor": "..." | null
}
```

| Status | Condition |
|---|---|
| `200` | Zero or more items |
| `403` | Authorization denied |
| `422` | Invalid scope, limit, or malformed cursor |
| `503` | Memory disabled |

Ordering: `ingested_at ASC, episode_id ASC`. Pagination fetches `limit + 1` rows; when
more than `limit` exist, return first `limit` items and set `next_cursor` from the last item.

### 4.3 Error codes

| Code | HTTP | Message |
|---|---|---|
| `episode_read_authorization_denied` | 403 | episode reading is not authorized |
| `episode_not_found` | 404 | episode not found |
| `invalid_episode_cursor` | 422 | episode list cursor is invalid |

Reused: `validation_error` (422), `service_unavailable` (503), `internal_error` (500).

## 5. Architecture

```text
HTTP Request (FastAPI)
  → bootstrap/http/schemas.py       # EpisodeResponse, ListEpisodesResponse
  → bootstrap/http/mappers.py       # query params → GetEpisodeQuery / ListEpisodesQuery
  → GetEpisodeHandler / ListEpisodesHandler
  → EpisodeStore.get / EpisodeStore.stream(limit, cursor)
  → PostgresMemoryUnitOfWork / InMemoryMemoryUnitOfWork
```

- FastAPI and uvicorn stay in `bootstrap/http/` and `bootstrap/server.py`
- HTTP layer accesses handlers via `AppRuntime.get_episode_handler()` and
  `AppRuntime.list_episodes_handler()`; no direct adapter imports
- Read handlers open a unit of work without `commit()` (read-only transactions)
- `create_app(runtime, *, lifespan)` remains the single factory for production and tests

## 6. JSON Schema

| File | Purpose |
|---|---|
| `episode-response.schema.json` | One `EpisodeResponse` body |
| `episode-list-response.schema.json` | List wrapper with `$ref` to episode response |

Independent from `record-episode-request.schema.json` and `episode-recorded.schema.json`.
HTTP `scope` includes `tenant_id`; event payload scope does not.

## 7. Testing

| Layer | Coverage |
|---|---|
| Unit | mappers, handlers, cursor encode/decode |
| Integration HTTP | httpx + `create_app`; in-memory runtime |
| Integration postgres | POST → GET by id → GET list |
| Contract | response JSON Schema; `EpisodeStore.stream` pagination |

Required scenarios (spec §9): record then GET, unknown id 404, wrong subject 404, list
pagination, limit 101 → 422, invalid cursor → 422, staging 403, memory_disabled 503,
HTTP cross-tenant GET → 404.

## 8. Acceptance criteria

See spec §11:

1. Full `pytest services/tests` passes
2. `ruff check` and `mypy services/src` pass
3. Local curl: record → GET by id → paginated list
4. PostgreSQL integration verifies read paths
5. No adapter leakage into HTTP layer
6. `episode-response.schema.json` contract test passes

## 9. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅ this slice
③ OIDC tenant context (actor from JWT, unify read/write auth)
④ Temporal runtime adapter
⑤ Claim extraction processor side effects (Phase 2 entry)
```

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cursor format becomes public ABI | Document as opaque; keyset fields inside only |
| Cross-tenant existence leak | Uniform `404` for scope/id mismatches |
| Large scope without pagination | `limit` max 100 at HTTP and handler layers |
| Sensitivity not enforced per episode | Phase 2; v1 uses `INTERNAL` action gate only |
