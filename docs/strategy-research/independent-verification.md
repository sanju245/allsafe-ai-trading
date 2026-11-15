# Independent strategy-result verification — 15 November 2026

Reviewer: indicator UT/research methodology specialist. Read-only review of `scripts/research_strategies.py`, `apps/api/app/indicators/strategies.py`, `research_decision.py`, and runtime freshness changes. No product source edits by this reviewer. Verification used existing local raw data and ledgers; no credentials, broker calls or trading operations were required.

## Verified independently

An independent Python verifier did not import the research runner's scoring, aggregation or selection functions. It read the raw Upstox candles, both strategy CSV ledgers and `strategy-results.json` directly.

- **14,770 ledger rows checked** across 5-, 30- and 60-minute horizons; **4,960 rows are 30-minute observations**.
- Every row had entry exactly one 5-minute candle after signal timestamp. Every exit was exactly its horizon after that entry. All required intermediate candles existed, with no overnight path; stored entry matched next-bar raw open and stored exit matched final-bar raw close.
- BUY/SELL direction, gross basis-point return and always-BUY benchmark return were recomputed from raw prices. Every value matched within floating-point tolerance. No duplicate strategy/symbol/signal/horizon key occurred.
- All nine rules/baselines × two indices × three horizon counts and accuracies matched the JSON. Full-year and later-period 30-minute event counts, wins, mean gross/2-bps net moves and BUY/SELL support/accuracy also matched.
- The regular annual calendar yielded 245 sessions. Initial training uses 60 sessions; evaluation covers 185. There are 10 chronological blocks, including the final partial block.

## Selection and target gates

All 10 selection boundaries were independently reconstructed. Training rows had both signal and completed exit strictly before each test block, and no training exit followed the recorded training-through session. Test starts were 12 February, 13 March, 16 April, 15 May, 15 June, 14 July, 11 August, 8 September, 8 October and 6 November 2026.

At every boundary, **none of the seven candidates passed the deterministic pre-bootstrap training requirements**. Therefore a bootstrap bound or tie-break could not make a candidate eligible. Each recorded selected strategy was null/WAIT; all block event counts were zero. The policy ledger contains zero rows. **WAIT 10/10 and policy accuracy N/A are verified**, not copied from the headline summary.

For each of the seven candidates, both indices already failed at least one deterministic retrospective target requirement on the later chronological period. Thus all seven failed-target flags are correct regardless of the uncertainty gate. This supports the reported refusal to promote a rule; it does not mean the candidates have been proven useless in every future market.

## Bootstrap and causal calculations

Independently reconstructed the NIFTY50 regime-consensus full-year 2,000-draw session-bootstrap calculation from its event ledger, including zero-event sessions and the fixed seed. It matched:

- Descriptive accuracy interval: **40.6417112299%–53.5714285714%**.
- Mean directional move after illustrative 2 bps interval: **−5.2001149576 to −0.1520739432 bps**.

These are the runner's one-session resampling intervals. Longer serial dependence and multiple strategy selection remain limitations; this is not a simultaneous or prospective confidence guarantee. The proposed five-session sensitivity is not implemented here. Because no candidate reaches the deterministic training gate, the current selection result is unaffected by that missing sensitivity.

Strategy output prefix invariance passed at prefixes of lengths 1, 14, 28, 50, 60, 62, 63, 75, 150 and 250 within a 320-bar real-candle slice. Appending later candles left each earlier output unchanged. This is a direct finite test of the implementation's causal behavior, not an exhaustive proof.

Rebuilt completed 15-minute closes and SMA-seeded EMA9/21 directions incrementally with an independent reference over 320 bars; every direction matched. The third 5-minute candle supplies the completed group's close. The implementation does not project the final group's value into its first two bars. Donchian compares against preceding bars and excludes the signal candle. No forward-outcome access was found in the strategy rules.

Source and protocol SHA-256 hashes in the result file matched the files inspected during this verification. Later edits require rerunning or updating this verification.

## Research gate and freshness

`research_decision.py` always returns research status and decision WAIT, with `is_current_signal=False` and no selected strategy. It may expose a fixed regime-consensus candidate observation, clearly separate from eligibility. It does not choose the full-year winning strategy or turn historical accuracy into a live probability.

Both legacy and research current-observation flags require LIVE/non-stale feed plus a confirmed five-minute candle whose close is no more than one five-minute interval old. The bounds are causal: candle-open +5 minutes <= evaluation time < candle-open +10 minutes. Missing/unvalidated data returns unavailable research context while preserving the WAIT decision. No orders are implemented by these modules.

## Reporting clarification

The reviewed count means sessions containing one or more events, not sessions whose aggregate return is positive. The manager corrected its name to `active_sessions` in the runner and is rerunning aggregate outputs before archiving. This naming correction does not affect the independently verified accuracy, selection or WAIT. No material outcome/selection/freshness blocker was found.

The manager added a cache keyed by instrument and the entire validated candle timestamp/OHLC/timeframe sequence. A subsequent read-only code review found its freshness flags still recomputed on every request rather than cached, while changed/added/removed candle values invalidate the snapshot. No code-review blocker was found. The manager's cache-invalidation tests complement this check; cache behavior is not covered by the independent full-ledger recomputation.

## Limits

This is exploratory reused-year research. The prior year had already been inspected before these hypotheses; the chronological split is not a pristine holdout. Raw prices came from the same saved provider files and were not independently checked against another vendor. This verifier checked all ledger outcomes and reported aggregates but did not independently reimplement every candidate's full signal-generation formula over the entire year. The manager's formula/regression tests complement this review. Index directional moves and illustrative costs are not executable futures/options P&L. Forward observation remains necessary before any promotion.
