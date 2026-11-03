# CLAUDE_ADMIN_AUTH_FIX_REPORT (revision 2)

Branch `fix/admin-login-any-ip`, from `main` @ `8d9138b`. Commit 1 `416216e` (first attempt), commit 2 corrects it (see `git log`).
Labels: VERIFIED / UNVERIFIED / NOT TESTED / BLOCKED.

## Correction in this revision
Commit 1 removed the IP allowlist for every account. Owner decision: **only the Super Admin may sign in from any IP; customers keep their exact-IP restriction.** Commit 2 restores the customer rule and the customer UI/API, and keeps the admin exemption and the new rate limiting. Net change versus `main` is now confined to `security.py`, `routers/auth.py` (nullable fields), `config.py`, `.env.example`, two small web files, one README sentence, tests and these reports.

## 1. Root cause — VERIFIED (code + Supabase data; no live reproduction)
Sign-in is browser -> Supabase Auth, then `GET /api/v1/auth/me`. `require_active_account()` demanded an exact match between the request IP (Render `CF-Connecting-IP`) and `profiles.allowed_ip` for every role, so the admin was refused (403 `ip_not_allowed`, or 503 without the header) on any network other than the stored one. Supabase confirms the single admin has `allowed_ip` set and a successful Supabase sign-in today.

## 2. New policy in `require_active_account()` (VERIFIED in mocked tests)
1. JWT validation mandatory for all (pinned algorithms, issuer, audience, exp/iat/nbf).
2. Per-account rate limit (before the profile lookup).
3. Profile fetched on every request; role must be `user`/`admin`; status must be `active` (paused / other -> 403).
4. `role == "admin"` and active: accepted from any IP; stored `allowed_ip` ignored; client IP is best-effort (None allowed).
5. `role == "user"` and active: trusted client IP must be verifiable (else 503) and the stored `allowed_ip` must be present (`ip_not_configured`), a single valid host (`ip_configuration_invalid`) and equal (`ip_not_allowed`). Fail closed.
6. Client IP comes only from Render's `CF-Connecting-IP` in production (a header list is rejected); `X-Forwarded-For`, `X-Real-IP`, `Forwarded` are never used.
7. Pause, delete, demotion, invalid/expired JWT take effect on the next request. A demoted admin is immediately IP-restricted.
8. Admin routes additionally require `role == "admin"` from the server-side profile; the role is never read from the token, body, headers or email.

## 3. Rate limiting and brute force
- Per account: default 120 requests/min (`AUTH_RATE_LIMIT_PER_MINUTE`), keyed by verified account id; cannot lock out other users.
- Failed authentications: default 60 per 5 min per trusted client IP (`AUTH_FAILURE_LIMIT`), counts only failures and only with a trusted IP; never blocks a valid token.
- Password guessing happens at Supabase Auth (browser -> Supabase), outside this API. Supabase's own sign-in limits were NOT READABLE with the available tools (UNVERIFIED).
- Other controls unchanged: CORS explicit origin list (no wildcard), generic error bodies, server-side secrets only.

## 4. MFA (owner-authorized off) — implications
Supabase shows 0 MFA factors for the admin and no MFA code exists in the API. For a Super Admin reachable from any network the password is the only factor. Rotate the password that was shared in chat; use a long unique one; consider CAPTCHA/leaked-password protection and TOTP later.

## 5. Supabase — VERIFIED read-only, no changes
Exactly one admin profile: `sanjay@gmail.com` (matches `auth.users`), confirmed, active, not banned, 0 MFA factors. Browser roles have SELECT-only on `profiles`; one SELECT policy; RLS on. No migration added (the separate two-admin migration is out of scope and untouched). No data or password change.

## 6. Trading safety — VERIFIED (static scan + source)
15 routes; mutating routes only under admin/auth and the pure `/market-data/validate`; no order/execution route; no broker order calls in `apps/api/app`. The flags `execution_disabled` / `allow_autonomous_live_trading` exist only in documentation on `main`, not in code, and are unchanged. Indicators, UT Bot, risk and live-data code untouched.

## 7. Rollback
Revert the PR / merge commit and let Render redeploy (previous deploy `d012167` is also available in Render). No database change to undo.

## 8. Deployment plan (NOT executed; needs owner approval)
Merge PR -> Render auto-deploys `main` (`allsafe-ai-api`) -> check build logs -> sign in as admin from a network other than the stored IP -> `/auth/me` 200 and `/admin/users` loads -> sign in as a test customer from a non-registered IP -> expect 403 `ip_not_allowed`.
