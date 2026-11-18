# Final website and project audit

**Audit date:** 2026-11-19 04:21 IST (2026-11-18 22:51 UTC)
**Repository:** `sanju245/allsafe-ai-trading`
**Production release:** web `0125822` (READY); API health reports version `0.2.0` (READY response; current Render commit SHA not verified)
**Overall:** the production website and API are reachable, and the automated frontend and backend checks pass. The chart code includes the requested candle labels and seven-day history. Follow-up items are the previously observed account-approval failure (a fix is merged to GitHub `main`, but the live API workflow has not been re-tested), the roughly one-minute sign-in verification wait, and the missing Nov 18 session in the seven-day chart data. The current chart has no confirmed BUY/SELL events, so its label renderer has nothing to draw.

## Highest-priority findings

### Medium — Previously observed account-approval failure needs live confirmation

In the earlier read-only admin browser session, the account-request queue showed a request still marked **pending** and the message **“Account approval failed. Please retry.”** I did not approve, decline, retry, or otherwise change the request. No personal details are recorded in this report.

Since that observation, GitHub `main` and the READY Vercel production deployment advanced to commit `0125822`, titled “Fix account request approval and email alerts.” The API's public health check now responds with status `ok` and version `0.2.0`, but it does not identify the Render commit. No approval was retried, so the prior 502 is now an unresolved historical observation rather than a verified current failure. Confirm which commit is running on Render and safely re-test with a test request before considering this resolved.

### Medium — Sign-in can look stalled for up to roughly a minute

Customer and administrator sign-in share the same flow. After the identity provider accepts credentials, the browser asks the API to verify the account profile. That request has a **65-second timeout**; the initial identity-provider request has a separate **12-second timeout**. The button remains disabled and says “Verifying account…” while this work runs. The page already explains that a sleeping account service can take about a minute to start.

This audit confirmed the wait in code, not the duration of a real credential-backed sign-in; no customer password was supplied. The API is on Render's free, single-instance plan, which is consistent with a cold-start delay. Keep the account service warm or move account verification to an always-on service, then measure the full customer and admin sign-in path.

### Medium — No labels appear because the visible history has no confirmed BUY/SELL events

The production chart was inspected in an existing signed-in browser session. It reported **WAIT**, **No signal** for the primary trigger, and **0 confirmed BUY/SELL signals** across 75 candles. The latest evaluated candle was November 17 at 15:15 IST. Its explanation says the late-session breakout was ignored because new signals stop after 14:15. The marker renderer only draws a label when a candle has a confirmed BUY or SELL event; it does not label WAIT. So the missing labels on this screenshot are not a rendering failure.

The seven-day history is also incomplete: the latest candle shown is November 17 at 15:15 IST, with no November 18 candles. NSE's official 2026 holiday list names November 10 and November 24 as November holidays, not November 18 ([NSE trading-holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf)); this indicates a normal trading session was omitted. The historical API requests returned HTTP 200, but the page has only 75 candles from November 13, 16, and 17. The source-level marker logic cannot draw signals for missing candles. The API response data or provider's historical result needs investigation; request logs alone do not show why November 18 is missing.

#### Live candle-label path audit

The implementation path is connected end to end: the chart polls the live candle endpoint every 15 seconds, requests signal history, merges those decisions with the displayed candles by timestamp, and draws a green **Buy** marker below a confirmed signal candle or a red **Sell** marker above it. The API excludes forming candles from signal evaluation, and the chart also suppresses markers on forming or incomplete candles. A `WAIT` decision correctly has no marker. A current signal is accepted only when the quote is live and fresh; previous confirmed signals can still be shown from the returned history.

Expected live behavior: after a 15-minute candle is confirmed, a qualifying BUY or SELL should appear on its matching candle on the next successful chart refresh (normally within 15 seconds). No label should appear while a candle is still forming, when the decision is WAIT, or when the API cannot validate a continuous candle series. The signal rules also stop accepting new 15-minute breakouts after the configured 14:15 candle-time cutoff. The production chart was inspected while the market was closed, so this audit did not observe an actual live label during an open session.

No focused frontend test currently asserts that a BUY/SELL decision becomes an SVG candle marker. Existing API coverage exercises live candle and signal-history responses, and the production chart source confirms the marker renderer, but a browser assertion for the visible marker is still missing. The current screenshot's zero-signal result is consistent with the renderer; the missing November 18 candles and absence of an open-session observation mean the production live-data-to-label path is not fully validated.

### Medium — Market-hour feed freshness remains unverified

The inspected chart showed **Feed: Closed**, as expected at the early-morning audit time, and the freshest available candle was still November 17. This does not verify that a live quote or new 15-minute candle arrives during a market session. The API health endpoint only checks that the service responds. Render logs show the historical and live chart requests returned HTTP 200; no response payload or upstream candle-fetch detail was recorded.
### Low — Local backend virtual environment is incomplete

Running the backend suite with `apps/api/.venv` stopped before collection because that environment lacks `jwt`, even though the package is declared in `apps/api/requirements.txt`. Running the same suite with the installed system Python 3.13 succeeded: **306 passed**. It emitted one Starlette/httpx deprecation warning. Rebuild or synchronize the project virtual environment so the documented local command works consistently.

### Low — The browser chart audit helper has stale selectors

`apps/web/scripts/browser-chart-audit.mjs` expects older chart text and uppercase accessible labels. The current page uses “Signal confirmation checks” and title-case “Buy”/“Sell” marker labels. The helper's Playwright dependency is not installed in this checkout, so I did not run it. Update those selectors before relying on that script for a browser-level pass of the latest release.

## Feature inventory reviewed

- **Public:** landing page, Indian-time clock and market-session status, account-request submission form, privacy information, and the workflow explanation page.
- **Customer:** sign-in, protected dashboard, provider selection, quote and 15-minute candle panels, separate forming-candle display, historical candles, full-chart tabs, zoom and older/newer/latest navigation, account status, password change, and sign-out across linked chart tabs.
- **Chart history:** NIFTY 50 and BANK NIFTY; seven-day history by default; selectable 1-, 7-, 14-, and 30-day ranges on the dashboard; timestamps joined to the matching candle; stale or unavailable data shown as such.
- **Administrator:** admin sign-in, account-request queue, approve/decline and failed-email retry controls, customer creation, search/status filtering, pause/resume, and customer deletion. The protected operations are also enforced by the API.
- **API:** service health, instrument/timeframe metadata, supplied-candle validation, historical 15-minute candles, live provider/status/quote/candle/forming-candle reads, account profile/password operations, account-request submission, and admin account operations. No order-placement endpoint was found.
## Surface-by-surface results

| Surface | Audit result | Evidence and limits |
| --- | --- | --- |
| Landing page | Reachable; content and source tests pass. | Production route returned HTTP 200. The market preview is illustrative, not a live quote. The public flow includes an account-request form, market-session display, and privacy/how-it-works pages. No live request was submitted. |
| Customer sign-in | Page loads; shared sign-in flow is covered by tests. | Production route returned HTTP 200. The delay described above is a code-defined maximum, not a measured production login time. No customer credential was used. |
| Customer terminal | Protected route and feature wiring pass local checks. | Route returned HTTP 200. An existing signed-in chart session was inspected read-only; it showed a closed feed and last candle Nov 17 at 15:15 IST. No fresh market-hour data was available. |
| Customer account and password setup | Routes load and are included in frontend checks. | `/account` and `/set-password` returned HTTP 200. Password change and invitation-link completion were not exercised against a real account. |
| Admin sign-in and portal | Portal loaded in an existing authenticated browser session; account directory and request queue rendered. | Routes returned HTTP 200. Admin API data endpoints reject requests without a token. The pending-request approval failure is the live functional issue above. No create, pause, resume, delete, approve, decline, or retry action was performed. |
| Index charts | Marker code is deployed, but no marker appears when the decision output contains no BUY/SELL event. | The inspected production chart showed 0 confirmed signals across 75 candles and WAIT on its latest candle. Its data ended Nov 17 and omitted the Nov 18 session. This is a decision/data availability issue in the displayed range, not evidence that marker drawing failed. |
| API and account controls | Liveness, API schema, access denial, and CORS checks passed. | `/health` and `/openapi.json` returned HTTP 200; the production-site CORS preflight returned HTTP 200 with the expected origin. Protected endpoints returned HTTP 401 without a token. The app remains read-only; no broker order-placement route was found in the reviewed API. |

All of these production pages returned HTTP 200: `/`, `/login`, `/admin/login`, `/admin`, `/terminal`, `/account`, `/set-password`, `/chart/nifty50`, `/chart/banknifty`, `/privacy`, and `/what-we-done`. A successful page response does not mean the protected account or market data was returned; the API checks above separately confirmed those routes require authentication.

## Signal-history performance record

The repository's earlier 15-minute evaluation records **15 correct directional outcomes out of 22 signals (68.2%)** for October 19–November 18, 2026: NIFTY 50 scored 7/11 (63.6%) and BANK NIFTY 8/11 (72.7%). It scores direction over a fixed one-hour horizon, entering at the next bar's open and exiting at the fourth bar's close.

Treat this as an exploratory historical result, not a guarantee or profitability measure. There were only 11 signals per index; the rule was selected after examining this same period; the recorded confidence intervals include true performance below 60%; and the score excludes fills, fees, slippage, and taxes. The raw OHLC file is not in the repository, so this audit did not independently recalculate that score. The existing methodology and limitations are in [`docs/INDICATOR_AUDIT_15M_2026-11.md`](INDICATOR_AUDIT_15M_2026-11.md).

## Verification performed

- Production web routes: all 11 listed routes returned HTTP 200.
- Production API: `/health` and `/openapi.json` returned HTTP 200; protected data/account endpoints returned HTTP 401 without credentials; CORS preflight passed.
- Vercel: production deployment is **READY** on commit `0125822` from GitHub `main`; the production domain returned HTTP 200. No Vercel runtime-error clusters were reported in the last 24 hours.
- Render: public `GET /health` returned `status: ok`, `environment: production`, and version `0.2.0` at 22:51 UTC. The public health response does not include a commit SHA; the current Render deployment was not checked in the dashboard during this report refresh.
- Frontend tests: **32 passed, 0 failed**.
- Backend tests: **306 passed** under system Python 3.13; the repository virtual environment could not collect them because `jwt` is missing there.
- Focused live-candle, signal-history, and runtime tests: **17 passed**; these do not replace an open-session browser check of the visible SVG marker.
- Frontend lint, TypeScript typecheck, and production build: **passed**.
- `npm audit` and `npm audit --omit=dev`: **0 vulnerabilities** reported.
- Python package advisory scan: not run because `pip-audit` is not installed.
- `git diff --check` passed for tracked changes; the new report passed a separate trailing-whitespace scan.

## Audit limits and next actions

This was a source, test, deployment, route, and read-only portal audit. It was not a penetration test, legal review, or a new customer sign-in test; the chart was viewed in an already-authenticated session. The market was closed, so live streaming freshness could not be tested. Account-request submission, password change, and invitation email were not exercised. The API's process-local request limit is documented as unsuitable for multiple API instances without a shared edge limit.

1. Trace and resolve the live account-approval failure using API logs before retrying that request.
2. Reduce account sign-in cold-start delay and measure the customer and admin flows.
3. Investigate why the seven-day history response has no November 18 candles, expose the returned last-candle timestamp, then verify live data during market hours.
4. Repair the local Python environment and refresh the browser-audit selectors.
5. Keep evaluating signal performance on unseen periods and authorized data before treating the historical percentage as expected future accuracy.

This audit adds documentation only; it does not change product logic or account and market-data settings.
