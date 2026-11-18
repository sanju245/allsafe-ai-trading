# 15-minute index charts and customer login audit

**Audit date:** 2026-11-19

**Scope:** NIFTY 50 and BANK NIFTY candles, separate chart tabs, indicator signals, and customer IP login restrictions.

## Findings and changes

- Live candles now use the 15-minute NSE session grid. The API defaults to `15m` and rejects other live candle intervals.
- The candle response combines validated historical bars with closed live bars, keeps a forming candle separate, and respects the requested history limit.
- Clicking either index name or its full-chart button opens `/chart/NIFTY50` or `/chart/BANKNIFTY` in a new tab. The larger page includes zoom and history navigation, the 15-minute chart, current signal, and UT Bot, EMA, RSI, MACD, and Supertrend readings.
- Upstox historical NIFTY 50 and BANK NIFTY chart headings also open the larger chart in a new tab and select Upstox for the live chart and indicator readings.
- BUY/SELL history uses the existing five-indicator decision engine and only complete, confirmed candles. Invalid, incomplete, or gapped series do not create historical markers. A signal may be `WAIT` or unavailable when its rules or feed do not support a confirmed signal.
- Customer sign-in and protected API access no longer compare the request IP with `profiles.allowed_ip`. Login, account requests, admin customer management, and account pages no longer ask for or manage a customer IP. Existing database IP fields are retained for compatibility; the source IP collected at account-request submission is used for abuse limiting and request auditing and is described in the privacy policy.
- The terminal now labels the interval and feed state, explains that the separate tab contains the larger chart, and states that signals are educational and do not place orders.

## Verification

| Check | Result |
| --- | --- |
| API test suite | 294 passed |
| Web test suite | 28 passed |
| ESLint | Passed |
| TypeScript typecheck | Passed |
| Production web build | Passed on Next.js 16.4.6; `/chart/[symbol]` emitted as a dynamic route |
| npm dependency audit | 0 vulnerabilities |
| Diff whitespace check | Passed; only a Windows line-ending notice for `apps/web/tsconfig.json` |
| Indicator strategy diff | None; the committed five-indicator decision engine is unchanged |

API fixture coverage checks the 15-minute default, rejection of `5m`, historical/live candle merge, separate forming candle, Upstox historical data, and aligned indicator history. Web tests check that both index names open separate chart tabs and that the dashboard shows the latest decision.

## Live-data limits

The checks above use repository fixtures and build/test tools. They do not establish that a real Groww or Upstox feed is connected or that a production customer session can fetch current prices. Live candle and signal availability still depends on the selected provider being configured, a valid customer session, and complete confirmed data. The chart identifies unavailable or stale data rather than treating it as a current signal.

## Follow-up repairs from the production audit

- Both index charts reuse an active browser session when opened from the terminal. The chart verifies the account with the API and joins sign-out across linked tabs. An expired invitation leads to sign-in and returns to the requested chart and history range.
- The chart provider selector updates the URL and requests the selected provider immediately. Upstox historical chart links keep their selected date range and can show completed candles when the live request is unavailable.
- A failed refresh clears the chart's current decision and live markers. The API only marks a BUY or SELL signal current when the feed is fresh and the decision comes from the latest closed candle in the current session.
- The Upstox runtime loads completed 15-minute history for both indices on startup. The historical adapter uses the intraday endpoint for the current session and the historical endpoint for earlier sessions.

The browser audit used a Next.js production build, real separate browser tabs, and synthetic sign-in and candle responses. It verified the two chart tabs after one sign-in, 15-minute candles, BUY and SELL markers, zoom, the historical range, provider switching, refresh error handling, and group sign-out. The test uses a disposable browser profile and can also verify the browser build on the public deployment. See `apps/web/scripts/browser-chart-audit.mjs`.
