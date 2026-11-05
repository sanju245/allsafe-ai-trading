# IMPLEMENTATION_REPORT

Branch `fix/admin-login-any-ip` (local). Commits, oldest first:
1. `416216e` — first fix: removed IP allowlist for all accounts; added per-account and failed-auth throttling.
2. `1acebe4` — corrected to owner decision: admin any IP, customers exact IP (customer UI/API/tests restored).
3. `6984e29` — audit hardening (V-1…V-5). History preserved; no rewrite, no force-push.
4. `b79c05d` - documentation.
5. Verification-audit commit (2026-11-05): corrected evidence/mutation counts, marked the 58-test log outdated, added `VERIFICATION_AUDIT_2026-11-05.md`. No code changed.

## Final behaviour of `require_active_account()` (`apps/api/app/security.py`)
JWT verified → per-account rate limit → profile fetched (role/status checked every request) → admin: any IP; customer: single trusted proxy header, canonical IP, exact match to stored host address, fail closed; wrong-IP attempts throttled.

## Files changed vs `main` (net)
`apps/api/app/security.py`, `apps/api/app/config.py`, `apps/api/app/routers/auth.py` (nullable `allowed_ip`/`client_ip` in `/me`), `apps/api/.env.example`, `apps/web/src/app/account/page.tsx`, `apps/web/src/components/auth/AuthProvider.tsx` (nullable `client_ip`, 429 message), `supabase/README.md`, tests (`test_auth_ip_policy.py`, `test_auth_ip_policy_api.py`, `test_auth_hardening.py`) and docs.
Unchanged vs `main`: login page, admin panel, `routers/admin.py`, `test_security.py`, `test_admin_api.py`, all trading/indicator/market-data code, all migrations.

Totals vs `main` at `b79c05d`: 22 files (7 modified, 15 added, 0 deleted), +1323/-52. Docs: `docs/admin-auth/` (2 earlier reports, partly superseded; 1 outdated evidence log) and `docs/admin-auth/final/`.

## New optional settings (defaults shown)
`AUTH_RATE_LIMIT_PER_MINUTE=120`, `AUTH_FAILURE_LIMIT=60`, `AUTH_IP_MISMATCH_LIMIT=10`. No secrets added.

## Safety invariants
No execution/order routes (static scan, 15 routes), no broker order calls in `apps/api/app`; `execution_disabled` / `allow_autonomous_live_trading` appear only in docs on `main` and are untouched; no live trading enabled.

## Delivery status
GitHub push/PR: BLOCKED (GitHub not linked to this session; push returned 403). Dropbox: BLOCKED (no tool). Deployment: NOT DONE (approval required). Delivered as a git bundle + patches.
