"""HTTP-level tests for authenticated Upstox historical candle charts."""

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.indicators.decision import TradeDecision
import app.providers.upstox_history as history_provider_module
import app.routers.upstox_history as upstox_router
from app.config import Settings
from app.main import app, startup_live_runtime
from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.timeframes import Timeframe
from app.routers.live import build_runtime_from_settings, set_live_runtime, set_live_runtimes
from app.providers.upstox_history import UpstoxHistoryError

client = TestClient(app)
IST = ZoneInfo("Asia/Kolkata")


def _candle(timestamp=None):
    return Candle(
        timestamp=timestamp or datetime(2026, 1, 5, 9, 15, tzinfo=IST),
        open=100,
        high=102,
        low=99,
        close=101,
        volume=None,
        instrument=InstrumentId.NIFTY50,
        timeframe=Timeframe.M15,
        source=DataSource(
            name="Upstox Historical Candle V3",
            kind=DataSourceKind.HISTORICAL,
            retrieved_at=datetime(2026, 1, 5, 10, tzinfo=IST),
        ),
    )


@pytest.mark.usefixtures("active_account_override")
def test_upstox_candle_route_returns_date_range_and_historical_labels(monkeypatch):
    captured = {}

    def fake_fetch(instrument, *, start_date, end_date, as_of):
        captured.update(instrument=instrument, start_date=start_date, end_date=end_date, as_of=as_of)
        target_day = end_date - timedelta(days=1)
        return [
            _candle(datetime.combine(start_date, time(9, 15), tzinfo=IST)),
            _candle(datetime.combine(target_day, time(9, 15), tzinfo=IST)),
            _candle(datetime.combine(target_day, time(9, 30), tzinfo=IST)),
        ]

    def fake_decisions(candles):
        return [
            SimpleNamespace(timestamp=candles[0].timestamp, decision=TradeDecision.BUY),
            SimpleNamespace(timestamp=candles[1].timestamp, decision=TradeDecision.BUY),
            SimpleNamespace(timestamp=candles[2].timestamp, decision=TradeDecision.SELL),
        ]

    monkeypatch.setattr(upstox_router, "fetch_15m_candles", fake_fetch)
    monkeypatch.setattr(upstox_router, "calculate_decisions", fake_decisions)
    response = client.get("/api/v1/market-data/upstox/candles?symbol=NIFTY50&days=7")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert data["provider"] == "Upstox"
    assert data["instrument"] == "NIFTY50"
    assert data["timeframe"] == "15m"
    assert len(data["candles"]) == 2
    assert data["candles"][0]["source"]["kind"] == "historical"
    assert data["candles"][-1]["timestamp"].endswith("09:30:00+05:30")
    assert data["last_candle_at"] == data["candles"][-1]["timestamp"]
    assert [point["decision"] for point in data["signals"]] == ["BUY", "SELL"]
    assert data["signals"][0]["timestamp"] == data["candles"][0]["timestamp"]
    assert captured["instrument"] is InstrumentId.NIFTY50
    assert (captured["end_date"] - captured["start_date"]).days == 27


@pytest.mark.usefixtures("active_account_override")
def test_upstox_route_reports_missing_server_token_without_echoing_secrets(monkeypatch):
    monkeypatch.setattr(
        upstox_router,
        "fetch_15m_candles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            UpstoxHistoryError(503, "Add UPSTOX_ACCESS_TOKEN to the API environment.")
        ),
    )
    response = client.get("/api/v1/market-data/upstox/candles?symbol=BANKNIFTY&days=7")

    assert response.status_code == 503
    assert response.json()["detail"] == "Add UPSTOX_ACCESS_TOKEN to the API environment."


def test_upstox_history_route_requires_a_verified_login(monkeypatch):
    # Configure the Supabase URL so missing Authorization is correctly reported as 401.
    from app import security
    from app.config import Settings

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(supabase_url="https://example.supabase.co"),
    )
    response = client.get("/api/v1/market-data/upstox/candles")
    assert response.status_code == 401


@pytest.mark.usefixtures("active_account_override")
def test_upstox_history_rejects_more_than_30_days():
    response = client.get("/api/v1/market-data/upstox/candles?days=31")
    assert response.status_code == 422


@pytest.mark.usefixtures("active_account_override")
def test_upstox_live_chart_route_includes_startup_historical_warmup(monkeypatch):
    as_of = datetime.now(IST)
    history = _candle()

    def fake_fetch(instrument, *, start_date, end_date, settings, as_of):
        return [history.model_copy(update={"instrument": instrument})]

    monkeypatch.setattr(history_provider_module, "fetch_15m_candles", fake_fetch)
    runtime = build_runtime_from_settings(
        Settings(_env_file=None, upstox_access_token=SecretStr("test-upstox-token")),
        provider="upstox",
    )
    startup_live_runtime(SimpleNamespace(state=SimpleNamespace(live_runtimes={"upstox": runtime})))
    set_live_runtimes(app, {"upstox": runtime})
    try:
        response = client.get(
            "/api/v1/live/candles",
            params={
                "symbol": "NIFTY50",
                "provider": "upstox",
                "timeframe": "15m",
                "limit": 500,
                "include_indicator_history": "true",
            },
        )
    finally:
        set_live_runtime(app, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body["candles"]) == 1
    assert body["candles"][0]["source"]["kind"] == "historical"
    assert body["indicator_history"]
