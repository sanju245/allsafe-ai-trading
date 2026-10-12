"""RSI 14 using Wilder smoothing."""
from dataclasses import dataclass
from datetime import datetime
from app.market_data.models import Candle

@dataclass(frozen=True)
class RSIPoint:
    timestamp: datetime
    rsi: float | None
    bullish: bool | None

def calculate_rsi(candles: list[Candle], period: int = 14) -> list[RSIPoint]:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    closes = [float(c.close) for c in candles]
    values: list[float | None] = [None] * len(closes)
    if len(closes) > period:
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(x, 0.0) for x in changes]
        losses = [max(-x, 0.0) for x in changes]
        avg_gain, avg_loss = sum(gains[:period])/period, sum(losses[:period])/period
        def calc(g, l):
            if l == 0:
                return 100.0 if g > 0 else 50.0
            if g == 0:
                return 0.0
            return 100.0 - 100.0/(1.0 + g/l)
        values[period] = calc(avg_gain, avg_loss)
        for i in range(period + 1, len(closes)):
            j = i - 1
            avg_gain = (avg_gain*(period-1) + gains[j])/period
            avg_loss = (avg_loss*(period-1) + losses[j])/period
            values[i] = calc(avg_gain, avg_loss)
    return [RSIPoint(c.timestamp, values[i], None if values[i] is None else values[i] > 50)
            for i, c in enumerate(candles)]
