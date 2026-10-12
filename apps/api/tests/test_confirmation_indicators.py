
from datetime import timedelta

import pytest

from app.indicators.ema import calculate_ema_trend
from app.indicators.rsi import calculate_rsi
from app.indicators.macd import calculate_macd
from app.indicators.supertrend import calculate_supertrend
from app.indicators.decision import TradeDecision, calculate_decisions
from app.market_data import Candle, DataSource, DataSourceKind, InstrumentId, Timeframe
from tests.fixtures.sample_data import ist


SOURCE = DataSource(name="TEST-SAMPLE", kind=DataSourceKind.SAMPLE)


def candles_from_closes(closes):
    """Create test candles with valid, chronological timestamps."""
    base = ist(2026, 1, 5, 9, 15)

    return [
        Candle(
            timestamp=base + timedelta(minutes=i),
            open=float(value) - 0.5,
            high=float(value) + 1,
            low=float(value) - 1,
            close=float(value),
            instrument=InstrumentId.NIFTY50,
            timeframe=Timeframe.M1,
            source=SOURCE,
        )
        for i, value in enumerate(closes)
    ]


def test_ema_warmup():
    # EMA 50 needs at least 50 candles to produce its first value.
    points = calculate_ema_trend(candles_from_closes(range(100, 160)))

    assert len(points) == 60
    assert all(point.ema50 is None for point in points[:49])
    assert points[49].ema50 is not None


def test_rsi_warmup_and_monotonic_rise():
    points = calculate_rsi(candles_from_closes(range(100, 130)))

    assert points[13].rsi is None
    assert points[14].rsi == pytest.approx(100)
    assert points[-1].bullish is True


def test_macd_warmup():
    points = calculate_macd(candles_from_closes(range(100, 150)))

    assert points[24].macd is None
    assert points[-1].histogram is not None


def test_supertrend_warmup():
    points = calculate_supertrend(candles_from_closes(range(100, 130)))

    assert all(point.direction is None for point in points[:9])
    assert points[9].direction in (-1, 1)


def test_decision_never_signals_during_warmup():
    points = calculate_decisions(candles_from_closes(range(100, 130)))

    assert points[0].decision == TradeDecision.DATA_UNAVAILABLE
    assert all(point.decision in set(TradeDecision) for point in points)


def test_empty_inputs():
    assert calculate_ema_trend([]) == []
    assert calculate_rsi([]) == []
    assert calculate_macd([]) == []
    assert calculate_supertrend([]) == []
    assert calculate_decisions([]) == []
