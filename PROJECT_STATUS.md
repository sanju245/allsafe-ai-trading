# Project Status

Updated 2026-11-16. This file describes the release implementation and current local branch. Live deployment records are tracked separately in the release handover; a source build alone does not prove production health.

## Application

- Public landing page at /, educational explanation at /what-we-done, signed-in terminal at /terminal, customer account at /account, customer sign-in at /login, and verified administrator portal at /admin with /admin/login.
- The landing preview is static and contains no fabricated market prices or trade sizing. The backend engine performs five deterministic checks over confirmed candles.
- Market-data failures clear old display values. Historical data is labeled not current. Account-service startup has a bounded wait with plain-language feedback.

## Access policy

- A valid Supabase token, matching profile identity, supported role, and active account are required.
- Customer and administrator access are not gated by an IP allowlist. Existing `profiles.allowed_ip` values are ignored and kept only for database compatibility.
- The current code branch `codex/customer-login-ip-audit-2026-11-16` adds an admin-only successful sign-in history. It records the source IP only when the trusted edge header is available; missing or invalid IP metadata does not block sign-in. History begins only after the new database migration and matching API/web changes are deployed, and prior logins are not reconstructed.
- These IP policy and history changes are local to the named branch and have not been deployed to production. The live behavior described in prior deployment records remains until deployment is separately approved.
- No email string in frontend code grants an admin role. Admin ownership is stored in Supabase and was verified through an authorized database session.
- Live Supabase inspection verified the single-admin index and an RLS admin helper requiring both the admin role and active status.
- Logout clears local session state immediately; stale authentication replies cannot restore it. Admin directory access denial clears customer rows and rechecks account access.

## Live observations before release

- Render /health returned HTTP 200 after its free instance woke up. The free tier can take more than 50 seconds on a cold start.
- Through the public Render hostname, forged CF-Connecting-IP was rejected at Cloudflare; forged X-Forwarded-For did not change the detected address.
- An invalid Groww authentication-mode setting was corrected to the API-key/secret flow for the next backend deployment. Existing provider secrets were not copied into source.
- Account-role changes were performed using a guarded transaction after explicit confirmation, with private rollback records. Passwords were not changed.
- No password-backed production login test was performed by the agents because the account's existing password was not supplied. Role/authorization logic is covered by local regression tests.

## Verification and safety

Run frontend tests, typecheck, lint, and production build from apps/web. Run the full backend suite from apps/api with LIVE_STREAM_ENABLED=false. Exact command outputs, tested commit, screenshots, deployment results, and outstanding provider limits belong in the private release handover.

No broker order-placement path was added. The application remains supervised, read-only market analysis. No autonomous or live orders are authorized by this release.
