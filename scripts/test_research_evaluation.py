"""Selection, abstention and dependence regressions for strategy research."""
from datetime import date, timedelta
import pytest
import research_strategies as audit


def row(day, *, symbol="NIFTY50", strategy="ema_pullback", side="BUY", bps=10):
    return {"symbol": symbol, "indicator": strategy, "signal_time": f"{day}T10:00:00+05:30",
            "entry_time": f"{day}T10:05:00+05:30", "exit_time": f"{day}T10:35:00+05:30",
            "side": side, "horizon_minutes": 30, "gross_bps": bps, "always_buy_bps": bps}


def test_empty_policy_is_wait_and_accuracy_unavailable():
    sessions = [date(2026, 1, 1) + timedelta(days=i) for i in range(85)]
    result, rows = audit.walk_forward([], sessions)
    assert rows == []
    assert result["wait_blocks"] == 2
    assert result["metrics"]["signals"] == 0
    assert result["metrics"]["accuracy_pct"] is None
    assert result["blocks"][-1]["sessions"] == 5


def test_walk_forward_never_selects_with_future_or_unmatured_outcome(monkeypatch):
    sessions = [date(2026, 1, 1) + timedelta(days=i) for i in range(101)]
    rows = [row(d) for d in sessions]
    # A historical event whose label isn't yet known cannot enter training.
    delayed = row(sessions[1])
    delayed["exit_time"] = f"{sessions[-1]}T10:35:00+05:30"
    rows.append(delayed)
    calls = []
    def select(training, train_sessions):
        boundary = str(sessions[len(train_sessions)])
        assert all(r["signal_time"][:10] < boundary and r["exit_time"][:10] < boundary for r in training)
        assert delayed not in training
        calls.append(len(train_sessions))
        return "ema_pullback", {}
    monkeypatch.setattr(audit, "select_candidate", select)
    result, chosen = audit.walk_forward(rows, sessions)
    assert calls == [60, 80, 100]
    assert len(chosen) == 41
    assert result["wait_blocks"] == 0


def test_high_hit_rate_fails_when_mean_after_cost_is_negative():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(50)]
    rows = [row(d, symbol=s, side="BUY" if i % 2 else "SELL", bps=1)
            for s in ("NIFTY50", "BANKNIFTY") for i,d in enumerate(days)]
    chosen, reasons = audit.select_candidate(rows, days)
    assert chosen is None
    assert any("after2bps" in r for r in reasons["ema_pullback"])


def test_gate_requires_both_instruments_and_both_sides():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(100)]
    stats = {s: audit.metrics([row(d, symbol=s) for d in days], days) for s in ("NIFTY50", "BANKNIFTY")}
    gate = audit.target_gate(stats)
    assert gate["passed_retrospective_gate"] is False
    assert gate["production_eligible"] is False
    assert any("side" in r for r in gate["failures"])


def test_session_resampling_keeps_correlated_index_pairs_together():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(8)]
    rows = [row(d, symbol=s, bps=10 if s == "NIFTY50" else -10)
            for d in days for s in ("NIFTY50", "BANKNIFTY")]
    a = audit.session_interval(rows, days, draws=100)
    assert a == audit.session_interval(rows, days, draws=100)
    assert a["accuracy_pct"] == [50.0, 50.0]
    assert a["mean_net_2bps"] == [-2.0, -2.0]


def test_positive_training_can_select_without_enabling_production():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(50)]
    rows = [row(d, symbol=s, side="BUY" if i % 2 else "SELL")
            for s in ("NIFTY50", "BANKNIFTY") for i,d in enumerate(days)]
    chosen, _ = audit.select_candidate(rows, days)
    assert chosen == "ema_pullback"
    stats = {s:audit.metrics([r for r in rows if r["symbol"] == s], days) for s in ("NIFTY50", "BANKNIFTY")}
    assert audit.target_gate(stats)["production_eligible"] is False
