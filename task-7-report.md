# Task 7 Report: HTTP Routes + Non-OIDC Integration Tests

## STATUS

**COMPLETE** — All deliverables implemented and verified.

## Commit

```
feat: add execution HTTP routes and integration coverage
```

(With DCO sign-off via `git commit -s`)

## Changes

| File | Action |
|------|--------|
| `services/src/engrammesh/bootstrap/http/app.py` | Added 3 execution routes (start, get snapshot, cancel) |
| `services/tests/integration/http/execution_http_helpers.py` | Created payload builders + `seed_succeeded_execution` |
| `services/tests/integration/http/test_execution_http.py` | Created full 14-test non-OIDC integration matrix |

### Routes added

- `POST /v1/tenants/{tenant_id}/executions` — start with `201`/`200` + `created`
- `GET /v1/tenants/{tenant_id}/executions/{execution_id}` — snapshot read
- `POST /v1/tenants/{tenant_id}/executions/{execution_id}/cancel` — cancel

All routes use `execution_auth_context`, existing mappers, and `AppRuntime` handler accessors.

## Test count

**14 / 14 passed**

```
uv run --python 3.14 --project services pytest services/tests/integration/http/test_execution_http.py -v
```

| Test | Result |
|------|--------|
| `test_post_start_returns_201` | PASS |
| `test_post_start_idempotent_replay_returns_200` | PASS |
| `test_post_start_idempotency_conflict_returns_409` | PASS |
| `test_post_start_invalid_correlation_id_returns_422` | PASS |
| `test_get_execution_after_start_returns_200` | PASS |
| `test_get_unknown_execution_returns_404` | PASS |
| `test_get_wrong_subject_returns_404` | PASS |
| `test_get_missing_actor_id_returns_422` | PASS |
| `test_post_cancel_returns_200_cancelled` | PASS |
| `test_post_cancel_body_tenant_mismatch_returns_422` | PASS |
| `test_post_cancel_succeeded_execution_returns_409` | PASS |
| `test_post_staging_environment_returns_403` | PASS |
| `test_runtime_disabled_returns_503` | PASS |
| `test_start_get_cancel_composed_flow` | PASS |

## Concerns

1. **`seed_succeeded_execution` uses private handler field** (`._orchestrator`) — matches plan; acceptable for integration tests but couples to handler internals.
2. **Plan's `async def _mark_succeeded` was incorrect** — `InMemoryRuntimeDatabase.write` expects a synchronous callback; implemented as `def _mark_succeeded`.
3. **Helper import pattern** — `execution_http_helpers.py` loads `episode_http_helpers` via `importlib` (same pattern as test modules) because the integration test directory is not a Python package.
4. **Task 8 (OIDC execution HTTP)** remains unimplemented — `test_oidc_execution_http.py` not in scope for this task.

## Next

- Task 8: OIDC execution HTTP integration tests
- Task 9: Documentation and CHANGELOG
