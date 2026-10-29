"""Tests for live index update validation, 5m IST session candle aggregation,
forming vs confirmed separation, incomplete intervals, and explicit gap tracking.
"""

from datetime import datetime, timedelta

import pytest

from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import (
    LiveSessionAggregator,
    groww_symbol_for,
    resolve_instrument_symbol,
)
from app.market_data.live_models import (
    TickRejectionReason,
)
from tests.fixtures.sample_data import ist


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NIFTY50", InstrumentId.NIFTY50),
        ("NIFTY 50", InstrumentId.NIFTY50),
        ("NIFTY", InstrumentId.NIFTY50),
        ("NSE-NIFTY", InstrumentId.NIFTY50),
        ("NSE_NIFTY", InstrumentId.NIFTY50),
        ("BANKNIFTY", InstrumentId.BANKNIFTY),
        ("BANK NIFTY", InstrumentId.BANKNIFTY),
        ("NIFTY BANK", InstrumentId.BANKNIFTY),
        ("NSE-BANKNIFTY", InstrumentId.BANKNIFTY),
        ("NSE_BANKNIFTY", InstrumentId.BANKNIFTY),
    ],
)
def test_groww_symbol_resolution(raw, expected):
    assert resolve_instrument_symbol(raw) == expected


def test_groww_symbol_for_instrument():
    assert groww_symbol_for(InstrumentId.NIFTY50) == "NSE-NIFTY"
    assert groww_symbol_for(InstrumentId.BANKNIFTY) == "NSE-BANKNIFTY"


def test_missing_and_naive_timestamps_rejected_without_inventing_time():
    agg = LiveSessionAggregator()
    now = ist(2026, 1, 5, 9, 15, 5)

    r_missing = agg.process_tick(symbol="NSE-NIFTY", price=24500.0, timestamp=None, as_of=now)
    assert not r_missing.accepted
    assert r_missing.rejection.reason == TickRejectionReason.MISSING_TIMESTAMP
    assert agg.get_latest_quote(InstrumentId.NIFTY50) is None

    r_naive = agg.process_tick(
        symbol="NSE-NIFTY",
        price=24500.0,
        timestamp=datetime(2026, 1, 5, 9, 15, 5),
        as_of=now,
    )
    assert not r_naive.accepted
    assert r_naive.rejection.reason == TickRejectionReason.NAIVE_TIMESTAMP


@pytest.mark.parametrize("bad_price", [0.0, -10.5, float("nan"), float("inf"), float("-inf"), True])
def test_invalid_prices_rejected(bad_price):
    agg = LiveSessionAggregator()
    ts = ist(2026, 1, 5, 9, 15, 1)
    r = agg.process_tick(symbol="NIFTY50", price=bad_price, timestamp=ts, as_of=ts)
    assert not r.accepted
    assert r.rejection.reason == TickRejectionReason.INVALID_PRICE


@pytest.mark.parametrize(
    "out_ts",
    [
        ist(2026, 1, 5, 9, 14, 59),
        ist(2026, 1, 5, 15, 30, 0),
        ist(2026, 1, 3, 10, 0, 0),
        ist(2026, 1, 4, 11, 0, 0),
    ],
)
def test_outside_session_updates_rejected(out_ts):
    agg = LiveSessionAggregator()
    r = agg.process_tick(symbol="NIFTY50", price=24500.0, timestamp=out_ts, as_of=out_ts)
    assert not r.accepted
    assert r.rejection.reason == TickRejectionReason.OUTSIDE_SESSION


def test_duplicate_future_stale_and_out_of_order_updates_rejected():
    agg = LiveSessionAggregator(max_future_skew_seconds=5.0, max_staleness_seconds=60.0)
    t1 = ist(2026, 1, 5, 9, 15, 10)
    assert agg.process_tick(symbol="NIFTY50", price=24500.0, timestamp=t1, as_of=t1).accepted

    # Duplicate
    r_dup = agg.process_tick(symbol="NIFTY50", price=24500.0, timestamp=t1, as_of=t1)
    assert not r_dup.accepted and r_dup.rejection.reason == TickRejectionReason.DUPLICATE_TICK

    # Out of order
    r_ooo = agg.process_tick(symbol="NIFTY50", price=24510.0, timestamp=ist(2026, 1, 5, 9, 15, 5), as_of=t1)
    assert not r_ooo.accepted and r_ooo.rejection.reason == TickRejectionReason.OUT_OF_ORDER_TICK

    # Future
    r_fut = agg.process_tick(symbol="NIFTY50", price=24510.0, timestamp=t1 + timedelta(seconds=10), as_of=t1)
    assert not r_fut.accepted and r_fut.rejection.reason == TickRejectionReason.FUTURE_TIMESTAMP

    # Stale
    t_later = ist(2026, 1, 5, 9, 18, 0)
    r_stale = agg.process_tick(symbol="NIFTY50", price=24510.0, timestamp=t_later - timedelta(seconds=70), as_of=t_later)
    assert not r_stale.accepted and r_stale.rejection.reason == TickRejectionReason.STALE_TICK


def test_forming_vs_confirmed_separation_and_missing_interval_tracking():
    agg = LiveSessionAggregator()
    agg.process_tick(symbol="NIFTY50", price=24500.0, timestamp=ist(2026, 1, 5, 9, 15, 2))
    agg.process_tick(symbol="NIFTY50", price=24530.0, timestamp=ist(2026, 1, 5, 9, 17, 0))
    agg.process_tick(symbol="NIFTY50", price=24490.0, timestamp=ist(2026, 1, 5, 9, 19, 30))

    assert agg.get_confirmed_candles(InstrumentId.NIFTY50) == []
    forming = agg.get_forming_candle(InstrumentId.NIFTY50)
    assert forming is not None and forming.is_forming is True and forming.is_confirmed is False
    assert forming.volume is None

    # Jump to 09:30 (skipping 09:20 and 09:25)
    rollover = agg.process_tick(symbol="NIFTY50", price=24550.0, timestamp=ist(2026, 1, 5, 9, 30, 5))
    assert rollover.confirmed_candle is not None
    assert rollover.confirmed_candle.timestamp == ist(2026, 1, 5, 9, 15)
    assert rollover.missing_interval is not None
    assert rollover.missing_interval.missing_slot_count == 2
    assert len(agg.get_confirmed_candles(InstrumentId.NIFTY50)) == 1
