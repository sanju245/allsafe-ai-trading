"""Five-indicator unanimous signal decision engine."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from app.market_data.models import Candle
from app.indicators.ut_bot import UTBotPoint, UTBotSignal, calculate_ut_bot
from app.indicators.ema import calculate_ema_trend
from app.indicators.rsi import calculate_rsi
from app.indicators.macd import calculate_macd
from app.indicators.supertrend import calculate_supertrend

class TradeDecision(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"

@dataclass(frozen=True)
class DecisionPoint:
    timestamp: datetime
    decision: TradeDecision
    ut_bot_signal: UTBotSignal | None
    ema_bullish: bool | None
    rsi_bullish: bool | None
    macd_bullish: bool | None
    supertrend_bullish: bool | None
    reason: str

def calculate_decisions(candles: list[Candle], *, sensitivity: float = 1.0,
                        atr_period: int = 10, use_heikin_ashi: bool = False,
                        rsi_period: int = 14, supertrend_period: int = 10,
                        supertrend_multiplier: float = 3.0) -> list[DecisionPoint]:
    """Caller must pass validated, chronological, closed candles. No orders are placed."""
    if not candles:
        return []
    ut = calculate_ut_bot(candles, sensitivity=sensitivity, atr_period=atr_period,
                          use_heikin_ashi=use_heikin_ashi)
    ema, rsi, macd = calculate_ema_trend(candles), calculate_rsi(candles, rsi_period), calculate_macd(candles)
    st = calculate_supertrend(candles, supertrend_period, supertrend_multiplier)
    out = []
    for i, candle in enumerate(candles):
        filters = (ema[i].bullish, rsi[i].bullish, macd[i].bullish, st[i].bullish)
        trigger = ut[i].signal
        if any(v is None for v in filters) or ut[i].atr is None or ut[i].trailing_stop is None:
            decision, reason = TradeDecision.DATA_UNAVAILABLE, "Indicator warm-up: insufficient candle history."
        elif trigger == UTBotSignal.BUY and all(v is True for v in filters):
            decision, reason = TradeDecision.BUY, "UT Bot BUY; all four confirmation indicators bullish."
        elif trigger == UTBotSignal.SELL and all(v is False for v in filters):
            decision, reason = TradeDecision.SELL, "UT Bot SELL; all four confirmation indicators bearish."
        else:
            decision, reason = TradeDecision.WAIT, "No unanimous confirmed signal on this candle."
        out.append(DecisionPoint(candle.timestamp, decision, trigger, *filters, reason))
    return out
