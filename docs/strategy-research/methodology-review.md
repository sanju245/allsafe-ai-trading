# Independent strategy research methodology review

Date: 15 November 2026. Scope: research design and read-only inspection of the available raw index candles. This reviewer changed no product code and makes no claim that any proposed rule is accurate or profitable.

## Research status and interpretation

The previous year has already been inspected. Every further comparison on that year is **exploratory research on reused data**. A correctly implemented expanding walk-forward policy is internally causal, but these results are not a pristine holdout or a prospective validation: the choice of seven rules and the thresholds themselves followed inspection of this year. Retain this distinction in filenames, charts and the user-facing summary. Do not relabel the final months as untouched.

Keep two outputs: full-year descriptive results for every fixed candidate, and the sequential policy ledger whose candidate was chosen only from preceding sessions. Never select the full-year winner and present its entire-year record as the walk-forward policy.

## Data finding: exclude VWAP

Independently inspected both raw files in `work/indicator-audit/annual-data/`: NIFTY50 and BANKNIFTY each contain 20,126 rows, all seven fields long. The volume field at index 5 is exactly zero on all 20,126 rows for each index; no positive volume was present. This does not supply usable traded volume for a volume-weighted benchmark. Exclude VWAP honestly; do not replace absent index volume with 1 or claim an equal-weighted price average is VWAP.

The existing annual manifest records 245 regular sessions per index, 18,375 regular 5-minute audit candles, 17 November 2025 through 13 November 2026. This reviewer read those manifest values but did not independently re-fetch exchange calendars or verify every raw timestamp. Preserve the original hashes and coverage evidence.

## Freeze the experiment before inspecting candidate results

The seven names are not sufficiently precise specifications. Record a configuration manifest with each threshold, period, event trigger, seed, tie rule, neutral behavior, warm-up, entry/exit convention and cooldown. Keep the seven candidates fixed: ADX confirmation, EMA pullback, Donchian20 breakout, Bollinger20x2 reentry, stochastic14/3 reversal, completed15m EMA9/21 plus UT, and regime consensus. Record any later edit as an additional experiment; do not silently iterate until a 60% result appears.

Specific calculation traps to verify:

- Donchian breakout compares the completed signal close against the **preceding** 20 candles' high/low channel, excluding the signal candle. Including its own high in a strict close-above-high test makes breakouts impossible.
- Completed15m confirmation must use a 15-minute candle only after its close. A 09:15, 09:20, 09:25 group closes at 09:30; it is unavailable at 09:20. Joining by the 15-minute candle's opening timestamp can introduce future data. Incomplete groups and session gaps must not produce a confirmation.
- ADX uses only completed OHLC and a pinned Wilder smoothing/initialization convention. Handle zero true range or directional denominator explicitly. Do not fill pre-warm-up values with tradable numbers.
- Bollinger must pin whether population or sample standard deviation is used and define precisely which previous candle was outside and which current closed candle returned inside. Stochastic must define range-zero behavior, %K/%D construction, and the exact reversal trigger.
- EMA pullback and regime consensus must be deterministic functions of completed information. The regime classifier must not use future realized volatility, future trend labels or full-year quantiles.
- Form every candidate signal at candle close; enter at the next real candle's open and exit 30 minutes after entry. Same-session eligibility and complete future path checks must match the original audit. Use true OHLC fills, including for any averaged-price indicator.

## Expanding walk-forward implementation

An initial 60 regular sessions followed by sequential 20-session evaluation blocks is a reasonable reproducible exploratory design. There are 245 audited sessions in the manifest, so the nominal policy has 185 sessions after initialization, with the last block possibly shorter. State those counts rather than pretending the policy was tradable for the full year.

At the start of each block, compute candidate eligibility and ranking using only labels that have fully matured before that block. Using earlier candles to initialize causal indicators is appropriate; using later outcomes to choose a candidate is not. Never randomly shuffle candles for selection. Keep the same calendar/block boundaries for both indices. With same-session exits, completed prior-session training labels do not cross the next-session boundary; a separate arbitrary embargo is unnecessary for that specific label design.

Apply the 30-minute cooldown identically in training and evaluation, per index and per candidate/policy. Define it from actual eligible entry to exit, not from an attempted signal that could not be filled. Allow a new entry exactly when the previous position expires if that is the pinned rule. Record suppressed events. Do not count overlapping candidate triggers as independent policy trades. Preserve cooldown state when necessary rather than resetting it to improve results at artificial boundaries.

## Eligibility gate and ranking

The proposed requirements—at least 60% gross direction accuracy, at least 40 training signals per index, positive mean after illustrative 2 bps total round-trip cost per index, at least 20 BUY and 20 SELL signals pooled, and a session-block-bootstrap lower bound above 50%—are acceptable **exploratory screening rules** if frozen before results. They cannot establish a future 60% success rate or justify live orders.

Clarify whether the bootstrap gate applies to each index or a pooled metric. Prefer each index: pooling can conceal failure in one index and the two indices are strongly related. Report index-and-side counts/accuracy even if pooled side support is the screening rule. A rule with little SELL support on one index cannot be advertised as validated for that side. A 40-event minimum is modest; it is a support filter rather than strong evidence.

Bootstrap entire session blocks, retaining all events and both indices together in each resample; do not independently resample individual trades or the two instruments. Use a fixed random seed and at least 1,000 replicates. A practical main block length is five adjacent trading sessions, with one- and ten-session sensitivity shown. Percentile intervals remain approximate; do not call them certainty. If a resample has no events for a required subgroup, mark it invalid/conservative rather than manufacturing a 100% rate.

There are seven candidate searches and repeated selection dates. A nominal per-rule 95% lower bound does not control the chance of selecting a lucky candidate. Publish all candidates and all selection decisions. A simultaneous adjusted lower bound or a training-only bootstrap that repeats the complete candidate-selection procedure can supplement the screen. These additions do not restore an untouched holdout after prior-year reuse.

Rank qualifying candidates by the minimum of their two index training accuracies, with a fully pinned deterministic tie-break. Do not inspect the next block to break ties. Hit-rate ranking can favor tiny wins and large losses, so retain mean net bps and payoff distribution alongside accuracy; the positive 2 bps mean condition is necessary for this screen but does not prove a profitable distribution. Report 5 and 10 bps sensitivity as illustrative cost scenarios, not a real broker fee estimate.

If no candidate qualifies, choose **WAIT**. Do not lower thresholds, remove a losing index, shorten the test period, or change thresholds after observing the block. All-WAIT produces zero trades and N/A accuracy, never 100% accuracy. Show abstention/block coverage and the number of qualifying candidates.

## Baselines and result presentation

Use the frozen original decision rule, the corrected decision rule, and UT Bot as fixed descriptive comparators with the same entry/exit/cooldown rules. At the candidate's exact event times, show always-BUY and always-SELL direction baselines to expose directional market bias. Also show a simple fixed persistence rule on a common eligible time grid; event-conditioned baselines alone do not compare coverage. Treat WAIT as abstention rather than a correct direction.

For each index and side, show events, wins/losses/flats, gross direction accuracy, after-cost win rates, mean/median net bps, worst event, monthly/block breakdown, and the cooldown/eligibility exclusions. Index-direction bps are not futures or option trade P&L. Baseline/candidate event sets may differ, so a higher percentage on fewer chosen events is not proof of broad improvement. Keep a complete per-event ledger and block-selection ledger for independent verification.

## Feasible acceptance decision

For this reused year, the maximum defensible outcome is an **exploratory paper candidate** passing the predeclared screen and showing plausible sequential results. No candidate should be promoted solely from the full-year leaderboard. It is possible that none passes; that is a valid result, not an audit failure. This reviewer has not yet seen proposed-rule results and cannot assert that none qualifies.

Freeze the full policy and then collect new forward data without changing it. A practical review gate is at least 60 new regular sessions and at least 100 eligible events per index, with both sides reported; if support is not achieved, continue collection and call evidence insufficient. Require positive after-cost expectancy and improvement over declared baselines by index with session-block uncertainty, plus acceptable loss behavior defined before that forward run. Any later parameter change restarts prospective validation. The gate is a proposed research acceptance policy, not a promise, broker-risk standard or authorization for autonomous/live orders.

## Primary sources

- Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting* (author-hosted paper): https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf — supports treating repeated financial-strategy selection as a source of false discoveries. No PBO statistic is claimed here.
- scikit-learn, `TimeSeriesSplit` documentation: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html — documents preserving time order so future observations do not enter past training. The proposed session-level design is specified above and does not assume ordinary 5-minute samples remain equally spaced across exchange closures.
