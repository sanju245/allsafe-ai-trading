import pytest

from app.indicators.ut_bot import UTBotSignal, calculate_ut_bot
from app.market_data import Candle, DataSource, DataSourceKind, InstrumentId, Timeframe
from tests.fixtures.sample_data import ist

SOURCE = DataSource(name="TEST-SAMPLE", kind=DataSourceKind.SAMPLE)


def candles_from_closes(closes):
    result = []
    for i, close in enumerate(closes):
        result.append(
            Candle(
                timestamp=ist(2026, 1, 5, 9, 15 + i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                instrument=InstrumentId.NIFTY50,
                timeframe=Timeframe.M1,
                source=SOURCE,
            )
        )
    return result


def test_atr_warmup_and_output_length():
    candles = candles_from_closes([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    points = calculate_ut_bot(candles, atr_period=10)

    assert len(points) == len(candles)
    assert all(point.atr is None for point in points[:9])
    assert points[9].atr is not None
    assert points[9].trailing_stop is not None


def test_default_parameters_work():
    points = calculate_ut_bot(candles_from_closes(range(100, 120)))
    assert len(points) == 20
    assert all(point.position in (-1, 0, 1) for point in points)


def test_heikin_ashi_source_uses_ohlc4():
    candle = candles_from_closes([100])[0]
    point = calculate_ut_bot([candle], atr_period=1, use_heikin_ashi=True)[0]

    assert point.source_price == pytest.approx(
        (candle.open + candle.high + candle.low + candle.close) / 4
    )


@pytest.mark.parametrize(
    ("sensitivity", "atr_period"),
    [(0, 10), (-1, 10), (float("nan"), 10), (1, 0), (1, 1.5)],
)
def test_invalid_parameters_are_rejected(sensitivity, atr_period):
    with pytest.raises(ValueError):
        calculate_ut_bot(
            candles_from_closes([100, 101]),
            sensitivity=sensitivity,
            atr_period=atr_period,
        )


def test_unordered_candles_are_rejected():
    candles = candles_from_closes([100, 101, 102])
    candles[1] = candles[0]

    with pytest.raises(ValueError, match="chronological"):
        calculate_ut_bot(candles)


def test_signal_values_are_only_buy_sell_or_none():
    points = calculate_ut_bot(candles_from_closes(
        [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
         110, 111, 112, 113, 114, 115, 116, 117, 118, 119]
    ))

    assert all(
        point.signal is None or point.signal in (UTBotSignal.BUY, UTBotSignal.SELL)
        for point in points
    )
