# CLAUDE_ADMIN_AUTH_FIX_REPORT

Branch: `fix/admin-login-any-ip` (from `main` @ `8d9138b`). Status labels: VERIFIED / UNVERIFIED / NOT TESTED / BLOCKED.

## 1. Root cause — VERIFIED (code + data; no live reproduction)

Sign-in is two steps: the browser signs in at Supabase Auth, then calls `GET /api/v1/auth/me`.
`require_active_account()` in `apps/api/app/security.py` also enforced an exact match between the
request IP (Render `CF-Connecting-IP`) and `public.profiles.allowed_ip`, returning 403
`ip_not_allowed` / `ip_not_configured` / `ip_configuration_invalid`, and 503 when the IP header was
missing. The frontend then signs the user out. Supabase data: the single admin
(`sanjay@gmail.com`) had `allowed_ip` set, and `last_sign_in_at` is recent, i.e. the Supabase
step succeeds and the API step is what rejects other networks.

## 2. Dependencies on `allowed_ip` (all found by repo-wide grep) — VERIFIED

| Where | Was | Now |
|---|---|---|
| `security.py` `require_active_account` | Enforced (the bug) | Removed; value kept only as informational field |
| `routers/auth.py` `/me` | Required non-null `allowed_ip`, `client_ip` | Both nullable, informational |
| `routers/admin.py` create/update customer | Required on create | Optional on create; PATCH unchanged (informational) |
| Frontend `AuthProvider`, login page, account page, admin panel | IP-specific errors, "current IP for setup" panel, required field | Removed / relabelled "not enforced" |
| DB column + CHECK constraint, RLS, `private.is_admin()` | Unchanged | Unchanged (no migration needed). No other security feature depends on `allowed_ip` |

## 3. Changes

Backend: IP check removed; rate limiting wired in; `trusted_client_ip_or_none()`; `reset()` on the limiter; two optional settings
(`AUTH_RATE_LIMIT_PER_MINUTE=120`, `AUTH_FAILURE_LIMIT=60`). Frontend: IP-specific messages removed, 429 message added.
Docs: `supabase/README.md` bootstrap steps corrected. Tests: see the test report.

## 4. Security design

- Authorization = valid Supabase JWT (pinned algorithms, issuer, audience, exp/iat/nbf) AND server-side `profiles` lookup on every request: role must be `user`/`admin`, status `active`. Admin routes additionally require `role == "admin"` from that profile row. Role is never taken from the token, request body, headers or email. Browser roles have SELECT-only grants on `profiles` (verified in Supabase), and admin create/update request models forbid extra fields, so a client cannot set a role.
- Immediate revocation: pausing/demoting/deleting a profile takes effect on the next request even for an unexpired JWT (tested).
- Per-account limiter (default 120/min, keyed by verified account id, applied before the Supabase profile lookup). Cannot lock out other users.
- Failed-authentication throttle (default 60 per 5 min per trusted client IP). Counts only failures, only with a trusted IP (Render `CF-Connecting-IP`), and never blocks a valid token. `X-Forwarded-For` is ignored.
- CORS reviewed, unchanged: explicit origin list, no wildcard, no credentials, methods limited. `allow_headers=["*"]` left as is to avoid breaking browser fetches I cannot test live.
- Error responses carry no IP, secret or provider detail.

## 5. MFA disabled — owner-authorized; implications

Confirmed in Supabase: 0 MFA factors for the admin, and no MFA code exists in the API. The password is therefore the only factor for a
Super Administrator reachable from any network. Mitigations that exist: Supabase Auth's own sign-in rate limits (NOT VERIFIED — Auth settings are not readable
with the available tools), the throttles above, instant revocation, single-admin constraint. Recommendations: a long unique password (the earlier one was shared in chat: rotate it),
enable CAPTCHA/leaked-password protection in Supabase if the plan allows, and consider re-enabling TOTP later.

## 6. Product-decision change to confirm

The brief says all active users may authenticate from any IP, so **customer IP restriction is no longer enforced** (it was before). The admin panel now says so. If you still want
customers restricted, that needs a separate opt-in design.

## 7. Supabase — VERIFIED read-only; no changes made

Exactly one `role='admin'` profile; email matches `auth.users` and equals `sanjay@gmail.com`; confirmed, `status=active`, not banned, 0 MFA factors. Single-admin
unique index present. No migration, no data change, no password change. Optional (not applied): `update public.profiles set allowed_ip = null where role='admin';` to clear the stale value.

## 8. Trading safety — VERIFIED (static + tests)

`main` contains no order-placement code and no execution route (15 routes; mutating routes only under admin/auth and the pure `/market-data/validate`). The
flags `execution_disabled` / `allow_autonomous_live_trading` appear only in documentation on `main`, not in code. UT Bot, indicators, risk and live-data modules are untouched.

## 9. Rollback

Revert the PR (`git revert <merge commit>`) and let Render redeploy; the old behavior returns. No database change to undo. Render also keeps the previous deploy `d012167` for a dashboard rollback.

## 10. Deployment plan (not executed; needs owner approval)

1. Merge PR. 2. Render auto-deploys `main` (service `allsafe-ai-api`); check build logs. 3. Vercel redeploys the web app. 4. Sign in as the admin from a network other than the stored IP;
confirm `/auth/me` = 200 and `/admin/users` loads. 5. Confirm a paused test customer is still refused.
