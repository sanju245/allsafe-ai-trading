# Project status

Updated 25 November 2026. This page describes the current source. GitHub and hosting release records identify which revision is live.

## Market terminal

- NIFTY 50 and BANK NIFTY use completed 15-minute candles for decisions. Live quotes and forming candles are shown separately. The Upstox historical chart supports a 1–30 day range.
- Full charts show the first opening-range attempt and the numeric opening range. Confirmed markers can display reference entry, stop-loss and 2R target overlays.
- The landing page uses the NSE schedule from the API. Before the exchange's future-year holiday calendar is recorded, weekday hours are labeled as estimates.
- The application provides read-only analysis and does not place orders.

## Accounts

- Supabase token verification, role, and active account status protect customer and admin routes. Customers and administrators can sign in from any network. The application form records the source IP for rate limiting and auditing.
- Sessions restore after reload through a same-origin HttpOnly refresh cookie. Password changes require the current password. Invite and recovery links use verified email proof.
- The admin queue supports paging, resuming interrupted approvals, retrying decision emails, sending replacement setup links, and removing stored applications.
- The versioned Supabase migrations create the profile guard and the account request workflow. The launch-readiness schema is required for the current API.

## Verification

Run the API suite with both live streams disabled. Run frontend tests, lint, a production build, and the browser chart test with fixtures. Confirm the release SHA on Vercel and Render and check the production endpoints before announcing deployment. Verify third-party email delivery separately from simulated account workflows.
