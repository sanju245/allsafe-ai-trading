"""UT Bot Alerts calculation for validated OHLC candles.

This module calculates indicator values only. It does not fetch prices,
place orders, or guarantee profitable signals.

Pass candles in chronological order. For confirmed signals, pass only
closed candles from the caller's validated market-data pipeline.
"""

from dataclasses import dataclass
from enum import StrEnum
import math

from app.market_data.models import Candle


class UTBotSignal(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class UTBotPoint:
    timestamp: object
    source_price: float
    atr: float | None
    trailing_stop: float | None
    position: int
    signal: UTBotSignal | None


def calculate_ut_bot(
    candles: list[Candle],
    *,
    sensitivity: float = 1.0,
    atr_period: int = 10,
    use_heikin_ashi: bool = False,
) -> list[UTBotPoint]:
    """Calculate standard UT Bot trailing stops and crossover signals.

    ATR uses Wilder's RMA, seeded with the simple average of the first
    `atr_period` true-range values. Heikin Ashi mode uses OHLC4 as source.
    """
    if not math.isfinite(sensitivity) or sensitivity <= 0:
        raise ValueError("sensitivity must be finite and greater than zero")
    if isinstance(atr_period, bool) or not isinstance(atr_period, int) or atr_period < 1:
        raise ValueError("atr_period must be a positive integer")

    if not candles:
        return []

    instrument = candles[0].instrument
    timeframe = candles[0].timeframe
    previous_timestamp = None

    sources: list[float] = []
    true_ranges: list[float] = []

    for candle in candles:
        timestamp = candle.timestamp
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("candle timestamps must be timezone-aware")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError("candles must be strictly chronological")
        if candle.instrument != instrument or candle.timeframe != timeframe:
            raise ValueError("all candles must share instrument and timeframe")

        values = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("OHLC values must be finite")
        if candle.low > min(candle.open, candle.close):
            raise ValueError("candle low is above open or close")
        if candle.high < max(candle.open, candle.close):
            raise ValueError("candle high is below open or close")
        if candle.low > candle.high:
            raise ValueError("candle low must not exceed high")

        source = (
            (candle.open + candle.high + candle.low + candle.close) / 4.0
            if use_heikin_ashi
            else candle.close
        )
        sources.append(source)

        if previous_timestamp is None:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[len(sources) - 2].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )

        true_ranges.append(true_range)
        previous_timestamp = timestamp

    atr_values: list[float | None] = [None] * len(candles)
    trailing_stops: list[float | None] = [None] * len(candles)
    positions = [0] * len(candles)
    signals: list[UTBotSignal | None] = [None] * len(candles)

    if len(candles) >= atr_period:
        atr = sum(true_ranges[:atr_period]) / atr_period
        atr_values[atr_period - 1] = atr

        for i in range(atr_period, len(candles)):
            atr = (
                atr * (atr_period - 1) + true_ranges[i]
            ) / atr_period
            atr_values[i] = atr

    for i, source in enumerate(sources):
        current_atr = atr_values[i]
        if current_atr is None:
            continue

        loss = sensitivity * current_atr
        previous_stop = trailing_stops[i - 1] if i > 0 else None
        previous_source = sources[i - 1] if i > 0 else None

        if previous_stop is None or previous_source is None:
            stop = source - loss if source > 0 else source + loss
        elif source > previous_stop and previous_source > previous_stop:
            stop = max(previous_stop, source - loss)
        elif source < previous_stop and previous_source < previous_stop:
            stop = min(previous_stop, source + loss)
        elif source > previous_stop:
            stop = source - loss
        else:
            stop = source + loss

        trailing_stops[i] = stop
        previous_position = positions[i - 1] if i > 0 else 0
        positions[i] = previous_position

        if previous_stop is not None and previous_source is not None:
            crossed_up = previous_source <= previous_stop and source > stop
            crossed_down = previous_source >= previous_stop and source < stop

            if crossed_up:
                signals[i] = UTBotSignal.BUY
                positions[i] = 1
            elif crossed_down:
                signals[i] = UTBotSignal.SELL
                positions[i] = -1

    return [
        UTBotPoint(
            timestamp=candle.timestamp,
            source_price=sources[i],
            atr=atr_values[i],
            trailing_stop=trailing_stops[i],
            position=positions[i],
            signal=signals[i],
        )
        for i, candle in enumerate(candles)
    ]
