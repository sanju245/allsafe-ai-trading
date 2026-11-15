# AllSafe AI Trading — Current Project Status

Verified: 2026-11-15 (Asia/Kolkata)
Repository: sanju245/allsafe-ai-trading
Default branch and production source: main at a20cb3bb20686c6eb574b00d2732a9c6007ffeba
Local review branch: codex/landing-portal-audit-2026-11-15
Production merge or deployment: none from this review

## Current findings

- Production main serves the authenticated market dashboard at /. The public landing page was only on non-main branches.
- The feature/landing-page branch still contains the reported invalid h: 24346 style property. The later audit branch removes it but has integration mismatches with the current auth context and refers to a marketData.ts test source that is absent from main.
- The Dropbox website handover dated 2026-11-14 describes commit 2280cfd on the audit branch. The current remote branch head is 097cc6e, so the handover is not a snapshot of the current remote tree.
- The Nov 15 Dropbox Render repair report and 063d070 patch are not in the current GitHub branch list. The live Render service still deploys main at a20cb3b. The patch was not applied.
- Active admins already bypass the customer allowed_ip comparison in production main when the request IP is successfully resolved. The current review branch removes the remaining dependence on client-IP parsing for active admins while keeping customer verification fail-closed.
- Production main trusts CF-Connecting-IP for customer IP matching. Direct-origin proxy-header spoofing has not been independently tested; PR #7 remains a draft and explicitly lists this as outstanding.
- Main has no verified separate AI-agent service, multi-timeframe analysis, or account-specific risk-size calculation. The public landing copy now labels its market and risk panels as static examples and describes the current deterministic rule engine.
- The market calendar is based on the published NSE 2026 schedule, includes the Jan 15 addendum, uses the announced Nov 8 Muhurat session hours, and fails closed outside verified calendar bounds.

## Platform status

- GitHub: 11 remote branches. PRs #1–#6 and #8 are merged; PR #7 is open as a draft. The current review branch is local only.
- Vercel: the allsafe-ai-trading project has a READY production deployment for main/a20cb3b. Production routes /, /login, /account, /admin/login, and /admin return HTTP 200; /terminal currently returns HTTP 404 because the local route move has not been deployed. The duplicate project named allsafe is connected to a different repository. Environment values were not exposed.
- Render: allsafe-ai-api is a live service on main, root directory apps/api, one free-tier Singapore instance, and no configured health-check path. A direct GET /health request timed out after 15 seconds from this audit environment; HTTP health is not confirmed.
- Supabase: no live database or auth connector was available. Current users/roles, applied migrations, and live sign-in behavior were not verified. The local web environment has no Supabase URL or anon key.
- Dropbox: the Nov 15 final handover, auth 403 root-cause report, remaining blockers, Render configuration audit, security review, and Nov 14 website handover were read. The Render repair report claims commit 063d070, which is absent from current remote refs. Its claims about live environment values and tests remain unverified against the deployed source.

## Local review changes

- Added a public landing page at / and moved the existing authenticated dashboard to /terminal.
- Kept the existing Supabase auth provider and customer/admin route guards; no sign-in credentials were submitted.
- Allowed an active admin to complete account verification when the proxy client-IP value is missing or invalid; client_ip is then null. Customers still require a valid client IP and exact allowlist match.
- Replaced unsupported AI-agent, live-feed, account-risk, and multi-timeframe marketing claims with source-verified descriptions and static-data disclosures.
- Corrected calendar details against official NSE circulars.
- Made initial market-clock and market-status rendering deterministic to avoid a server/client hydration mismatch.
- Added a web test command and regression coverage for the landing-page copy and calendar logic.
- No database migrations, production configuration, provider credentials, broker routes, or order behavior were changed.

## Verification

- Backend with LIVE_STREAM_ENABLED=false: 263 passed; one Starlette/httpx deprecation warning.
- Focused backend security/auth suite: 24 passed; one deprecation warning.
- Frontend tests: 6 passed.
- Frontend typecheck, lint, and Next.js production build: passed.
- Built routes: /, /login, /account, /admin, /admin/login, /terminal, and /what-we-done.
- Production route checks are observations of the existing main deployment, not the local review branch.

## Remaining operational checks

- Verify the Supabase project binding, current active admin profile, and applied migrations through an authorized Supabase session.
- Verify the customer IP header trust path through Render's public edge and direct origin using test accounts, and decide whether the separate PR #7 hardening is suitable.
- Investigate the Render /health timeout and configure an appropriate health-check path after review.
- Confirm Vercel production and preview environment bindings without exposing secret values.
- Review the local branch and handover package. Do not push, merge, or deploy without explicit approval.
