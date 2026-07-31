# RFC: OIDC Tenant Context

- **Status**: Approved
- **Date**: 2026-07-31
- **Type**: Public API / security boundary
- **Authority**: `docs/superpowers/specs/2026-07-31-oidc-tenant-context-design.md` (spec is source of truth)
- **Related roadmap**: Phase 1 — production foundation and single-agent vertical slice
- **Prerequisites**: Episode ingest HTTP API, Episode read HTTP API, Inbox consumer + episode-recorded processor

## 1. Background

Episode HTTP APIs use query/body `actor_id` and `EnvironmentGatedMemoryAuthorization`, which denies all staging/production traffic. External integrators cannot deploy against non-dev environments until Bearer JWT authentication and tenant binding are implemented.

## 2. Goals

1. `TokenVerifierPort` with `StaticDevTokenVerifier` (dev/test) and `JwksTokenVerifier` (staging/prod).
2. Bearer JWT on episode routes when `oidc.enabled=true`; path tenant must match JWT tenant claim.
3. `TenantScopedMemoryAuthorization` replacing the environment gate when OIDC is enabled.
4. `record-episode-request` JSON Schema v1.1.0 (`actor_id` optional in contract).
5. Unit, integration, contract, and PostgreSQL E2E tests; bilingual services documentation.

## 3. Non-goals

Control Plane sync, Memory ACL, PostgreSQL RLS, login UI, refresh tokens, mandatory `oidc.enabled` in production.

## 4. Design summary

See spec §3–§6. Key points:

- JWT libraries confined to `bootstrap/`.
- Handler signatures unchanged; HTTP mappers inject `actor_id` from `AuthenticatedPrincipal`.
- `dev_signing_key` forbidden in production; staging/prod use JWKS in real deployments.
- Tests inject `token_verifier` via `create_app` for staging scenarios without a live IdP.

## 5. Testing

See spec §7. Staging 403 regression tests (`oidc.enabled=false`) must remain green.

## 6. Acceptance

See spec §8.

## 7. Follow-up

```text
① Inbox consumer + episode-recorded processor   ✅
② Episode read API                               ✅
③ OIDC tenant context                            ✅
④ Temporal runtime adapter
⑤ Claim extraction processor (Phase 2 entry)
```
