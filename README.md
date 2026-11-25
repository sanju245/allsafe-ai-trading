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
| /forgot-password | Request a password reset email | Public |
| /set-password | Password setup or reset | One-time email link |
| /privacy | Account request data handling | Public |

## Current behavior

- The analysis engine is a deterministic five-check signal rule over confirmed candles. It returns BUY, SELL, WAIT, or DATA_UNAVAILABLE according to the engine rules.
- Each regular 15-minute session can confirm its first BUY above the 09:15 opening high and its first SELL below the opening low independently. Filtered or warming-up candidates remain eligible on later completed closes through the 14:15 IST candle. An emitted side stays suppressed for the rest of the session.
- The signed-in terminal provides completed Upstox 15-minute NIFTY 50 and BANK NIFTY charts for a selectable 1–30 calendar-day range. This history is separate from the selected provider's live 15-minute chart.
- A full chart can show reference entry, stop-loss and 2R target lines for any visible confirmed opening-range signal. Entry is the signal candle's market close. Stop-loss is the opposite edge of the opening range, and the target is twice that price distance in the signal direction. The first breakout's result and the numeric opening range remain visible in the decision details.
- The landing page reads the API's verifiable NSE schedule via `/health?calendar=1`. Future years use an amber weekday schedule estimate until official holidays are recorded. Provider freshness is reported in the terminal.
- The current API exposes market-data analysis and account access. No broker order-placement route was found in the reviewed main source.
- Treat every signal as informational. It is not investment advice and can be wrong or delayed.

## Authentication policy

The landing page offers **Create account with us**. Applicants provide their name, date of birth, email, phone number, and WhatsApp number, then choose a password and verify their email with a code. The API records the observed source IP for abuse limiting and request auditing. The applicant receives a receipt and the administrator receives the application details. The password hash is stored separately in a private table while the application is pending. Approval in `/admin` creates the Auth account and emails a sign-in link. The customer signs in with the password they chose on the form. Earlier applications use a one-time setup link. Decline emails the decision and clears the pending password hash. The admin portal can resume interrupted approvals, retry decision emails, and remove stored applications. Deleting a customer login also removes its linked application.

Apply the tracked migrations in `supabase/migrations` before releasing changes to the API. Configure `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_FROM_EMAIL`, and `PUBLIC_SITE_URL` on the API service. The OAuth token must have the `gmail.send` scope for the sender account. Gmail API calls use HTTPS so they work on Render Free. Add `<PUBLIC_SITE_URL>/set-password` to the Supabase Auth redirect allowlist. Keep Supabase public self-signup disabled so administrators control account creation. Application details are accessible to the API service role and authenticated admins. Only the service role can access pending password hashes. Submissions and verification emails have process-local rate limits. A shared edge limit can enforce the same policy across multiple API instances.

For Gmail setup, enable the Gmail API in a Google Cloud project and create a Desktop OAuth client with only the `gmail.send` permission. Set the OAuth app's publishing status to **In production** before authorizing; a Testing refresh token expires after seven days. Run `python apps/api/scripts/authorize_gmail.py --credentials <downloaded-client.json> --output <private-file-outside-repo>` from the repository root, open its printed URL, and authorize the sender account. Move the four values from the generated file into the Render API service environment, then delete the local credentials and token files. Never commit or paste these secrets into chat.

The API verifies the Supabase token, profile, role, and active account status. Customers can sign in from any network. Legacy `profiles.allowed_ip` and request IP values remain in the database for historical reference and auditing; account authorization does not read or enforce them.

In **Admin → Customers → Sign-in history**, an active administrator can review up to ten successful portal sign-ins per customer, newest first in IST. The API links the new Supabase password session to the client IP observed by Render on the browser's account verification request. The history survives sign-out, keeps at most ten entries, and is deleted with the customer profile. Apply the sign-in history migrations before deploying the API.

In **Admin → Customers**, use **Warning** beside one customer or **Warn all customers** above the directory. Each warning appears in the recipient's dashboard and account. A broadcast covers the customer accounts present when it is sent. **Pause login** requires a reason, which the customer sees after entering valid credentials. A paused customer is blocked from protected features until an administrator chooses **Resume login**.

The public account form still uses the trusted `CF-Connecting-IP` value for request rate limiting and audit metadata. This check is independent of customer authentication. Source tests cover missing, malformed, comma-separated, and duplicate proxy headers.

The app restores sessions through a same-origin HttpOnly refresh cookie. **Account → Change password** requires the current password. After the change succeeds, AllSafe sends a confirmation to the account’s registered email using the configured Gmail sender. Sign-in also offers email recovery for active accounts. The API screens new passwords set through AllSafe against the padded Pwned Passwords database before updating an account.

## Telegram chart alerts

Signed-in customers can connect a private Telegram chat from **Account → Telegram alerts**. AllSafe sends the same neutral message for any new confirmed signal and links to the matching chart after login. Customers can disconnect in AllSafe or send `/stop` in Telegram.

To enable the feature on an existing deployment:

1. Create a bot in Telegram with [BotFather](https://t.me/BotFather). Apply the `telegram_signal_alerts` Supabase migration.
2. On the API, set `TELEGRAM_ALERTS_ENABLED=true` and `TELEGRAM_BOT_USERNAME`. Set `MARKET_DATA_PROVIDER` to the existing enabled live feed that should drive alerts.
3. Run one background worker from `apps/api` using the same Python build as the API and start it with `python -m app.telegram_worker`. Set `TELEGRAM_ALERTS_ENABLED=true`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and the HTTPS `PUBLIC_SITE_URL` on the worker. Keep the bot token in the worker's private environment. This bot uses long polling, so it needs a single poller and no webhook.
4. Sign in with a pilot AllSafe account, connect Telegram, and tap **Start**. Check that a fresh signal generates a neutral message and that the link opens the chart after login. The API live feed and delivery worker both need to stay running during market hours.

The API and chart share the confirmed-candle analysis. An outbox and separate worker handle Telegram delivery. Jobs expire two minutes after the candle closes. The worker retries explicit Telegram rate limits while the alert is current and avoids retrying ambiguous deliveries that may have reached Telegram.

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
