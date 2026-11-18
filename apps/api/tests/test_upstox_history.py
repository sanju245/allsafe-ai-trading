"""Tests for the read-only Upstox 15-minute historical candle adapter."""

from datetime import date, datetime
from io import BytesIO
import json
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.market_data.instruments import InstrumentId
from app.market_data.timeframes import Timeframe
from app.providers import upstox_history
from app.providers.upstox_history import UpstoxHistoryError

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
    monkeypatch.setattr(
        upstox_history,
        "urlopen",
        lambda request, timeout: calls.append((request, timeout)) or FakeResponse({
            "status": "success",
            "data": {"candles": [
                ["2026-01-05T09:30:00+05:30", 102, 104, 101, 103, 0, 0],
                ["2026-01-05T09:15:00+05:30", 100, 103, 99, 102, 0, 0],
                ["2026-01-05T09:45:00+05:30", 103, 105, 102, 104, 0, 0],
            ]},
        }),
    )

    candles = upstox_history.fetch_15m_candles(
        InstrumentId.NIFTY50,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        settings=_settings(" Bearer test-analytics-token "),
        as_of=datetime(2026, 1, 5, 9, 45, tzinfo=IST),
    )

    request, timeout = calls[0]
    assert request.full_url.endswith("/NSE_INDEX%7CNifty%2050/minutes/15/2026-01-05/2026-01-01")
    assert request.get_header("Authorization") == "Bearer test-analytics-token"
    assert request.get_header("User-agent") == "AllSafeAITrading/0.2"
    assert timeout == 12
    assert [c.timestamp.isoformat() for c in candles] == [
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

    assert "/NSE_INDEX%7CNifty%20Bank/minutes/15/" in calls[0]


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
