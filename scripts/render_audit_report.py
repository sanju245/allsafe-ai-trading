"""Generate a readable report from real audited results; no data or credentials fetched."""
import csv
import html
import json
from pathlib import Path
import sys

source=Path(sys.argv[1])
output=Path(sys.argv[2])
output.mkdir(parents=True,exist_ok=True)
r=json.loads((source/"annual-results.json").read_text(encoding="utf-8"))

lines=["# AllSafe — five-indicator and decision-engine audit", "",
       f'**Requested period:** {r["audit_start"]} to {r["audit_end"]}.',
       "**Scope:** NIFTY 50 and BANK NIFTY, regular weekday NSE sessions, five-minute candles. No autonomous orders.","",
       "## Result", "",
       "The current five-indicator system has weak directional accuracy under the agreed test. Correcting SELL confirmation logic removes mixed/neutral confirmations, but does not establish a profitable strategy or a statistically reliable predictive improvement. Production has not been changed by this indicator audit.","",
       "## How a signal was scored", "",
       "A signal uses a completed five-minute candle. Entry is the next candle's real open. The main result uses the close 30 minutes after entry. BUY is correct when exit is higher; SELL is correct when exit is lower. Flat outcomes are not wins. WAIT and warmup are excluded from the denominator. Events whose holding period crosses the session close or a data gap are excluded and counted in JSON.","",
       "EMA, RSI, MACD and Supertrend are confirmation states in the product. For their individual audit, a new non-neutral direction is an event; repeated bars in the same state are not counted as new signals. UT Bot and the decision engine use their emitted BUY/SELL triggers. Thus individual signal percentages use a declared event rule, not a claim that those confirmations place trades alone.","",
       "The original decision engine at commit d7e41fb is compared against the corrected version. Indicator formulas and production parameter defaults are retained. The changes were chosen from code defects before fetching outcomes. No parameters were tuned on this year. The last 90 calendar days are also reported separately as an untuned time split; small samples and correlated signals still limit inference.","",
       "This is a causal offline calculation replay on continuous complete history, not a recovered log of past deployed alerts. Live restarts, missing feed intervals, historical warmup and rolling-buffer reseeding can change which signals were actually available. The current Upstox adapter does not seed historical candles into the live runtime; it needs live candle warmup after restart. The live buffer is finite, whereas this annual calculation carries recursive history forward. These integration differences must be resolved or simulated before claiming exact parity with deployed alerts.","",
       "## Data coverage and provenance", ""]
for symbol, result in r["instruments"].items():
    c=result["coverage"]
    lines.append(f'- **{symbol}:** {c["sessions"]} sessions, {c["candles"]:,} candles from {c["first"]} to {c["last"]}; {len(c["partial_regular_sessions"])} partial regular sessions; {len(c.get("unexplained_missing_sessions",[]))} unexplained missing weekday sessions. Coverage status: {c["annual_coverage"]}.')
lines += ["", "Source: authenticated Upstox Historical V3, fetched in 28-day chunks, with 35 calendar days of pre-period warmup. Raw responses include the request ranges and are archived with SHA-256 hashes. Weekends and nonregular rows are explicitly excluded, including special trading sessions. Overnight gaps remain part of indicator true range; missing intraday bars reset indicator history. No candles are imputed. This audit covers regular weekday sessions rather than every special exchange session.","",
          "An independent agent checked all 12,812 eligible 30-minute ledger rows against raw prices and timestamps: zero mismatches. The manager independently executed the reproduction from the saved raw files and the regression suite.","",
          "## Primary results before trading costs", "",
          "| Indicator | NIFTY correct | Signals | BANK NIFTY correct | Signals |",
          "|---|---:|---:|---:|---:|"]
names=list(r["instruments"]["NIFTY50"]["metrics"])
summary=[]
for name in names:
    a=r["instruments"]["NIFTY50"]["metrics"][name]["30"]
    b=r["instruments"]["BANKNIFTY"]["metrics"][name]["30"]
    lines.append(f'| {name} | {a["accuracy_pct"]:.2f}% | {a["signals"]} | {b["accuracy_pct"]:.2f}% | {b["signals"]} |')
for symbol, result in r["instruments"].items():
    for name, horizons in result["metrics"].items():
        s=horizons["30"]
        summary.append({"instrument":symbol,"indicator":name,"signals":s["signals"],
                        "wins":s["wins"],"accuracy_pct":s["accuracy_pct"],
                        "buy_signals":s["side_results"]["BUY"]["signals"],
                        "buy_accuracy_pct":s["side_results"]["BUY"]["accuracy_pct"],
                        "sell_signals":s["side_results"]["SELL"]["signals"],
                        "sell_accuracy_pct":s["side_results"]["SELL"]["accuracy_pct"],
                        "mean_gross_bps":s["mean_gross_bps"]})
lines += ["", "## BUY and SELL separately, 30 minutes", "",
          "| Instrument | Indicator | BUY signals | BUY correct | SELL signals | SELL correct |",
          "|---|---|---:|---:|---:|---:|"]
for row in summary:
    lines.append(f'| {row["instrument"]} | {row["indicator"]} | {row["buy_signals"]} | {row["buy_accuracy_pct"]:.2f}% | {row["sell_signals"]} | {row["sell_accuracy_pct"]:.2f}% |')
lines += ["", "## Decision fixes and practical effect", "",
          "1. EMA: a mixed or equal 9/21/50 arrangement no longer counts as bearish. SELL now requires EMA9 < EMA21 < EMA50.",
          "2. RSI: exactly 50 is neutral; SELL requires RSI < 50.",
          "3. MACD: a zero histogram is neutral; SELL requires histogram < 0.","",
          "The BUY rule and numeric indicator formulas are retained. Supertrend's midpoint-based seed differs from TradingView's initial downtrend convention. That is documented as a variant; changing it without a defined parity target was not presented as an accuracy improvement.","",
          "| Instrument | Original → corrected signals | Accuracy change | Mean gross move, corrected | Corrected after 2 bps cost |",
          "|---|---:|---:|---:|---:|"]
for symbol,result in r["instruments"].items():
    a=result["metrics"]["Decision baseline"]["30"]
    b=result["metrics"]["Decision corrected"]["30"]
    lines.append(f'| {symbol} | {a["signals"]} → {b["signals"]} | {b["accuracy_pct"]-a["accuracy_pct"]:+.2f} percentage points | {b["mean_gross_bps"]:.3f} bps | {b["accuracy_after_cost_pct"]["2"]:.2f}% |')
lines += ["", "A basis point is 0.01%. Both corrected average moves are below 2 bps, so the mean directional return after even that illustrative round-trip cost is negative. Index levels are not directly executable instruments: these figures do not model option premiums, futures basis, spreads, brokerage, taxes or actual fills. The small accuracy increase alone is not evidence of a reliable edge.","",
          "## Untuned last 90 days", "",
          "| Instrument | Original signals / correct | Corrected signals / correct | Corrected mean gross move |",
          "|---|---:|---:|---:|"]
for symbol,result in r["instruments"].items():
    a=result["periods"]["Decision baseline"]["final_90_days_untuned_holdout"]
    b=result["periods"]["Decision corrected"]["final_90_days_untuned_holdout"]
    lines.append(f'| {symbol} | {a["signals"]} / {a["accuracy_pct"]:.2f}% | {b["signals"]} / {b["accuracy_pct"]:.2f}% | {b["mean_gross_bps"]:.3f} bps |')
lines += ["", "NIFTY's last-period accuracy and mean move worsen after correction; BANK NIFTY improves on a small sample. This mixed outcome supports fixing the classification defect but does not support promoting an optimized trading strategy. Overall Wilson intervals include 50% for both corrected decisions, and are only descriptive because events overlap and the two indices are correlated.","",
          "## Tests and reproducibility", "",
          "Backend and audit suite: 290 passed; one existing Starlette/httpx deprecation warning. Added checks cover mixed/equal EMA, neutral RSI/MACD SELL gating, exact UT Bot reversal prices, prefix causality, realistic entry/exit timing, missing intraday gaps and empty denominators. Full diffs, modified files, raw responses, per-signal CSV ledgers, monthly splits, 5/30/60-minute metrics, illustrative 2/5/10-bps cost sensitivity and nonoverlapping event results are included.","",
          "Reproduce without a credential: `python scripts/audit_indicators.py --input-dir <raw-data-folder> --output <new-results-folder>`. A new broker fetch uses `--fetch --token-dialog`; the token is used in memory and is never included in reports, files or command arguments.","",
          "Five specialist scopes: UT Bot, EMA, RSI, MACD and Supertrend. The manager reviewed the decision engine, implemented the fixes, checked real data, reproduced the results and reviewed agent findings against source.","",
          "## Next improvements justified by the evidence", "",
          "Use the corrected neutral handling in a reviewed release. Retain supervised analysis mode. Collect a separate forward paper-trading period using actual intended instruments and costs before claiming strategy improvement. If optimization is requested, predeclare a small candidate set, use rolling training/validation windows, and reserve later untouched data; do not tune until this year's headline percentage looks good.","",
          "## Primary sources", "",
          "- Upstox historical endpoint, limits and timestamps: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/",
          "- NSE 2025 holiday circular: https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf",
          "- NSE 2026 holiday circular: https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf",
          "- Additional 15 January 2026 holiday: https://nsearchives.nseindia.com/content/circulars/CMTR72260.pdf",
          "- Formula references and parity limitations are recorded in the five specialist reports."]
(output/"READ_ME_AUDIT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
with (output/"accuracy-summary.csv").open("w",newline="",encoding="utf-8") as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0]))
    writer.writeheader();writer.writerows(summary)
# A browser-readable version preserves all report text and table alignment.
(output/"READ_ME_AUDIT.html").write_text('<!doctype html><meta charset="utf-8"><title>AllSafe annual indicator audit</title><style>body{font:16px/1.55 system-ui;margin:40px;max-width:1200px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>'+html.escape("\n".join(lines))+'</pre>',encoding="utf-8")
print("Readable audit report and summary CSV created.")
