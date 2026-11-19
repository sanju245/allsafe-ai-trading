# Final website and project audit

**Audit date:** 2026-11-19 10:22 IST (2026-11-19 04:52 UTC)
**Repository:** `sanju245/allsafe-ai-trading`
**Production baseline:** web `6f9b696` (Vercel READY); API `0125822` (Render live)
**Overall:** the website and API are reachable. The account-approval fix is deployed. This follow-up exposes the latest returned historical-candle time, fixes zoom when fewer candles are loaded than the initial viewport, repairs the chart browser audit, synchronizes the local API environment, and raises two transitive Python packages above published security fixes. Frontend and backend checks pass. The provider's missing Nov 18 candles and a credential-backed live-market chart check remain unresolved.

## Highest-priority findings

### Medium — Previously observed account-approval failure needs live confirmation

In the earlier read-only admin browser session, the account-request queue showed a request still marked **pending** and the message **“Account approval failed. Please retry.”** I did not approve, decline, retry, or otherwise change the request. No personal details are recorded in this report.

Since that observation, Render's deployment history confirms commit `0125822`—“Fix account request approval and email alerts”—is **live** on the API service. The account-request and storage regression tests pass. I did not approve or retry a real customer request, so the prior 502 is a historical observation; the live transaction still needs a safe test request before declaring the workflow fully verified.

### Medium — Sign-in can look stalled for up to roughly a minute

Customer and administrator sign-in share the same flow. After the identity provider accepts credentials, the browser asks the API to verify the account profile. That request has a **65-second timeout**; the initial identity-provider request has a separate **12-second timeout**. The button remains disabled and says “Verifying account…” while this work runs. The page already explains that a sleeping account service can take about a minute to start.

This audit confirmed the wait in code, not the duration of a real credential-backed sign-in; no customer password was supplied. The API is on Render's free, single-instance plan, which is consistent with a cold-start delay. Keep the account service warm or move account verification to an always-on service, then measure the full customer and admin sign-in path.

### Medium — No labels appear because the visible history has no confirmed BUY/SELL events

The production chart was inspected in an existing signed-in browser session. It reported **WAIT**, **No signal** for the primary trigger, and **0 confirmed BUY/SELL signals** across 75 candles. The latest evaluated candle was November 17 at 15:15 IST. Its explanation says the late-session breakout was ignored because new signals stop after 14:15. The marker renderer only draws a label when a candle has a confirmed BUY or SELL event; it does not label WAIT. So the missing labels on this screenshot are not a rendering failure.

The seven-day history observed in production ended November 17 at 15:15 IST and had no November 18 candles. NSE's official 2026 holiday list names November 10 and November 24 as November holidays, not November 18 ([NSE trading-holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf)); this indicates that a normal session was omitted. The endpoint returned HTTP 200 and 75 bars across November 13, 16, and 17. The response already contains `last_candle_at`, but the UI did not display it. This follow-up adds the latest returned candle time to the chart and dashboard so incomplete range coverage is visible; it cannot reconstruct candles the data source did not return. Upstox documents the 15-minute historical range limit as one month, and the requested range was within that limit ([Upstox V3 historical-data documentation](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)). Render application-log retrieval returned HTTP 503, so the raw upstream response and reason for the missing session remain unknown.

#### Live candle-label path audit

The implementation path is connected end to end: the chart polls the live candle endpoint every 15 seconds, requests signal history, merges those decisions with the displayed candles by timestamp, and draws a green **Buy** marker below a confirmed signal candle or a red **Sell** marker above it. The API excludes forming candles from signal evaluation, and the chart also suppresses markers on forming or incomplete candles. A `WAIT` decision correctly has no marker. A current signal is accepted only when the quote is live and fresh; previous confirmed signals can still be shown from the returned history.

Expected live behavior: after a 15-minute candle is confirmed, a qualifying BUY or SELL should appear on its matching candle on the next successful chart refresh (normally within 15 seconds). No label should appear while a candle is still forming, when the decision is WAIT, or when the API cannot validate a continuous candle series. The signal rules also stop accepting new 15-minute breakouts after the configured 14:15 candle-time cutoff. The market was open during this follow-up, but no signed-in customer chart session was available in the browser. Therefore, the audit did not observe a real-time quote or an actual live label on a confirmed signal candle.

The repaired browser audit now exercises the current UI with synthetic data: it asserts both BUY and SELL SVG labels, the latest returned history timestamp, chart zoom, provider switching, refresh failure handling, and sign-out across tabs. It passes locally against a production build. This verifies marker rendering, but it does not validate Upstox data or prove that a fresh signal arrives during a real market session. The production screenshot's zero-signal result is consistent with the renderer.

### Medium — Market-hour feed freshness remains unverified

The audit ran while the market was open, but there was no signed-in customer chart session available in the browser. The API health endpoint confirms only that the service responds; the live feed and a fresh market-hour signal were not verified. Render application-log retrieval was unavailable, and the protected live-data routes require a customer session.
### Resolved — Local backend environment and package advisories

The local `.venv` initially lacked `jwt` despite the declared requirements. It was synchronized from `requirements.txt`; the full backend suite then passed: **311 passed**. The first advisory scan found vulnerable `certifi` and `opentelemetry-api` versions. The API now uses `certifi 2026.10.23` and `opentelemetry-api 1.45.2`, the fixed releases listed by the [certifi advisory](https://github.com/advisories/GHSA-6q48-6c7w-9gw2) and [OpenTelemetry advisory](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-mf5v-w3w3-f6cg). The published market-data SDK capped `certifi` below 2026, so its MIT-licensed 1.5.0 source is vendored with package code unchanged and only that dependency bound updated; see `apps/api/vendor/growwapi/UPSTREAM.md`. The API dependency set installs cleanly and `pip check` reports no broken requirements. `pip-audit --local` found no known vulnerable installed dependencies; it notes that the locally patched SDK version is not published on PyPI and therefore cannot be matched to a package advisory record.

### Resolved — The browser chart audit helper now matches the chart

The script's selectors were updated to match the title-case candle labels and current “Signal confirmation checks” section. Its fixture now includes the latest session, and its zoom assertion matches the chart's actual bar count. The local production-build browser audit passes.

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
| Customer terminal | Protected route and feature wiring pass local checks. | Route returned HTTP 200. The prior production view showed the last returned candle at Nov 17, 15:15 IST. This follow-up ran during market hours but had no signed-in chart session, so live freshness remains unverified. |
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
- Vercel: the current `main` deployment on `6f9b696` was **READY**; the production domain returned HTTP 200. The follow-up UI release is to be verified after this commit.
- Render: deployment history confirms API commit `0125822` is **live**; public `GET /health` returned `status: ok`, `environment: production`, and version `0.2.0`.
- Frontend tests: **32 passed, 0 failed**.
- Backend tests: **311 passed** in the synchronized project virtual environment.
- Focused account-approval, storage, and historical-data tests: **34 passed**; one Starlette/httpx deprecation warning.
- Browser chart audit: **passed** against a local production build with synthetic market responses; both candle labels, the newest history timestamp, zoom, provider switching, refresh failure, and cross-tab sign-out passed.
- Frontend lint, TypeScript typecheck, and production build: **passed**.
- `npm audit` and `npm audit --omit=dev`: **0 vulnerabilities** reported.
- Python dependency checks: `pip check` reported no broken requirements; `pip-audit --local` found no known vulnerable installed dependencies and noted the local patched SDK is not listed on PyPI.
- `git diff --check` passed for tracked changes; the new report passed a separate trailing-whitespace scan.

## Audit limits and next actions

This was a source, test, deployment, route, and read-only portal audit. It was not a penetration test, legal review, or a new customer sign-in test; no signed-in chart was available in the browser for this follow-up. The market was open, but live streaming freshness could not be tested without that session. Account-request submission, password change, and invitation email were not exercised. The API's process-local request limit is documented as unsuitable for multiple API instances without a shared edge limit.

1. Trace and resolve the live account-approval failure using API logs before retrying that request.
2. Reduce account sign-in cold-start delay and measure the customer and admin flows.
3. Investigate why the seven-day provider response omitted November 18; inspect a fresh response with an authorized customer session and do not synthesize missing candles.
4. During an authenticated market session, verify a fresh quote and a real BUY/SELL marker on the corresponding confirmed candle.
5. Keep evaluating signal performance on unseen periods and authorized data before treating the historical percentage as expected future accuracy.

This follow-up changes chart presentation and zoom behavior, the browser-audit helper, and API dependency resolution to apply the patched certificate bundle. It does not change signal generation, API routes, customer data, or market-data settings.
