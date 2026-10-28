# Test Outcome — RAGFlow SSO QA (2026-10-28)

Branch: main-dev-fork | Commits: 95ed069a6, b65bc30fd

## Automated

- backend `tests/test_ragflow_sso.py`: **27 passed, 0 failed** (PYTHONPATH=. uv run pytest)
- frontend `tests/unit/app/settings/basic-settings.test.ts`: **passed** (pnpm test)
- ruff check/format on touched files: **clean**
- eslint/tsc on touched frontend files: **clean** (pre-existing debt in untouched files: TracebackDrawer.tsx tsc errors ×7, eslint 7E/4W elsewhere)

## Live E2E (dev, localhost:2026)

- POST /api/extensions/auth/login → 200 (session cookies)
- GET /api/extensions/auth/ragflow-sso/login → **302** → Location `http://localhost:9381/?auth=<fresh session token>`
- Bearer token vs RAGFlow GET /api/v1/datasets → **200** (real KB payload)

## Data fix applied (live dev DB)

- ragflow MySQL `user.access_token` LIKE 'INVALID%' ×2 rows reset via `REPLACE(UUID(),'-','')` — root cause: itsdangerous serialization-failure marker persisted by old image; current exchange code verified healthy via fresh-user probe.

## Environment notes

- gateway restart → nginx stale upstream IP → 502 ×2; fixed each time with `docker exec deer-flow-nginx nginx -s reload` (bug-3233 pattern)
- gateway cold start after restart ~75s silent (no log output) — poll health, don't panic
