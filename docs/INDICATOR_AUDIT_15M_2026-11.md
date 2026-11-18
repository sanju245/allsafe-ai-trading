# 15-Minute Indicator Audit

## One-month result

The revised 15-minute decision rule recorded a **68.2% directional hit rate** across NIFTY 50 and Bank Nifty in the checked month. It exceeded 60% for each index in this sample:

| Index | Previous unanimous rule | Revised rule | Revised 95% Wilson interval |
|---|---:|---:|---:|
| Bank Nifty | 2/8 (25.0%) | 8/11 (72.7%) | 43.4–90.3% |
| NIFTY 50 | 4/7 (57.1%) | 7/11 (63.6%) | 35.4–84.8% |
| Combined | 6/15 (40.0%) | 15/22 (68.2%) | 47.3–83.6% |

The evaluation window is **October 19–November 18, 2026**, inclusive: 21 NSE sessions and 525 valid 15-minute bars per index. OHLC data were retrieved from Yahoo Finance's 15-minute chart history for [NIFTY 50](https://finance.yahoo.com/quote/%5ENSEI/history/) and [NIFTY BANK](https://finance.yahoo.com/quote/%5ENSEBANK/history/). Its chart feed also returned one flat 15:30 record per symbol on November 18; those out-of-session records were excluded. The checked window ends at the last completed session available before this audit.

This is a **historical directional hit rate**, not a claim that the scanner will maintain 60% accuracy. There were only 11 signals per index. The confidence intervals include true hit rates below 60%. The rule was selected after comparing alternatives, and this month was inspected during that comparison, so this is exploratory rather than an untouched holdout.

An earlier comparison slice, September 21–October 16 (19 sessions), scored 3/7 (42.9%) on Bank Nifty and 6/8 (75.0%) on NIFTY 50, or 9/15 (60.0%) combined. The rule selection also considered that slice, so it is not independent confirmation.

## Accuracy definition

A signal is scored at a fixed one-hour directional horizon. Entry is the next 15-minute bar's open; exit is the close of the fourth bar after the signal candle. The full interval must remain within the same NSE session and have all four 15-minute bars. A BUY is correct only if the index moves up; a SELL is correct only if it moves down. Flat moves count as incorrect.

These are index-spot direction checks. NIFTY 50 and Bank Nifty indices cannot be bought or sold directly. This score does not simulate futures or options, stops, spreads, slippage, brokerage, market impact, or taxes, and therefore is not a profitability measure.

## Indicator-by-indicator gate comparison

The table below applies each confirmation separately to UT Bot crossover signals and scores the same one-hour outcome. Each row is a gate ablation, not a standalone strategy or a signal forecast for every bar.

| 15-minute rule | Bank Nifty | NIFTY 50 |
|---|---:|---:|
| UT Bot crossover alone | 19/58 (32.8%) | 26/53 (49.1%) |
| UT Bot + EMA 9/21/50 stack | 11/20 (55.0%) | 10/18 (55.6%) |
| UT Bot + RSI side of 50 | 13/37 (35.1%) | 14/30 (46.7%) |
| UT Bot + MACD histogram sign | 4/26 (15.4%) | 12/24 (50.0%) |
| UT Bot + Supertrend direction | 13/28 (46.4%) | 13/26 (50.0%) |

The revised rule combines the five indicators differently from the one-at-a-time ablation: UT Bot position, EMA direction, and Supertrend direction must agree with the opening-range break; RSI **or** MACD must also agree.

## What changed

- **EMA:** bullish only when EMA 9 > EMA 21 > EMA 50; bearish only for the strict reverse. Mixed stacks are neutral.
- **RSI:** above 50 is bullish, below 50 is bearish, and exactly 50 is neutral.
- **MACD:** the histogram sign determines direction; zero is neutral.
- **Supertrend:** exposes explicit bullish/bearish direction and validates its multiplier input.
- **UT Bot:** validates numeric sensitivity and requires an actual boolean Heikin Ashi setting; its output timestamp is typed as `datetime`.
- **15-minute decision:** waits for a confirmed close beyond the 09:15 candle's high or low. The first range break is the only eligible attempt that session. UT Bot position, EMA, and Supertrend must agree; RSI or MACD must confirm. Missing 09:15 data disables that day's setup, and signals after 14:15 are blocked so the one-hour evaluation window fits within the session.
- **Other timeframes:** retain UT Bot crossover triggers and require all four confirmation indicators to agree directionally. Neutral indicator states do not confirm a sell.

Spot index candles do not provide traded volume, so no volume or VWAP filter was added.

## Research notes

The NSE intraday-activity study reports a U-shaped pattern in activity and volatility, with increased activity near the open and close ([Sampath & Gopalaswamy, 2020](https://journals.sagepub.com/doi/10.1177/0972652720930586)). That supports evaluating an opening-range setup and avoiding late signals; it does not prove this rule's hit rate.

[TA-Lib](https://github.com/TA-Lib/ta-lib) is a useful reference for standard indicator calculations, not evidence that a strategy is profitable. The [India Trader Skill repository](https://github.com/prakhar728/india-trader-skill) describes a logged research workflow and notes its intraday experiments require broker data not bundled in the repository. No unverified GitHub win-rate claim was adopted. Research on [data-snooping bias](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=65140) explains why testing many candidate rules and reporting the best one can inflate apparent historical performance.

For a stronger follow-up, keep this rule fixed and evaluate more unseen months with authorized broker data and realistic fill and transaction-cost assumptions.

## Reproduce

The raw CSV is not committed. Export authorized OHLC history with these columns: `symbol,timestamp,open,high,low,close`. Timestamps must be ISO 8601 with a timezone. From the repository root:

```powershell
.venv/Scripts/python.exe apps/api/scripts/audit_indicator_accuracy_15m.py path/to/candles.csv --start 2026-10-19 --end 2026-11-18
```
