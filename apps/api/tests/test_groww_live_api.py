"""HTTP API and lifecycle tests for Groww `/api/v1/live/*` endpoints."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.market_data.live_runtime import LiveMarketDataRuntime
from app.providers.groww_auth import GrowwCredentials
from app.providers.groww_stream import GrowwLiveStreamManager
from app.routers.live import set_live_runtime
from tests.fixtures.sample_data import ist
from tests.test_groww_historical import HistoricalFakeGrowwAPI
from tests.test_groww_stream_and_runtime import StatefulFakeGrowwFeed


def make_test_runtime(*, streaming_enabled: bool = False, stale_after_seconds: float = 60.0, hist_rows=None) -> LiveMarketDataRuntime:
    for m in ("subscribe_index_value", "get_index_value", "unsubscribe_index_value", "consume"):
        setattr(StatefulFakeGrowwFeed, m, getattr(StatefulFakeGrowwFeed, m))

    rows = hist_rows or []

    class _Client(HistoricalFakeGrowwAPI):
        def __init__(self, token: str):
            super().__init__(rows)

    creds = GrowwCredentials(
        auth_mode="access_token",
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJncm93dyJ9.secret_tok_999",
    )
    mgr = GrowwLiveStreamManager(
        credentials=creds,
        streaming_enabled=streaming_enabled,
        stale_after_seconds=stale_after_seconds,
        api_cls=_Client,
        feed_cls=StatefulFakeGrowwFeed,
    )
    return LiveMarketDataRuntime(stream_manager=mgr)


def test_default_startup_has_live_streaming_disabled_and_no_store_headers():
    set_live_runtime(app, None)
    with TestClient(app) as client:
        res = client.get("/api/v1/live/status")
        assert res.status_code == 200
        assert res.headers.get("cache-control") == "no-store"
        body = res.json()
        assert body["streaming_enabled"] is False
        assert body["connected"] is False
        assert body["provider"] == "groww"
        assert "NSE-NIFTY" in body["subscribed_symbols"]
        assert "NSE-BANKNIFTY" in body["subscribed_symbols"]
        assert "NIFTY50" in body["instruments"]
        assert "BANKNIFTY" in body["instruments"]


def test_quote_endpoint_unavailable_never_invents_prices_or_volume():
    rt = make_test_runtime(streaming_enabled=False)
    set_live_runtime(app, rt)
    client = TestClient(app)

    res = client.get("/api/v1/live/quote", params={"symbol": "NIFTY50"})
    assert res.status_code == 200
    assert res.headers.get("cache-control") == "no-store"
    body = res.json()
    assert body["instrument"] == "NIFTY50"
    assert body["groww_symbol"] == "NSE-NIFTY"
    assert body["trading_symbol"] == "NIFTY"
    assert body["available"] is False
    assert body["quote"] is None


def test_all_four_live_endpoints_and_indicator_decision_over_http():
    import app.routers.live as live_router

    base = ist(2026, 1, 5, 9, 15)
    rows = []
    for i in range(55):
        slot = base + timedelta(minutes=5 * i)
        p = 24000.0 + 5.0 * i
        rows.append([slot.strftime("%Y-%m-%dT%H:%M:%S"), p, p + 10.0, p - 5.0, p + 3.0, None, None])

    rt = make_test_runtime(streaming_enabled=True, stale_after_seconds=60.0, hist_rows=rows)
    t_open = ist(2026, 1, 5, 13, 50, 0)
    assert rt.start(as_of=t_open, run_warmup=True) is True

    # Feed 2 updates in 13:50 slot, then rollover to 13:55 slot
    rt.stream_manager.handle_index_feed_payload(
        {"NSE": {"CASH": {"NIFTY": {"tsInMillis": float(int(ist(2026, 1, 5, 13, 50, 5).timestamp() * 1000)), "value": 24300.0}}}},
        as_of=ist(2026, 1, 5, 13, 50, 5),
    )
    rt.stream_manager.handle_index_feed_payload(
        {"NSE": {"CASH": {"NIFTY": {"tsInMillis": float(int(ist(2026, 1, 5, 13, 53, 0).timestamp() * 1000)), "value": 24325.0}}}},
        as_of=ist(2026, 1, 5, 13, 53, 0),
    )
    t_curr = ist(2026, 1, 5, 13, 55, 10)
    rt.stream_manager.handle_index_feed_payload(
        {"NSE": {"CASH": {"NIFTY": {"tsInMillis": float(int(t_curr.timestamp() * 1000)), "value": 24340.0}}}},
        as_of=t_curr,
    )

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return ist(2026, 1, 5, 13, 55, 15)

    orig_dt = live_router.datetime
    live_router.datetime = _FrozenNow
    try:
        set_live_runtime(app, rt)
        client = TestClient(app)

        # 1. /api/v1/live/status
        rs = client.get("/api/v1/live/status")
        assert rs.status_code == 200
        assert rs.headers.get("cache-control") == "no-store"
        sb = rs.json()
        assert sb["provider"] == "groww"
        assert sb["feed_state"] == "live"
        assert sb["instruments"]["NIFTY50"]["exchange_token"] == "NIFTY"
        assert sb["instruments"]["BANKNIFTY"]["exchange_token"] == "26009"
        assert sb["instruments"]["NIFTY50"]["historical_candle_count"] == 55
        assert sb["instruments"]["NIFTY50"]["confirmed_candle_count"] == 1
        assert sb["instruments"]["NIFTY50"]["has_forming_candle"] is True

        # 2. /api/v1/live/quote
        rq = client.get("/api/v1/live/quote", params={"symbol": "NSE-NIFTY"})
        assert rq.status_code == 200
        assert rq.headers.get("cache-control") == "no-store"
        qb = rq.json()
        assert qb["available"] is True
        assert qb["quote"]["ltp"] == 24340.0
        assert qb["quote"]["volume"] is None
        assert qb["quote"]["provider_symbol"] == "NSE-NIFTY"

        # 3. /api/v1/live/candles -> confirmed candles only + 5-indicator decision
        rc = client.get("/api/v1/live/candles", params={"symbol": "NIFTY50", "timeframe": "5m", "limit": 10})
        assert rc.status_code == 200
        assert rc.headers.get("cache-control") == "no-store"
        cb = rc.json()
        assert cb["candle_count"] == 1
        assert cb["candles"][0]["open"] == 24300.0
        assert cb["candles"][0]["high"] == 24325.0
        assert cb["candles"][0]["close"] == 24325.0
        assert cb["candles"][0]["volume"] is None
        assert cb["candles"][0]["is_confirmed"] is True
        assert cb["candles"][0]["is_forming"] is False
        assert cb["indicator_decision"]["confirmed_candle_count"] == 56
        assert cb["indicator_decision"]["decision"] in ("BUY", "SELL", "WAIT")

        # 4. /api/v1/live/forming-candle -> 13:55 forming candle only
        rf = client.get("/api/v1/live/forming-candle", params={"symbol": "NIFTY50"})
        assert rf.status_code == 200
        assert rf.headers.get("cache-control") == "no-store"
        fb = rf.json()
        assert fb["available"] is True
        assert fb["forming_candle"]["open"] == 24340.0
        assert fb["forming_candle"]["is_forming"] is True
        assert fb["forming_candle"]["is_confirmed"] is False
    finally:
        live_router.datetime = orig_dt


def test_invalid_query_parameters_return_422():
    rt = make_test_runtime(streaming_enabled=False)
    set_live_runtime(app, rt)
    client = TestClient(app)

    assert client.get("/api/v1/live/quote", params={"symbol": "UNKNOWN"}).status_code == 422
    assert client.get("/api/v1/live/candles", params={"symbol": "NIFTY50", "timeframe": "15m"}).status_code == 422
    assert client.get("/api/v1/live/candles", params={"symbol": "NIFTY50", "timeframe": "5m", "limit": 0}).status_code == 422
    assert client.get("/api/v1/live/forming-candle", params={"symbol": "BAD"}).status_code == 422


def test_http_responses_never_leak_groww_secrets():
    rt = make_test_runtime(streaming_enabled=True)
    rt.start(as_of=ist(2026, 1, 5, 9, 15, 0), run_warmup=False)
    rt.stream_manager.handle_feed_error(
        f"GrowwAPIAuthenticationException: Bearer {rt.stream_manager.credentials.access_token} unauthorized GA005"
    )
    set_live_runtime(app, rt)
    client = TestClient(app)

    res = client.get("/api/v1/live/status")
    assert res.status_code == 200
    assert "secret_tok_999" not in res.text
    assert res.json()["feed_state"] == "failed"


def test_smoke_script_exits_2_when_credentials_missing():
    from app.config import get_settings
    from scripts.smoke_groww_live import run_smoke_test

    get_settings.cache_clear()
    assert run_smoke_test(duration_seconds=1.0) == 2
