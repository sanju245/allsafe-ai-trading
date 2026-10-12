"""Duplicates, ordering, grid alignment, trading hours and missing intervals."""

from datetime import datetime

import pytest

from app.market_data import Timeframe
from tests.fixtures.sample_data import (
    UTC,
    codes,
    error_codes,
    issues_with,
    ist,
    make_candle,
    minutes_from,
    run_validation,
    series,
)

MON_OPEN = ist(2026, 1, 5, 9, 15)
FRI_OPEN = ist(2026, 1, 9, 9, 15)


def times(*hm: tuple[int, int], day: tuple[int, int, int] = (2026, 1, 5)):
    return [ist(*day, h, m) for h, m in hm]


# ---------------------------------------------------------------- duplicates / order


def test_duplicate_timestamp_is_an_error_and_not_a_gap():
    ts = times((9, 15), (9, 16), (9, 16), (9, 17))
    report = run_validation(series(ts))
    assert not report.is_valid
    assert error_codes(report) == {"DUPLICATE_TIMESTAMP"}
    assert issues_with(report, "DUPLICATE_TIMESTAMP")[0].index == 2


def test_duplicate_is_detected_across_time_zones():
    a = make_candle(ist(2026, 1, 5, 9, 15))
    b = make_candle(datetime(2026, 1, 5, 3, 45, tzinfo=UTC))  # the same instant, in UTC
    report = run_validation([a, b])
    assert "DUPLICATE_TIMESTAMP" in error_codes(report)


def test_out_of_order_candle_is_flagged_once_and_causes_no_false_gap():
    ts = times((9, 15), (9, 17), (9, 16), (9, 18))
    report = run_validation(series(ts))
    assert error_codes(report) == {"OUT_OF_ORDER"}
    assert [i.index for i in issues_with(report, "OUT_OF_ORDER")] == [2]
    assert report.missing_candle_count == 0


def test_fully_reversed_series_flags_every_step_down():
    ts = list(reversed(times((9, 15), (9, 16), (9, 17))))
    report = run_validation(series(ts))
    assert [i.index for i in issues_with(report, "OUT_OF_ORDER")] == [1, 2]


def test_naive_timestamp_is_an_error():
    report = run_validation([make_candle(datetime(2026, 1, 5, 9, 15))])
    assert not report.is_valid
    assert error_codes(report) == {"NAIVE_TIMESTAMP"}


def test_utc_timestamps_are_converted_to_ist_for_the_grid():
    # 03:45 UTC is 09:15 IST, the first slot of the session.
    ts = [datetime(2026, 1, 5, 3, 45 + i, tzinfo=UTC) for i in range(5)]
    report = run_validation(series(ts))
    assert report.is_valid
    assert codes(report) == {"SAMPLE_DATA"}


# ---------------------------------------------------------------- grid and hours


@pytest.mark.parametrize(
    ("timeframe", "when"),
    [
        (Timeframe.M3, ist(2026, 1, 5, 9, 16)),
        (Timeframe.M5, ist(2026, 1, 5, 9, 17)),
        (Timeframe.M15, ist(2026, 1, 5, 9, 20)),
        (Timeframe.H1, ist(2026, 1, 5, 10, 0)),   # hourly bars open at :15, not :00
        (Timeframe.M1, ist(2026, 1, 5, 9, 15, 30)),
    ],
    ids=["3m", "5m", "15m", "1h-on-the-hour", "1m-with-seconds"],
)
def test_off_grid_timestamp_is_an_error(timeframe, when):
    report = run_validation([make_candle(when, timeframe=timeframe)], timeframe=timeframe)
    assert "TIMESTAMP_NOT_ON_GRID" in error_codes(report)


@pytest.mark.parametrize(
    ("timeframe", "stamps"),
    [
        (Timeframe.M3, times((9, 15), (9, 18), (9, 21))),
        (Timeframe.M5, times((9, 15), (9, 20), (9, 25))),
        (Timeframe.M15, times((9, 15), (9, 30), (9, 45))),
        # A full session of hourly candles; the last one (15:15) is a 15-minute stub.
        (Timeframe.H1, times((9, 15), (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (15, 15))),
    ],
    ids=["3m", "5m", "15m", "1h-full-day"],
)
def test_on_grid_series_has_no_errors_or_gaps(timeframe, stamps):
    report = run_validation(series(stamps, timeframe=timeframe), timeframe=timeframe)
    assert report.is_valid
    assert codes(report) == {"SAMPLE_DATA"}
    assert report.missing_candle_count == 0


@pytest.mark.parametrize(
    "when",
    [
        ist(2026, 1, 5, 8, 59),   # before the open
        ist(2026, 1, 5, 15, 30),  # the close itself; the last 1m candle opens at 15:29
        ist(2026, 1, 10, 10, 0),  # Saturday
    ],
    ids=["before-open", "at-close", "saturday"],
)
def test_outside_trading_hours_is_a_warning_only(when):
    report = run_validation([make_candle(when)])
    assert report.is_valid
    issue = issues_with(report, "OUTSIDE_TRADING_HOURS")[0]
    assert issue.severity.value == "warning"


# ---------------------------------------------------------------- intraday gaps


def test_missing_candles_in_the_middle_of_a_session():
    ts = times((9, 15), (9, 16), (9, 17), (9, 18), (9, 19), (9, 23), (9, 24), (9, 25))
    report = run_validation(series(ts))
    assert not report.is_valid
    gap = issues_with(report, "MISSING_INTERVAL")[0]
    assert gap.count == 3
    assert gap.timestamp == ist(2026, 1, 5, 9, 20)
    assert report.missing_candle_count == 3


def test_overnight_and_weekend_are_not_gaps():
    ts = (
        times((15, 27), (15, 28), (15, 29), day=(2026, 1, 9))       # Friday close
        + times((9, 15), (9, 16), (9, 17), day=(2026, 1, 12))       # Monday open
    )
    report = run_validation(series(ts))
    assert report.is_valid
    assert codes(report) == {"SAMPLE_DATA"}
    assert report.missing_candle_count == 0


def test_missing_end_of_previous_day_is_a_gap():
    ts = times((15, 27), day=(2026, 1, 9)) + times((9, 15), day=(2026, 1, 12))
    report = run_validation(series(ts))
    gap = issues_with(report, "MISSING_INTERVAL")[0]
    assert gap.count == 2  # 15:28 and 15:29 on Friday
    assert gap.timestamp == ist(2026, 1, 9, 15, 28)


def test_missing_start_of_next_day_is_a_gap():
    ts = times((15, 29), day=(2026, 1, 9)) + times((9, 17), day=(2026, 1, 12))
    report = run_validation(series(ts))
    gap = issues_with(report, "MISSING_INTERVAL")[0]
    assert gap.count == 2  # 09:15 and 09:16 on Monday
    assert gap.timestamp == ist(2026, 1, 12, 9, 15)


def test_one_missing_weekday_is_only_a_warning_because_it_may_be_a_holiday():
    ts = times((15, 29), day=(2026, 1, 5)) + times((9, 15), day=(2026, 1, 7))  # Tuesday absent
    report = run_validation(series(ts))
    assert report.is_valid
    issue = issues_with(report, "MISSING_SESSION")[0]
    assert issue.severity.value == "warning"
    assert issue.count == 1
    assert report.missing_session_count == 1
    assert report.missing_candle_count == 375  # a whole 1m session


def test_four_missing_weekdays_is_still_a_warning():
    # Tue 6, Wed 7, Thu 8, Fri 9 absent; Sat/Sun are never counted.
    ts = times((15, 29), day=(2026, 1, 5)) + times((9, 15), day=(2026, 1, 12))
    report = run_validation(series(ts))
    assert report.is_valid
    assert report.missing_session_count == 4


def test_five_missing_weekdays_is_an_error():
    # Tue 6 through Fri 9 plus Mon 12 absent: no run of holidays is that long.
    ts = times((15, 29), day=(2026, 1, 5)) + times((9, 15), day=(2026, 1, 13))
    report = run_validation(series(ts))
    assert not report.is_valid
    assert "MISSING_INTERVAL" in error_codes(report)
    assert report.missing_session_count == 5


# ---------------------------------------------------------------- daily candles


def d1(*days: int):
    return series([ist(2026, 1, d) for d in days], timeframe=Timeframe.D1)


def test_consecutive_daily_candles_are_valid():
    report = run_validation(d1(5, 6, 7), timeframe=Timeframe.D1)
    assert report.is_valid
    assert codes(report) == {"SAMPLE_DATA"}


def test_friday_to_monday_daily_is_not_a_gap():
    report = run_validation(d1(9, 12), timeframe=Timeframe.D1)
    assert report.is_valid
    assert report.missing_session_count == 0


def test_missing_weekday_in_daily_series_is_a_warning():
    report = run_validation(d1(5, 7), timeframe=Timeframe.D1)
    assert report.is_valid
    assert report.missing_session_count == 1
    assert report.missing_candle_count == 1


def test_daily_candles_on_the_same_date_are_duplicates():
    candles = [
        make_candle(ist(2026, 1, 5, 0, 0), timeframe=Timeframe.D1),
        make_candle(ist(2026, 1, 5, 9, 15), timeframe=Timeframe.D1),
    ]
    report = run_validation(candles, timeframe=Timeframe.D1)
    assert "DUPLICATE_TIMESTAMP" in error_codes(report)


def test_daily_candle_on_a_weekend_is_a_warning():
    report = run_validation(
        [make_candle(ist(2026, 1, 10), timeframe=Timeframe.D1)], timeframe=Timeframe.D1
    )
    assert report.is_valid
    assert "OUTSIDE_TRADING_HOURS" in codes(report)


def test_large_series_validates_quickly_and_correctly():
    # Four full trading days of 1m candles: 4 x 375.
    ts = []
    for day in (5, 6, 7, 8):
        ts += minutes_from(ist(2026, 1, day, 9, 15), 375)
    report = run_validation(series(ts))
    assert report.is_valid
    assert report.candle_count == 1500
    assert report.missing_candle_count == 0
