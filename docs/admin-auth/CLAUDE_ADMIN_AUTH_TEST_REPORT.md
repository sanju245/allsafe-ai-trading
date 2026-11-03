# CLAUDE_ADMIN_AUTH_TEST_REPORT

## How the tests were run (read this first)

The sandbox cannot install packages: PyPI and the npm registry are refused by the session's network policy (HTTP 403 from the egress proxy). FastAPI, pytest, httpx and
pydantic-settings were therefore NOT available, and the real `pytest` suite was **NOT RUN**.

What was run: the security-layer tests (`tests/test_security.py`, `tests/test_auth_any_ip.py`) under a small local runner with stand-in `fastapi`/`pytest`/`pydantic_settings`
modules (kept outside the repo). They exercise the **real** `app/security.py`, real PyJWT signature/claim checks and real Starlette `Request` objects. All Supabase calls are **mocked**.
No live Supabase or production test was performed.

Result: **47 passed, 0 failed** (`test-evidence-security-layer-shim-run.txt`).

Mutation check (VERIFIED): re-inserting the old IP check into a scratch copy made 18 of the new tests fail; removing the two throttle calls made 4 fail. The tests detect the bug.

## Required scenarios

| Scenario | Expected | Status | Evidence |
|---|---|---|---|
| Admin from IP A | Success | VERIFIED (mocked) | `test_admin_authenticates_from_any_ip_in_production[198.51.100.7]` |
| Admin from IP B | Success | VERIFIED (mocked) | `...[203.0.113.200]` |
| Admin from mobile network (IPv6 / CGNAT) | Success | VERIFIED (mocked) | `...[2001:db8:abcd::1]`, `...[100.64.12.34]` |
| Stale/invalid/missing stored IP, unknown client IP | Success | VERIFIED (mocked) | `test_invalid_or_missing_stored_ip...`, `test_unknown_client_ip...` |
| Active user | Allowed | VERIFIED (mocked) | `test_active_user_is_allowed_from_any_ip` |
| Paused user / admin | Rejected 403 | VERIFIED (mocked) | `test_paused_user_is_rejected`, `test_paused_admin_is_rejected` |
| Inactive / missing profile | Rejected 403 | VERIFIED (mocked) | `test_inactive_account_is_rejected[*]`, `test_account_without_a_profile...` |
| Non-admin on admin dependency | 403 | VERIFIED (mocked, dependency level) | `test_non_admin_cannot_use_admin_dependency` |
| Non-admin on admin HTTP routes | 403 | NOT TESTED (written, needs FastAPI) | `test_auth_any_ip_api.py` |
| Invalid / malformed / tampered JWT | 401 | VERIFIED (mocked) | `test_missing_or_malformed...`, `test_tampered_signature...`, `test_token_for_another_project...` |
| Expired JWT | 401 | VERIFIED (mocked) | `test_expired_token_is_401` |
| Invalid password | Rejected | NOT TESTED — performed by Supabase Auth in the browser flow; no live credentials were used | — |
| Rate limit exceeded | 429 + Retry-After | VERIFIED (mocked, function level) | `test_per_account_rate_limit...`, `test_repeated_failed_authentication...` |
| Rate limit not global / valid token not blocked | — | VERIFIED (mocked) | `test_rate_limit_is_per_account_not_global`, `test_failed_attempts_never_block...` |
| Role escalation via token claims / email | Rejected | VERIFIED (mocked) | `test_admin_role_in_token_claims_is_ignored`, `test_token_claiming_admin...`, `test_owner_email_alone...` |
| Role escalation via admin API body | 422 | NOT TESTED (written) | `test_clients_cannot_set_a_role...` |
| Instant revocation (pause / demote) | Next request rejected | VERIFIED (mocked) | `test_pausing_an_account_revokes...`, `test_demoting_an_admin...` |
| Trading execution disabled | No execution route / order call | VERIFIED (static scan of 15 routes + source) ; route-table pytest NOT RUN | static script output in the final report; `test_no_trading_execution_route_exists` written |
| CORS explicit allowlist | — | NOT TESTED (written) | `test_cors_*` |

## Other checks
- `python -m compileall` on `apps/api` : OK (VERIFIED).
- TypeScript syntax-only check of the four changed web files: no syntax errors (VERIFIED; a deliberately broken file was flagged, so the check works). **Type-check, ESLint and `next build` were NOT RUN** (dependencies cannot be installed).
- Existing suites other than `test_security.py` (admin API, auth API, CORS, Groww, indicators) were NOT RUN here; `test_admin_api.py` was edited (one validation test now uses an invalid email, as `allowed_ip` is optional).

## To run the real suite
```
cd apps/api && pip install -r requirements-dev.txt && pytest
```
Expected: all tests pass; if any fail, they are the route-level tests above, which I could not execute.
