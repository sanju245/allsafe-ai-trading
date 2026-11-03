# TEST_EVIDENCE

## What was and was not run
| Check | Status |
|---|---|
| Real `pytest` + FastAPI suite | **NOT RUN by me.** FastAPI/pytest/httpx cannot be installed in this environment (PyPI and npm refused by network policy; re-checked). A separate reviewer reported 320/320 passing on an earlier bundle; I have not reproduced that and it predates `6984e29`. |
| Security-layer tests under a local stand-in harness | **71 passed, 0 failed** — `test_security.py`, `test_auth_ip_policy.py`, `test_auth_hardening.py`; real `security.py`, real PyJWT, real Starlette `Request`, Supabase **mocked**. Log: `test-evidence-shim-run-3.txt`. This is NOT a full integration test. |
| Route-level, CORS, admin-API, auth-API and all unrelated suites | NOT RUN (need real FastAPI). Written: `test_auth_ip_policy_api.py`. |
| Frontend lint / type-check / build | NOT RUN (npm blocked). |
| Live Supabase / production tests, invalid-password test | NOT TESTED. |
| `python -m compileall` | OK. Static route/source scan (no execution routes or broker calls) | OK. |

## Mutation checks (VERIFIED, scratch copies)
Removing each control makes tests fail: customer IP match (4), admin exemption (8+), trusting `X-Forwarded-For` (2), throttles (4); then for `6984e29`: IPv4-mapped normalisation (3), wrong-IP throttle (1), JWKS refresh limit (2), single-header rule (1), unknown-client bucket (1).

## Command to run the full suite
`cd apps/api && pip install -r requirements-dev.txt && pytest -v` ; `cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build`.
