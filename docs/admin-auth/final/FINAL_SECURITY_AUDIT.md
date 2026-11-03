# FINAL_SECURITY_AUDIT

Scope: branch `fix/admin-login-any-ip` — commits `416216e`, `1acebe4` (reviewed, unchanged) and `6984e29` (audit fixes). Base `main` @ `8d9138b`.
Method: read every changed file and the surrounding auth code; reproduced behaviour with mocked tests; checked live configuration read-only (Render, Supabase). Earlier reports and another reviewer's results were **not** taken on trust (see "Not independently verified").
Labels: VERIFIED / NOT TESTED / BLOCKED / UNVERIFIED.

## Policy audited
Admin (active) may authenticate from any IP; customer (active) must match the stored exact IP; JWT + profile role/status checked on every request. VERIFIED by code reading and mocked tests, including that a demoted admin is IP-restricted immediately and that no client-controlled input (token claims, body, headers, email) can set a role.

## Areas reviewed
| Area | Result |
|---|---|
| JWT validation (HS256/ES256/RS256) | Algorithms pinned, issuer/audience/exp/iat/nbf checked, constant-time HMAC compare. No flaw found. VERIFIED (code + tests) |
| JWKS refresh | **Finding V-2** fixed (forced refresh on every unknown `kid`) |
| CF-Connecting-IP trust | **Open O-1** (deployment assumption). Hardened: one header only (V-4) |
| `X-Forwarded-For` / `X-Real-IP` / `Forwarded` | Never used. Render's own forum thread says it only appends to a client-supplied XFF, which supports that choice. VERIFIED |
| Customer IP enforcement | Fail-closed on missing/invalid/unverifiable/mismatch. V-1, V-5 fixed |
| Admin exemption | Depends only on `profiles.role`, written via SQL/service role; browser roles are SELECT-only; one SELECT policy; single-admin unique index present. VERIFIED (Supabase read-only) |
| Failed-login throttling | V-3 fixed; limits are process-local (O-2) |
| Admin endpoints | Require server-side admin role; create/update models forbid extra fields (no role field); only `role=user` rows manageable. VERIFIED by code; HTTP-level tests written, NOT RUN here |
| CORS | Explicit origin list from env, no credentials, no wildcard origin; `allow_headers=["*"]` left (O-6). Render env value not readable → UNVERIFIED |
| Supabase RLS | RLS on `profiles`; `private.is_admin()` is `security definer` with empty `search_path`. Advisors 2026-11-03: leaked-password protection OFF; 10 mutable-`search_path` functions in unrelated outreach tables; `terms_acceptances` RLS without policy. VERIFIED (advisor output) |
| Frontend | Token kept in memory, `credentials: "omit"`, server enforces all authorization; UI only displays. Lint/type-check/build NOT RUN (npm registry blocked). Syntax-only check done earlier |

## Vulnerabilities / weaknesses found and fixed (details in VULNERABILITY_FIXES.md)
V-1 wrong-IP cycling unthrottled · V-2 JWKS refresh amplification · V-3 failed-auth throttle skipped without trusted IP · V-4 ambiguous duplicate proxy header · V-5 IPv4-mapped IPv6 mismatch (availability).

## Open items (not fixed here; require a decision or access)
- **O-1 (High, deployment): customer IP enforcement rests on `CF-Connecting-IP`.** It is safe only if the Render origin cannot be reached except through Cloudflare. Render's public documentation I could reach does not state this guarantee; I cannot test it from this environment. Until confirmed, treat customer IP restriction as defence in depth. Action: ask Render support to confirm in writing, or add an independent control.
- **O-2 (Medium): limiters are process-local** (reset on restart/idle spin-down of the free-plan single instance; not shared across instances). Acceptable for one instance; revisit before scaling.
- **O-3 (Medium): `PUT /auth/password` needs only a valid token** (no current-password re-check) and does not revoke other sessions. A stolen token could change the password. Needs a design decision (re-authentication via Supabase).
- **O-4: MFA is disabled for the Super Admin by owner decision; leaked-password protection is off.** Password is the only factor for an any-IP admin. Rotate the password shared in chat.
- O-5 (Info): FastAPI docs/OpenAPI are public by default (not disabled).
- O-6 (Low): `allow_headers=["*"]`.
- O-7: Supabase sign-in rate limits and the public-signup setting are not readable with the available tools (UNVERIFIED). If signup were enabled, a new user gets role `user` and no `allowed_ip`, so the API denies it (fail closed).

## Not independently verified
- Another reviewer reported 320/320 real-pytest passes; I could not install pytest/FastAPI here and did not reproduce it.
- Vercel configuration: BLOCKED (scope consent not granted to this session).
- Statements in `README.md` / `IMPLEMENTATION_STATUS.md` on `main` about features not present in code were not relied upon.
- No live or production test was performed; nothing was deployed.

## Conclusion
No flaw was found that lets a customer bypass IP restriction or lets any client obtain admin rights, **assuming** the CF-Connecting-IP trust model holds (O-1). The branch is suitable for PR review. Do not deploy until the real test suite has been run in a full environment and O-1 is confirmed or consciously accepted.
