# AllSafe chart and portal audit

**24 November 2026 · NIFTY 50 and BANK NIFTY · 15-minute NSE regular-session candles**

The chart release went live on the production website and API from GitHub commit `399f44d`. Each index scored **8 of 12 correct** in a 30-calendar-day broker replay. The seven-day chart contained one Buy for NIFTY 50 and two Buys for BANK NIFTY. NSE was closed on the audit date. A real-time signal during an open session could only be checked by replay for this release. [Release commit](https://github.com/sanju245/allsafe-ai-trading/commit/399f44d45437b27d0e483c4a76330242c6443253) · [NSE holiday circular](https://archives.nseindia.com/content/circulars/CMTR71775.pdf)

## What was wrong and what changed

The previous chart could draw a week of broker history while the decision panel counted only the candles collected since a stream restart. One interrupted candle could block the decision even when the broker had subsequently supplied that completed interval. Replaying this sequence with one partial live close and 102 completed broker candles confirmed the defect. The repaired API used all 102 candles and returned the matching Buy or Sell for the two test cases.

The full chart requests the selected broker's history, signals and decision together. The default view fits seven calendar days. History supplies prices for intervals missed by the stream. A genuine gap starts a new calculation warm-up and preserves earlier confirmed labels. Quote polling runs separately, normally two seconds after the previous response while the feed is fresh. At a 15-minute boundary, the chart requests the latest decision. Broker delivery and network latency still affect when a label arrives.

The white Heikin Ashi chart supports drag, wheel and pinch controls, a crosshair with IST time and OHLC, fit, latest, full screen and a signal visibility switch. Green Buy labels point to the candle low and red Sell labels point to the high. Historical warm-up seeds the first displayed averaged candle. The quote and price-axis line identify the actual index price or last market close. Signals use completed market OHLC. A forming or partial candle cannot generate a badge. The fixed decision rule can issue at most one signal per index per regular session. [Charting library](https://tradingview.github.io/lightweight-charts/) · [Heikin Ashi calculation](https://www.tradingview.com/support/solutions/43000619436-understanding-heikin-ashi-charts/)

## Seven-day label check

The selected range was **18–24 November**, with 100 completed candles per index across four regular sessions. The dates below give the **candle open** in IST. The signal first becomes eligible at the close 15 minutes later. The deployed interface, tested with these recorded Upstox candles, placed the badges at the listed times. Moving the crosshair to each badge returned its matching candle time. [Upstox historical candle API](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)

| Index | Candle open, IST | Earliest confirmation, IST | Label | One-hour direction |
|---|---|---|---|---|
| NIFTY 50 | 20 Nov 09:45 | 20 Nov 10:00 | Buy | Correct |
| BANK NIFTY | 19 Nov 09:45 | 19 Nov 10:00 | Buy | Incorrect |
| BANK NIFTY | 20 Nov 09:30 | 20 Nov 09:45 | Buy | Correct |

There were zero confirmed Sells in this window. A separate controlled live-session replay verified the red Sell badge, the green Buy badge and the transition from a forming candle to a confirmed candle on the next interval.

## One-month directional accuracy

The scoring window was **25 October–23 November 2026**, with 20 regular sessions and 500 completed 15-minute bars per index. Earlier broker history supplied warm-up. Each daily replay used a trailing 30-calendar-day input window. All 24 signal timestamps and directions matched when the calculation was repeated using only data available at the signal close.

A Buy was correct when the fourth following candle closed above the next candle's open. A Sell required a lower close. All four following candles had to belong to the same session. Flat outcomes counted as incorrect. This measures spot-index direction before trading costs.

| Index | Buy correct / scored | Sell correct / scored | Total correct / scored | Hit rate |
|---|---:|---:|---:|---:|
| NIFTY 50 | 8 / 11 | 0 / 1 | 8 / 12 | 66.7% |
| BANK NIFTY | 8 / 12 | 0 / 0 | 8 / 12 | 66.7% |
| Combined | 16 / 23 | 0 / 1 | 16 / 24 | **66.7%** |

The combined 95% Wilson interval was **46.7%–82.0%**. The sample contained a single Sell. Most of the month overlapped an earlier rule-selection audit. Neither result establishes 60% forward accuracy or a reliable Sell-specific rate. This release changed chart delivery and data reconciliation. It used the previously selected trading rule. [Previous scoring audit](INDICATOR_AUDIT_15M_2026-11.md)

### Individual checks

These comparisons apply one confirmation to the historical primary-trigger events. They use the same one-hour outcome. Each row can select a different number of events.

| Check applied | NIFTY 50 | BANK NIFTY | Combined |
|---|---:|---:|---:|
| Primary trigger alone | 25 / 46 | 19 / 47 | 44 / 93 (47.3%) |
| Primary trigger with trend check A | 9 / 15 | 10 / 15 | 19 / 30 (63.3%) |
| Primary trigger with momentum check A | 13 / 23 | 13 / 28 | 26 / 51 (51.0%) |
| Primary trigger with momentum check B | 14 / 21 | 7 / 22 | 21 / 43 (48.8%) |
| Primary trigger with trend check B | 12 / 20 | 12 / 21 | 24 / 41 (58.5%) |
| Previous unanimous decision | 5 / 8 | 3 / 6 | 8 / 14 (57.1%) |

## Release and website verification

| Check | Observed result |
|---|---|
| GitHub and hosting | The production Vercel alias served `399f44d`. Render reported the same commit live at 10:32 IST. |
| Production broker connection | After deployment, Render logged successful Upstox startup history loads of 75 completed candles for each index. |
| Automated checks | 315 API tests and 35 website tests passed. Type checking, linting and the production build passed. The API suite emitted one test-client dependency deprecation warning. |
| Browser on the production website | Controlled sign-in, both chart tabs, seven-day history, zoom, drag, fit, full screen, mobile layout, signal toggle, provider switching, delayed feed, confirmed-candle rollover and cross-tab sign-out passed. The broker-data replay matched every visible historical badge to its candle. The browser used an isolated test identity and intercepted data for these repeatable checks. |
| Public pages | The home page, feature explanation, privacy page and customer login rendered their expected headings. All ten tested routes returned HTTP 200 and had zero uncaught page errors during the check. |
| Customer access | Signed-out visits to the terminal, account and both charts showed their access screens. The live production quote API returned HTTP 401 without a customer session. |
| Customer session inspected | The customer's existing NIFTY 50 tab showed the earlier chart, 100 displayed candles, 75 bars used for its decision and the 23 November close of 25,366.40. The shared tab subsequently required sign-in. The production interface with recorded candles was verified separately. |
| Admin access | The admin landing and login screens rendered. Automated tests cover denied access and stale responses. A production approval, password change or customer mutation was outside this read-only release check. The previous admin audit records the earlier approval incident. |
| Public response times | One warm network check measured 0.28 s for the login page, 0.55 s for API health, 0.55 s for the NIFTY chart route and 0.66 s for the BANK NIFTY route. These timings measure page or health responses. |

The public checks covered the customer and administrator entry points. The earlier full project audit provides the feature-by-feature history for account requests, approvals, privacy and password management. [Earlier portal audit](FINAL_AUDIT_2026-11-19.md)

### Customer sign-in delay

The account profile check previously had to wait for broker startup when the API was waking. Broker startup now runs in the background. A regression test held the broker connection open while health and account verification both responded. Before deployment one production health call timed out at 40 seconds and its retry succeeded. The API is on Render's Free plan, where idle instances can spin down after 15 minutes. The platform wake-up, identity provider and network can still contribute to a customer's total sign-in time. [Render Free service behavior](https://render.com/docs/free)

[NIFTY 50 chart](https://allsafe-ai-trading.vercel.app/chart/NIFTY50?provider=upstox) · [BANK NIFTY chart](https://allsafe-ai-trading.vercel.app/chart/BANKNIFTY?provider=upstox) · [Production health](https://allsafe-ai-api.onrender.com/health)
