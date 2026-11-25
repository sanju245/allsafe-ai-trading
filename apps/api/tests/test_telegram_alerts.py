from dataclasses import replace
from datetime import datetime, timedelta
from threading import Event
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import security, telegram_worker
from app.config import Settings
from app.indicators.decision import TradeDecision
from app.main import app
from app.market_data import live_runtime
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState
from app.market_data.live_runtime import LiveDecisionSummary, LiveMarketDataRuntime
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.sessions import IST
from app.market_data.timeframes import Timeframe
from app.routers import telegram
from app.telegram_alerts import alertable_signal, link_digest

SUBSCRIPTION = "/api/v1/telegram/subscription"
SLOT = datetime(2026, 11, 26, 10, 0, tzinfo=IST)


def test_subscription_requires_login(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: Settings(
        supabase_url="https://test-project.supabase.co",
    ))
    assert TestClient(app).post(f"{SUBSCRIPTION}/link").status_code == 401


def test_link_is_bound_to_current_account_and_stored_as_digest(monkeypatch, active_account_override):
    settings = Settings(telegram_alerts_enabled=True, telegram_bot_username="AllSafeTestBot")
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)
    rpc = Mock(return_value=True)
    monkeypatch.setattr(telegram, "telegram_rpc", rpc)
    response = TestClient(app).post(f"{SUBSCRIPTION}/link")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    url = urlsplit(response.json()["url"])
    code = parse_qs(url.query)["start"][0]
    assert (url.netloc, url.path, len(code)) == ("t.me", "/AllSafeTestBot", 43)
    rpc.assert_called_once_with(settings, "create_link", p_user=active_account_override.id,
                                p_digest=link_digest(code))


def test_message_is_neutral_and_returns_to_the_correct_chart():
    message = telegram_worker.alert_message("https://allsafe.example", "BANKNIFTY", "upstox")
    body, url = message.split("\n\n")
    assert body == "There’s a new signal on your AllSafe chart. Sign in to your AllSafe account to check it."
    link = urlsplit(url)
    assert (link.scheme, link.netloc, link.path) == ("https", "allsafe.example", "/login")
    assert parse_qs(link.query)["next"] == ["/chart/BANKNIFTY?provider=upstox"]
    assert "buy" not in message.lower() and "sell" not in message.lower()


@pytest.mark.parametrize("decision", [TradeDecision.BUY, TradeDecision.SELL])
def test_only_fresh_confirmed_signals_qualify(decision):
    summary = LiveDecisionSummary(
        instrument=InstrumentId.NIFTY50, timeframe=Timeframe.M15, decision=decision,
        is_current_signal=True, feed_state=FeedState.LIVE, is_stale=False, candle_timestamp=SLOT,
        evaluated_at=SLOT + timedelta(minutes=15), source=DataSource(name="feed", kind=DataSourceKind.LIVE),
        ut_bot_signal=None, ema_bullish=None, rsi_bullish=None, macd_bullish=None,
        supertrend_bullish=None, reason="", confirmed_candle_count=100,
    )
    assert alertable_signal(summary, SLOT)
    assert not alertable_signal(replace(summary, is_stale=True), SLOT)
    assert not alertable_signal(replace(summary, is_current_signal=False), SLOT)
    assert not alertable_signal(replace(summary, decision=TradeDecision.WAIT), SLOT)
    assert not alertable_signal(summary, SLOT + timedelta(minutes=15))


def test_worker_claims_and_sends_without_indicator_data(monkeypatch):
    job = {
        "symbol": "NIFTY50", "provider": "groww", "chat_id": 383,
        "expires_at": "2099-11-26T04:47:00+00:00",
    }
    monkeypatch.setattr(telegram_worker, "telegram_rpc", Mock(side_effect=[[job], []]))
    bot = Mock()
    assert not telegram_worker.drain_deliveries(Settings(), bot, "https://allsafe.example", Event())
    bot.send.assert_called_once_with(
        383, telegram_worker.alert_message("https://allsafe.example", "NIFTY50", "groww"),
    )


def test_chart_and_publisher_share_unchanged_candle_analysis(monkeypatch):
    candle = Candle(timestamp=SLOT, open=100, high=110, low=95, close=105,
                    instrument=InstrumentId.NIFTY50, timeframe=Timeframe.M15,
                    source=DataSource(name="feed", kind=DataSourceKind.LIVE))
    runtime = LiveMarketDataRuntime(stream_manager=Mock())
    calculate = Mock(return_value=([], 1))
    monkeypatch.setattr(live_runtime, "validated_decisions", calculate)
    now = SLOT + timedelta(minutes=15)
    runtime.evaluate_series(candle.instrument, [candle], as_of=now)
    runtime.evaluate_series(candle.instrument, [candle], as_of=now + timedelta(seconds=5))
    assert calculate.call_count == 1
    runtime.evaluate_series(candle.instrument, [candle.model_copy(update={"close": 106})], as_of=now)
    assert calculate.call_count == 2
