"""HTTP-level tests for authenticated Upstox historical candle charts."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.routers.upstox_history as upstox_router
from app.main import app
from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.timeframes import Timeframe
from app.providers.upstox_history import UpstoxHistoryError

client = TestClient(app)
IST = ZoneInfo("Asia/Kolkata")


def _candle():
    return Candle(
        timestamp=datetime(2026, 1, 5, 9, 15, tzinfo=IST),
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
        return [_candle()]

    monkeypatch.setattr(upstox_router, "fetch_15m_candles", fake_fetch)
    response = client.get("/api/v1/market-data/upstox/candles?symbol=NIFTY50&days=7")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert data["provider"] == "Upstox"
    assert data["instrument"] == "NIFTY50"
    assert data["timeframe"] == "15m"
    assert data["candles"][0]["source"]["kind"] == "historical"
    assert data["last_candle_at"] == "2026-01-05T09:15:00+05:30"
    assert captured["instrument"] is InstrumentId.NIFTY50
    assert (captured["end_date"] - captured["start_date"]).days == 6


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
