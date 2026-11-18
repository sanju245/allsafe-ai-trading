# Upstox 15-minute chart handover

Date: 2026-11-19
Branch: `codex/upstox-15m-chart-2026-11-19`

## Finding

The current terminal supports choosing Groww or Upstox for live 5-minute candles, but its in-memory live chart keeps only the latest 60 candles. That is roughly five trading hours and does not reliably cover earlier sessions. The API had no Upstox historical-candle route. This history branch adds a separate read-only path for completed 15-minute candles; the documented interval limit is one month.

## Change

- Added an authenticated API endpoint for Upstox 15-minute historical candles for NIFTY 50 and BANK NIFTY, with a selectable 1–30 calendar-day window.
- Added a history chart to the signed-in terminal. It shows completed candles oldest-first, has date labels and horizontal scrolling, and clearly labels the data as historical.
- Kept the existing provider selector and live 5-minute charts separate.
- Reused the existing server-only `UPSTOX_ACCESS_TOKEN` configuration. The browser receives candles but never the provider token. Provider errors are sanitized, and the request identifies the app using the same Upstox client User-Agent as its existing feed connector.
- Updated Next.js and its matching ESLint configuration to 16.4.6 after the prior installed version caused the production build to stop on a framework security block.
- No order-placement, account trading, or autonomous trading behavior was added.

## Files

- `apps/api/app/providers/upstox_history.py`
- `apps/api/app/routers/upstox_history.py`
- `apps/api/app/main.py`
- `apps/api/.env.example`
- `apps/api/tests/test_upstox_history.py`
- `apps/api/tests/test_upstox_history_api.py`
- `apps/api/tests/test_cors.py`
- `apps/api/tests/test_market_data_api.py`
- `apps/web/src/components/Upstox15mHistory.tsx`
- `apps/web/src/app/terminal/page.tsx`
- `apps/web/tests/customerPortal.test.mjs`
- `apps/web/package.json`
- `apps/web/package-lock.json`
- `README.md`
- `PROJECT_STATUS.md`
- `docs/UPSTOX_15M_CHART_SETUP.md`
- `docs/UPSTOX_15M_CHART_HANDOVER_2026-11-19.md`

## Checks

- API: `300 passed`; one third-party Starlette/httpx deprecation warning.
- Web: `27 passed`.
- TypeScript: passed.
- ESLint: passed.
- Next production build: passed with Next.js 16.4.6.
- `git diff --check`: passed.

## Release and live-data status

This feature is live in production from commit `d33fcccefa1b21c82b235bd4defaff94c472ad76` (2026-11-19). Render deploy `dep-dbuvis2vcj2c73a7t2c0` is `live`; Vercel production deployment `dpl_3MXUxYZkqb4NkrVrDAWBe4gtabHg` is `READY` and serves the production aliases. Post-deploy checks returned HTTP 200 from Render `/health`, found the new route in `/openapi.json`, and got HTTP 401 from the route without a sign-in token. No authenticated Upstox request was made, so actual `UPSTOX_ACCESS_TOKEN` validity and candle availability remain unverified. If that variable is missing in Render, add it to the API service there; never put it in Vercel or a `NEXT_PUBLIC_*` variable.

The implementation follows the [Upstox Historical Candle V3 documentation](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/) and [Analytics Access Token documentation](https://upstox.com/developer/api-documentation/analytics-token/).
