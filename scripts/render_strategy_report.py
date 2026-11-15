"""Render aggregate research evidence into a portable report; no broker access."""
import argparse
import csv
import html
import json
from pathlib import Path


def number(x, unit=""):
    return "N/A" if x is None else f"{x:.2f}{unit}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    r = json.loads(args.results.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    lines = ["# AllSafe strategy research — completed 16 November 2026", "",
        "**The 60–80% accuracy target was not achieved. No new strategy qualified for promotion.**",
        "", "Seven fixed strategy variants were researched and implemented, alongside two decision baselines. "
        "Rules were recorded in commit ce5007c before their results were evaluated. "
        "All seven had negative average directional movement after the illustrative 2-basis-point cost on both indices in the later test period. "
        "The selection policy correctly chose WAIT in all 10 test blocks, producing zero trades and N/A accuracy.",
        "", "## Evidence and scope", "",
        "- Requested historical window: 2025-11-15 through 2026-11-14. Each index has 245 complete regular sessions and 18,375 five-minute candles; actual first/last session 2025-11-17 and 2026-11-13.",
        "- Initial 60 sessions for training; next 185 sessions for chronological testing, starting 12 February 2026. Selection uses only completed outcomes from earlier sessions. Ten blocks, including the final partial block.",
        "- Main measure: signal on a closed five-minute candle; entry at the next open; direction after 30 minutes, exiting within the same session. Flat moves are not wins. 5/60-minute sensitivity is also recorded.",
        "- This year was already examined in the previous audit. All results here are exploratory reused-data evidence, including the chronological test. It is not a pristine holdout or future validation.",
        "- Both saved index datasets have zero reported volume throughout. VWAP/OBV were excluded; index volume was not invented.",
        "- Independent review recomputed all 14,770 ledger outcomes, including 4,960 observations at 30 minutes, against raw candle prices, with no mismatches. This is not an independent second-vendor verification of prices.",
        "", "## Later chronological test results", "",
        "The columns below evaluate each fixed rule over the later 185 sessions. These rule-specific results are separate from the selection policy, which stayed at WAIT. All-year descriptive results are included afterward.",
        "", "| Rule | NIFTY accuracy (events) | BANK NIFTY accuracy (events) | NIFTY mean after 2 bps | BANK mean after 2 bps |",
        "|---|---:|---:|---:|---:|"]
    indices = r["instruments"]
    lookup = {s:{x["id"]:x for x in v["strategies"]} for s,v in indices.items()}
    for x in indices["NIFTY50"]["strategies"]:
        a, b = x["forward"], lookup["BANKNIFTY"][x["id"]]["forward"]
        lines.append(f'| {x["label"]} | {number(a["accuracy_pct"], "%")} ({a["signals"]}) | {number(b["accuracy_pct"], "%")} ({b["signals"]}) | {number(a["mean_net_2bps"], "bps")} | {number(b["mean_net_2bps"], "bps")} |')
    lines += ["", "## All-year descriptive results", "", "| Rule | NIFTY accuracy (events) | BANK NIFTY accuracy (events) |", "|---|---:|---:|"]
    for a in indices["NIFTY50"]["strategies"]:
        b = lookup["BANKNIFTY"][a["id"]]
        lines.append(f'| {a["label"]} | {number(a["accuracy_pct"], "%")} ({a["signals"]}) | {number(b["accuracy_pct"], "%")} ({b["signals"]}) |')
    lines += ["", "## What was implemented", "",
        "- New causal indicators and signal rules: ADX/DMI trend strength, EMA pullback, Donchian breakout, Bollinger re-entry, stochastic reversal, fully completed 15-minute UT confirmation, and a trend/range consensus.",
        "- A research decision layer that can expose observations but always returns WAIT until prospective validation and review. It never turns a backtest hit rate into a current probability of success.",
        "- Website research page with all rule results, counts, costs, limitations and sources; market dashboard shows the existing five-indicator decision separately from research observations.",
        "- Confirmed-candle freshness guard: even a fresh quote cannot revive an old confirmed BUY/SELL candle. Missing, incomplete, stale or invalid data cannot become a current research signal.",
        "- Per-instrument cache avoids recomputing the seven strategies for unchanged validated candles. Complete OHLC/timeframe/timestamp changes invalidate it; freshness is always recomputed.",
        "- No new strategy replaces the existing corrected five-indicator decision. This avoids silently promoting rules that failed the evidence criteria. Orders remain absent; supervised analysis only.",
        "", "## Interpretation", "",
        "Adding extra price-based indicators did not establish an accuracy or profitability improvement on this sample. "
        "The best NIFTY new-rule test hit rate is 54.74% with 95 observations (ADX confirmation); BANK NIFTY's best is 53.60% with 125 observations (EMA pullback). "
        "These were chosen by observing the table and are descriptive maxima, not independently validated winners. The corrected original decision remains 55.31%/54.14% on those test dates, and it too is negative after the 2 bps assumption.",
        "", "A higher hit rate on fewer events is not automatically better. The report includes side support, descriptive session-bootstrap intervals, monthly results, cost sensitivity, non-overlap subsets and same-time always-BUY/SELL comparisons in strategy-results.json. "
        "One-session intervals do not fully account for longer dependence or repeated model selection; no multiple-testing correction or PBO statistic is claimed. "
        "Index direction is not options/futures P&L; fees, slippage, spreads, derivatives mechanics and actual executions were not modeled.",
        "", "## Next validation step", "",
        "Freeze the rules and collect new closed-candle observations in supervised paper mode. Review after at least 60 new regular sessions and 100 eligible events per index, with BUY/SELL support and costs reported. "
        "If the support threshold is not met, continue observation. Any parameter change starts a new prospective evaluation. "
        "The 60% target remains a research goal; 80% is not supported by these results. Neither threshold authorizes orders or guarantees future performance.",
        "", "## Release and reproduction", "",
        "Review branch: codex/strategy-research-2026-11-15. Main/production were not merged or deployed for this task. "
        "The branch includes the earlier neutral/bearish decision corrections. Production publication requires explicit approval after reviewing this evidence.",
        "", "Run from the repository with Python and installed API dependencies:", "",
        "```text", "python scripts/research_strategies.py --input-dir PATH_TO_RAW --output PATH_TO_RESULTS --web-json apps/web/src/data/strategy-research.json",
        "python scripts/render_strategy_report.py PATH_TO_RESULTS/strategy-results.json PATH_TO_REPORT", "```", "",
        "No credentials are needed to reproduce from the saved files. Keep raw data and full ledgers in the private handover; the website contains aggregate results only. See VERIFICATION.md for checks, full-diff.patch for source changes, and file-manifest.json for evidence hashes.",
        "", "## Research sources", "",
        "- [TradingView ADX](https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/): trend strength, distinguished from direction.",
        "- [John Bollinger's rules](https://www.bollingerbands.com/bollinger-band-rules): band touches alone do not imply reversals; related indicators are not independent evidence.",
        "- [TradingView Donchian Channels](https://www.tradingview.com/support/solutions/43000502253-donchian-channels-dc/): high/low channels and breakout context.",
        "- [Fidelity fast stochastic](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/fast-stochastic): close position relative to a recent range.",
        "- [TradingView VWAP](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/): meaningful traded volume is required.",
        "- [Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): repeated historical strategy searches can select false discoveries.",
        "", "Sources motivate hypotheses; none supplies a 60–80% accuracy guarantee for this application."]
    report = "\n".join(lines)+"\n"
    (args.output/"STRATEGY_RESEARCH.md").write_text(report, encoding="utf-8")
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AllSafe Strategy Research</title><style>body{margin:0;background:#101725;color:#e6edf7;font:16px/1.65 system-ui}main{max-width:1100px;margin:40px auto;padding:28px;border:1px solid #344058;border-radius:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}</style><main><pre>'+html.escape(report)+'</pre></main></html>'
    (args.output/"STRATEGY_RESEARCH.html").write_text(document, encoding="utf-8")
    fields = ["symbol", "strategy", "period", "signals", "accuracy_pct", "buy_signals", "sell_signals", "mean_gross_bps", "mean_net_2bps"]
    with (args.output/"accuracy-comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for symbol, instrument in indices.items():
            for strategy in instrument["strategies"]:
                for period, metric in (("all_year_descriptive", strategy), ("later_185_sessions", strategy["forward"])):
                    writer.writerow({"symbol":symbol, "strategy":strategy["label"], "period":period, **{k:metric.get(k) for k in fields[3:]}})
    print("Portable report and accuracy table written.")


if __name__ == "__main__":
    main()
