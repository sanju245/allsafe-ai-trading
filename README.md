# AllSafe AI Trading

A public Indian stock-market analysis website for **NIFTY 50** and **BANK NIFTY**, built around transparent, rule-based signals (UT Bot Alerts as the primary indicator).

> **Analysis only.** This project never places broker orders. Users trade manually. Nothing here is investment advice, and no strategy guarantees profit.

**Current phase:** 2 of the roadmap (market-data foundation). The backend can describe supported instruments and timeframes and validate a candle series you give it. There is **no data provider, no live prices, no indicators and no signals yet**. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for exactly what exists and what has been tested.

## Repository layout

```
allsafe-ai-trading/
├─ apps/
│  ├─ web/   Next.js (App Router, TypeScript, Tailwind CSS) frontend
│  └─ api/   Python FastAPI backend (market logic lives here)
├─ docs/
│  └─ ARCHITECTURE.md
├─ PROJECT_STATUS.md
└─ README.md
```

## Prerequisites

- Node.js 20.9 or newer (22 recommended) and npm
- Python 3.11 or newer
- Git

All tooling used so far is free.

## Backend setup (FastAPI)

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Check it: open <http://127.0.0.1:8000/health>. Interactive docs are at <http://127.0.0.1:8000/docs>.

Run the backend tests (from `apps/api`, venv active):

```bash
pytest
```

The tests use only synthetic **SAMPLE** data (`apps/api/tests/fixtures/sample_data.py`). The HTTP tests in `tests/test_market_data_api.py` and `tests/test_health.py` need FastAPI and httpx from `requirements-dev.txt`; if they are not installed, the API module is reported as *skipped*, not passed.

## Market-data foundation (Phase 2)

Nothing in this phase fetches data. It defines what a candle is, how to check one, and the contract a future data provider must follow.

### Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness check (unchanged from Phase 1) |
| `GET /api/v1/market-data/instruments` | Supported instruments and session metadata |
| `GET /api/v1/market-data/timeframes` | Supported timeframes: `1m`, `3m`, `5m`, `15m`, `1h`, `1d` |
| `POST /api/v1/market-data/validate` | Validate a candle series you supply; nothing is stored |

Instrument ids are `NIFTY50` and `BANKNIFTY`. Both are NSE indices, not directly tradable.

```bash
curl -s http://127.0.0.1:8000/api/v1/market-data/instruments

curl -s -X POST http://127.0.0.1:8000/api/v1/market-data/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "instrument": "NIFTY50",
    "timeframe": "1m",
    "source": {"name": "my-test-data", "kind": "historical"},
    "candles": [
      {"timestamp": "2026-01-05T09:15:00+05:30", "open": 1000, "high": 1002, "low": 998, "close": 1001, "volume": 10},
      {"timestamp": "2026-01-05T09:16:00+05:30", "open": 1001, "high": 990,  "low": 999, "close": 1002, "volume": -3}
    ]
  }'
```

The second candle above is deliberately bad: the response has `"is_valid": false` and lists `INVALID_OHLC` and `NEGATIVE_VOLUME`. Bad market data returns HTTP 200 with a report. HTTP 422 means the request itself is malformed (unknown field, unsupported timeframe or instrument, more than 10,000 candles, a timezone-less `as_of`).

`source.kind` is one of `live`, `delayed`, `historical`, `sample`. Staleness is checked only for `live` and `delayed` (override with `check_staleness`). A `sample` series always carries a `SAMPLE_DATA` warning and must never be shown as market data.

### Conventions

- A candle's `timestamp` is its **open** time. It closes at open plus the timeframe, capped at the session close.
- Regular session: Monday to Friday, 09:15 to 15:30 IST. Intraday candles sit on a grid starting at 09:15 IST, so a `1h` candle opens at 09:15, 10:15, ... 15:15 (the last is a 15-minute stub).
- A `1d` candle is identified by its IST calendar date; its time of day is ignored.
- Timestamps must carry a timezone. `volume` may be omitted (common for index data); that is different from a volume of `0`.

### What is checked

| Severity | Codes |
|---|---|
| Error (do not use for signals) | `EMPTY_SERIES`, `INSTRUMENT_MISMATCH`, `TIMEFRAME_MISMATCH`, `SOURCE_MISMATCH`, `NON_FINITE_VALUE`, `NON_POSITIVE_PRICE`, `INVALID_OHLC`, `NEGATIVE_VOLUME`, `NAIVE_TIMESTAMP`, `DUPLICATE_TIMESTAMP`, `OUT_OF_ORDER`, `TIMESTAMP_NOT_ON_GRID`, `MISSING_INTERVAL`, `FUTURE_TIMESTAMP`, `STALE_DATA` |
| Warning (usable, but know this) | `OUTSIDE_TRADING_HOURS`, `MISSING_SESSION`, `FORMING_CANDLE`, `VOLUME_UNAVAILABLE`, `SAMPLE_DATA` |

- **Missing candles inside a trading day** are an error. **A whole missing weekday** is only a warning, because no exchange holiday calendar is bundled yet; a run of more than 4 consecutive missing weekdays is an error.
- **Stale** means more than `allowed_lag_candles` (default 1) expected candles have already closed since the latest one, allowing 30 seconds for delivery. Weekends and hours outside the session are skipped. On an exchange holiday, live data can look stale.
- **`FORMING_CANDLE`** marks a latest candle that has not closed yet. Later phases must treat any signal from it as provisional.

### Provider interface

`apps/api/app/providers/base.py` defines `MarketDataProvider`, `CandleRequest` and the `ProviderError` family. No provider is implemented or chosen. Credentials for a future provider are read server-side only; they are never accepted from a request. `app/market_data/service.py` provides `fetch_and_validate`, which fetches, validates, and never repairs or drops data; `FetchResult.require_valid()` raises if the series has errors.

## Frontend setup (Next.js)

```bash
cd apps/web
npm install
cp .env.example .env.local         # Windows: copy .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The header shows **Backend online** when the API above is running, otherwise **Backend offline**.

Other frontend scripts:

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # production build
```

## Environment variables

Real secrets must never be committed. Only the `.env.example` files are tracked.

| File | Purpose |
|---|---|
| `apps/api/.env.example` | Server-side settings (CORS, future Supabase and data-provider keys) |
| `apps/web/.env.example` | `API_BASE_URL` (server-only) and future public Supabase values |

Rules: provider keys and the Supabase service-role key belong only in `apps/api/.env`. Nothing sensitive may use the `NEXT_PUBLIC_` prefix.

## Data integrity rules

- No live prices are shown unless they come from a tested data provider. None exists yet.
- Sample or demo data must never be labelled live. Test fixtures live under `apps/api/tests/` and nothing in `apps/api/app/` imports them.
- Default signals use confirmed candle closes; provisional signals are labelled as such.
- Signal rules are deterministic. An LLM may only explain a signal; it never creates prices or decides trades.

## Known limitations (Phase 2)

- No market-data provider is connected, so the site shows no prices.
- No exchange holiday calendar: holidays can appear as missing sessions or stale data.
- The API has no authentication or rate limiting yet (planned with Supabase auth in Phase 5). Request size is capped at 10,000 candles.
- CORS allows `GET` only. The `POST /validate` endpoint is meant for server-side calls and tools like `curl`, not browsers on another origin.

## Roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [PROJECT_STATUS.md](PROJECT_STATUS.md).
