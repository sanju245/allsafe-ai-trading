"""Read-only, causal five-indicator audit. Token stays in process memory only."""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from datetime import date, datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.indicators.decision import calculate_decisions
from app.indicators.ema import calculate_ema_trend
from app.indicators.macd import calculate_macd
from app.indicators.rsi import calculate_rsi
from app.indicators.supertrend import calculate_supertrend
from app.indicators.ut_bot import calculate_ut_bot
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.instruments import InstrumentId
from app.market_data.timeframes import Timeframe
from app.market_data.sessions import IST
from indicator_baseline import calculate_decisions as baseline_decisions

KEYS = {"NIFTY50": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank"}
SOURCE = DataSource(name="upstox-historical-v3", kind=DataSourceKind.HISTORICAL)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def fetch_history(token, symbol, start, end, output):
    """28-day requests satisfy Upstox's one-month 5-minute limit."""
    opener = build_opener(NoRedirects())
    collected, requests = {}, []
    cursor = start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=27))
        url = ("https://api.upstox.com/v3/historical-candle/"
               f"{quote(KEYS[symbol], safe='')}/minutes/5/{stop}/{cursor}")
        request = Request(url, headers={"Authorization": f"Bearer {token}",
                          "Accept": "application/json", "User-Agent": "AllSafeAITrading/0.2"})
        for attempt in range(3):
            try:
                with opener.open(request, timeout=30) as response:
                    body = json.load(response)
                break
            except HTTPError as error:
                if error.code == 429 and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError(f"Upstox historical request failed HTTP {error.code}; credential not logged.") from None
        if body.get("status") != "success" or not isinstance(body.get("data", {}).get("candles"), list):
            raise RuntimeError("Upstox returned an invalid historical response.")
        rows = body["data"]["candles"]
        for row in rows:
            if not isinstance(row, list) or len(row) < 5:
                raise ValueError("Malformed historical candle.")
            key = row[0]
            if key in collected and collected[key] != row:
                raise ValueError("Conflicting duplicate historical candle.")
            collected[key] = row
        requests.append({"from": str(cursor), "to": str(stop), "rows": len(rows)})
        print(f"{symbol}: {cursor} to {stop}, {len(rows)} candles", flush=True)
        cursor = stop + timedelta(days=1)
        time.sleep(0.25)
    rows = list(collected.values())
    write_json(output / f"{symbol}-raw.json", {"source": SOURCE.name, "requests": requests, "candles": rows})
    return rows


def normalize(rows, symbol, start, end):
    candles, excluded = [], 0
    seen = set()
    for row in rows:
        stamp = datetime.fromisoformat(row[0])
        if stamp.tzinfo is None:
            raise ValueError("Timezone missing in historical data.")
        stamp = stamp.astimezone(IST)
        values = [float(v) for v in row[1:5]]
        o, h, l, c = values
        if (not all(math.isfinite(v) and v > 0 for v in values)
                or not l <= min(o, c) <= max(o, c) <= h):
            raise ValueError("Invalid OHLC values.")
        if not start <= stamp.date() <= end:
            raise ValueError("Provider returned out-of-range timestamp.")
        if stamp in seen:
            raise ValueError("Duplicate timestamp in input.")
        seen.add(stamp)
        minute = stamp.hour * 60 + stamp.minute
        if stamp.weekday() >= 5 or not 555 <= minute < 930:
            excluded += 1
            continue
        if (minute - 555) % 5 or stamp.second or stamp.microsecond:
            raise ValueError("Candle is not aligned to regular NSE 5-minute grid.")
        candles.append(Candle(timestamp=stamp, open=o, high=h, low=l, close=c,
                              instrument=InstrumentId(symbol), timeframe=Timeframe.M5, source=SOURCE))
    candles.sort(key=lambda c: c.timestamp)
    return candles, excluded


def segments(candles):
    out, current = [], []
    for candle in candles:
        if current and candle.timestamp.date() == current[-1].timestamp.date() and candle.timestamp-current[-1].timestamp != timedelta(minutes=5):
            out.append(current)
            current = []
        current.append(candle)
    if current:
        out.append(current)
    return out


def series(candles):
    """Confirmation indicators emit events on direction change; UT/decision emit triggers."""
    ema, rsi, macd = calculate_ema_trend(candles), calculate_rsi(candles), calculate_macd(candles)
    st, ut = calculate_supertrend(candles), calculate_ut_bot(candles)
    states = {
        "EMA": [None if p.ema50 is None else 1 if p.bullish else -1 if p.bearish else 0 for p in ema],
        "RSI": [None if p.rsi is None else 1 if p.rsi > 50 else -1 if p.rsi < 50 else 0 for p in rsi],
        "MACD": [None if p.histogram is None else 1 if p.histogram > 0 else -1 if p.histogram < 0 else 0 for p in macd],
        "Supertrend": [p.direction for p in st],
    }
    events = {}
    for name, values in states.items():
        previous, signals = None, []
        for value in values:
            signals.append(value if value in (-1, 1) and previous is not None and value != previous else 0)
            previous = value
        events[name] = signals
    events["UT Bot"] = [1 if p.signal == "BUY" else -1 if p.signal == "SELL" else 0 for p in ut]
    for name, fn in (("Decision baseline", baseline_decisions), ("Decision corrected", calculate_decisions)):
        events[name] = [1 if p.decision == "BUY" else -1 if p.decision == "SELL" else 0 for p in fn(candles)]
    return events


def score_events(candles, events, audit_start, audit_end):
    trades, exclusions = [], {}
    for name, signals in events.items():
        exclusions[name] = {str(h): 0 for h in (1, 6, 12)}
        for i, direction in enumerate(signals):
            if not direction or not audit_start <= candles[i].timestamp.date() <= audit_end:
                continue
            for horizon in (1, 6, 12):
                final = i + horizon
                if final >= len(candles):
                    exclusions[name][str(horizon)] += 1
                    continue
                signal_time = candles[i].timestamp
                last = candles[final]
                if (last.timestamp.date() != signal_time.date()
                        or last.timestamp != signal_time + timedelta(minutes=5*horizon)):
                    exclusions[name][str(horizon)] += 1
                    continue
                entry = candles[i+1]
                gross = direction * (last.close/entry.open - 1) * 10000
                trades.append({"indicator": name, "signal_time": signal_time.isoformat(),
                               "entry_time": entry.timestamp.isoformat(),
                               "exit_time": (last.timestamp+timedelta(minutes=5)).isoformat(),
                               "side": "BUY" if direction == 1 else "SELL", "horizon_minutes": horizon*5,
                               "entry": entry.open, "exit": last.close, "gross_bps": gross,
                               "always_buy_bps": (last.close/entry.open-1)*10000})
    return trades, exclusions


def summarize(rows):
    if not rows:
        return {"signals": 0, "accuracy_pct": None}
    wins = sum(r["gross_bps"] > 0 for r in rows)
    n, p = len(rows), wins/len(rows)
    z = 1.96
    mid = (p + z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/(1+z*z/n)
    occupied, nonoverlap = None, []
    for row in sorted(rows, key=lambda r:r["entry_time"]):
        if occupied is None or row["entry_time"] >= occupied:
            nonoverlap.append(row)
            occupied = row["exit_time"]
    sides = {}
    for side in ("BUY", "SELL"):
        subset = [r for r in rows if r["side"] == side]
        sides[side] = {"signals": len(subset), "accuracy_pct":
                       100*sum(r["gross_bps"]>0 for r in subset)/len(subset) if subset else None}
    return {"signals": n, "side_results": sides, "buy_signals": sum(r["side"] == "BUY" for r in rows),
            "sell_signals": sum(r["side"] == "SELL" for r in rows), "wins": wins,
            "losses": sum(r["gross_bps"] < 0 for r in rows), "flat": sum(r["gross_bps"] == 0 for r in rows),
            "accuracy_pct": 100*p, "wilson_95_interval_pct": [100*(mid-half), 100*(mid+half)],
            "mean_gross_bps": sum(r["gross_bps"] for r in rows)/n,
            "accuracy_after_cost_pct": {str(cost):100*sum(r["gross_bps"] > cost for r in rows)/n for cost in (2,5,10)},
            "same_time_always_buy_pct": 100*sum(r["always_buy_bps"] > 0 for r in rows)/n,
            "same_time_always_sell_pct": 100*sum(r["always_buy_bps"] < 0 for r in rows)/n,
            "nonoverlapping_signals": len(nonoverlap),
            "nonoverlapping_accuracy_pct": 100*sum(r["gross_bps"]>0 for r in nonoverlap)/len(nonoverlap)}


def run_audit(candles, start, end):
    all_rows, excluded = [], {}
    started = time.perf_counter()
    for chunk in segments(candles):
        rows, exclusions = score_events(chunk, series(chunk), start, end)
        all_rows.extend(rows)
        for name, horizons in exclusions.items():
            for horizon, count in horizons.items():
                key = f"{name}/{int(horizon)*5}m"
                excluded[key] = excluded.get(key, 0) + count
    names = list(series([]))
    primary = [r for r in all_rows if r["horizon_minutes"] == 30]
    cutoff = end - timedelta(days=90)
    stats = {name: {str(h):summarize([r for r in all_rows if r["indicator"]==name and r["horizon_minutes"]==h]) for h in (5,30,60)} for name in names}
    months = sorted({r["signal_time"][:7] for r in primary})
    periods = {"earlier_period": lambda r:r["signal_time"][:10]<=str(cutoff),
               "final_90_days_untuned_holdout":lambda r:r["signal_time"][:10]>str(cutoff)}
    detail = {name:{period:summarize([r for r in primary if r["indicator"]==name and test(r)]) for period,test in periods.items()} for name in names}
    monthly = {month:{name:summarize([r for r in primary if r["indicator"]==name and r["signal_time"].startswith(month)]) for name in names} for month in months}
    return {"metrics":stats,"periods":detail,"monthly":monthly,"excluded_horizon_events":excluded,
            "evaluation_seconds":time.perf_counter()-started}, all_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--token-dialog", action="store_true")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--calendar-file", type=Path, default=ROOT/"docs/indicator-audit/calendar.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025,11,15))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026,11,14))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    start_fetch = args.start - timedelta(days=35)
    if args.start > args.end or args.end >= datetime.now(IST).date():
        raise ValueError("Audit dates must be ordered and end before today.")
    token = ""
    if args.fetch:
        write_json(args.output / "STATUS.json", {"status":"awaiting_hidden_token_input"})
        print("Paste your Upstox ANALYTICS token below. Characters will be hidden. It is not saved.", flush=True)
        token = os.environ.get("UPSTOX_ACCESS_TOKEN")
        if not token and args.token_dialog:
            import tkinter as tk
            from tkinter import simpledialog
            root=tk.Tk()
            root.withdraw()
            root.attributes("-topmost",True)
            token=simpledialog.askstring("AllSafe private historical audit", "Paste Upstox Analytics Token, then click OK.\nThe token is masked and stays in memory only.",show="*",parent=root)
            root.destroy()
        elif not token:
            token=getpass.getpass("Analytics token: ")
        token = token or ""
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            raise ValueError("Token was empty.")
    write_json(args.output / "STATUS.json", {"status":"running"})
    report = {"audit_start":str(args.start),"audit_end":str(args.end),"primary_horizon_minutes":30,
              "baseline_commit":"d7e41fbfd5b4a6fa4413a61855473ef073715ef5",
              "baseline_decision_file_sha256":hashlib.sha256(Path(__file__).with_name("indicator_baseline.py").read_bytes()).hexdigest(),
              "method":"closed 5m signal; next-bar open entry; same-session 30m close exit; flat is not a win",
              "limitations":["Index direction is not futures/options trade P&L.","Overlapping events are correlated; Wilson intervals are descriptive, not independence proof.",
                             "Costs are illustrative total round-trip basis points; not a broker fee estimate.",
                             "Final 90 days are not tuned; coding fixes do not prove predictive improvement.",
                             "Weekday dates without data may be exchange holidays or missing data; not imputed."],"instruments":{}}
    for symbol in KEYS:
        if args.fetch:
            raw = fetch_history(token,symbol,start_fetch,args.end,args.output)
        else:
            if args.input_dir is None:
                raise ValueError("Supply --fetch or --input-dir.")
            data = json.loads((args.input_dir/f"{symbol}-raw.json").read_text(encoding="utf-8-sig"))
            raw = data["candles"]
        candles, excluded = normalize(raw,symbol,start_fetch,args.end)
        if not candles:
            raise ValueError(f"No valid historical candles for {symbol}.")
        stats, rows = run_audit(candles,args.start,args.end)
        selected = [c for c in candles if args.start<=c.timestamp.date()<=args.end]
        days = sorted({c.timestamp.date() for c in selected})
        if not days:
            raise ValueError("No candles within audit period.")
        counts = {str(d):sum(c.timestamp.date()==d for c in selected) for d in days}
        missing_weekdays = []
        cursor=args.start
        while cursor<=args.end:
            if cursor.weekday()<5 and cursor not in days:
                missing_weekdays.append(str(cursor))
            cursor+=timedelta(days=1)
        stats["coverage"]={"candles":len(selected),"sessions":len(days),"first":str(days[0]),"last":str(days[-1]),
                           "annual_coverage":"incomplete" if len(days)<180 or (days[0]-args.start).days>7 or (args.end-days[-1]).days>7 else "range_spans_year_exchange_calendar_unverified",
                           "partial_regular_sessions":{d:n for d,n in counts.items() if n!=75},
                           "excluded_nonregular_rows":excluded,"missing_weekdays_review_required":missing_weekdays,
                           "raw_sha256":hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()}
        if args.calendar_file.exists():
            calendar=json.loads(args.calendar_file.read_text(encoding="utf-8"))
            if str(args.start)>=calendar["coverage_start"] and str(args.end)<=calendar["coverage_end"]:
                holidays=set(calendar["holidays"])
                missing=[d for d in missing_weekdays if d not in holidays]
                unexpected=[str(d) for d in days if str(d) in holidays]
                stats["coverage"].update({"calendar_sources":calendar["sources"],
                    "confirmed_holidays": [d for d in missing_weekdays if d in holidays],
                    "unexplained_missing_sessions":missing,"unexpected_holiday_sessions":unexpected,
                    "annual_coverage":"verified_regular_weekday_sessions" if not missing and not unexpected and not stats["coverage"]["partial_regular_sessions"] else "incomplete"})
        report["instruments"][symbol]=stats
        with (args.output/f"{symbol}-signal-ledger.csv").open("w",newline="",encoding="utf-8") as file:
            fields=list(rows[0]) if rows else ["indicator","signal_time","horizon_minutes","gross_bps"]
            writer=csv.DictWriter(file,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    token = ""
    write_json(args.output/"annual-results.json",report)
    lines=["# Indicator audit — requested annual window",f"Requested period: {args.start} through {args.end}","",report["method"],"",
           "These are directional event statistics, not a promise or an executed trading return.","", "## Data coverage (review before percentages)"]
    for symbol, result in report["instruments"].items():
        c=result["coverage"]
        lines.append(f'- {symbol}: {c["annual_coverage"]}; {c["first"]} through {c["last"]}; {c["sessions"]} sessions; {c["candles"]} candles; {len(c["partial_regular_sessions"])} partial sessions; {len(c.get("unexplained_missing_sessions",c["missing_weekdays_review_required"]))} unexplained absent weekdays.')
    lines += ["", "Partial data is never a verified full-year result. See annual-results.json for missing dates, monthly and BUY/SELL results.", "",
           "| Instrument | Indicator | 30m signals | Correct direction | Mean gross bps |", "|---|---|---:|---:|---:|"]
    for symbol, result in report["instruments"].items():
        for name, horizons in result["metrics"].items():
            s=horizons["30"]
            pct="N/A" if s["accuracy_pct"] is None else f'{s["accuracy_pct"]:.2f}%'
            mean="N/A" if s.get("mean_gross_bps") is None else f'{s["mean_gross_bps"]:.2f}'
            lines.append(f'| {symbol} | {name} | {s["signals"]} | {pct} | {mean} |')
    lines += ["", "## Limitations"]+[f"- {item}" for item in report["limitations"]]
    (args.output/"ANNUAL_RESULTS.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    write_json(args.output/"STATUS.json",{"status":"completed","report":"annual-results.json"})
    print("Audit complete. Results and per-signal ledgers saved.",flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Avoid tracebacks/provider response bodies that could echo credentials.
        print(f"Audit stopped ({type(error).__name__}). No accuracy result is claimed.",flush=True)
        output_arg = sys.argv[sys.argv.index("--output")+1] if "--output" in sys.argv else None
        if output_arg:
            dest=Path(output_arg)
            dest.mkdir(parents=True,exist_ok=True)
            write_json(dest/"STATUS.json",{"status":"failed","error_type":type(error).__name__})
        sys.exit(1)
