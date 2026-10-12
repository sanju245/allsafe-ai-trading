from datetime import datetime, timedelta

import pytest

from app.market_data import INSTRUMENTS, InstrumentId, Timeframe
from app.market_data.instruments import list_instruments
from app.market_data.timeframes import list_timeframes
from tests.fixtures.sample_data import UTC, ist, make_candle


def test_supported_timeframes_are_exactly_the_required_six():
    assert [t.value for t in Timeframe] == ["1m", "3m", "5m", "15m", "1h", "1d"]


@pytest.mark.parametrize(
    ("identifier", "interval"),
    [
        ("1m", timedelta(minutes=1)),
        ("3m", timedelta(minutes=3)),
        ("5m", timedelta(minutes=5)),
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("1d", timedelta(days=1)),
    ],
)
def test_timeframe_intervals(identifier, interval):
    assert Timeframe(identifier).interval == interval


@pytest.mark.parametrize("bad", ["2m", "30m", "4h", "1w", "", "1M", "60s"])
def test_unsupported_timeframe_identifiers_are_rejected(bad):
    with pytest.raises(ValueError):
        Timeframe(bad)


def test_only_daily_is_not_intraday():
    assert [t.value for t in Timeframe if not t.is_intraday] == ["1d"]


def test_timeframe_listing_matches_enum():
    info = list_timeframes()
    assert [i.id for i in info] == list(Timeframe)
    assert info[0].seconds == 60
    assert info[-1].seconds == 86400


def test_supported_instruments():
    assert {i.value for i in InstrumentId} == {"NIFTY50", "BANKNIFTY"}
    names = {i.name for i in list_instruments()}
    assert names == {"NIFTY 50", "BANK NIFTY"}
    assert set(INSTRUMENTS) == set(InstrumentId)


def test_instrument_session_metadata():
    for inst in list_instruments():
        assert inst.exchange == "NSE"
        assert inst.asset_class == "index"
        assert inst.currency == "INR"
        assert (inst.session_open.hour, inst.session_open.minute) == (9, 15)
        assert (inst.session_close.hour, inst.session_close.minute) == (15, 30)


def test_candle_carries_required_fields():
    c = make_candle(ist(2026, 1, 5, 9, 15))
    for field in (
        "timestamp", "open", "high", "low", "close", "volume",
        "instrument", "timeframe", "source",
    ):
        assert hasattr(c, field)
    assert c.source.kind.value == "sample"


@pytest.mark.parametrize(
    ("timeframe", "open_at", "closes_at"),
    [
        (Timeframe.M1, ist(2026, 1, 5, 9, 15), ist(2026, 1, 5, 9, 16)),
        (Timeframe.M3, ist(2026, 1, 5, 15, 27), ist(2026, 1, 5, 15, 30)),
        (Timeframe.M15, ist(2026, 1, 5, 15, 15), ist(2026, 1, 5, 15, 30)),
        # The last hourly candle is a 15-minute stub that closes with the session.
        (Timeframe.H1, ist(2026, 1, 5, 15, 15), ist(2026, 1, 5, 15, 30)),
        (Timeframe.H1, ist(2026, 1, 5, 9, 15), ist(2026, 1, 5, 10, 15)),
        # A daily candle closes at the session close of its IST date, whatever its time of day.
        (Timeframe.D1, ist(2026, 1, 5, 0, 0), ist(2026, 1, 5, 15, 30)),
    ],
)
def test_candle_close_time(timeframe, open_at, closes_at):
    c = make_candle(open_at, timeframe=timeframe)
    assert c.close_time == closes_at


def test_is_closed_boundaries():
    c = make_candle(ist(2026, 1, 5, 9, 15))
    assert not c.is_closed(ist(2026, 1, 5, 9, 15, 59))
    assert c.is_closed(ist(2026, 1, 5, 9, 16))
    assert c.is_closed(datetime(2026, 1, 5, 3, 46, tzinfo=UTC))  # 09:16 IST


def test_close_time_requires_timezone():
    c = make_candle(datetime(2026, 1, 5, 9, 15))
    with pytest.raises(ValueError):
        _ = c.close_time
