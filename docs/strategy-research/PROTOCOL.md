# Strategy research protocol — frozen before candidate results

Date: 2026-11-15. Parent: indicator audit at 9b06e29. This is read-only research, not order execution.

The goal is to investigate 60–80% next-30-minute directional accuracy, not guarantee it. Accuracy alone is insufficient: signal coverage, both BUY/SELL sides, costs, robustness and uncertainty must be disclosed. The year was examined in the previous audit; these chronological tests are retrospective, reused-data research, NOT an untouched holdout. A new forward observation period is required before any claim of validated improvement.

## Fixed candidates (no parameter sweep)

All consume only closed five-minute candles. Defaults are research variants, not a claim of replicating any vendor strategy. Each candidate has a separate elapsed 30-minute signal cooldown, applied before outcome scoring.

1. `adx_confirmation`: existing corrected five-indicator trigger, ADX14 >=25 and matching directional movement (+DI/-DI).
2. `ema_pullback`: EMA21/50 trend with ADX14 >=25 and matching DI; close recrosses EMA21 in the trend direction.
3. `donchian_breakout`: close breaks the preceding 20-bar high/low (current bar excluded); ADX14 >=25 and matching DI.
4. `bollinger_reentry`: SMA20, population standard deviation x2. ADX14 <20; preceding close outside its band and current close re-enters the band. Band touch alone is not a signal.
5. `stochastic_reversal`: fast K14 and SMA3 D; ADX14 <20; K crosses back above20 with K>D (BUY) or below80 with K<D (SELL).
6. `higher_timeframe_ut`: UT trigger with ADX14 >=25, matching DI and the direction of EMA9/21 on fully completed, session-aligned15-minute bars.
7. `regime_consensus`: in ADX>=25, at least two of pullback/breakout/higher-timeframe raw events agree and none oppose; in ADX<20, Bollinger and stochastic raw events must agree; otherwise WAIT. Its cooldown is independent.

Baselines: corrected original decision and the same decision with identical30-minute cooldown. No parameters or thresholds will change after reading returns. Implementation correctness fixes must be recorded and results rerun, not hidden as new trials. No volume-based rules: both source index datasets have zero reported volume throughout; no invented VWAP/OBV.

## Evaluation

Data: existing authenticated Upstox V3 raw history; requested2025-11-15 through2026-11-14, with35 calendar days of warm-up. Verify hashes and weekday session calendar. Retain provider provenance; prices are not independently verified against a second vendor.

Signal at candle close; enter next candle open; exit after30 minutes (also5/60 minutes). Exact, contiguous same-session paths only. Flat is not a win. Use fixed2/5/10 total round-trip basis-point cost scenarios, not broker fee estimates. No repeated state bars counted as new events. Never use future prices, unfinished15-minute bars, or same-close entry.

Initial60 sessions form the first expanding training window. Select for each next20-session test block using only outcomes completed in earlier sessions. The final partial block is retained. The seven fixed candidates are also reported separately across all later test sessions; ranking after seeing those results is descriptive selection bias, not an independent winning model.

Training eligibility, unchanged if nothing qualifies: each index >=40 signals, >=60% gross accuracy, positive mean after2bps and session-bootstrap95% lower accuracy bound >50%; pooled BUY and SELL each >=20. Among eligible candidates choose the largest minimum of the two index accuracies; tie-break by fixed candidate order. No qualifier means WAIT for that entire block. Use paired session resampling for the pooled cross-index report and session-block resampling within each index. Fixed random seed,2,000 draws. Intervals are descriptive and are not multiple-testing-adjusted or a guarantee of independence.

Research target gate on chronological test results: each index >=100 observations, BUY and SELL each >=20 per index, gross accuracy >=60%, positive mean after2bps, session-bootstrap95% accuracy lower bound >50%. This gate does NOT authorize production use or establish60% as a lower bound. At least one new forward period and execution-cost evaluation remain necessary. No automatic promotion from these results.

Report all rules (including failures), chronological test accuracy/counts, full-year descriptive accuracy, BUY/SELL breakdown, monthly results, cost sensitivity, mean directional move, profit factor, non-overlap subset, same-time always-BUY/SELL comparators, confidence intervals, exclusions and policy WAIT blocks. Preserve raw ledgers and full diffs.

## Primary research sources

- ADX/DMI: https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/ — strength and direction must be distinguished; conventional20/25 thresholds.
- John Bollinger: https://www.bollingerbands.com/bollinger-band-rules — band tags alone are not signals; related indicators do not provide independent confirmation.
- Donchian: https://www.tradingview.com/support/solutions/43000502253-donchian-channels-dc/ — high/low channels and trend context.
- Stochastic: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/fast-stochastic — closing position within range.
- VWAP: https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/ — requires usable volume, absent here.
- Bailey et al., The Probability of Backtest Overfitting: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf — repeated strategy selection can overfit historical data.

These sources motivate hypotheses, not60–80% accuracy claims for NIFTY/BANKNIFTY. More complicated Ichimoku/CCI/ML or volume strategies are deferred instead of trying unlimited configurations on this same year.
