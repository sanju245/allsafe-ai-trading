# Verification and handover — completed 16 November 2026

This change adds seven fixed research strategies, a separate evidence gate and website results. The requested 60–80% accuracy was not achieved. No strategy was promoted; no order execution was added.

## Checks

- Manager backend/audit run: 318 tests passed, including synthetic formula fixtures, no-lookahead prefixes, completed 15-minute bars, neutral values, gap resets, independent cooldowns, previous-session selection, no-trade/N/A handling, API research-only output, authentication/access regressions and cache/freshness checks. One existing Starlette/httpx deprecation warning remains.
- Frontend: 29 tests, lint, typecheck and production build passed. Manager also captured an independent run in `frontend-manager-checks.txt` rather than relying only on the specialist summary.
- Research was reproduced from saved raw files without credentials after the `active_sessions` reporting-name correction. Source and frozen-protocol hashes are included in `strategy-results.json`.
- Independent reviewer recomputed 14,770 outcome rows directly from saved OHLC, including all 4,960 observations at 30 minutes; aggregate results and all ten WAIT selection blocks matched. Details are in `independent-verification.md`.
- Browser inspection of the local production build `/research`: result tables, WAIT 10/10, N/A for zero policy trades, coverage, sources, and expandable annual results were visible. No browser console errors were returned. Screenshots saved. No authenticated production customer session was used for this preview; dashboard decisions are covered by backend and frontend tests, not a claim of a live production end-to-end session.
- No source changes to authentication roles, IP policy, provider credentials or broker order handling. No credentials were needed for this research.

## Behaviour and limitations

The existing corrected five-indicator logic remains distinct from the new research observations. A confirmed signal describes a closed-candle calculation, not proven predictive accuracy. Even a live quote cannot mark a five-minute signal current once its confirmed candle is older than the current five-minute decision window. The frontend clock expires old observations independently of network refresh.

The research engine emits WAIT and `is_current_signal=false` unconditionally until a separate prospective validation and release review. It can expose timestamped hypothetical setups, but these are not automatically selected from the best historical result. Each candidate has its own fixed 30-minute cooldown. Source validation resets on intraday gaps and rejects invalid timestamps, OHLC, instruments or timeframes.

One cached snapshot per instrument is keyed by the full validated timestamp/OHLC/timeframe sequence. Changed or added candles cause recomputation. Feed and candle freshness is evaluated on every request, so cached data cannot preserve an expired signal. This avoids redundant computation; no measured latency or throughput improvement is claimed.

The supplied year was already studied. Chronological tests remain retrospective reused-data evidence. One-session bootstrap intervals are descriptive, not adjusted for all serial dependence or repeated model selection. Actual derivatives fills and broker costs are not evaluated; fixed 2/5/10 bps scenarios are sensitivities. No new candidate has positive mean after 2 bps on both indices in the later 185-session period.

The live feed's existing history/warm-up and rolling-buffer limitations remain: a restart or incomplete provider history can differ from full-history offline replay. The research UI shows unavailable/warming states when insufficient data exists; it does not manufacture missing candles. No future collection run has been completed or started as a persistent service in this task.

## Release boundary

Branch: `codex/strategy-research-2026-11-15`, based on `9b06e29`. Protocol commit: `ce5007c`. `git-release.txt` records final commit and remote verification. Production main was checked at `d7e41fbfd5b4a6fa4413a61855473ef073715ef5` before publishing the review branch.

No merge to main or production deployment was performed. The review branch also contains the previously audited strict bearish/neutral confirmation corrections. To release, review both the accumulated diff against production and the strategy-only diff. Production publication remains subject to the user's explicit approval.

## Archive contents

- Portable research report, accuracy comparison CSV and browser screenshots.
- Frozen protocol, methodology review, independent verification and this handover.
- Original provider raw candles, full strategy outcome ledgers, complete aggregate results and policy ledger.
- Created/modified source files, full diff from production, strategy-only diff, file inventory, test outputs and SHA-256 manifest.
- No environment files or access tokens. Dropbox account-only destination remains `/AllSafe_AI_Trading_Launch_2026-11-15`; no public sharing link is created.

Reproduction commands are in `STRATEGY_RESEARCH.md`. The raw files are unchanged from the earlier indicator audit. Rules and thresholds were frozen before evaluating these seven candidates; no losing strategy was hidden or tuned until it appeared to meet the target.
