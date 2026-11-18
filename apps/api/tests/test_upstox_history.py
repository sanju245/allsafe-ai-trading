"""Tests for the read-only Upstox 15-minute historical candle adapter."""

from datetime import date, datetime
from io import BytesIO
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.indicators.decision import TradeDecision
from app.market_data import live_runtime
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.timeframes import Timeframe
from app.providers.base import CandleRequest
from app.providers import upstox_history
from app.providers.upstox_history import UpstoxHistoricalProvider, UpstoxHistoryError
from app.routers.live import build_runtime_from_settings

IST = ZoneInfo("Asia/Kolkata")


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def _settings(token="test-analytics-token"):
    return Settings(_env_file=None, upstox_access_token=SecretStr(token or ""))


def test_fetches_nifty_15m_candles_with_server_token_and_sorts_oldest_first(monkeypatch):
    calls = []
    def open_what_was_requested(request, timeout):
        calls.append((request, timeout))
        if "/intraday/" in request.full_url:
            candles = [
                ["2026-01-05T09:30:00+05:30", 102, 104, 101, 103, 0, 0],
                ["2026-01-05T09:15:00+05:30", 100, 103, 99, 102, 0, 0],
                ["2026-01-05T09:45:00+05:30", 103, 105, 102, 104, 0, 0],
            ]
        else:
            candles = [
                ["2026-01-02T15:15:00+05:30", 99, 103, 98, 100, 0, 0],
                ["2026-01-02T15:30:00+05:30", 100, 100, 100, 100, 0, 0],
            ]
        return FakeResponse({"status": "success", "data": {"candles": candles}})

    monkeypatch.setattr(upstox_history, "urlopen", open_what_was_requested)

    candles = upstox_history.fetch_15m_candles(
        InstrumentId.NIFTY50,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        settings=_settings(" Bearer test-analytics-token "),
        as_of=datetime(2026, 1, 5, 9, 45, tzinfo=IST),
    )

    request, timeout = calls[0]
    assert request.full_url.endswith("/NSE_INDEX%7CNifty%2050/minutes/15/2026-01-04/2026-01-01")
    assert calls[1][0].full_url.endswith("/intraday/NSE_INDEX%7CNifty%2050/minutes/15")
    assert request.get_header("Authorization") == "Bearer test-analytics-token"
    assert request.get_header("User-agent") == "AllSafeAITrading/0.2"
    assert timeout == 12
    assert [c.timestamp.isoformat() for c in candles] == [
        "2026-01-02T15:15:00+05:30",
        "2026-01-05T09:15:00+05:30",
        "2026-01-05T09:30:00+05:30",
    ]
    assert all(c.timeframe is Timeframe.M15 for c in candles)
    assert all(c.instrument is InstrumentId.NIFTY50 for c in candles)
    assert all(c.source.kind == "historical" and c.volume is None for c in candles)


def test_banknifty_uses_upstox_index_instrument_key(monkeypatch):
    calls = []
    monkeypatch.setattr(
        upstox_history,
        "urlopen",
        lambda request, timeout: calls.append(request.full_url) or FakeResponse({"status": "success", "data": {"candles": []}}),
    )

    upstox_history.fetch_15m_candles(
        InstrumentId.BANKNIFTY,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
        settings=_settings(),
        as_of=datetime(2026, 1, 5, 10, tzinfo=IST),
    )

    assert calls[0].endswith("/intraday/NSE_INDEX%7CNifty%20Bank/minutes/15")


def test_upstox_runtime_warms_both_indices_and_excludes_future_data(monkeypatch):
    def get_closed_history(*_args, **_kwargs):
        return FakeResponse({"status": "success", "data": {"candles": [
            ["2026-01-02T15:15:00+05:30", 100, 102, 99, 101],
        ]}})

    monkeypatch.setattr(upstox_history, "urlopen", get_closed_history)
    runtime = build_runtime_from_settings(_settings(), provider="upstox")
    now = datetime(2026, 1, 5, 9, 15, tzinfo=IST)

    assert runtime.warmup_from_historical_provider(as_of=now) == {
        InstrumentId.NIFTY50: 1,
        InstrumentId.BANKNIFTY: 1,
    }
    for symbol in InstrumentId:
        candles = runtime.merged_complete_confirmed_candles(symbol, as_of=now)
        assert len(candles) == 1
        assert candles[0].instrument is symbol
        assert candles[0].timeframe is Timeframe.M15
        assert runtime.stream_manager.evaluate_instrument_state(symbol, as_of=now).historical_candle_count == 1

    monkeypatch.setattr(
        runtime.stream_manager, "evaluate_instrument_state",
        lambda *_args, **_kwargs: SimpleNamespace(feed_state=FeedState.LIVE, is_stale=False),
    )
    monkeypatch.setattr(
        live_runtime, "calculate_decisions",
        lambda bars: [SimpleNamespace(
            timestamp=bars[-1].timestamp, decision=TradeDecision.BUY, reason="Confirmed fixture.",
            ut_bot_signal=None, ema_bullish=True, rsi_bullish=True,
            macd_bullish=True, supertrend_bullish=True,
        )],
    )
    summary = runtime.evaluate_decision_for_instrument(InstrumentId.NIFTY50, as_of=now)
    assert summary.decision is TradeDecision.BUY
    assert not summary.is_current_signal
    assert "latest session candle is not available" in summary.reason


def test_missing_token_and_ranges_over_upstox_limit_are_rejected_before_request(monkeypatch):
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(upstox_history, "urlopen", unexpected)
    with pytest.raises(UpstoxHistoryError, match="UPSTOX_ACCESS_TOKEN") as missing:
        upstox_history.fetch_15m_candles(
            InstrumentId.NIFTY50,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            settings=_settings(token=""),
        )
    assert missing.value.status_code == 503

    with pytest.raises(UpstoxHistoryError, match="30 days") as too_long:
        upstox_history.fetch_15m_candles(
            InstrumentId.NIFTY50,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            settings=_settings(),
        )
    assert too_long.value.status_code == 422
    assert called is False


def test_upstox_auth_error_is_sanitized_and_never_echoes_response_body(monkeypatch):
    secret = "test-analytics-token"

    def unauthorized(*_args, **_kwargs):
        raise HTTPError("https://api.upstox.com", 401, "Unauthorized", {}, BytesIO(secret.encode()))

    monkeypatch.setattr(upstox_history, "urlopen", unauthorized)
    with pytest.raises(UpstoxHistoryError) as error:
        upstox_history.fetch_15m_candles(
            InstrumentId.NIFTY50,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            settings=_settings(secret),
        )
    assert error.value.status_code == 502
    assert secret not in error.value.detail


def test_upstox_gateway_block_is_distinguished_from_bad_token(monkeypatch):
    secret = "test-analytics-token"

    def gateway_block(*_args, **_kwargs):
        raise HTTPError(
            "https://api.upstox.com/v3/historical-candle",
            403,
            "Forbidden",
            {},
            BytesIO(
                json.dumps({
                    "cloudflare_error": True,
                    "error_code": 1010,
                    "detail": secret,
                }).encode(),
            ),
        )

    monkeypatch.setattr(upstox_history, "urlopen", gateway_block)
    with pytest.raises(UpstoxHistoryError, match="Cloudflare 1010") as error:
        upstox_history.fetch_15m_candles(
            InstrumentId.NIFTY50,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            settings=_settings(secret),
        )
    assert secret not in error.value.detail


def test_invalid_ohlc_is_rejected(monkeypatch):
    monkeypatch.setattr(
        upstox_history,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({
            "status": "success",
            "data": {"candles": [["2026-01-05T09:15:00+05:30", 100, 99, 98, 102, 0, 0]]},
        }),
    )
    with pytest.raises(UpstoxHistoryError, match="OHLC"):
        upstox_history.fetch_15m_candles(
            InstrumentId.NIFTY50,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
            settings=_settings(),
            as_of=datetime(2026, 1, 5, 10, tzinfo=IST),
        )


def test_upstox_provider_adapts_runtime_request_and_respects_limit(monkeypatch):
    calls = []
    now = datetime(2026, 1, 8, 10, tzinfo=IST)
    candle = Candle(
        timestamp=datetime(2026, 1, 8, 9, 15, tzinfo=IST),
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
            retrieved_at=now,
        ),
    )

    def fake_fetch(instrument, *, start_date, end_date, settings, as_of):
        calls.append((instrument, start_date, end_date, settings, as_of))
        return [candle, candle]

    monkeypatch.setattr(upstox_history, "fetch_15m_candles", fake_fetch)
    settings = _settings()
    provider = UpstoxHistoricalProvider(settings=settings)
    request = CandleRequest(
        instrument=InstrumentId.NIFTY50,
        timeframe=Timeframe.M15,
        start=datetime(2026, 1, 5, 9, 15, tzinfo=IST),
        end=now,
        limit=1,
    )

    result = provider.fetch_candles(request)

    assert len(result) == 1
    assert calls == [(InstrumentId.NIFTY50, date(2026, 1, 5), date(2026, 1, 8), settings, now)]


def test_upstox_runtime_build_warms_history_for_both_indices(monkeypatch):
    from app.main import startup_live_runtime
    from app.routers.live import build_runtime_from_settings

    now = datetime(2026, 1, 8, 10, tzinfo=IST)
    calls = []

    def fake_fetch(instrument, *, start_date, end_date, settings, as_of):
        calls.append((instrument, start_date, end_date))
        price = 24_000 if instrument is InstrumentId.NIFTY50 else 50_000
        return [Candle(
            timestamp=datetime(2026, 1, 8, 9, 15, tzinfo=IST),
            open=price,
            high=price + 10,
            low=price - 5,
            close=price + 3,
            volume=None,
            instrument=instrument,
            timeframe=Timeframe.M15,
            source=DataSource(
                name="Upstox Historical Candle V3",
                kind=DataSourceKind.HISTORICAL,
                retrieved_at=as_of,
            ),
        )]

    monkeypatch.setattr(upstox_history, "fetch_15m_candles", fake_fetch)
    runtime = build_runtime_from_settings(_settings(), provider="upstox")
    app = SimpleNamespace(state=SimpleNamespace(live_runtimes={"upstox": runtime}))

    # History must still be loaded when the streaming switch is off; the full
    # chart can then show earlier candles while correctly marking the feed idle.
    startup_live_runtime(app)

    assert runtime.stream_manager.streaming_enabled is False
    assert [call[0] for call in calls] == [InstrumentId.NIFTY50, InstrumentId.BANKNIFTY]
    for instrument in InstrumentId:
        candles = runtime.merged_complete_confirmed_candles(instrument, as_of=now)
        assert len(candles) == 1
        assert candles[0].source.kind is DataSourceKind.HISTORICAL
        status = runtime.stream_manager.evaluate_instrument_state(instrument, as_of=now)
        assert status.historical_candle_count == 1
