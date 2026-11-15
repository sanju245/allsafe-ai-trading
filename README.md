# AllSafe AI Trading

A read-only Indian index market-analysis and decision-support application for NIFTY 50 and BANK NIFTY. The API does not place broker orders or trade autonomously.

## Application routes

| Route | Purpose | Access |
|---|---|---|
| / | Public landing page; sample prices and signals are illustrative | Public |
| /login | Customer sign-in | Public |
| /terminal | Market dashboard | Active signed-in account |
| /account | Account details and password change | Active signed-in account |
| /admin/login | Administrator sign-in | Public sign-in route |
| /admin | Customer-access administration | Active admin account |
| /what-we-done | Explanation of the analysis workflow | Public |

## Current behavior

- The analysis engine is a deterministic five-check signal rule over confirmed candles. It returns BUY, SELL, WAIT, or DATA_UNAVAILABLE according to the engine rules.
- Landing-page price, candle, decision, and risk figures are static illustrations. They are not live quotes, current signals, or enforced account risk limits.
- The current API exposes market-data analysis and account access. No broker order-placement route was found in the reviewed main source.
- Treat every signal as informational. It is not investment advice and can be wrong or delayed.

## Authentication and IP policy

The API verifies the Supabase token, profile, role, and active account status. Active administrators do not use the customer IP allowlist. Active customers require an exact match to their configured single-host public IP.

This review branch also lets an active administrator continue when the production proxy does not provide a valid client IP; the returned current-IP field is null in that case. Customers still fail closed when the API cannot verify their IP. The production deployment does not yet contain this local review change.

Production IP detection trusts the CF-Connecting-IP header. Testing that direct-origin traffic cannot spoof that header remains outstanding, so the customer IP rule has not been independently verified against the live network edge.

The local review environment has no Supabase URL or anon key configured. Sign-in was not attempted.

## Trading safety

The reviewed API is read-only and does not place broker orders. No live stream or production credentials were started or used during this audit. Keep LIVE_STREAM_ENABLED=false for local tests. Do not add execution or autonomous-order behavior without a separately reviewed change and explicit approval.

## Local checks

Frontend, from apps/web/:

    npm test
    npm run typecheck
    npm run lint
    npm run build

Backend, from apps/api/:

    .venv\Scripts\python.exe -m pytest -q

Set LIVE_STREAM_ENABLED=false while testing. Browser configuration uses NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, and NEXT_PUBLIC_API_BASE_URL. The API service-role key and provider credentials belong only in the backend environment. Never put them in a NEXT_PUBLIC_* variable or commit them.

## Review status

The production Vercel and Render deployments point at GitHub main commit a20cb3bb20686c6eb574b00d2732a9c6007ffeba. The current landing, terminal, calendar, copy, and admin-IP changes are on the local branch codex/landing-portal-audit-2026-11-15. They have not been pushed, merged, or deployed.
