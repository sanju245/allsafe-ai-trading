# MACD independent audit

Reviewed `apps/api/app/indicators/macd.py`, `decision.py`, and `tests/test_confirmation_indicators.py` on 2026-11-15. Specialist scope: MACD only. No product source files modified.

## Confirmed finding

**Medium severity: neutral MACD is admitted as bearish confirmation.** The implementation returns `bullish=False` whenever the warmed-up histogram is not greater than zero. `decision.py` requires all confirmation booleans to be False for SELL. A histogram of exactly zero therefore passes the bearish filter even though MACD equals its signal line and supplies no directional confirmation.

Concrete hand-calculated fixture: closes `[1,2,3,4,5]`, fast=2, slow=3, signal=2. Fast EMA values at indices 1..4 are 1.5,2.5,3.5,4.5; slow EMA values at indices 2..4 are 2,3,4. MACD at indices 2..4 is 0.5. Its signal is 0.5 at indices 3..4, leaving histogram 0. The current `bullish` field is False there. It is not legitimate to count that False as an explicit bearish confirmation.

This finding concerns confirmation semantics. It does not prove that the complete engine emits a SELL on this fixture: the UT trigger and other filters may prevent one.

Minimal correction: keep `bullish = histogram > 0` and add a distinct `bearish = histogram < 0` after warmup. In the decision engine, require explicit bearish confirmation for SELL. Neutral should produce neither bullish nor bearish; it must remain separate from missing warmup values. Returning None for neutral without changing the engine would incorrectly classify a valid neutral reading as DATA_UNAVAILABLE.

## Arithmetic and timing

- Fast and slow calculations use the ordinary EMA recurrence, seeded by an SMA of their respective first periods.
- MACD is fast EMA minus slow EMA, signal is an EMA of available MACD points, histogram is MACD minus signal. These relationships match the TradingView primary explanation: https://www.tradingview.com/support/solutions/43000502344-moving-average-convergence-divergence-macd-indicator/
- First MACD exists at zero-based index `slow-1`. The first histogram exists at `slow+signal-2`, index33 or the34th candle with defaults12/26/9.
- `m > s and hist > 0` repeats the same predicate because hist=m-s; simplification would improve clarity but provides no accuracy gain.
- No future values are read. The recurrence and compact signal series advance in chronological order. Prefix invariance follows from that recurrence; a numerical prefix-invariance regression test is recommended.
- SMA seed behavior is explicit. Exact parity with a platform using another EMA seed should not be claimed. Use sufficient pre-period history for both the audit and production; restarting with only the newest short window can change boundary values.
- Public standalone MACD calculations assume validated chronological finite candles; unlike UT, this function does not reject NaN, mixed instruments, or out-of-order timestamps. The current combined decision path calls UT first, which validates those attributes. Audit ingestion must validate candles before any individual-indicator scoring.

## Scoring implications

MACD here is a confirmation state, not an independent buy/sell event generator. For fair single-indicator comparisons, disclose whether evaluation samples each closed candle with positive/negative histogram or only sign-crossing events. Count neutral and warmup separately. Score next-candle-open entries, not the closing price used to compute the signal. Do not silently equate all False states with SELL.

Recommended regressions: exact-zero fixture above, positive and negative histogram sequences, exact default warmup boundary, prefix invariance, and combined-engine SELL with MACD-neutral confirmation blocked while warmed-up data remains available.

## Historical result

Annual correctness percentage is **not yet measured**. This review had no genuine one-year candle dataset. Synthetic arithmetic examples establish code behavior only; they are not performance evidence. The manager is preparing the actual annual next-open/30-minute evaluation. No parameter tuning or performance improvement is claimed here.
