"""Five-indicator decision engine with a dedicated 15-minute index setup."""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from app.indicators.ema import calculate_ema_trend
from app.indicators.macd import calculate_macd
from app.indicators.rsi import calculate_rsi
from app.indicators.supertrend import calculate_supertrend
from app.indicators.ut_bot import UTBotSignal, calculate_ut_bot
from app.market_data.models import Candle
from app.market_data.sessions import to_ist
from app.market_data.timeframes import Timeframe


class TradeDecision(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class OpeningRangeState(StrEnum):
    MISSING = "MISSING"
    SET = "SET"
    INSIDE = "INSIDE"
    ABOVE_HIGH = "ABOVE_HIGH"
    BELOW_LOW = "BELOW_LOW"


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
    opening_range_state: OpeningRangeState | None = None
    ut_bot_position: int | None = None


def _has_warmup(ut, ema, rsi, macd, supertrend) -> bool:
    return (
        ut.atr is None
        or ut.trailing_stop is None
        or ema.ema9 is None
        or ema.ema21 is None
        or ema.ema50 is None
        or rsi.rsi is None
        or macd.histogram is None
        or supertrend.direction is None
    )


def _directional_confirmation(point, direction: int) -> bool:
    return point.bullish is True if direction == 1 else point.bearish is True


def calculate_decisions(
    candles: list[Candle],
    *,
    sensitivity: float = 1.0,
    atr_period: int = 10,
    use_heikin_ashi: bool = False,
    rsi_period: int = 14,
    supertrend_period: int = 10,
    supertrend_multiplier: float = 3.0,
) -> list[DecisionPoint]:
    """Evaluate confirmed candles; no orders are placed.

    Fifteen-minute candles use one opening-range breakout attempt per NSE session.
    Other timeframes retain the UT Bot crossover trigger and require all four
    confirmations to point in the same direction.
    """
    if not candles:
        return []

    ut_points = calculate_ut_bot(
        candles,
        sensitivity=sensitivity,
        atr_period=atr_period,
        use_heikin_ashi=use_heikin_ashi,
    )
    ema_points = calculate_ema_trend(candles)
    rsi_points = calculate_rsi(candles, rsi_period)
    macd_points = calculate_macd(candles)
    supertrend_points = calculate_supertrend(
        candles, supertrend_period, supertrend_multiplier
    )

    is_15m = candles[0].timeframe is Timeframe.M15
    opening_ranges: dict[date, tuple[int, float, float]] = {}
    if is_15m:
        for index, candle in enumerate(candles):
            local = to_ist(candle.timestamp)
            if local.time() == time(9, 15):
                opening_ranges[local.date()] = (index, candle.high, candle.low)

    attempted_sessions: set[date] = set()
    decisions: list[DecisionPoint] = []

    for index, candle in enumerate(candles):
        ut = ut_points[index]
        ema = ema_points[index]
        rsi = rsi_points[index]
        macd = macd_points[index]
        supertrend = supertrend_points[index]
        filters = (ema.bullish, rsi.bullish, macd.bullish, supertrend.bullish)
        local = to_ist(candle.timestamp)

        opening_reason = "Waiting for the first confirmed close outside the 09:15 opening range."
        opening_direction = 0
        opening_range_state = None
        if is_15m:
            session = local.date()
            opening = opening_ranges.get(session)
            if opening is None:
                opening_range_state = OpeningRangeState.MISSING
                opening_reason = "No 09:15 opening candle; opening-range signals are disabled for this session."
            elif index <= opening[0]:
                opening_range_state = OpeningRangeState.SET
            else:
                opening_high, opening_low = opening[1], opening[2]
                if candle.close > opening_high:
                    opening_range_state = OpeningRangeState.ABOVE_HIGH
                elif candle.close < opening_low:
                    opening_range_state = OpeningRangeState.BELOW_LOW
                else:
                    opening_range_state = OpeningRangeState.INSIDE

                if local.time() > time(14, 15):
                    opening_reason = "This candle opened after the last eligible slot at 14:15 IST."
                elif session in attempted_sessions:
                    opening_reason = "The first opening-range breakout for this session was already evaluated."
                elif opening_range_state is not OpeningRangeState.INSIDE:
                    opening_direction = 1 if opening_range_state is OpeningRangeState.ABOVE_HIGH else -1
                    # Consume the first range break even if a gate is neutral or
                    # warming up; later breaks are not a second attempt.
                    attempted_sessions.add(session)

        if _has_warmup(ut, ema, rsi, macd, supertrend):
            decision = TradeDecision.DATA_UNAVAILABLE
            reason = "Signal checks are warming up: insufficient candle history."
        elif is_15m:
            if not opening_direction:
                decision = TradeDecision.WAIT
                reason = opening_reason
            else:
                side = TradeDecision.BUY if opening_direction == 1 else TradeDecision.SELL
                momentum_aligned = (
                    _directional_confirmation(rsi, opening_direction)
                    or _directional_confirmation(macd, opening_direction)
                )
                checks = (
                    ("Trend position", ut.position == opening_direction),
                    ("Trend check A", _directional_confirmation(ema, opening_direction)),
                    ("Trend check B", _directional_confirmation(supertrend, opening_direction)),
                    ("Momentum checks A and B", momentum_aligned),
                )
                blocked_by = [name for name, aligned in checks if not aligned]
                if blocked_by:
                    decision = TradeDecision.WAIT
                    reason = f"Opening-range {side} breakout filtered. {', '.join(blocked_by)} did not confirm."
                else:
                    decision = side
                    reason = f"15-minute opening-range {side}; trend and momentum checks confirm."
        elif ut.signal == UTBotSignal.BUY and all(value is True for value in filters):
            decision = TradeDecision.BUY
            reason = "BUY signal confirmed by all required trend and momentum checks."
        elif ut.signal == UTBotSignal.SELL and all(value is False for value in filters):
            decision = TradeDecision.SELL
            reason = "SELL signal confirmed by all required trend and momentum checks."
        else:
            decision = TradeDecision.WAIT
            reason = "No confirmed trigger with all directional checks aligned."

        decisions.append(
            DecisionPoint(
                timestamp=candle.timestamp,
                decision=decision,
                ut_bot_signal=ut.signal,
                ema_bullish=ema.bullish,
                rsi_bullish=rsi.bullish,
                macd_bullish=macd.bullish,
                supertrend_bullish=supertrend.bullish,
                reason=reason,
                opening_range_state=opening_range_state,
                ut_bot_position=ut.position if ut.trailing_stop is not None else None,
            )
        )

    return decisions
