"""Supertrend with Wilder ATR; +1 bullish, -1 bearish."""
from dataclasses import dataclass
from datetime import datetime
import math
from app.market_data.models import Candle

@dataclass(frozen=True)
class SupertrendPoint:
    timestamp: datetime
    atr: float | None
    value: float | None
    direction: int | None
    bullish: bool | None

def calculate_supertrend(candles: list[Candle], period: int = 10, multiplier: float = 3.0) -> list[SupertrendPoint]:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("multiplier must be finite and greater than zero")
    n = len(candles)
    tr = []
    for i, c in enumerate(candles):
        if i == 0:
            tr.append(c.high-c.low)
        else:
            pc = candles[i-1].close
            tr.append(max(c.high-c.low, abs(c.high-pc), abs(c.low-pc)))
    atr: list[float | None] = [None]*n
    if n >= period:
        current = sum(tr[:period])/period
        atr[period-1] = current
        for i in range(period, n):
            current = (current*(period-1)+tr[i])/period
            atr[i] = current
    upper: list[float | None] = [None]*n
    lower: list[float | None] = [None]*n
    value: list[float | None] = [None]*n
    direction: list[int | None] = [None]*n
    for i, c in enumerate(candles):
        if atr[i] is None:
            continue
        mid = (c.high+c.low)/2
        bu, bl = mid+multiplier*atr[i], mid-multiplier*atr[i]
        pu = upper[i-1] if i else None
        pl = lower[i-1] if i else None
        upper[i] = bu if pu is None or bu < pu or candles[i-1].close > pu else pu
        lower[i] = bl if pl is None or bl > pl or candles[i-1].close < pl else pl
        if i == 0 or direction[i-1] is None:
            direction[i] = 1 if c.close >= mid else -1
        elif value[i-1] == pu:
            direction[i] = 1 if c.close > upper[i] else -1
        else:
            direction[i] = -1 if c.close < lower[i] else 1
        value[i] = lower[i] if direction[i] == 1 else upper[i]
    return [SupertrendPoint(c.timestamp, atr[i], value[i], direction[i],
                            None if direction[i] is None else direction[i] == 1)
            for i, c in enumerate(candles)]
