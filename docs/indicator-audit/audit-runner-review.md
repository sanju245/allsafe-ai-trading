# Independent audit-runner review — 2026-11-15

Reviewed `scripts/audit_indicators.py` and `scripts/indicator_baseline.py` read-only. No source edits by this reviewer.

## Correct behavior observed

- Indicator series are calculated from historical candles without accessing forward outcomes. Forward values are used only by scoring.
- A 5-minute candle opening at t signals after t+5. Entry is the next candle's open at t+5. The 30-minute horizon uses the close of candle index i+6, at t+35, giving exactly 30 minutes after entry.
- Intraday missing slots split calculation chunks. Labels require a same-date exit at the exact expected grid position, excluding overnight outcomes and incomplete future horizons.
- Flat outcomes do not count as wins; WAIT/zero events do not inflate accuracy. Non-overlap summaries and illustrative total-cost sensitivity are included.
- Token authentication is limited to a fixed HTTPS Upstox host. Redirects are disabled, User-Agent is descriptive, and provider bodies/credential values are absent from output/error logs. Local hidden input avoids asking for chat disclosure; execute it in a real terminal so getpass does not fall back to visible input.
- Baseline uses the old decision conditions while importing current indicator implementations. This is equivalent to the pinned baseline only while indicator math/old bullish fields remain unchanged. The current EMA change adds bearish without changing bullish values or EMA arithmetic, so the present comparison is valid. Freeze hashes and warn against treating this as a frozen baseline after later arithmetic changes.

## Reporting findings sent to manager

1. The Markdown title and completed state must not imply a complete year when input may contain a few sessions. JSON already records first/last dates, partial sessions and missing weekdays, but the user-facing Markdown needs those values and explicit coverage-review status. Missing weekdays cannot be certified as holidays without an exchange calendar. This is a reporting blocker for publishing a one-year accuracy claim, not for fetching/scoring data.
2. Add BUY-only and SELL-only accuracy, not only counts, because the user requested correctness of both types.
3. Distinguish changed selectivity from predictive improvement: baseline and corrected decisions may emit different event sets. A higher win percentage on fewer events alone does not establish a generally better strategy. Report counts, matched-event differences and final-period results.
4. Keep overlapping-event confidence intervals explicitly descriptive. Their current caveat is appropriate; overlapping labels do not provide independent evidence.

No forward-leakage defect or secret-exposure defect was found in the inspected runner. This review does not certify historical-data completeness or measured accuracy because the full dataset was not available to this reviewer.
