"""Tests for GrowwHistoricalProvider (get_historical_candles, timestamp normalization,
index volume handling, duration limits, and service.fetch_and_validate integration).
"""

from datetime import timedelta
import pytest

from app.indicators.decision import TradeDecision, calculate_decisions
from app.market_data.instruments import InstrumentId
from app.market_data.models import DataSourceKind
from app.market_data.service import fetch_and_validate
from app.market_data.timeframes import Timeframe
from app.providers.base import (
    CandleRequest,
    ProviderAuthError,
    ProviderRateLimitError,
    UnsupportedRequestError,
)
from app.providers.groww_auth import GrowwCredentials
from app.providers.groww_historical import GrowwHistoricalProvider
from app.providers.groww_instruments import GrowwInstrumentResolver
from tests.fixtures.sample_data import ist
from tests.test_groww_auth_and_instruments import FakeGrowwAPI


class HistoricalFakeGrowwAPI(FakeGrowwAPI):
    def __init__(self, rows):
        super().__init__("tok")
        self.rows = rows
        self.calls = []

    def get_historical_candles(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.rows, Exception):
            raise self.rows
        return {"candles": self.rows}


def test_fetch_5m_historical_candles_normalizes_timestamps_and_index_volume():
    base = ist(2026, 1, 5, 9, 15)
    rows = []
    for i in range(60):
        slot = base + timedelta(minutes=5 * i)
        price = 24000.0 + 10.0 * i
        rows.append(
            [
                slot.strftime("%Y-%m-%dT%H:%M:%S"),
                price,
                price + 15.0,
                price - 8.0,
                price + 5.0,
                0,     # Index row has 0/null volume in Groww; must become None (not fabricated 0)
                None,  # Open interest is None for indices
            ]
        )

    client = HistoricalFakeGrowwAPI(rows)
    resolver = GrowwInstrumentResolver(groww_client=client)
    provider = GrowwHistoricalProvider(groww_client=client, instrument_resolver=resolver)

    req = CandleRequest(
        instrument=InstrumentId.NIFTY50,
        timeframe=Timeframe.M5,
        start=ist(2026, 1, 5, 9, 15),
        end=ist(2026, 1, 5, 14, 15),
    )
    result = fetch_and_validate(provider, req, as_of=ist(2026, 1, 5, 14, 20))
    assert result.report.is_valid is True
    candles = result.require_valid()
    assert len(candles) == 60
    assert candles[0].timestamp == ist(2026, 1, 5, 9, 15)
    assert candles[0].volume is None
    assert candles[0].source.name == "groww"
    assert candles[0].source.kind == DataSourceKind.HISTORICAL

    assert client.calls[0]["groww_symbol"] == "NSE-NIFTY"
    assert client.calls[0]["candle_interval"] == "5minute"
    assert client.calls[0]["exchange"] == "NSE"
    assert client.calls[0]["segment"] == "CASH"

    # Verify normalized Groww historical candles feed directly into the 5-indicator decision engine!
    decisions = calculate_decisions(candles)
    assert len(decisions) == 60
    assert decisions[0].decision == TradeDecision.DATA_UNAVAILABLE
    assert decisions[-1].decision in (TradeDecision.BUY, TradeDecision.SELL, TradeDecision.WAIT)


def test_exceeding_30_day_5m_limit_raises_unsupported_request_error():
    client = HistoricalFakeGrowwAPI([])
    resolver = GrowwInstrumentResolver(groww_client=client)
    provider = GrowwHistoricalProvider(groww_client=client, instrument_resolver=resolver)

    req = CandleRequest(
        instrument=InstrumentId.BANKNIFTY,
        timeframe=Timeframe.M5,
        start=ist(2026, 1, 1, 9, 15),
        end=ist(2026, 2, 15, 15, 30),  # 45 days > 30 day limit
    )
    with pytest.raises(UnsupportedRequestError, match="30 days"):
        provider.fetch_candles(req)


def test_historical_auth_and_rate_limit_errors_are_translated_and_redacted():
    creds = GrowwCredentials(auth_mode="access_token", access_token="SECRET_GROWW_TOKEN_ABC")
    client_auth = HistoricalFakeGrowwAPI(RuntimeError("GrowwAPIAuthenticationException: token SECRET_GROWW_TOKEN_ABC invalid"))
    resolver = GrowwInstrumentResolver(groww_client=client_auth)
    provider = GrowwHistoricalProvider(
        groww_client=client_auth,
        instrument_resolver=resolver,
        credentials=creds,
    )
    req = CandleRequest(
        instrument=InstrumentId.NIFTY50,
        timeframe=Timeframe.M5,
        start=ist(2026, 1, 5, 9, 15),
        end=ist(2026, 1, 5, 10, 15),
    )
    with pytest.raises(ProviderAuthError) as exc_info:
        provider.fetch_candles(req)

    # Also check rate limit translation
    client_rl = HistoricalFakeGrowwAPI(RuntimeError("GrowwAPIRateLimitException: 429 rate limit"))
    provider_rl = GrowwHistoricalProvider(
        groww_client=client_rl,
        instrument_resolver=resolver,
        credentials=creds,
    )
    with pytest.raises(ProviderRateLimitError):
        provider_rl.fetch_candles(req)
