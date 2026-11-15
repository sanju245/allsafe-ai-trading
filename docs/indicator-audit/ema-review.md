# EMA specialist audit

Reviewed source: apps/api/app/indicators/ema.py and apps/api/app/indicators/decision.py at project baseline d7e41fb.

## Findings

### P1 — Mixed or flat EMA alignment incorrectly confirms SELL

`calculate_ema_trend` assigns `bullish = a > b > c` after warmup. Every other alignment becomes `False`, including a mixed arrangement or all three EMAs being equal. `calculate_decisions` then accepts all four filter booleans being `False` as unanimous bearish confirmation. Thus its message that all four indicators are bearish is not established by the EMA filter.

Concrete numerical counterexample: closes 100,101,...,199,150,150. With the code's SMA seeding and recurrence, final EMA9=178.8, EMA21 approximately182.2314, EMA50 approximately172.6152. This arrangement satisfies neither EMA9>EMA21>EMA50 nor EMA9<EMA21<EMA50. The current indicator nevertheless supplies the same `False` value as a strictly bearish alignment. A flat series also produces `False` once warmed up.

Independent arithmetic verification: a PowerShell recurrence using those closes reproduced EMA9=178.80, EMA21=182.23, EMA50=172.62. This checks the numeric example; no Python product test was run by this specialist.

Recommended minimal change: preserve `bullish` and add an explicit `bearish` field computed as EMA9<EMA21<EMA50. Use the explicit bearish field in SELL confirmation. Mixed and equal arrangements should produce WAIT when no other rule establishes entry. Do not simply represent mixed alignment as `None` without changing the decision engine's warmup detection: it currently treats every `None` as insufficient history.

### Formula and warmup are internally consistent

The EMA recurrence uses alpha=2/(period+1), a simple-average initial seed, and only prior/current closes. EMA9 first appears at index8, EMA21 at20, and EMA50 at49. The trend becomes available only after50 candles. These choices are coherent; the source should explicitly document its SMA seed because initialization can differ between charting libraries. The existing test checks only EMA50 availability, not its numeric value or direction semantics.

The code has no future-data access. Appending future candles cannot change a previously calculated EMA prefix. Slicing a rolling history window does change the initial seed and therefore subsequent EMA values; a historical audit must use a single consistent warmup prefix or reproduce the production window exactly rather than resetting each signal.

The EMA module assumes validated chronological, finite closes and does not itself enforce them. The combined decision calls UT Bot first, which validates chronological order, common instrument/timeframe, finite OHLC, and OHLC bounds. Direct EMA consumers should preserve the same validation contract.

## Necessary regression cases

1. Strict rising series: bullish true, bearish false after50-bar warmup.
2. Strict falling series: bullish false, bearish true.
3. Flat series: neither bullish nor bearish; no SELL confirmation from equality.
4. Mixed numerical example above: neither direction.
5. First available EMA9/21/50 numeric seed values and recursive update values.
6. Prefix invariance when future candles are appended.
7. Combined decision with SELL trigger and other bearish filters: mixed/equal EMA should yield WAIT rather than SELL.

## Annual performance status

No year of genuine historical candles was supplied to this specialist, so annual accuracy and return percentages are unavailable. No synthetic example above is historical performance evidence. Measure BUY and SELL separately with the user's agreed next-open entry and30-minute outcome, include eligible-signal counts and neutral/warmup exclusions, and report the combined decision separately from the EMA trend filter. State-based EMA direction should not be misrepresented as a fresh crossover on every candle.

## Primary reference

TradingView's EMA explanation describes recursive weighting of the close and previous EMA, and cautions that moving averages lag price. It does not guarantee this application's three-EMA classification or annual accuracy: https://www.tradingview.com/support/solutions/43000592270-exponential-moving-average/

No product source was modified by this specialist.
