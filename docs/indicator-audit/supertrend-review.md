# Supertrend specialist review

Reviewed source: `apps/api/app/indicators/supertrend.py` at baseline `d7e41fb`.
Scope: formula, warmup, causal behavior, direction state, validated-candle contract. No product files changed.

## Findings

### Medium: the initial trend state differs from TradingView's published Supertrend convention

The app chooses its first valid direction using `1 if close >= (high+low)/2 else -1`. TradingView's published algorithm initializes the direction to downtrend until the ATR seed is available; its built-in reference initialization also starts downtrend when the prior ATR is unavailable. These are different variants, and the app must not claim exact TradingView parity without adopting/testing the same initialization.

Hand-computed counterexample: repeated candles with open=close=100, high=101, low=99; period=2, multiplier=3. True range is 2 on every bar, so the first valid ATR is 2. Basic/final bands are 106 and 94. The app selects bullish (+1) and value94 because close equals HL2. A bearish reference seed selects the upper band106. With flat candles neither band is crossed, so this difference can persist indefinitely; merely discarding a fixed warmup window is not a proof of convergence.

This is a reference-convention discrepancy, not evidence that either variant has better annual accuracy. Recommended action: explicitly name the current midpoint-seeded variant in the audit, freeze it for baseline comparisons, and introduce reference-compatible initialization only as a separately evaluated candidate if TradingView parity is the desired contract. Do not tune the seed against the same annual evaluation period.

### Low: standalone calculation trusts valid input

Unlike UT Bot, this function does not itself reject out-of-order timestamps, mixed instruments, nonfinite OHLC, malformed high/low values, or missing intraday intervals. The current decision path invokes UT validation first and the live runtime validates merged candles, so this is not a demonstrated bypass of current live signal protection. Any new standalone audit caller must validate data before invoking Supertrend. Retaining overnight gaps in true range is standard; an unexpected missing intraday bar must be reported rather than silently treated as contiguous history.

### Coverage gap: existing test asserts only warmup presence

The existing `test_supertrend_warmup` checks that direction exists after period candles; it does not check numeric ATR, final bands, initialization, flips, or equality boundary behavior. Meaningful regression cases should pin a hand-calculated band/flip sequence and the declared initialization variant. Prefix invariance should be checked to ensure a future candle cannot alter an earlier point.

## Formula review

- True range uses max(high-low, abs(high-previous_close), abs(low-previous_close)), with first-bar high-low.
- Wilder ATR is seeded with the period-bar true-range mean, then updates `(previous_atr*(period-1)+tr)/period`.
- Upper/lower final bands use prior close and previous bands according to the published recurrence.
- Subsequent direction uses previous Supertrend position and the current close relative to the current final band. Strict crossing rules agree with the primary reference.
- App numeric direction signs (+1 bullish, -1 bearish) are an explicit app convention; numeric signs alone do not establish a defect. TradingView's built-in direction sign convention differs.
- The calculation references only the current and prior candles and previous computed state. No forward access is present.
- A Supertrend direction is a continuing state. An individual BUY/SELL event should normally mean a direction transition, not a new order on every candle with the same state. The manager's audit should report state observations separately from transition events.

## Primary reference

TradingView, Supertrend calculation and band/direction definitions:
https://www.tradingview.com/support/solutions/43000634738-supertrend/

Read on 2026-11-15. Findings above paraphrase the equations and distinguish the app's initialization variant from the reference.

## Annual performance status

No historical market dataset was supplied to this specialist. No one-year hit rate, win rate, return, or improvement percentage has been calculated here. The manager is preparing a causal next-open, 30-minute directional audit on actual five-minute candles. This review does not claim predictive improvement.
