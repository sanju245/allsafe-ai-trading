"""Reproducible, read-only strategy comparison with prior-session selection only.

Uses locally saved Upstox candles; never needs a token or places orders.
The prior audit already exposed this year: all results remain exploratory.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import sys

from audit_indicators import ROOT, KEYS, normalize, segments, score_events, summarize, write_json
from app.indicators.decision import calculate_decisions
from app.indicators.strategies import STRATEGY_IDS, STRATEGY_LABELS, calculate_strategy_points

START, END = date(2025, 11, 15), date(2026, 11, 14)
INITIAL_SESSIONS, BLOCK_SESSIONS, BOOTSTRAPS = 60, 20, 2000
LABELS = {"decision_corrected": "Original corrected decision", "decision_cooldown": "Original with 30-minute spacing", **STRATEGY_LABELS}
ALL_IDS = tuple(LABELS)


def cooldown(candles, values):
    last = None
    out = []
    for c, value in zip(candles, values, strict=True):
        if value and (last is None or c.timestamp - last >= timedelta(minutes=30)):
            last = c.timestamp
            out.append(value)
        else:
            out.append(0)
    return out


def events(candles):
    points = calculate_strategy_points(candles)
    raw = [1 if p.decision == "BUY" else -1 if p.decision == "SELL" else 0 for p in calculate_decisions(candles)]
    return {"decision_corrected": raw, "decision_cooldown": cooldown(candles, raw),
            **{key: [p.signals[key] for p in points] for key in STRATEGY_IDS}}


def session_interval(rows, sessions, *, draws=BOOTSTRAPS):
    """Resample whole sessions (both symbols paired when supplied together).

    Include zero-event sessions. This is descriptive; long serial dependence and
    model selection are not fully corrected by a one-session block bootstrap.
    """
    if not rows:
        return None
    aggregates = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        a = aggregates[r["signal_time"][:10]]
        a[0] += 1
        a[1] += r["gross_bps"] > 0
        a[2] += r["gross_bps"] - 2
    values = [aggregates[str(s)] for s in sessions]
    if not values:
        return None
    rng = random.Random(20261115)
    accuracies, net = [], []
    for _ in range(draws):
        total, wins, ret = 0, 0, 0.0
        for _ in values:
            n, w, g = values[rng.randrange(len(values))]
            total += n
            wins += w
            ret += g
        if total:
            accuracies.append(100 * wins / total)
            net.append(ret / total)
    if not accuracies:
        return None
    accuracies.sort()
    net.sort()
    def interval(a):
        return [a[int(.025 * (len(a)-1))], a[int(.975 * (len(a)-1))]]
    return {"accuracy_pct": interval(accuracies), "mean_net_2bps": interval(net),
            "draws": draws, "valid_draws": len(accuracies), "unit": "paired_session_if_pooled"}


def metrics(rows, sessions, *, bootstrap=True):
    s = summarize(rows)
    if not rows:
        return {**s, "wins": 0, "buy_signals": 0, "sell_signals": 0,
                "mean_gross_bps": None, "mean_net_2bps": None, "session_bootstrap_95": None}
    gains = sum(max(r["gross_bps"], 0) for r in rows)
    losses = -sum(min(r["gross_bps"], 0) for r in rows)
    s.update({"mean_net_2bps": s["mean_gross_bps"] - 2,
              "profit_factor_gross": gains / losses if losses else None,
              "active_sessions": len({r["signal_time"][:10] for r in rows}),
              "session_bootstrap_95": session_interval(rows, sessions) if bootstrap else None})
    return s


def select_candidate(training_rows, training_sessions):
    """Only completed outcomes in preceding sessions may reach this function."""
    eligible, reasons = [], {}
    for strategy in STRATEGY_IDS:
        rows = [r for r in training_rows if r["indicator"] == strategy and r["horizon_minutes"] == 30]
        per_index = {}
        failed = []
        for symbol in KEYS:
            selected = [r for r in rows if r["symbol"] == symbol]
            stat = metrics(selected, training_sessions, bootstrap=False)
            per_index[symbol] = stat
            if stat["signals"] < 40:
                failed.append(f"{symbol}: fewer than40 training signals")
            if (stat["accuracy_pct"] or 0) < 60:
                failed.append(f"{symbol}: direction accuracy below60%")
            if stat["mean_net_2bps"] is None or stat["mean_net_2bps"] <= 0:
                failed.append(f"{symbol}: no positive mean after2bps")
        for side in ("BUY", "SELL"):
            if sum(r["side"] == side for r in rows) < 20:
                failed.append(f"Fewer than20 pooled {side} observations")
        # Resampling is only needed after the deterministic gates pass.
        if not failed:
            for symbol in KEYS:
                interval = session_interval([r for r in rows if r["symbol"] == symbol], training_sessions)
                if interval is None or interval["accuracy_pct"][0] <= 50:
                    failed.append(f"{symbol}: session interval lower bound does not exceed50%")
        reasons[strategy] = failed
        if not failed:
            eligible.append((min(s["accuracy_pct"] for s in per_index.values()), strategy))
    # Python's stable sort preserves the frozen candidate order for ties.
    eligible.sort(key=lambda x: -x[0])
    return (eligible[0][1] if eligible else None), reasons


def walk_forward(rows, sessions):
    primary = [r for r in rows if r["horizon_minutes"] == 30]
    blocks, policy_rows = [], []
    for offset in range(INITIAL_SESSIONS, len(sessions), BLOCK_SESSIONS):
        training_sessions, testing_sessions = sessions[:offset], sessions[offset:offset+BLOCK_SESSIONS]
        boundary = str(testing_sessions[0])
        training = [r for r in primary if r["signal_time"][:10] < boundary and r["exit_time"][:10] < boundary]
        selected, reasons = select_candidate(training, training_sessions)
        test_dates = {str(s) for s in testing_sessions}
        chosen = [r for r in primary if r["indicator"] == selected and r["signal_time"][:10] in test_dates]
        policy_rows.extend(chosen)
        blocks.append({"training_through": str(training_sessions[-1]), "test_start": boundary,
                       "test_end": str(testing_sessions[-1]), "sessions": len(testing_sessions),
                       "selected_strategy": selected, "ineligibility": reasons,
                       "metrics": metrics(chosen, testing_sessions, bootstrap=False)})
    return {"blocks": blocks, "metrics": metrics(policy_rows, sessions[INITIAL_SESSIONS:]),
            "wait_blocks": sum(b["selected_strategy"] is None for b in blocks),
            "test_sessions": len(sessions[INITIAL_SESSIONS:])}, policy_rows


def target_gate(results):
    failures = []
    for symbol, m in results.items():
        if m["signals"] < 100:
            failures.append(f"{symbol}: fewer than100 test observations")
        if min(m.get("buy_signals", 0), m.get("sell_signals", 0)) < 20:
            failures.append(f"{symbol}: fewer than20 observations for at least one side")
        if (m["accuracy_pct"] or 0) < 60:
            failures.append(f"{symbol}: accuracy below60%")
        if m["mean_net_2bps"] is None or m["mean_net_2bps"] <= 0:
            failures.append(f"{symbol}: mean after2bps not positive")
        interval = m.get("session_bootstrap_95")
        if interval is None or interval["accuracy_pct"][0] <= 50:
            failures.append(f"{symbol}: lower descriptive accuracy bound not above50%")
    return {"passed_retrospective_gate": not failures, "failures": failures,
            "forward_validation_required": True, "production_eligible": False}


def write_ledger(path, rows):
    if not rows:
        path.write_text("symbol,indicator,signal_time,entry_time,exit_time,side,horizon_minutes,entry,exit,gross_bps,always_buy_bps\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--web-json", type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"version": "strategy-research-v1", "audit_start": str(START), "audit_end": str(END),
              "horizon_minutes": 30, "evidence_status": "exploratory_reused_data",
              "protocol_sha256": hashlib.sha256((ROOT/"docs/strategy-research/PROTOCOL.md").read_bytes()).hexdigest(),
              "strategy_source_sha256": hashlib.sha256((ROOT/"apps/api/app/indicators/strategies.py").read_bytes()).hexdigest(),
              "instruments": {}, "target_gates": {}}
    all_rows, shared_sessions = [], None
    calendar = json.loads((ROOT/"docs/indicator-audit/calendar.json").read_text(encoding="utf-8"))
    expected = []
    cursor = START
    while cursor <= END:
        if cursor.weekday() < 5 and str(cursor) not in calendar["holidays"]:
            expected.append(cursor)
        cursor += timedelta(days=1)
    for symbol in KEYS:
        raw_path = args.input_dir/f"{symbol}-raw.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))["candles"]
        candles, excluded = normalize(raw, symbol, START-timedelta(days=35), END)
        annual = [c for c in candles if START <= c.timestamp.date() <= END]
        sessions = sorted({c.timestamp.date() for c in annual})
        if sessions != expected or any(sum(c.timestamp.date() == d for c in annual) != 75 for d in sessions):
            raise ValueError("Annual weekday coverage differs from verified calendar; research stopped.")
        if shared_sessions is not None and sessions != shared_sessions:
            raise ValueError("Instruments do not share a session calendar.")
        shared_sessions = sessions
        rows, exclusions = [], {}
        for chunk in segments(candles):
            scored, exc = score_events(chunk, events(chunk), START, END)
            rows.extend({"symbol": symbol, **r} for r in scored)
            for key, horizons in exc.items():
                for h, count in horizons.items():
                    name = f"{key}/{int(h)*5}m"
                    exclusions[name] = exclusions.get(name, 0) + count
        all_rows.extend(rows)
        write_ledger(args.output/f"{symbol}-strategy-ledger.csv", rows)
        primary = [r for r in rows if r["horizon_minutes"] == 30]
        test_start = str(sessions[INITIAL_SESSIONS])
        detail = []
        for strategy in ALL_IDS:
            selected = [r for r in primary if r["indicator"] == strategy]
            test = [r for r in selected if r["signal_time"][:10] >= test_start]
            detail.append({"id": strategy, "label": LABELS[strategy],
                           "evaluation_label": "All-year descriptive", **metrics(selected, sessions),
                           "forward": metrics(test, sessions[INITIAL_SESSIONS:]),
                           "horizons": {str(h): metrics([r for r in rows if r["indicator"] == strategy and r["horizon_minutes"] == h], sessions, bootstrap=False) for h in (5, 30, 60)},
                           "monthly": {m: metrics([r for r in selected if r["signal_time"].startswith(m)], sessions, bootstrap=False) for m in sorted({str(s)[:7] for s in sessions})}})
        report["instruments"][symbol] = {"strategies": detail, "exclusions": exclusions,
            "coverage": {"sessions": len(sessions), "candles": len(annual), "first": str(sessions[0]), "last": str(sessions[-1]),
                         "raw_file_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(), "excluded_nonregular": excluded,
                         "zero_volume_rows": sum(len(r)>5 and r[5] == 0 for r in raw), "raw_rows": len(raw)}}
    policy, policy_rows = walk_forward(all_rows, shared_sessions)
    report["walk_forward_detail"] = policy
    report["walk_forward"] = {**policy["metrics"], "blocks": len(policy["blocks"]), "wait_blocks": policy["wait_blocks"]}
    for strategy in STRATEGY_IDS:
        report["target_gates"][strategy] = target_gate({s: next(x for x in r["strategies"] if x["id"] == strategy)["forward"] for s, r in report["instruments"].items()})
    write_ledger(args.output/"walk-forward-policy-ledger.csv", policy_rows)
    write_json(args.output/"strategy-results.json", report)
    if args.web_json:
        # Ship aggregate evidence only; raw history and individual trades remain in the private archive.
        public = {k: report[k] for k in ("version", "audit_start", "audit_end", "horizon_minutes", "evidence_status", "walk_forward", "target_gates")}
        public["instruments"] = {s: {"coverage": r["coverage"], "strategies": [{k:v for k,v in q.items() if k not in ("monthly", "horizons")} for q in r["strategies"]]} for s,r in report["instruments"].items()}
        args.web_json.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.web_json, public)
    print(json.dumps({"status": "completed", "walk_forward_signals": policy["metrics"]["signals"],
                      "wait_blocks": policy["wait_blocks"], "blocks": len(policy["blocks"]),
                      "passed_retrospective_gate": [k for k,v in report["target_gates"].items() if v["passed_retrospective_gate"]]}))


if __name__ == "__main__":
    main()
