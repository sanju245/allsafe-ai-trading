# UT Bot specialist audit — 2026-11-15

Scope: `apps/api/app/indicators/ut_bot.py` on baseline `d7e41fb`. No product source was modified by this specialist. This is a formula, causality and audit-method review; it is not a one-year performance result.

## Outcome

No material arithmetic error was demonstrated in the ATR recurrence, trailing-stop updates or BUY/SELL crossover conditions. All calculations depend only on the current closed candle and preceding candles. The optional source uses OHLC4, which is the Heikin Ashi close; it is not an executable market price.

Defaults inspected: sensitivity 1.0; Wilder ATR period 10; standard close source (`use_heikin_ashi=False`). ATR first becomes available on candle 10; a crossover requires a previous valid trailing stop, so the first eligible crossover is candle 11. The decision engine also waits for all confirmation indicators.

## Direct checks run

Credential-free synthetic fixture: chronological 5-minute candles with closes/open prices `[100, 103, 99, 105]`, highs `close+1`, lows `close-1`, ATR period 1, sensitivity 1. This is SAMPLE data and must not be used for accuracy percentages.

| Candle | ATR | Stop | Position | Signal |
|---|---:|---:|---:|---|
| 1 | 2 | 98 | 0 | none |
| 2 | 4 | 99 | 0 | none |
| 3 | 5 | 104 | -1 | SELL |
| 4 | 7 | 98 | 1 | BUY |

The implementation matched these hand-calculated values. Recalculating every prefix produced exactly the same corresponding prefix of full-series output. Removing the final candle did not change earlier output. Four flat candles with zero ranges produced ATR 0, stop 100, and no signals. These checks verify arithmetic and absence of future dependence on this fixture; they do not establish predictive accuracy.

## Findings and recommendations

1. **High priority audit gap: existing regression tests do not assert an expected BUY or SELL on a specified candle.** `test_signal_values_are_only_buy_sell_or_none` validates the enum domain even if a broken implementation never emits a signal. Add the hand-calculated reversal fixture above, a non-unit ATR smoothing fixture and a longer prefix-invariance case. This is a test-coverage finding, not a proven live calculation bug.
2. **Pin initialization when comparing references.** The code intentionally seeds ATR with the first period's average range and initializes a valid stop only when ATR exists. Exact parity with a TradingView script depends on the reference script's initial `na`/`nz` handling and warm-up history. No claim of exact full-bar TradingView parity is supported by this review because the original published Pine source body was unavailable through the browser extraction. Keep a substantial pre-audit warm-up and record it in the data manifest.
3. **Session gaps require an explicit audit policy.** The pure function checks ordering and homogeneous instrument/timeframe but does not reject missing intraday slots. It includes an overnight gap in true range using the prior close, which is internally consistent and should remain the baseline. The current live runtime separately blocks missing/incomplete intervals and validates merged candles. Historical audit must validate the series first and exclude labels whose entry/exit path crosses missing bars. Do not invent candles or reset ATR daily without labelling that as a separate strategy variant.
4. **Heikin Ashi prices must remain signal-only.** If enabled, evaluate fills and returns using real OHLC next-open prices. Backtesting on OHLC4 fills would misstate executable results.
5. **Do not optimize sensitivity on the entire audited year.** UT Bot reacts after a price/stop crossover. Larger sensitivity changes the delay and flip frequency; improvement must be measured on a held-out period with the same cost and horizon assumptions. Fewer flips alone is not evidence of greater accuracy.
6. **Minor input consistency:** sensitivity accepts `True` as 1.0, unlike the ATR period which explicitly rejects booleans. Rejecting booleans would make parameter validation clearer, but it does not explain a wrong signal with numeric production defaults.

`UTBotPoint.position` is state set by signal emission rather than a position created by broker execution. It must not be counted as a filled trade. BUY/SELL occurrences in `signal` are the event series to audit; `None` is no trigger, not a correct prediction.

## One-year performance status

No full-year authenticated historical 5-minute dataset was supplied to this specialist. Win rates, signal counts, monthly results and improvements remain **not measured**. Required inputs: real NIFTY50/BANKNIFTY 5-minute OHLC with timezone-aware candle-open timestamps, period/coverage manifest, pre-period warm-up, missing-slot accounting and an agreed future-outcome horizon. Enter only after the signal candle closes, normally at the next actual candle's open. Report BUY and SELL separately, sample sizes, flat outcomes and uncertainty; do not count WAIT as a successful prediction.

## Primary sources consulted

- Original author publication: https://www.tradingview.com/script/n8ss8BID-UT-Bot-Alerts/ — confirms script identity/open-source status and attribution; source body was not accessible in extracted page, so exact Pine parity is not asserted.
- Author's current methodology explanation: https://www.tradingview.com/script/lDGmh7ou-UT-Bot-v2-ATR-Trailing-Stop/ — describes ATR stop and price-crossing framework; not used to replace this project's pinned baseline.
- TradingView Heikin Ashi construction: https://www.tradingview.com/support/solutions/43000619436-understanding-heikin-ashi-charts/ — confirms HA close is current OHLC4 and represents averaged prices.
- TradingView repainting concepts: https://www.tradingview.com/pine-script-docs/concepts/repainting/ — supports distinguishing confirmed-bar output from changing unconfirmed-bar values.
