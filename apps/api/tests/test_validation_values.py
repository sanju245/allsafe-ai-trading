import math

import pytest

from app.market_data import DataSource, DataSourceKind, Timeframe
from tests.fixtures.sample_data import (
    BANKNIFTY,
    HISTORICAL_TEST_SOURCE,
    NIFTY50,
    codes,
    error_codes,
    issues_with,
    ist,
    make_candle,
    minutes_from,
    run_validation,
    series,
)

T0 = ist(2026, 1, 5, 9, 15)


def test_valid_series_has_no_errors_and_is_flagged_sample():
    candles = series(minutes_from(T0, 10))
    report = run_validation(candles)
    assert report.is_valid
    assert report.error_count == 0
    assert report.candle_count == 10
    assert report.first_timestamp == T0
    assert report.last_timestamp == minutes_from(T0, 10)[-1]
    assert report.missing_candle_count == 0
    # The only note is that this is sample data.
    assert codes(report) == {"SAMPLE_DATA"}
    assert report.source.kind.value == "sample"


def test_invalid_ohlc_message_names_the_specific_problem():
    report = run_validation([make_candle(T0, o=100, h=99, low=101, c=100)])
    message = issues_with(report, "INVALID_OHLC")[0].message
    assert "high is below low" in message


def test_flat_candle_is_valid():
    report = run_validation([make_candle(T0, o=100, h=100, low=100, c=100)])
    assert report.is_valid


@pytest.mark.parametrize(
    ("o", "h", "low", "c"),
    [
        (100, 99, 101, 100),   # high below low
        (100, 99, 98, 100),    # high below open and close
        (100, 105, 101, 100),  # low above open and close
        (100, 103, 99, 105),   # close above high
        (100, 103, 99, 98),    # close below low
    ],
    ids=["high<low", "high<open", "low>open", "close>high", "close<low"],
)
def test_invalid_ohlc_is_an_error(o, h, low, c):
    report = run_validation([make_candle(T0, o=o, h=h, low=low, c=c)])
    assert not report.is_valid
    assert "INVALID_OHLC" in error_codes(report)
    assert issues_with(report, "INVALID_OHLC")[0].index == 0


@pytest.mark.parametrize(
    ("o", "h", "low", "c"),
    [(-1, 5, -2, 1), (0, 2, 0, 1), (10, 10, 0, 10)],
    ids=["negative", "zero-open", "zero-low"],
)
def test_non_positive_prices_are_errors(o, h, low, c):
    report = run_validation([make_candle(T0, o=o, h=h, low=low, c=c)])
    assert not report.is_valid
    assert "NON_POSITIVE_PRICE" in error_codes(report)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"c": math.nan},
        {"h": math.inf},
        {"o": -math.inf},
        {"volume": math.nan},
        {"volume": math.inf},
    ],
    ids=["nan-close", "inf-high", "-inf-open", "nan-volume", "inf-volume"],
)
def test_non_finite_values_are_errors(kwargs):
    report = run_validation([make_candle(T0, **kwargs)])
    assert not report.is_valid
    assert "NON_FINITE_VALUE" in error_codes(report)


def test_negative_volume_is_an_error():
    report = run_validation([make_candle(T0, volume=-5)])
    assert not report.is_valid
    assert "NEGATIVE_VOLUME" in error_codes(report)


def test_zero_volume_is_valid():
    report = run_validation([make_candle(T0, volume=0)])
    assert report.is_valid
    assert "NEGATIVE_VOLUME" not in codes(report)
    assert "VOLUME_UNAVAILABLE" not in codes(report)


def test_missing_volume_is_a_warning_not_an_error():
    report = run_validation([make_candle(T0, volume=None)])
    assert report.is_valid
    assert "VOLUME_UNAVAILABLE" in codes(report)
    assert issues_with(report, "VOLUME_UNAVAILABLE")[0].severity.value == "warning"


def test_several_bad_candles_are_all_reported_with_their_index():
    good = series(minutes_from(T0, 3))
    candles = [
        good[0],
        make_candle(ist(2026, 1, 5, 9, 16), o=100, h=99, low=101, c=100),
        good[2].model_copy(update={"volume": -1}),
    ]
    report = run_validation(candles)
    assert [i.index for i in issues_with(report, "INVALID_OHLC")] == [1]
    assert [i.index for i in issues_with(report, "NEGATIVE_VOLUME")] == [2]


def test_issue_listing_is_capped_but_counts_are_exact():
    candles = [
        make_candle(ts, o=100, h=99, low=101, c=100) for ts in minutes_from(T0, 30)
    ]
    report = run_validation(candles, max_issues_per_code=5)
    assert len(issues_with(report, "INVALID_OHLC")) == 5
    assert report.issue_counts["INVALID_OHLC"] == 30
    assert report.error_count == 30
    assert report.issues_truncated


def test_empty_series_is_invalid():
    report = run_validation([])
    assert not report.is_valid
    assert error_codes(report) == {"EMPTY_SERIES"}
    assert report.candle_count == 0


def test_mismatched_instrument_timeframe_and_source_are_errors():
    candles = [
        make_candle(T0),
        make_candle(ist(2026, 1, 5, 9, 16), instrument=BANKNIFTY),
        make_candle(ist(2026, 1, 5, 9, 17), timeframe=Timeframe.M5),
        make_candle(ist(2026, 1, 5, 9, 18), source=HISTORICAL_TEST_SOURCE),
    ]
    report = run_validation(candles)
    assert {"INSTRUMENT_MISMATCH", "TIMEFRAME_MISMATCH", "SOURCE_MISMATCH"} <= error_codes(report)
    assert issues_with(report, "INSTRUMENT_MISMATCH")[0].index == 1
    assert issues_with(report, "TIMEFRAME_MISMATCH")[0].index == 2
    assert issues_with(report, "SOURCE_MISMATCH")[0].index == 3


def test_naive_as_of_and_negative_lag_are_programming_errors():
    with pytest.raises(ValueError):
        run_validation([make_candle(T0)], as_of=T0.replace(tzinfo=None))
    with pytest.raises(ValueError):
        run_validation([make_candle(T0)], allowed_lag_candles=-1)


def test_sample_source_is_always_labelled_sample():
    report = run_validation(series(minutes_from(T0, 3)))
    assert report.source == DataSource(
        name="SAMPLE-FIXTURE-NOT-MARKET-DATA", kind=DataSourceKind.SAMPLE
    )
    assert report.instrument == NIFTY50
