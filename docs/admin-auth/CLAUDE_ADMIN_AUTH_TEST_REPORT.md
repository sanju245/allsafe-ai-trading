# CLAUDE_ADMIN_AUTH_TEST_REPORT (revision 2)

> **Superseded in part by `docs/admin-auth/final/` (commit `6984e29` added audit hardening; the test counts below predate it). Where they differ, `final/` is authoritative.**

## Limitation (read first)
The genuine pytest + FastAPI integration suite was **NOT RUN**: `fastapi`, `pytest`, `httpx` and `pydantic-settings` are not installed and cannot be installed here (PyPI and the npm registry are refused by the session network policy; re-checked on this revision). The route-level tests (`test_auth_ip_policy_api.py`), CORS tests, the existing admin/auth/CORS suites and all unrelated suites are therefore **NOT TESTED**.

What was run: `tests/test_security.py` (unchanged from `main`) and `tests/test_auth_ip_policy.py` under a **local stand-in harness** (fake `fastapi`/`pytest`/`pydantic_settings` modules kept outside the repo). They execute the real `app/security.py`, real PyJWT checks and real Starlette `Request` objects, with Supabase **mocked**. This is NOT a full integration test. Result: **58 passed, 0 failed** (`test-evidence-security-layer-shim-run.txt`). No live Supabase/production test was done.

Mutation check: superseded - exact counts are in `final/TEST_EVIDENCE.md`.

## Requested scenarios
| Scenario | Status | Test |
|---|---|---|
| Admin succeeds from multiple IPs (v4, v6, CGNAT, no IP) | VERIFIED (mocked) | `test_admin_succeeds_from_multiple_ips[*]`, `test_admin_ignores_missing_or_malformed_stored_ip[*]`, `..._client_ip_cannot_be_determined` |
| Customer succeeds from registered IP | VERIFIED (mocked) | `test_customer_succeeds_from_their_registered_ip` (+ original `test_security.py` cases) |
| Customer fails from a different IP | VERIFIED (mocked) | `test_customer_fails_from_a_different_ip` |
| Customer with missing / malformed IP denied | VERIFIED (mocked) | `test_customer_with_missing_or_malformed_ip_is_denied[*]` (6 cases) |
| Header manipulation cannot bypass | VERIFIED (mocked) | `test_customer_cannot_bypass_the_ip_check_with_forged_headers` |
| Invalid / expired / tampered JWT denied (401) | VERIFIED (mocked) | `test_missing_or_malformed...`, `test_expired_token_is_401`, `test_tampered_signature...`, `test_token_for_another_project...` |
| Paused account denied | VERIFIED (mocked) | `test_paused_account_is_denied[*]`, `test_pausing_an_account_revokes...` |
| Deleted profile / inactive / unknown role denied | VERIFIED (mocked) | `test_deleted_profile...`, `test_inactive_account...`, `test_unknown_role...` |
| Demoted admin immediately restricted | VERIFIED (mocked) | `test_demoted_admin_becomes_subject_to_user_restrictions_immediately` |
| Role escalation denied (claims, JWT role, email) | VERIFIED (mocked) | `test_promoting_a_customer...`, `test_token_claiming_an_admin_jwt_role...`, `test_owner_email_alone...` |
| Role escalation via admin API body (422) | NOT TESTED (written) | `test_clients_cannot_set_a_role...` |
| Non-admin on admin dependency 403 | VERIFIED (mocked) | `test_non_admin_cannot_use_admin_dependency`; HTTP-level: NOT TESTED |
| Rate limiting works, unrelated users unaffected | VERIFIED (mocked) | `test_per_account_rate_limit...`, `test_rate_limiting_does_not_affect_unrelated_users`, failed-auth throttle tests |
| Invalid password rejected | NOT TESTED (Supabase Auth, no live credentials used) | — |
| Trading execution disabled | VERIFIED by static scan of routes/source; pytest route-table test NOT RUN | `test_no_trading_execution_route_exists` (written) |

## Other
`python -m compileall` OK. TypeScript syntax-only check of the changed web files: no errors (type-check, ESLint, `next build` NOT RUN).

## To run the real suite
`cd apps/api && pip install -r requirements-dev.txt && pytest`
