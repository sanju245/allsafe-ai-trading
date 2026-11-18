# Upstox 15-minute chart setup

The signed-in terminal on this branch has a separate Upstox historical-chart path for NIFTY 50 and BANK NIFTY. It requests completed 15-minute candles for a selected 1–30 calendar-day range. The default is 7 days, which normally includes yesterday and the prior session. The current Groww/Upstox live 5-minute selector remains separate.

## Server environment

The API reads one secret environment variable:

- `UPSTOX_ACCESS_TOKEN` — use the existing Upstox Analytics Access Token (or another Upstox read-only token with historical market-data permission) in the Render API web service's Environment settings.

Keep the token on the API service. Do not put it in Vercel, a `NEXT_PUBLIC_*` variable, browser source, or this repository, and do not send it in chat. Save the Render environment change to restart/redeploy that service after the matching API branch is deployed.

## API behavior

- `GET /api/v1/market-data/upstox/candles?symbol=NIFTY50&days=7`
- `GET /api/v1/market-data/upstox/candles?symbol=BANKNIFTY&days=7`
- Requires a currently active signed-in account.
- Returns historical OHLC only, sorted oldest to newest; incomplete current 15-minute candles are excluded.
- The maximum request window is 30 calendar days. Larger histories require multiple bounded requests.
- If the token is absent, the endpoint returns a safe setup message. If Upstox rejects it, the API does not reveal the token or raw provider response.
- No order placement, quote execution, or autonomous trading behavior is involved.

## Release status

This implementation is on branch `codex/upstox-15m-chart-2026-11-19`, based on current GitHub `main`. It has not been merged or deployed. Review the branch before any production release.
