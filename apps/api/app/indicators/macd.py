"""MACD 12/26/9 with SMA-seeded EMA warm-up."""
from dataclasses import dataclass
from datetime import datetime
from app.market_data.models import Candle

@dataclass(frozen=True)
class MACDPoint:
    timestamp: datetime
    macd: float | None
    signal_line: float | None
    histogram: float | None
    bullish: bool | None

def _ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    current = sum(values[:period])/period
    out[period-1] = current
    alpha = 2/(period+1)
    for i in range(period, len(values)):
        current = alpha*values[i] + (1-alpha)*current
        out[i] = current
    return out

def calculate_macd(candles: list[Candle], fast: int = 12, slow: int = 26, signal: int = 9) -> list[MACDPoint]:
    if any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in (fast, slow, signal)) or fast >= slow:
        raise ValueError("periods must be positive integers and fast must be less than slow")
    closes = [float(c.close) for c in candles]
    ef, es = _ema(closes, fast), _ema(closes, slow)
    raw = [None if ef[i] is None or es[i] is None else ef[i]-es[i] for i in range(len(candles))]
    indexes = [i for i, v in enumerate(raw) if v is not None]
    sig = [None] * len(candles)
    if indexes:
        compact = _ema([raw[i] for i in indexes], signal)
        for j, i in enumerate(indexes):
            sig[i] = compact[j]
    out = []
    for i, candle in enumerate(candles):
        m, s = raw[i], sig[i]
        hist = None if m is None or s is None else m-s
        bullish = None if hist is None else m > s and hist > 0
        out.append(MACDPoint(candle.timestamp, m, s, hist, bullish))
    return out
