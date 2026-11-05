# TEST_EVIDENCE

## What was and was not run
| Check | Status |
|---|---|
| Real `pytest` + FastAPI suite | **NOT RUN by me.** FastAPI/pytest/httpx cannot be installed in this environment (PyPI and npm refused by network policy; re-checked). A separate reviewer reported 320/320 passing on an earlier bundle; I have not reproduced that and it predates `6984e29`. |
| Security-layer tests under a local stand-in harness | **71 passed, 0 failed** — `test_security.py`, `test_auth_ip_policy.py`, `test_auth_hardening.py`; real `security.py`, real PyJWT, real Starlette `Request`, Supabase **mocked**. Re-run on exact HEAD `b79c05d` on 2026-11-05 (exit 0, 71 passed: 13 `test_security`, 45 `test_auth_ip_policy`, 13 `test_auth_hardening`): `test-evidence-shim-run-head-b79c05d.txt` (earlier log `test-evidence-shim-run-3.txt` was at `6984e29`; no non-doc file changed between them). This is NOT a full integration test. |
| Route-level, CORS, admin-API, auth-API and all unrelated suites | NOT RUN (need real FastAPI). Written: `test_auth_ip_policy_api.py`. |
| Frontend lint / type-check / build | NOT RUN (npm blocked). |
| Live Supabase / production tests, invalid-password test | NOT TESTED. |
| `python -m compileall` | OK. Static route/source scan (no execution routes or broker calls) | OK. |

## Mutation checks (VERIFIED 2026-11-05, scratch copy of HEAD, bytecode cache cleared; 71 tests total)
| Mutation of `security.py` | Result |
|---|---|
| M1 drop customer IP match | 9 failed |
| M2 treat admin like customer | 15 failed |
| M3 no IPv4-mapped normalisation | 3 failed |
| M4 no wrong-IP throttle | 1 failed |
| M5 no JWKS refresh limit | 2 failed |
| M6 accept first of duplicate `CF-Connecting-IP` | 1 failed |
| M7 no shared unknown-client bucket | 1 failed |
| M8 trust `X-Forwarded-For` instead | 30 failed |
| M9 no per-account rate limit | 2 failed |
| Unmutated | 71 passed, 0 failed |

These replace earlier approximate counts (e.g. "8+"), which came from a truncated listing and a smaller test set.

## Command to run the full suite
`cd apps/api && pip install -r requirements-dev.txt && pytest -v` ; `cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build`.
