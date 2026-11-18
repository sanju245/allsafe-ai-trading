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
| /set-password | Password setup after approved invitation | One-time email link |
| /privacy | Account request data handling | Public |

## Current behavior

- The analysis engine is a deterministic five-check signal rule over confirmed candles. It returns BUY, SELL, WAIT, or DATA_UNAVAILABLE according to the engine rules.
- The signed-in terminal provides completed Upstox 15-minute NIFTY 50 and BANK NIFTY charts for a selectable 1–30 calendar-day range. This history is separate from the selected provider's live 5-minute chart.
- Landing-page price, candle, decision, and risk figures are static illustrations. They are not live quotes, current signals, or enforced account risk limits.
- The current API exposes market-data analysis and account access. No broker order-placement route was found in the reviewed main source.
- Treat every signal as informational. It is not investment advice and can be wrong or delayed.

## Authentication policy

The landing page offers **Create account with us**. Applicants provide their name, date of birth, email, phone number, and WhatsApp number. The API records the source IP it observes for abuse limiting and request auditing; applicants do not need to provide it, and it is not used to authorize an account. A successful request is stored privately and receives a thank-you email; no Auth account exists until an administrator approves it in `/admin`. Approval creates the account and emails a one-time password setup link. Decline emails the decision without creating an account. The admin portal can retry a failed decision email.

Apply `supabase/migrations/20261116000000_account_requests.sql` before releasing the API. Configure `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM_EMAIL`, and `PUBLIC_SITE_URL` on the API service. The OAuth token must have the `gmail.send` scope for the sender account; Gmail API calls use HTTPS so they work on Render Free. Add `<PUBLIC_SITE_URL>/set-password` to the Supabase Auth redirect allowlist. Keep Supabase public self-signup disabled; the API creates an invitation only after approval. Request details are restricted to the API service role and authenticated admins. A process-local IP rate limit applies to submissions; use a shared edge limit for multiple API instances.

For Gmail setup, enable the Gmail API in a Google Cloud project and create a Desktop OAuth client with only the `gmail.send` permission. Set the OAuth app's publishing status to **In production** before authorizing; a Testing refresh token expires after seven days. Run `python apps/api/scripts/authorize_gmail.py --credentials <downloaded-client.json> --output <private-file-outside-repo>` from the repository root, open its printed URL, and authorize the sender account. Move the four values from the generated file into the Render API service environment, then delete the local credentials and token files. Never commit or paste these secrets into chat.

The API verifies the Supabase token, profile, role, and active account status. Customers can sign in from any network. Legacy `profiles.allowed_ip` and request IP values remain in the database for historical reference and auditing; account authorization does not read or enforce them.

The public account form still uses the trusted `CF-Connecting-IP` value for request rate limiting and audit metadata. This check is independent of customer authentication. Source tests cover missing, malformed, comma-separated, and duplicate proxy headers.

The local review environment has no Supabase URL or anon key configured. Sign-in was not attempted.

## Trading safety

The reviewed API is read-only and does not place broker orders. Local checks do not start production feeds. Keep both feed flags false for local tests. Do not add execution or autonomous-order behavior without a separately reviewed change and explicit approval.

The customer market dashboard supports a server-managed market-data source selector for Groww and Upstox. Groww uses `LIVE_STREAM_ENABLED` and the existing `GROWW_*` settings. Upstox V3 live streaming remains separately disabled unless `UPSTOX_LIVE_STREAM_ENABLED=true`; the same server-only `UPSTOX_ACCESS_TOKEN` is used for the historical 15-minute chart. Never expose the token in browser settings or logs. Live status is reported only after a connected feed produces fresh, validated updates. Confirm that provider and exchange permissions cover displaying a shared feed to customers before enabling either source for customer distribution.

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
