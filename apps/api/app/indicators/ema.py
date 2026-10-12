"""EMA 9/21/50 trend filter."""
from dataclasses import dataclass
from datetime import datetime
from app.market_data.models import Candle

@dataclass(frozen=True)
class EMAPoint:
    timestamp: datetime
    ema9: float | None
    ema21: float | None
    ema50: float | None
    bullish: bool | None

def _ema(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    if len(values) < period:
        return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    alpha = 2.0 / (period + 1)
    for i in range(period, len(values)):
        current = alpha * values[i] + (1 - alpha) * current
        out[i] = current
    return out

def calculate_ema_trend(candles: list[Candle]) -> list[EMAPoint]:
    closes = [float(c.close) for c in candles]
    arrays = [_ema(closes, p) for p in (9, 21, 50)]
    result = []
    for i, candle in enumerate(candles):
        a, b, c = (values[i] for values in arrays)
        bullish = None if a is None or b is None or c is None else a > b > c
        result.append(EMAPoint(candle.timestamp, a, b, c, bullish))
    return result
