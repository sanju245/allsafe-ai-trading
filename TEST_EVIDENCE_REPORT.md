# AllSafe AI Trading — Complete Test Evidence Report (`TEST_EVIDENCE_REPORT.md`)

- **Audit Date**: November 5, 2026
- **Verification Branch**: `audit/landing-auth-integration-verification`

## 1. Summary of Executed Test Suites (Previously Existing vs. Newly Executed)

| Suite Category | Command Executed | Exit Code | Previously Existing Tests | Newly Added Verification Tests | Total Passed | Failed | Skipped |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: |
| **Backend Python Suite (`apps/api/tests/`)** | `python3 artifacts/file_generation/ttl=63d/intermediate/run_backend_tests.py` | `0` | `119` (`13` files) | `6` (`test_independent_security_revalidation.py`) | **`125`** | `0` | `0` |
| **Frontend Node Test Suite (`apps/web/tests/`)** | `node --test apps/web/tests/marketData.test.mjs apps/web/tests/landingPage.test.mjs apps/web/tests/portalIntegrationAndSecurity.test.mjs` | `0` | `23` (`marketData` `17` + `landingPage` `6`) | `2` (`portalIntegrationAndSecurity.test.mjs`) | **`25`** | `0` | `0` |
| **Frontend 29-File TS/JSX & ESLint Verifier** | `node artifacts/file_generation/ttl=63d/intermediate/verify_frontend_build.mjs` | `0` | `19` files | `10` new landing/portal files | **`29`** | `0` | `0` |
| **Headless Chromium Multi-Viewport & Web App Audit** | `python3 run_chromium_audit.py` & `check_web_app.py --previous` | `0` | `4` viewports + `/login` | `/what-we-done` + zero-indicator DOM check | **`6`** checks | `0` | `0` |

## 2. Backend Test Execution Log (`125 Passed, 0 Failed`)

```text
PASS: test_auth_and_admin.py (8 tests passed)
PASS: test_independent_security_revalidation.py (6 tests passed)
PASS: test_candle_builder.py (16 tests passed)
PASS: test_confirmation_indicators.py (6 tests passed)
PASS: test_groww_auth_and_instruments.py (7 tests passed)
PASS: test_groww_historical.py (3 tests passed)
PASS: test_groww_live_api.py (6 tests passed)
PASS: test_groww_stream_and_runtime.py (3 tests passed)
PASS: test_health.py (3 tests passed)
PASS: test_hub_phase1_contracts.py (15 tests passed)
PASS: test_hub_phase2_api.py (6 tests passed)
PASS: test_live_ticks_and_candles.py (24 tests passed)
PASS: test_market_intelligence.py (12 tests passed)
PASS: test_ut_bot.py (10 tests passed)

=== BACKEND SUITE SUMMARY: 125 passed, 0 failed in 10204.1 ms ===
```

## 3. Frontend Test Execution Log (`25 Passed, 0 Failed`)

```text
TAP version 13
# Subtest: Live IST Clock: formats exact HH:MM:SS AM/PM IST and uppercase date in Asia/Kolkata regardless of visitor timezone
ok 1 - Live IST Clock: formats exact HH:MM:SS AM/PM IST and uppercase date in Asia/Kolkata regardless of visitor timezone
  ---
  duration_ms: 3.95594
  ...
# Subtest: Live IST Clock: applies serverTimeOffsetMs accurately when device clock is skewed
ok 2 - Live IST Clock: applies serverTimeOffsetMs accurately when device clock is skewed
  ---
  duration_ms: 0.49386
  ...
# Subtest: Indian Stock Market Status: regular weekday pre-open, exact open (09:15), active session, and exact close (15:30)
ok 3 - Indian Stock Market Status: regular weekday pre-open, exact open (09:15), active session, and exact close (15:30)
  ---
  duration_ms: 3.247739
  ...
# Subtest: Indian Stock Market Status: weekends, official NSE/BSE trading holidays, and Diwali Muhurat special sessions
ok 4 - Indian Stock Market Status: weekends, official NSE/BSE trading holidays, and Diwali Muhurat special sessions
  ---
  duration_ms: 1.85436
  ...
# Subtest: Indian Stock Market Status: returns MARKET STATUS UNAVAILABLE when data is invalid or out of verified calendar bounds
ok 5 - Indian Stock Market Status: returns MARKET STATUS UNAVAILABLE when data is invalid or out of verified calendar bounds
  ---
  duration_ms: 0.53017
  ...
# Subtest: Landing Page & What We Done Page compile cleanly, disclose ZERO indicator names, and present the 5 AI Agents for Buy/Sell decisions
ok 6 - Landing Page & What We Done Page compile cleanly, disclose ZERO indicator names, and present the 5 AI Agents for Buy/Sell decisions
  ---
  duration_ms: 5099.797438
  ...
# Subtest: formatPrice and formatInrCurrency format numbers in en-IN locale safely using singleton Intl formatters
ok 7 - formatPrice and formatInrCurrency format numbers in en-IN locale safely using singleton Intl formatters
  ---
  duration_ms: 5.906739
  ...
# Subtest: formatSignedDelta formats positive, negative, and flat index changes
ok 8 - formatSignedDelta formats positive, negative, and flat index changes
  ---
  duration_ms: 0.47537
  ...
# Subtest: formatIstTime formats UTC timestamps and Date objects into Asia/Kolkata IST 24-hour time
ok 9 - formatIstTime formats UTC timestamps and Date objects into Asia/Kolkata IST 24-hour time
  ---
  duration_ms: 0.49439
  ...
# Subtest: mergeAndSortCandles strictly separates confirmed candles from the forming candle
ok 10 - mergeAndSortCandles strictly separates confirmed candles from the forming candle
  ---
  duration_ms: 1.58583
  ...
# Subtest: mergeAndSortCandles drops forming candle if its slot is already confirmed
ok 11 - mergeAndSortCandles drops forming candle if its slot is already confirmed
  ---
  duration_ms: 0.335
  ...
# Subtest: computeMarketStats computes accurate session OHLC, change, and range position
ok 12 - computeMarketStats computes accurate session OHLC, change, and range position
  ---
  duration_ms: 0.52605
  ...
# Subtest: getFeedStateBadge maps backend feed states and staleness flags to semantic badges
ok 13 - getFeedStateBadge maps backend feed states and staleness flags to semantic badges
  ---
  duration_ms: 0.37969
  ...
# Subtest: getDecisionBadge and getAIRecommendationBadge lock signals when feed is non-live or stale
ok 14 - getDecisionBadge and getAIRecommendationBadge lock signals when feed is non-live or stale
  ---
  duration_ms: 1.18328
  ...
# Subtest: computeClientPositionSizing enforces max risk cap and lot size multiples
ok 15 - computeClientPositionSizing enforces max risk cap and lot size multiples
  ---
  duration_ms: 0.654061
  ...
# Subtest: classifyFetchError categorizes auth (401/403), gateway (502/503), and rate-limit (429) errors
ok 16 - classifyFetchError categorizes auth (401/403), gateway (502/503), and rate-limit (429) errors
  ---
  duration_ms: 1.58218
  ...
# Subtest: Phase 3 P2-A4: Capital input debouncing, empty/invalid/partial draft preservation, blur fallback, and unmount cleanup
ok 17 - Phase 3 P2-A4: Capital input debouncing, empty/invalid/partial draft preservation, blur fallback, and unmount cleanup
  ---
  duration_ms: 221.555325
  ...
# Subtest: Phase 3 P2-A1: Request deduplication, subscriber cancellation isolation, full-abort cleanup, and zero memory leaks
ok 18 - Phase 3 P2-A1: Request deduplication, subscriber cancellation isolation, full-abort cleanup, and zero memory leaks
  ---
  duration_ms: 106.317978
  ...
# Subtest: Phase 3 P2-A2: Adaptive polling transitions and Closed -> Open forming-candle recovery fetch
ok 19 - Phase 3 P2-A2: Adaptive polling transitions and Closed -> Open forming-candle recovery fetch
  ---
  duration_ms: 1.319511
  ...
# Subtest: Phase 3 P2-A5: Refresh lifecycle — manual refresh queuing, cancellation safety, token switching, auto-refresh toggles, and unmount cleanup
ok 20 - Phase 3 P2-A5: Refresh lifecycle — manual refresh queuing, cancellation safety, token switching, auto-refresh toggles, and unmount cleanup
  ---
  duration_ms: 217.358846
  ...
# Subtest: Phase 3 P2-A3 & P2-A5: LiveMarketDashboard and all dashboard components enforce pure state updaters, React.memo, and stale-on-error safety
ok 21 - Phase 3 P2-A3 & P2-A5: LiveMarketDashboard and all dashboard components enforce pure state updaters, React.memo, and stale-on-error safety
  ---
  duration_ms: 3681.212228
  ...
# Subtest: Phase 3 P2-A3 & P2-A5 Runtime Component Test: LiveMarketDashboard executes refresh, handleToggleAutoRefresh, manual refresh queuing, accessToken switching, cancellation, stale-on-error, and unmount under Strict Mode
ok 22 - Phase 3 P2-A3 & P2-A5 Runtime Component Test: LiveMarketDashboard executes refresh, handleToggleAutoRefresh, manual refresh queuing, accessToken switching, cancellation, stale-on-error, and unmount under Strict Mode
  ---
  duration_ms: 862.464516
  ...
# Subtest: Phase 3 Admin Control Center, Login, Account & Auth components compile cleanly, pass ESLint, and enforce IP-independent admin access
ok 23 - Phase 3 Admin Control Center, Login, Account & Auth components compile cleanly, pass ESLint, and enforce IP-independent admin access
  ---
  duration_ms: 2272.304519
  ...
# Subtest: Client/Server API Boundary: clientApi.ts and api.ts export API_BASE_URL, fetchApi, AuthApiError, and getApiHealth without leaking server-only env vars to browser bundle
ok 24 - Client/Server API Boundary: clientApi.ts and api.ts export API_BASE_URL, fetchApi, AuthApiError, and getApiHealth without leaking server-only env vars to browser bundle
  ---
  duration_ms: 1642.130169
  ...
# Subtest: Admin Portal (/admin/login & /admin) and Customer Portal (/login & /terminal) separation and route guards
ok 25 - Admin Portal (/admin/login & /admin) and Customer Portal (/login & /terminal) separation and route guards
  ---
  duration_ms: 2634.645394
  ...
1..25
# tests 25
# suites 0
# pass 25
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 26100.970508
```
