from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.indicators.decision import TradeDecision
from app.indicators.research_decision import research_summary
from app.indicators.strategies import STRATEGY_IDS, StrategyPoint
from app.main import app
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState
from app.market_data.live_schemas import ResearchDecisionSchema
from app.market_data.sessions import IST
from app.market_data.timeframes import Timeframe
from app.routers.live import set_live_runtime
from tests.test_groww_live_api import make_test_runtime
from tests.test_confirmation_indicators import candles_from_closes


def research_point():
    return StrategyPoint(datetime(2026, 1, 5, 10, 0, tzinfo=IST),
                         {key: 1 for key in STRATEGY_IDS}, 35.0, 25.0, 10.0, "trend", "test")


def test_even_fresh_consensus_buy_is_not_promoted():
    p = research_point()
    result = research_summary(p, evaluated_at=p.timestamp+timedelta(minutes=5), fresh=True)
    assert result.candidate_decision == "BUY" and result.candidate_is_current
    assert result.decision == "WAIT" and result.is_current_signal is False
    assert result.selected_strategy is None
    assert result.evidence_status == "not_validated"
    assert ResearchDecisionSchema.model_validate(asdict(result)).decision == "WAIT"
    for invalid in ({"is_current_signal": True}, {"decision": "BUY"}, {"selected_strategy": "ema_pullback"}):
        with pytest.raises(ValidationError):
            ResearchDecisionSchema.model_validate({**asdict(result), **invalid})


def test_stale_and_unavailable_research_have_no_current_observation():
    p = research_point()
    r = research_summary(p, evaluated_at=p.timestamp+timedelta(minutes=30), fresh=False)
    assert not r.candidate_is_current and not r.is_current_signal
    assert "not fresh" in r.reason
    r = research_summary(None, evaluated_at=p.timestamp, unavailable_reason="Missing interval.")
    assert r.candidate_decision == "DATA_UNAVAILABLE"
    assert r.strategies == [] and r.candle_timestamp is None


def test_fresh_quote_cannot_revive_an_old_confirmed_signal(monkeypatch):
    from app.market_data import live_runtime as module
    rt = make_test_runtime()
    candles = candles_from_closes([100+i for i in range(60)])
    candles = [c.model_copy(update={"timestamp": datetime(2026, 1, 5, 9, 15, tzinfo=IST)+timedelta(minutes=5*i), "timeframe": Timeframe.M5}) for i, c in enumerate(candles)]
    last = candles[-1]
    rt.seed_historical_candles(InstrumentId.NIFTY50, candles)
    monkeypatch.setattr(rt.stream_manager, "evaluate_instrument_state", lambda *a,**k: SimpleNamespace(feed_state=FeedState.LIVE, is_stale=False))
    monkeypatch.setattr(module, "calculate_decisions", lambda cs: [SimpleNamespace(
        decision=TradeDecision.BUY, timestamp=last.timestamp, reason="test confirmed signal", ut_bot_signal=None,
        ema_bullish=True, rsi_bullish=True, macd_bullish=True, supertrend_bullish=True)])
    at_close = last.timestamp + timedelta(minutes=5)
    assert rt.evaluate_decision_for_instrument(InstrumentId.NIFTY50, as_of=at_close).is_current_signal
    assert not rt.evaluate_decision_for_instrument(InstrumentId.NIFTY50, as_of=at_close+timedelta(minutes=5)).is_current_signal


@pytest.mark.usefixtures("active_account_override")
def test_candles_endpoint_exposes_research_gate_and_never_orders():
    set_live_runtime(app, make_test_runtime())
    try:
        response = TestClient(app).get("/api/v1/live/candles", params={"symbol": "NIFTY50"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        research = response.json()["research"]
        assert research["decision"] == "WAIT"
        assert research["candidate_decision"] == "DATA_UNAVAILABLE"
        assert not research["is_current_signal"] and not research["candidate_is_current"]
        assert research["strategies"] == []
    finally:
        set_live_runtime(app, None)


def test_missing_intervals_block_research_calculation(monkeypatch):
    rt = make_test_runtime()
    monkeypatch.setattr(rt.stream_manager.aggregator, "get_missing_intervals", lambda *a, **k: [object()])
    from app.market_data import live_runtime as module
    def never_calculate(_):
        raise AssertionError("Invalid series must not reach research")
    monkeypatch.setattr(module, "calculate_strategy_points", never_calculate)
    r = rt.evaluate_research_for_instrument(InstrumentId.NIFTY50)
    assert r.candidate_decision == "DATA_UNAVAILABLE" and not r.candidate_is_current


def test_research_cache_invalidates_on_price_changes_but_never_caches_freshness(monkeypatch):
    from app.market_data import live_runtime as module
    rt = make_test_runtime()
    p = research_point()
    candles = [candles_from_closes([100])[0].model_copy(update={"timestamp": p.timestamp, "timeframe": Timeframe.M5})]
    monkeypatch.setattr(rt, "merged_complete_confirmed_candles", lambda *a,**k: candles)
    legacy = SimpleNamespace(decision=TradeDecision.WAIT, feed_state=FeedState.LIVE, is_stale=False)
    calls = []
    def calculate(cs):
        calls.append(cs[-1].close)
        return [p]
    monkeypatch.setattr(module, "calculate_strategy_points", calculate)
    when = p.timestamp+timedelta(minutes=5)
    assert rt.evaluate_research_for_instrument(InstrumentId.NIFTY50, as_of=when, decision_summary=legacy).candidate_is_current
    assert not rt.evaluate_research_for_instrument(InstrumentId.NIFTY50, as_of=when+timedelta(minutes=5), decision_summary=legacy).candidate_is_current
    assert len(calls) == 1
    candles[0] = candles[0].model_copy(update={"close": 100.5})
    rt.evaluate_research_for_instrument(InstrumentId.NIFTY50, as_of=when, decision_summary=legacy)
    assert len(calls) == 2
    legacy.is_stale = True
    assert not rt.evaluate_research_for_instrument(InstrumentId.NIFTY50, as_of=when, decision_summary=legacy).candidate_is_current
    assert len(calls) == 2
