import pytest

from app.market_data import DataSource, DataSourceKind, InstrumentId
from app.market_data.candle_builder import FiveMinuteCandleBuilder
from tests.fixtures.sample_data import ist

SAMPLE_SOURCE = DataSource(
    name="TEST-PRICE-FEED",
    kind=DataSourceKind.SAMPLE,
)


def make_builder():
    return FiveMinuteCandleBuilder(source=SAMPLE_SOURCE)


def test_first_price_starts_a_provisional_candle():
    builder = make_builder()

    result = builder.add_price(
        InstrumentId.NIFTY50, ist(2026, 1, 5, 9, 15), 100.0
    )

    assert result is None
    candle = builder.current_candle(InstrumentId.NIFTY50)
    assert candle is not None
    assert candle.timestamp == ist(2026, 1, 5, 9, 15)
    assert (candle.open, candle.high, candle.low, candle.close) == (
        100.0, 100.0, 100.0, 100.0
    )
    assert candle.volume is None
    assert candle.source.kind is DataSourceKind.SAMPLE


def test_prices_in_same_slot_update_ohlc():
    builder = make_builder()
    instrument = InstrumentId.NIFTY50

    builder.add_price(instrument, ist(2026, 1, 5, 9, 15), 100.0)
    builder.add_price(instrument, ist(2026, 1, 5, 9, 16), 105.0)
    builder.add_price(instrument, ist(2026, 1, 5, 9, 19, 59), 98.0)

    candle = builder.current_candle(instrument)
    assert candle is not None
    assert (candle.open, candle.high, candle.low, candle.close) == (
        100.0, 105.0, 98.0, 98.0
    )


def test_next_slot_returns_previous_candle():
    builder = make_builder()
    instrument = InstrumentId.NIFTY50

    builder.add_price(instrument, ist(2026, 1, 5, 9, 15), 100.0)
    completed = builder.add_price(
        instrument, ist(2026, 1, 5, 9, 20), 103.0
    )

    assert completed is not None
    assert completed.timestamp == ist(2026, 1, 5, 9, 15)
    assert completed.close == 100.0

    current = builder.current_candle(instrument)
    assert current is not None
    assert current.timestamp == ist(2026, 1, 5, 9, 20)
    assert current.open == 103.0


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_invalid_prices_are_rejected(price):
    builder = make_builder()

    with pytest.raises(ValueError, match="price"):
        builder.add_price(
            InstrumentId.NIFTY50, ist(2026, 1, 5, 9, 15), price
        )


@pytest.mark.parametrize(
    "timestamp",
    [
        ist(2026, 1, 5, 9, 14, 59),
        ist(2026, 1, 5, 15, 30),
        ist(2026, 1, 3, 10, 0),
    ],
    ids=["before-open", "at-session-close", "weekend"],
)
def test_out_of_session_timestamps_are_rejected(timestamp):
    builder = make_builder()

    with pytest.raises(ValueError, match="outside"):
        builder.add_price(InstrumentId.NIFTY50, timestamp, 100.0)


def test_naive_timestamp_is_rejected():
    builder = make_builder()

    with pytest.raises(ValueError, match="timezone-aware"):
        builder.add_price(
            InstrumentId.NIFTY50,
            ist(2026, 1, 5, 9, 15).replace(tzinfo=None),
            100.0,
        )


def test_older_slot_is_rejected():
    builder = make_builder()
    instrument = InstrumentId.NIFTY50

    builder.add_price(instrument, ist(2026, 1, 5, 9, 20), 100.0)

    with pytest.raises(ValueError, match="out-of-order"):
        builder.add_price(instrument, ist(2026, 1, 5, 9, 15), 99.0)


def test_instruments_have_independent_candles():
    builder = make_builder()

    builder.add_price(InstrumentId.NIFTY50, ist(2026, 1, 5, 9, 15), 100.0)
    builder.add_price(InstrumentId.BANKNIFTY, ist(2026, 1, 5, 9, 15), 500.0)

    assert builder.current_candle(InstrumentId.NIFTY50).close == 100.0
    assert builder.current_candle(InstrumentId.BANKNIFTY).close == 500.0

def test_older_update_in_same_slot_is_rejected():
    builder = make_builder()
    instrument = InstrumentId.NIFTY50

    builder.add_price(instrument, ist(2026, 1, 5, 9, 16), 100.0)

    with pytest.raises(ValueError, match="out-of-order"):
        builder.add_price(instrument, ist(2026, 1, 5, 9, 15, 30), 99.0)


def test_finalize_closed_emits_candle_and_rejects_late_tick():
    builder = make_builder()
    instrument = InstrumentId.NIFTY50

    builder.add_price(instrument, ist(2026, 1, 5, 9, 15), 100.0)

    assert builder.finalize_closed(ist(2026, 1, 5, 9, 19, 59)) == []

    completed = builder.finalize_closed(ist(2026, 1, 5, 9, 20))
    assert len(completed) == 1
    assert completed[0].timestamp == ist(2026, 1, 5, 9, 15)
    assert builder.current_candle(instrument) is None

    with pytest.raises(ValueError, match="out-of-order"):
        builder.add_price(instrument, ist(2026, 1, 5, 9, 19), 101.0)
