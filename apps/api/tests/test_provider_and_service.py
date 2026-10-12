"""Provider interface contract and the service layer (no FastAPI needed)."""

import pytest
from pydantic import ValidationError

from app.market_data import DataSource, DataSourceKind, InstrumentId, Timeframe
from app.market_data.schemas import MAX_CANDLES_PER_VALIDATION, ValidateSeriesRequest
from app.market_data.service import (
    InvalidMarketDataError,
    fetch_and_validate,
    validate_series_request,
)
from app.providers import (
    CandleRequest,
    MarketDataProvider,
    ProviderAuthError,
    ProviderError,
    ProviderUnavailableError,
    UnsupportedRequestError,
)
from tests.fixtures.sample_data import (
    AS_OF_PAST,
    BANKNIFTY,
    NIFTY50,
    UTC,
    codes,
    error_codes,
    ist,
    make_candle,
    minutes_from,
    series,
)

FAKE_SOURCE = DataSource(name="FAKE-SAMPLE-PROVIDER", kind=DataSourceKind.SAMPLE)
T0 = ist(2026, 1, 5, 9, 15)


class FakeProvider(MarketDataProvider):
    """Test double. Returns SAMPLE data only; it can never be mistaken for a live feed."""

    def __init__(self, candles=None, *, timeframes=None, error: Exception | None = None):
        self._candles = candles if candles is not None else series(minutes_from(T0, 5), source=FAKE_SOURCE)
        self._timeframes = timeframes
        self._error = error

    @property
    def name(self) -> str:
        return FAKE_SOURCE.name

    @property
    def source_kind(self) -> DataSourceKind:
        return DataSourceKind.SAMPLE

    @property
    def supported_timeframes(self):
        return self._timeframes if self._timeframes is not None else super().supported_timeframes

    def fetch_candles(self, request):
        if self._error:
            raise self._error
        return list(self._candles)


REQUEST = CandleRequest(instrument=NIFTY50, timeframe=Timeframe.M1)


# ---------------------------------------------------------------- provider interface


def test_abstract_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MarketDataProvider()  # type: ignore[abstract]


def test_incomplete_provider_cannot_be_instantiated():
    class Incomplete(MarketDataProvider):
        @property
        def name(self):
            return "x"

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_provider_defaults_support_everything():
    p = FakeProvider()
    assert p.supported_instruments == frozenset(InstrumentId)
    assert p.supported_timeframes == frozenset(Timeframe)


def test_provider_errors_share_a_base_class():
    for exc in (ProviderUnavailableError, ProviderAuthError, UnsupportedRequestError):
        assert issubclass(exc, ProviderError)


def test_candle_request_rejects_bad_ranges():
    with pytest.raises(ValidationError):
        CandleRequest(instrument=NIFTY50, timeframe=Timeframe.M1, start=T0.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        CandleRequest(instrument=NIFTY50, timeframe=Timeframe.M1, start=ist(2026, 1, 6), end=ist(2026, 1, 5))
    with pytest.raises(ValidationError):
        CandleRequest(instrument=NIFTY50, timeframe=Timeframe.M1, limit=0)
    with pytest.raises(ValidationError):
        CandleRequest(instrument=NIFTY50, timeframe=Timeframe.M1, limit=10_001)
    with pytest.raises(ValidationError):
        CandleRequest(instrument="FTSE100", timeframe=Timeframe.M1)


# ---------------------------------------------------------------- fetch_and_validate


def test_fetch_and_validate_returns_candles_and_a_report():
    result = fetch_and_validate(FakeProvider(), REQUEST, as_of=AS_OF_PAST)
    assert len(result.candles) == 5
    assert result.report.is_valid
    assert result.report.source == FAKE_SOURCE
    assert result.require_valid() == result.candles


def test_invalid_data_is_reported_not_repaired_or_dropped():
    bad = [make_candle(T0, o=100, h=99, low=101, c=100, source=FAKE_SOURCE)]
    result = fetch_and_validate(FakeProvider(bad), REQUEST, as_of=AS_OF_PAST)
    assert result.candles == bad  # untouched
    assert not result.report.is_valid
    with pytest.raises(InvalidMarketDataError) as info:
        result.require_valid()
    assert "INVALID_OHLC" in str(info.value)
    assert info.value.report is result.report


def test_provider_returning_the_wrong_instrument_is_caught():
    wrong = series(minutes_from(T0, 3), instrument=BANKNIFTY, source=FAKE_SOURCE)
    result = fetch_and_validate(FakeProvider(wrong), REQUEST, as_of=AS_OF_PAST)
    assert "INSTRUMENT_MISMATCH" in error_codes(result.report)


def test_unsupported_timeframe_is_refused_before_fetching():
    provider = FakeProvider(timeframes=frozenset({Timeframe.D1}), error=AssertionError("must not fetch"))
    with pytest.raises(UnsupportedRequestError):
        fetch_and_validate(provider, REQUEST)


def test_provider_failures_propagate():
    provider = FakeProvider(error=ProviderUnavailableError("down"))
    with pytest.raises(ProviderUnavailableError):
        fetch_and_validate(provider, REQUEST)


def test_sample_provider_data_stays_labelled_sample():
    result = fetch_and_validate(FakeProvider(), REQUEST, as_of=AS_OF_PAST)
    assert result.report.source.kind is DataSourceKind.SAMPLE
    assert "SAMPLE_DATA" in codes(result.report)


# ---------------------------------------------------------------- validate-series request


def request_body(**overrides):
    body = {
        "instrument": "NIFTY50",
        "timeframe": "1m",
        "source": {"name": "caller-supplied", "kind": "historical"},
        "candles": [
            {
                "timestamp": "2026-01-05T09:15:00+05:30",
                "open": 1000, "high": 1002, "low": 998, "close": 1001, "volume": 10,
            },
            {
                "timestamp": "2026-01-05T09:16:00+05:30",
                "open": 1001, "high": 1003, "low": 999, "close": 1002, "volume": 12,
            },
        ],
    }
    body.update(overrides)
    return body


def test_valid_request_gives_a_valid_report():
    report = validate_series_request(ValidateSeriesRequest(**request_body()), now=AS_OF_PAST)
    assert report.is_valid
    assert report.candle_count == 2
    assert report.source.kind is DataSourceKind.HISTORICAL


def test_bad_values_give_a_report_not_an_exception():
    body = request_body()
    body["candles"][1]["high"] = 990  # below low and open
    body["candles"][1]["volume"] = -3
    report = validate_series_request(ValidateSeriesRequest(**body), now=AS_OF_PAST)
    assert not report.is_valid
    assert {"INVALID_OHLC", "NEGATIVE_VOLUME"} <= error_codes(report)


def test_request_as_of_overrides_the_clock():
    body = request_body(as_of="2026-01-05T09:15:30+05:30")
    report = validate_series_request(ValidateSeriesRequest(**body), now=AS_OF_PAST)
    assert report.checked_at == ist(2026, 1, 5, 9, 15, 30)
    assert "FUTURE_TIMESTAMP" in error_codes(report)  # the 09:16 candle is after as_of


def test_live_labelled_request_is_checked_for_staleness():
    body = request_body(source={"name": "caller-supplied", "kind": "live"})
    report = validate_series_request(ValidateSeriesRequest(**body), now=ist(2026, 1, 5, 11, 0))
    assert report.staleness_checked
    assert "STALE_DATA" in error_codes(report)


def test_empty_candle_list_is_a_report_not_a_422():
    report = validate_series_request(ValidateSeriesRequest(**request_body(candles=[])), now=AS_OF_PAST)
    assert error_codes(report) == {"EMPTY_SERIES"}
    assert report.instrument is InstrumentId.NIFTY50


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeframe": "2m"},
        {"instrument": "SENSEX"},
        {"source": {"name": "", "kind": "live"}},
        {"source": {"name": "x", "kind": "magic"}},
        {"as_of": "2026-01-05T09:15:00"},          # no timezone
        {"allowed_lag_candles": -1},
        {"unexpected_field": 1},
    ],
    ids=["timeframe", "instrument", "empty-name", "kind", "naive-as-of", "lag", "extra-field"],
)
def test_malformed_requests_are_rejected(overrides):
    with pytest.raises(ValidationError):
        ValidateSeriesRequest(**request_body(**overrides))


def test_unknown_field_inside_a_candle_is_rejected():
    body = request_body()
    body["candles"][0]["vol"] = 1
    with pytest.raises(ValidationError):
        ValidateSeriesRequest(**body)


def test_request_size_is_bounded():
    one = request_body()["candles"][0]
    ValidateSeriesRequest(**request_body(candles=[one] * MAX_CANDLES_PER_VALIDATION))
    with pytest.raises(ValidationError):
        ValidateSeriesRequest(**request_body(candles=[one] * (MAX_CANDLES_PER_VALIDATION + 1)))


def test_nan_in_supplied_data_is_reported():
    body = request_body()
    body["candles"][0]["close"] = float("nan")
    report = validate_series_request(ValidateSeriesRequest(**body), now=AS_OF_PAST)
    assert "NON_FINITE_VALUE" in error_codes(report)


def test_utc_is_available_for_fixtures():
    assert UTC.utcoffset(None).total_seconds() == 0
