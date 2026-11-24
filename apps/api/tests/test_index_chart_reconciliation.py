from datetime import date, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.indicators.decision import TradeDecision
from app.main import app
from app.market_data.instruments import InstrumentId
from app.market_data.live_runtime import latest_closed_slot, validated_decisions
from app.market_data.sessions import session_slots
from app.market_data.timeframes import Timeframe
from app.routers import live
from tests.fixtures.sample_data import HISTORICAL_TEST_SOURCE, ist, make_candle
from tests.test_groww_live_api import make_test_runtime


def market_bars(symbol, move):
    stamps = [s for day in (12, 13, 16, 17, 18) for s in session_slots(date(2026, 11, day), Timeframe.M15)]
    bars = []
    for i, stamp in enumerate(stamps):
        # Reverse during warm-up so the trigger establishes a directional position.
        price = 25000 + move * 5 * abs(i - 18)
        bars.append(make_candle(stamp, o=price, h=price + 3, low=price - 3, c=price + move,
                                instrument=symbol, timeframe=Timeframe.M15, source=HISTORICAL_TEST_SOURCE))
    return bars


@pytest.mark.usefixtures("active_account_override")
@pytest.mark.parametrize(("symbol", "direction"), [(InstrumentId.NIFTY50, 1), (InstrumentId.BANKNIFTY, -1)])
def test_chart_repairs_one_partial_live_bar_and_replays_the_next_close(monkeypatch, symbol, direction):
    bars = market_bars(symbol, direction)
    partial = ist(2026, 11, 18, 9, 30)
    clock = [partial + timedelta(minutes=15, seconds=2)]
    calls = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    def fetch(request):
        calls.append(request)
        return [c for c in bars if request.start <= c.timestamp and c.close_time <= request.end]

    runtime = make_test_runtime(streaming_enabled=True)
    runtime.start(as_of=partial + timedelta(minutes=4), run_warmup=False)
    runtime.historical_provider = SimpleNamespace(name="historical replay", fetch_candles=fetch)
    agg = runtime.stream_manager.aggregator
    for stamp in (partial + timedelta(minutes=4), clock[0]):
        agg.process_tick(symbol=symbol, timestamp=stamp, price=18765.0, as_of=stamp)
    assert len(agg.get_confirmed_candles(symbol, as_of=clock[0])) == 1
    assert agg.get_confirmed_candles(symbol)[0].is_incomplete

    monkeypatch.setattr(live, "datetime", Clock)
    live.set_live_runtime(app, runtime)
    try:
        client = TestClient(app)
        params = {"symbol": symbol.value, "timeframe": "15m", "limit": 750, "history_days": 7,
                  "include_indicator_history": "true"}
        snapshot = client.get("/api/v1/live/candles", params=params).json()
        expected = next(c for c in bars if c.timestamp == partial)
        last = snapshot["candles"][-1]
        assert last["close"] == expected.close and not last["is_incomplete"] and last["tick_count"] is None
        assert snapshot["indicator_decision"]["confirmed_candle_count"] == len(snapshot["candles"]) == 102
        assert snapshot["indicator_decision"]["is_current_signal"]
        expected_side = "BUY" if direction > 0 else "SELL"
        assert snapshot["indicator_decision"]["decision"] == expected_side
        marks = [(p["timestamp"], p["decision"]) for p in snapshot["indicator_history"]]
        assert (partial.isoformat(), expected_side) in marks
        quote = client.get("/api/v1/live/quote", params={"symbol": symbol.value, "include_forming": True}).json()
        assert quote["forming_candle"]["is_forming"] and quote["quote"]["ltp"] == 18765
        assert quote["forming_candle"]["timestamp"] not in dict(marks)
        today = client.get("/api/v1/live/candles", params={**params, "history_days": 1}).json()
        assert len(calls) == 1 and len(today["candles"]) == 2 and today["heikin_ashi_previous_open_close"]

        clock[0] += timedelta(minutes=15)
        agg.process_tick(symbol=symbol, price=expected.close, timestamp=clock[0], as_of=clock[0])
        after = client.get("/api/v1/live/candles", params=params).json()
        assert len(calls) == 2 and calls[-1].start.date() == partial.date()
        assert all(pair in [(p["timestamp"], p["decision"]) for p in after["indicator_history"]] for pair in marks)
        assert after["indicator_decision"]["confirmed_candle_count"] == 103
        assert not after["indicator_decision"]["is_current_signal"]
    finally:
        live.set_live_runtime(app, None)
        runtime.stop(as_of=clock[0])


def test_unresolved_gap_preserves_earlier_events_and_restarts_the_warmup():
    symbol = InstrumentId.NIFTY50
    bars = market_bars(symbol, 1)
    as_of = ist(2026, 11, 18, 15, 30)
    before, _ = validated_decisions(bars[:107], instrument=symbol, as_of=as_of)
    points, count = validated_decisions(bars[:107] + bars[108:], instrument=symbol, as_of=as_of)
    assert any(p.decision == TradeDecision.BUY for p in before)
    assert points[:107] == before and count == len(bars) - 108
    assert all(p.decision == TradeDecision.DATA_UNAVAILABLE for p in points[107:])
    assert latest_closed_slot(ist(2026, 11, 24, 11)) is None


def test_health_and_account_requests_can_run_during_broker_startup(monkeypatch, active_account_override):
    from app import main

    started, release = Event(), Event()

    def slow_broker_start(application):
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(main, "startup_live_runtime", slow_broker_start)
    with TestClient(app) as client:
        try:
            assert started.wait(timeout=2)
            assert client.get("/health").status_code == 200
            account = client.get("/api/v1/auth/me")
            assert account.status_code == 200 and account.json()["id"] == active_account_override.id
        finally:
            release.set()


@pytest.mark.usefixtures("active_account_override")
def test_connected_broker_is_reported_as_closed_on_a_holiday(monkeypatch):
    from pydantic import SecretStr
    from app.market_data.live_models import FeedState

    runtime = make_test_runtime()
    monkeypatch.setattr(runtime.stream_manager, "status_snapshot",
                        lambda: SimpleNamespace(connected=True, feed_state=FeedState.CLOSED))
    settings = live.get_settings().model_copy(update={
        "upstox_live_stream_enabled": True, "upstox_access_token": SecretStr("test-only"),
    })
    monkeypatch.setattr(live, "get_settings", lambda: settings)
    live.set_live_runtimes(app, {"upstox": runtime})
    try:
        data = TestClient(app).get("/api/v1/live/providers").json()
        upstox = next(p for p in data["providers"] if p["id"] == "upstox")
        assert upstox["connected"] and upstox["feed_state"] == "closed"
        assert "session is closed" in upstox["message"]
    finally:
        live.set_live_runtime(app, None)
