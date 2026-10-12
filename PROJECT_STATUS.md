# Project Status

**Project:** AllSafe AI Trading
**Last updated:** 2026-10-11
**Current phase:** Phase 2 (Market-data foundation) implemented, **awaiting your review**. Not committed, not pushed, not deployed.

> **Read this first.** The validation logic has real passing tests (124 passed). The HTTP layer (the new endpoints, `/health`, app start-up) and the whole frontend have **not** been executed in this build environment, because FastAPI and the npm/pip registries were not available. See "What was not tested".

## Repository state

- GitHub `main` (`60318b4`, "Initial AllSafe AI Trading project") contains exactly the Phase 1 files. It was compared with the Phase 1 working copy and the only difference was an empty folder.
- Phase 2 changes exist on a local branch `phase-2-market-data`, **uncommitted**, on top of `60318b4`. They were **not pushed**: this session has no linked GitHub account, so it could not write to the repository. Review the patch (or zip), then commit and push yourself.
- Phase 1 verification: no local results (pytest, typecheck, lint, build) have been reported to me, so Phase 1 is still unverified by me.

## Completed tasks (Phase 2)

| # | Requirement | Status |
|---|---|---|
| 1 | Inspect backend, preserve `/health` | Done. `/health` code is unchanged; only `__version__` moved 0.1.0 to 0.2.0, which `/health` reports. **Not run** (needs FastAPI). |
| 2 | Reusable `Candle` model | Done: timestamp, OHLC, volume, instrument, timeframe, source metadata |
| 3 | Validation | Done: OHLC, non-positive and non-finite prices, negative volume, duplicates, out-of-order, missing intervals, stale data, plus future and forming candles, grid alignment, mismatched metadata |
| 4 | Timeframes `1m 3m 5m 15m 1h 1d` | Done |
| 5 | Provider interface | Done (`MarketDataProvider`, `CandleRequest`, error types). No provider implemented. |
| 6 | SAMPLE fixtures for unit tests only | Done, under `tests/fixtures/`, never imported by `app/` |
| 7 | API endpoints | Written: `GET instruments`, `GET timeframes`, `POST validate`. **Not executed.** |
| 8 | Automated tests | 124 written and passing for the core; HTTP tests written but skipped here |
| 9 | Credentials server-side, no fake prices, no signals, no orders, no paid provider | Held. No credentials were added at all. |
| 10 | Update this file and README | Done |

Not done by design: UT Bot and any indicator, any real provider, any signal, frontend changes.

## Files changed

**Modified: code (3 files)**
- `apps/api/app/main.py`: registers the market-data router; docstring updated. `/health` and CORS untouched.
- `apps/api/app/__init__.py`: version 0.1.0 to 0.2.0.
- `apps/api/app/providers/__init__.py`: replaces the placeholder docstring with exports of the interface.

**Modified: docs (3 files)**
- `README.md`, `docs/ARCHITECTURE.md`, `PROJECT_STATUS.md`.

**Created: application code**
- `apps/api/app/market_data/__init__.py`: public exports.
- `apps/api/app/market_data/timeframes.py`: `Timeframe` enum, intervals, `TimeframeInfo`.
- `apps/api/app/market_data/instruments.py`: `NIFTY50`, `BANKNIFTY` with session metadata.
- `apps/api/app/market_data/sessions.py`: IST, 09:15 to 15:30 session, grid, gap and freshness helpers.
- `apps/api/app/market_data/models.py`: `Candle`, `DataSource`, `DataSourceKind`.
- `apps/api/app/market_data/validation.py`: `validate_candles` and the report models.
- `apps/api/app/market_data/schemas.py`: request model for the validate endpoint.
- `apps/api/app/market_data/service.py`: `validate_series_request`, `fetch_and_validate`, `FetchResult`.
- `apps/api/app/providers/base.py`: provider contract and errors.
- `apps/api/app/routers/__init__.py`, `apps/api/app/routers/market_data.py`: the three endpoints.

**Created: tests**
- `apps/api/tests/__init__.py`, `tests/fixtures/__init__.py`, `tests/fixtures/sample_data.py` (SAMPLE fixtures).
- `tests/test_timeframes_instruments_models.py` (27), `test_validation_values.py` (25), `test_validation_time.py` (31), `test_validation_freshness.py` (14), `test_provider_and_service.py` (27).
- `tests/test_market_data_api.py`: HTTP tests; skipped here (FastAPI missing).

No dependencies were added: `requirements.txt` and `package.json` are unchanged.

## Commands executed and results

| Command (summary) | Result |
|---|---|
| `git ls-remote` / `git clone` of the public repo (read-only, scratch dir) | Succeeded; matches Phase 1 copy |
| `add_repo` for `sanju245/allsafe-ai-trading` | **Failed**: GitHub account not linked |
| `pip install -r requirements-dev.txt` | **Failed**: `pypi.org` did not resolve |
| same, retried once via the session proxy | **Failed**: `403 Forbidden` (organisation egress policy; not retried or bypassed) |
| `uv pip install --offline` from the local cache | **Failed**: `fastapi` and `pytest` not cached |
| `git fetch`, `git reset origin/main`, `git checkout -b phase-2-market-data` | Succeeded; tree clean before my changes |
| `pytest -q --ignore=tests/test_health.py` | **124 passed, 1 skipped** (see below) |
| 7 deliberate code mutations in a scratch copy, then `pytest` | 6 caught immediately; the 7th was an equivalent mutation (redundant `high < low` rule), now covered by a message assertion and caught |
| `ast.parse` of `main.py`, `routers/market_data.py`, `test_health.py`, `test_market_data_api.py` | No syntax errors (syntax only, files not imported) |
| README curl payload run through `validate_series_request` | `is_valid: False`, codes `INVALID_OHLC`, `NEGATIVE_VOLUME`, as documented |

## Tests actually run and their results

Run with the pre-installed pytest 9.1.1 on Python 3.13.16 and the system pydantic 2.13.5 (not the versions pinned in `requirements-dev.txt`, which could not be installed). Result: **124 passed, 1 skipped, 0 failed**.

| File | Tests | Covers |
|---|---|---|
| `test_timeframes_instruments_models.py` | 27 | six timeframes, rejection of others, instruments, Candle fields, close times, `is_closed` |
| `test_validation_values.py` | 25 | valid series, 5 bad-OHLC shapes, non-positive and non-finite prices, volume rules, metadata mismatch, issue cap, empty series |
| `test_validation_time.py` | 31 | duplicates, out-of-order, naive and UTC timestamps, grid per timeframe, trading hours, intraday gaps, overnight and weekend, holiday-run threshold, daily candles |
| `test_validation_freshness.py` | 14 | stale and fresh, lag and grace settings, weekends, overnight, daily, forced on/off, future and forming candles |
| `test_provider_and_service.py` | 27 | provider contract, `fetch_and_validate`, request schema limits and malformed requests |

The 1 skip is `tests/test_market_data_api.py` (`could not import 'fastapi'`).

## What was not tested

- **Every HTTP behaviour.** `GET /health`, `/instruments`, `/timeframes`, `POST /validate`, status codes (200 vs 422), OpenAPI output, CORS. The handlers are three-line wrappers over tested functions, but the wiring has never run.
- **`tests/test_health.py`** (from Phase 1): cannot be collected here without FastAPI. It is unchanged.
- **`pydantic-settings`** (used by `config.py`): not installed here.
- **The whole frontend** (`npm install`, typecheck, lint, build): unchanged this phase and still never run.
- **Package versions** in `requirements*.txt` were not resolved against a registry.

## Design decisions to review

1. **Candle timestamp = open time.** Confirmed-candle logic later depends on this.
2. **Hourly grid starts at 09:15** (09:15, 10:15 ... 15:15 stub). A provider that aligns hourly bars to `:00` will be flagged `TIMESTAMP_NOT_ON_GRID`. This is strict on purpose; relax it or normalise in the provider adapter.
3. **Daily candles are keyed by IST date**, any time of day accepted.
4. **Whole missing weekdays are warnings, not errors**, because there is no holiday calendar. More than 4 in a row is an error.
5. **Partial-day gaps are errors.**
6. **Staleness defaults:** applies to `live` and `delayed` only; tolerance 1 candle plus 30 s grace. A `delayed` feed will usually need a larger `allowed_lag_candles`.
7. **`volume` may be `None`** (index data often has none); reported as a warning.
8. **Validation never raises on bad data.** It returns a report.
9. **IST is a fixed +05:30 offset**, avoiding a `tzdata` dependency on Windows.
10. **CORS still allows `GET` only**, so the POST endpoint is not callable from another origin in a browser. Left unchanged to keep the surface small.
11. **No auth or rate limiting** on the public POST endpoint; request size capped at 10,000 candles. Proper protection belongs with Supabase auth in Phase 5.

## Remaining problems

- The HTTP layer needs a first real run (commands below).
- No holiday calendar; special sessions (e.g. Muhurat) show as `OUTSIDE_TRADING_HOURS` warnings.
- Phase 1 items still open: first `npm install`, typecheck, lint, build, and lockfiles.
- Open decisions carried over: market-data provider and its terms of use; free-tier hosting terms for a public site; regulatory review of publishing buy/sell signals in India.

## Commands to run locally

```bash
cd allsafe-ai-trading
git apply --check phase-2-market-data.patch && git apply phase-2-market-data.patch   # or unzip over a clean checkout
cd apps/api
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -v                                              # expect everything to run, nothing skipped
uvicorn app.main:app --reload --port 8000              # then open http://127.0.0.1:8000/docs
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/v1/market-data/instruments
```

## Next recommended prompt

> Phase 2 is applied and verified locally (results pasted below). If anything failed, fix only that. Then begin Phase 3: implement the UT Bot Alerts indicator in `apps/api/app/indicators` as a pure pandas function that takes validated candles, with configurable key value and ATR period, no repainting on closed candles, and unit tests using only SAMPLE data. Do not generate signals yet. Update PROJECT_STATUS.md and stop.
>
> Local results: [paste `pytest -v` output and the `/health` and `/instruments` responses]
