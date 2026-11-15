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

Active administrators can continue when the production proxy does not provide a valid client IP; the returned current-IP field is null in that case. Customers still fail closed when the API cannot verify their IP.

Production IP detection trusts one valid CF-Connecting-IP header. A live check through the public Render hostname rejected a forged CF-Connecting-IP and ignored forged X-Forwarded-For. These checks cover the tested public route; source tests also cover missing, malformed, comma-separated, and duplicate headers.

The local review environment has no Supabase URL or anon key configured. Sign-in was not attempted.

## Trading safety

The reviewed API is read-only and does not place broker orders. Local checks do not start production feeds. Keep both feed flags false for local tests. Do not add execution or autonomous-order behavior without a separately reviewed change and explicit approval.

The customer market dashboard supports a server-managed market-data source selector for Groww and Upstox. Groww uses `LIVE_STREAM_ENABLED` and the existing `GROWW_*` settings. Upstox V3 is separately disabled unless `UPSTOX_LIVE_STREAM_ENABLED=true` and the server-only `UPSTOX_ACCESS_TOKEN` are configured. The Upstox credential is an Analytics token and must never be exposed in browser settings or logs. Customers can choose a source, but a source reports live only after its connected feed produces fresh, validated updates. Confirm that the provider and exchange permissions cover displaying a shared feed to customers before enabling either source for customer distribution.

## Local checks

Frontend, from apps/web/:

    npm test
    npm run typecheck
    npm run lint
    npm run build

Backend, from apps/api/:

    .venv\Scripts\python.exe -m pytest -q

Set LIVE_STREAM_ENABLED=false and UPSTOX_LIVE_STREAM_ENABLED=false while testing. Browser configuration uses NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, and NEXT_PUBLIC_API_BASE_URL. The API service-role key and provider credentials belong only in the backend environment. Never put them in a NEXT_PUBLIC_* variable or commit them.

## Release records

See PROJECT_STATUS.md for the current implementation and verification limits. Historical audit and completion reports describe earlier revisions; they do not establish the current deployment or account state. Keep exact account transfer and rollback records in the private operational handover.
