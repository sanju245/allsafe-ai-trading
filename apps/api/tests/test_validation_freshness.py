"""Stale data, future timestamps and still-forming candles."""

from app.market_data import Timeframe
from tests.fixtures.sample_data import (
    HISTORICAL_TEST_SOURCE,
    LIVE_LABELLED_TEST_SOURCE,
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


def live_minutes(count: int = 10):
    """Ten LIVE-labelled 1m candles, 09:15 to 09:24 on Monday. Last candle closes 09:25."""
    return series(minutes_from(MON_OPEN, count), source=LIVE_LABELLED_TEST_SOURCE)


# ---------------------------------------------------------------- staleness


def test_fresh_live_data_passes():
    report = run_validation(live_minutes(), as_of=ist(2026, 1, 5, 9, 25, 20))
    assert report.is_valid
    assert report.staleness_checked
    assert "STALE_DATA" not in codes(report)


def test_one_candle_of_lag_is_tolerated_by_default():
    # At 09:27:00 (minus 30s grace) the 09:25 candle has closed and is missing.
    report = run_validation(live_minutes(), as_of=ist(2026, 1, 5, 9, 27, 0))
    assert report.is_valid


def test_data_several_candles_behind_is_stale():
    report = run_validation(live_minutes(), as_of=ist(2026, 1, 5, 9, 30, 0))
    assert not report.is_valid
    assert "STALE_DATA" in error_codes(report)
    assert issues_with(report, "STALE_DATA")[0].timestamp == ist(2026, 1, 5, 9, 24)


def test_allowed_lag_can_be_tightened_or_loosened():
    at_0927 = ist(2026, 1, 5, 9, 27, 0)
    assert "STALE_DATA" in error_codes(
        run_validation(live_minutes(), as_of=at_0927, allowed_lag_candles=0)
    )
    assert "STALE_DATA" not in codes(
        run_validation(live_minutes(), as_of=ist(2026, 1, 5, 9, 30), allowed_lag_candles=5)
    )


def test_grace_period_covers_delivery_delay():
    # At 09:29:30 the 09:25 to 09:28 candles have closed, so 4 are missing: stale with the
    # default 30s grace. A 5-minute grace says only candles closed before 09:24:30 count,
    # and none have, so the same data passes.
    at = ist(2026, 1, 5, 9, 29, 30)
    assert "STALE_DATA" in error_codes(run_validation(live_minutes(), as_of=at))
    assert "STALE_DATA" not in codes(run_validation(live_minutes(), as_of=at, grace_seconds=300))


def test_weekend_is_not_stale():
    friday_last = [make_candle(ist(2026, 1, 9, 15, 29), source=LIVE_LABELLED_TEST_SOURCE)]
    report = run_validation(friday_last, as_of=ist(2026, 1, 10, 12, 0))  # Saturday noon
    assert report.is_valid
    assert report.staleness_checked


def test_overnight_is_not_stale_but_monday_morning_with_no_new_data_is():
    friday_last = [make_candle(ist(2026, 1, 9, 15, 29), source=LIVE_LABELLED_TEST_SOURCE)]
    just_opened = run_validation(friday_last, as_of=ist(2026, 1, 12, 9, 15, 10))
    assert "STALE_DATA" not in codes(just_opened)
    twenty_min_in = run_validation(friday_last, as_of=ist(2026, 1, 12, 9, 35))
    assert "STALE_DATA" in error_codes(twenty_min_in)


def test_daily_data_is_stale_after_more_than_one_missed_session():
    monday = series([ist(2026, 1, 5)], timeframe=Timeframe.D1, source=LIVE_LABELLED_TEST_SOURCE)
    kw = {"timeframe": Timeframe.D1}
    assert "STALE_DATA" not in codes(run_validation(monday, as_of=ist(2026, 1, 6, 17, 0), **kw))
    assert "STALE_DATA" in error_codes(run_validation(monday, as_of=ist(2026, 1, 7, 17, 0), **kw))


def test_historical_and_sample_sources_skip_staleness_by_default():
    hist = series(minutes_from(MON_OPEN, 5), source=HISTORICAL_TEST_SOURCE)
    sample = series(minutes_from(MON_OPEN, 5))
    for candles in (hist, sample):
        report = run_validation(candles)  # reference time is weeks later
        assert not report.staleness_checked
        assert "STALE_DATA" not in codes(report)


def test_staleness_can_be_forced_on_or_off():
    sample = series(minutes_from(MON_OPEN, 5))
    forced_on = run_validation(sample, check_staleness=True)
    assert "STALE_DATA" in error_codes(forced_on)
    live = live_minutes()
    forced_off = run_validation(live, as_of=ist(2026, 1, 5, 12, 0), check_staleness=False)
    assert not forced_off.staleness_checked
    assert "STALE_DATA" not in codes(forced_off)


# ---------------------------------------------------------------- future and forming


def test_candles_after_the_reference_time_are_errors():
    candles = series(minutes_from(MON_OPEN, 10), source=HISTORICAL_TEST_SOURCE)
    report = run_validation(candles, as_of=ist(2026, 1, 5, 9, 20))
    assert not report.is_valid
    # 09:21, 09:22, 09:23 and 09:24 are later than 09:20.
    assert report.issue_counts["FUTURE_TIMESTAMP"] == 4


def test_latest_candle_still_forming_is_a_warning():
    candles = series(minutes_from(MON_OPEN, 10), source=HISTORICAL_TEST_SOURCE)
    report = run_validation(candles, as_of=ist(2026, 1, 5, 9, 24, 30))
    assert report.is_valid
    issue = issues_with(report, "FORMING_CANDLE")[0]
    assert issue.severity.value == "warning"
    assert issue.index == 9


def test_candle_is_confirmed_exactly_at_its_close():
    candles = series(minutes_from(MON_OPEN, 10), source=HISTORICAL_TEST_SOURCE)
    report = run_validation(candles, as_of=ist(2026, 1, 5, 9, 25, 0))
    assert "FORMING_CANDLE" not in codes(report)


def test_daily_candle_is_forming_until_the_session_closes():
    today = series([ist(2026, 1, 5)], timeframe=Timeframe.D1, source=HISTORICAL_TEST_SOURCE)
    during = run_validation(today, timeframe=Timeframe.D1, as_of=ist(2026, 1, 5, 10, 0))
    after = run_validation(today, timeframe=Timeframe.D1, as_of=ist(2026, 1, 5, 15, 30))
    assert "FORMING_CANDLE" in codes(during)
    assert "FORMING_CANDLE" not in codes(after)
