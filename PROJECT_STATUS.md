# Project Status

Updated 2026-11-19. This file describes the released implementation. Live deployment records are tracked separately in the release handover; a source build alone does not prove production health.

## Application

- Public landing page at /, educational explanation at /what-we-done, signed-in terminal at /terminal, customer account at /account, customer sign-in at /login, and verified administrator portal at /admin with /admin/login.
- The landing preview is static and contains no fabricated market prices or trade sizing. The backend engine performs five deterministic checks over confirmed candles.
- Market-data failures clear old display values. Historical data is labeled not current. Account-service startup has a bounded wait with plain-language feedback.
- Production includes authenticated Upstox Historical Candle V3 charts for completed 15-minute NIFTY 50 and BANK NIFTY candles, with a selectable 1–30 calendar-day range. This extends the Groww/Upstox live 5-minute selector with a separate historical view.
- The production chart reads `UPSTOX_ACCESS_TOKEN` on the API service only. The route and deployment are live, but no authenticated historical request was made, so token validity and returned candle data remain unverified.

## Access policy

- A valid Supabase token, matching profile identity, supported role, and active account are required.
- Active administrators can access from any IP, including when proxy client-IP metadata is unavailable.
- Active customers require one valid client IP and exact configured IP match. Missing, invalid, comma-separated, and duplicate proxy-IP headers fail closed for customers.
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

Upstox 15-minute history was released to production from commit `d33fcccefa1b21c82b235bd4defaff94c472ad76` on 2026-11-19. Render reported the deploy live; Vercel reported the production deployment ready.
