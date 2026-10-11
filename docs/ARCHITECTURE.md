# Architecture

## Overview

```
Browser -> Next.js (UI, Supabase auth session)
               | Bearer JWT (Phase 5)
               v
           FastAPI (owns all market logic)
               |- providers/   fetch + validate candles
               |- indicators/  pure pandas functions
               |- signals/     deterministic BUY/SELL/WAIT rules
               |- backtest/    historical tests (later)
               v
           Supabase Postgres (users, signals, backtests, paper trades)
```

## Principles

1. **Separation.** The frontend renders data; it never calls market-data providers and holds no secrets.
2. **Server-side secrets.** Provider keys and the Supabase service-role key exist only in `apps/api`. Browser-visible variables use `NEXT_PUBLIC_` and contain nothing sensitive.
3. **Validate first.** Candles are validated (schema, ordering, gaps, staleness) before any indicator runs.
4. **Honest data labelling.** Missing, delayed or stale data is surfaced as such. Sample data is never labelled live.
5. **Deterministic signals.** Rules are fixed and testable. Signals default to confirmed candle closes; provisional ones are marked.
6. **Audit trail.** Each signal stores its timestamp and the data it was computed from.
7. **No order placement.** There is no broker integration, by design.
8. **LLM boundary.** An LLM may explain a signal in words. It never supplies prices or makes the trading decision.

## Backend modules (`apps/api/app`)

| Module | Responsibility | Phase |
|---|---|---|
| `main.py`, `config.py` | App, CORS, settings, `/health` | 1 (done) |
| `providers/` | Data provider interface and validation | 2 |
| `indicators/` | UT Bot first, then EMA, VWAP, RSI, MACD, Supertrend, ADX, ATR, S/R | 3 |
| `signals/` | Rules, confirmed vs provisional, entry/stop/targets | 4 |
| `backtest/` | Historical backtests, paper trading | 6 |

## Frontend (`apps/web/src`)

| Path | Responsibility |
|---|---|
| `app/` | Routes (App Router) |
| `components/` | UI components |
| `lib/api.ts` | Server-side backend client |

## Phase plan

1. Foundation (this phase)
2. Data provider interface and validation
3. Indicators (UT Bot first) with unit tests
4. Signal engine
5. Charts, Supabase auth, dashboards
6. Multi-timeframe analysis, backtesting, paper trading
7. Admin dashboard; news analysis later

## Open decisions

- **Market-data provider.** Not chosen. Free options for Indian intraday data are limited and carry terms-of-use constraints that must be checked before public use.
- **Hosting.** Free-tier terms must be confirmed to permit a public, commercial-style site before deploying.
- **Regulatory review.** Publishing buy/sell signals publicly in India may fall under SEBI rules. Get qualified advice before launch.
