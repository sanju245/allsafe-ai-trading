# Independent RSI audit

Reviewed 15 November 2026. Scope: `apps/api/app/indicators/rsi.py`, its use in `decision.py`, and existing confirmation tests. No product source was changed by this reviewer.

## Formula and causal behavior

The implementation computes close-to-close gains/losses, seeds averages from the first `period` changes, then uses Wilder smoothing `(previous * (period - 1) + current) / period`. RSI14 first becomes available on candle index 14 (15 candles), which is consistent with requiring 14 changes. Each output depends only on current and preceding closes; no future values are referenced.

TradingView's own RSI description specifies RMA of gains/losses and the usual relative-strength formula: https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/ . The app's `>50` confirmation rule is a strategy choice, not a universal definition of a profitable BUY signal. The source describes RSI around 50 as no trend.

## Confirmed finding: neutral is treated as bearish

`rsi.py:38` reports `bullish=False` for RSI exactly 50. `decision.py:50` treats every confirmation's `False` value as bearish when allowing SELL. Thus RSI with balanced gains/losses (including a completely flat series) passes the RSI side of bearish unanimity. A flat RSI does not itself produce a complete SELL—the UT Bot trigger and other filters are still required—but this is a confirmation classification flaw.

Minimal correction: keep explicit conditions for bullish `RSI > 50`, bearish `RSI < 50`, and neutral `RSI == 50`. Preserve insufficient history separately. Do not simply return `None` for neutral while the decision engine interprets all `None` values as warmup/data unavailable. An explicit bearish property or explicit numeric comparison in the decision engine avoids that ambiguity. A wider neutral band (for example 45–55) must be evaluated out of sample before adoption; no evidence yet supports changing the threshold.

## Executed local numerical checks

An isolated Python audit imported the actual RSI function and constructed synthetic candles using the existing test helper:

- Period 3, closes `[100, 101, 100, 102, 101]`: first RSI `75.0`, next `54.54545454545455`. Both match independently hand-computed seed and Wilder-update values.
- Period 14, 20 closes all equal to 100: RSI `50.0`, `bullish=False`. This reproduces the neutral classification finding.
- A 100-candle alternating deterministic series: each prefix's final RSI object equalled the corresponding full-series output (`prefix_equal=True`). This verifies causal behavior for that check.

Existing tests cover warmup and a monotonic rise but omit mixed-change reference values, monotonic decline, neutral equality and prefix invariance.

## Input boundary and efficiency

RSI validates its period but assumes finite, ordered, consistent candles. `Candle` deliberately allows malformed data. The combined decision path invokes UT Bot first, whose checks catch many malformed inputs, and documents validated chronological closed input. The year-audit loader must independently reject invalid, duplicate, mixed-timeframe and unclosed candles before standalone RSI evaluation. Avoid interpreting NaN-produced `False` as bearish.

The calculation is linear in candle count. It allocates several lists, which is acceptable for a year of ordinary 5-minute index candles; no measured bottleneck establishes a need to change the numerical implementation. Reusing precomputed RSI arrays in the historical evaluator is preferable to recalculating RSI separately for every prefix.

## Historical accuracy status and evaluation requirements

No one-year real-data accuracy percentage is available from this review. Synthetic checks establish calculation properties and do not estimate market predictive accuracy.

Use the user-approved next-open to 30-minute close direction outcome. Disclose whether standalone RSI signals mean every eligible state, a state transition/crossing, or a specific entry strategy; these yield different denominators. Report BUY and SELL counts and hit rates separately, neutrals/warmup excluded, and zero-return ties separately. Prevent overnight exits unless explicitly intended, reject missing target bars, include 5-minute and 60-minute secondary horizons, and report cost sensitivity. Preserve a final untouched time segment when evaluating any proposed threshold or period change.

## Recommended regression cases

1. Mixed-close hand-reference series above.
2. Monotonic fall yields RSI 0 after warmup.
3. Flat prices yield RSI 50 and neutral confirmation; neutral cannot satisfy SELL unanimity.
4. Prefix outputs remain unchanged when future bars are appended.
5. Invalid periods fail, including booleans; evaluator rejects malformed candles and incomplete future horizons.
