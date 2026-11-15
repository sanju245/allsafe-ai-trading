"""Fixed, causal research strategies evaluated only on caller-supplied closed M5 bars.

These rules are research hypotheses, not claims of improved returns. No prices are
fetched and no orders are placed. A point's timestamp is its candle OPEN time;
its signal becomes available only when that candle closes. Outcomes and future
bars never enter a rule. Each strategy has its own 30-minute elapsed-time cooldown.
Consensus uses the constituent raw setups before their independent cooldowns.

Variants frozen before outcome evaluation:
* Wilder DMI14 uses 14 actual high/low transitions (bars 1..14), then RMA;
  ADX14 seeds from the first 14 DX values (first ADX at zero-based index 27).
  Zero true range or zero DI sum gives zero directional movement/DX.
* Bollinger20 uses a close SMA and population standard deviation times two.
* Stochastic is FAST K14, D=SMA3(K); a zero high-low range gives neutral K=50.
* Intraday missing bars reset all indicator history and cooldowns. Normal overnight
  gaps preserve history and their price gaps enter true range. Special sessions
  outside the regular 09:15..15:30 IST grid are rejected.
* M15 EMA9/21 uses only complete, session-aligned groups of three M5 candles.
  The third candle's close makes that M15 value available; incomplete groups are
  discarded. No unfinished M15 value is projected into its first two candles.

Primary formula references (rules/thresholds below are explicitly our hypotheses):
https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/
https://www.tradingview.com/support/solutions/43000502250-directional-movement-dmi/
https://www.tradingview.com/support/solutions/43000502253-donchian-channels-dc/
https://www.bollingerbands.com/bollinger-band-rules
https://www.fidelity.com/viewpoints/active-investor/trading-with-stochastics
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import fmean, pstdev

from app.indicators.decision import TradeDecision, calculate_decisions
from app.indicators.ema import _ema
from app.indicators.ut_bot import UTBotSignal, calculate_ut_bot
from app.market_data.models import Candle
from app.market_data.sessions import IST
from app.market_data.timeframes import Timeframe

STRATEGY_IDS = (
    "adx_confirmation",
    "ema_pullback",
    "donchian_breakout",
    "bollinger_reentry",
    "stochastic_reversal",
    "higher_timeframe_ut",
    "regime_consensus",
)
STRATEGY_LABELS = {
    "adx_confirmation": "ADX filtered five-indicator confirmation",
    "ema_pullback": "EMA trend pullback",
    "donchian_breakout": "Donchian trend breakout",
    "bollinger_reentry": "Bollinger range reentry",
    "stochastic_reversal": "Stochastic range reversal",
    "higher_timeframe_ut": "Closed M15 confirmed UT Bot",
    "regime_consensus": "Regime-specific setup consensus",
}
COOLDOWN = timedelta(minutes=30)
M5 = timedelta(minutes=5)


@dataclass(frozen=True)
class StrategyPoint:
    timestamp: datetime
    signals: dict[str, int]
    adx: float | None
    plus_di: float | None
    minus_di: float | None
    regime: str
    reason: str


@dataclass(frozen=True)
class DMIPoint:
    adx: float | None
    plus_di: float | None
    minus_di: float | None


def _adx_dmi(candles: list[Candle], period: int = 14) -> list[DMIPoint]:
    """Wilder smoothing; private helper requires already validated candles."""
    n = len(candles)
    plus: list[float | None] = [None] * n
    minus: list[float | None] = [None] * n
    dx: list[float | None] = [None] * n
    adx: list[float | None] = [None] * n
    trs, ups, downs = [], [], []
    for previous, current in zip(candles, candles[1:]):
        up, down = current.high - previous.high, previous.low - current.low
        ups.append(up if up > 0 and up > down else 0.0)
        downs.append(down if down > 0 and down > up else 0.0)
        trs.append(max(current.high - current.low,
                       abs(current.high - previous.close),
                       abs(current.low - previous.close)))
    if n <= period:
        return [DMIPoint(None, None, None) for _ in candles]
    atr, p_dm, m_dm = (fmean(values[:period]) for values in (trs, ups, downs))
    for i in range(period, n):
        if i > period:
            atr = (atr * (period - 1) + trs[i - 1]) / period
            p_dm = (p_dm * (period - 1) + ups[i - 1]) / period
            m_dm = (m_dm * (period - 1) + downs[i - 1]) / period
        p, m = (100 * p_dm / atr, 100 * m_dm / atr) if atr else (0.0, 0.0)
        plus[i], minus[i] = p, m
        dx[i] = 100 * abs(p - m) / (p + m) if p + m else 0.0
    seed = 2 * period - 1
    if n > seed:
        current_adx = fmean(dx[period:seed + 1])
        adx[seed] = current_adx
        for i in range(seed + 1, n):
            current_adx = (current_adx * (period - 1) + dx[i]) / period
            adx[i] = current_adx
    return [DMIPoint(adx[i], plus[i], minus[i]) for i in range(n)]


def _bollinger(candles: list[Candle], period: int = 20) -> list[tuple[float, float] | None]:
    closes = [c.close for c in candles]
    result = []
    for i in range(len(candles)):
        if i < period - 1:
            result.append(None)
        else:
            window = closes[i - period + 1:i + 1]
            mean, spread = fmean(window), 2 * pstdev(window)
            result.append((mean - spread, mean + spread))
    return result


def _stochastic(candles: list[Candle], period: int = 14) -> list[tuple[float | None, float | None]]:
    k_values: list[float | None] = [None] * len(candles)
    result = []
    for i, candle in enumerate(candles):
        if i >= period - 1:
            window = candles[i - period + 1:i + 1]
            high, low = max(c.high for c in window), min(c.low for c in window)
            k_values[i] = 100 * (candle.close - low) / (high - low) if high > low else 50.0
        d = fmean(k_values[i - 2:i + 1]) if i >= period + 1 else None
        result.append((k_values[i], d))
    return result


def _higher_timeframe_directions(candles: list[Candle]) -> list[int]:
    """Return latest fully closed M15 EMA direction known at each M5 close."""
    complete, completion_indexes = [], []
    pending: list[Candle] = []
    for i, candle in enumerate(candles):
        local = candle.timestamp.astimezone(IST)
        offset = (local.hour * 60 + local.minute - (9 * 60 + 15)) % 15
        if offset == 0:
            pending = [candle]
        elif pending and candle.timestamp - pending[-1].timestamp == M5:
            pending.append(candle)
        else:
            pending = []
        if offset == 10 and len(pending) == 3:
            first, _, last = pending
            complete.append(Candle(timestamp=first.timestamp, open=first.open,
                                   high=max(c.high for c in pending), low=min(c.low for c in pending),
                                   close=last.close, volume=None, instrument=first.instrument,
                                   timeframe=Timeframe.M15, source=last.source))
            completion_indexes.append(i)
            pending = []
    fast = _ema([c.close for c in complete], 9)
    slow = _ema([c.close for c in complete], 21)
    updates = {}
    for j, i in enumerate(completion_indexes):
        a, b = fast[j], slow[j]
        updates[i] = 0 if a is None or b is None else 1 if a > b else -1 if a < b else 0
    result, direction = [], 0
    for i in range(len(candles)):
        if i in updates:
            direction = updates[i]
        result.append(direction)
    return result


def _validate_and_split(candles: list[Candle]) -> list[list[Candle]]:
    segments: list[list[Candle]] = []
    previous = None
    for candle in candles:
        if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
            raise ValueError("candle timestamps must be timezone-aware")
        local = candle.timestamp.astimezone(IST)
        minute = local.hour * 60 + local.minute
        if (candle.timeframe != Timeframe.M5 or local.weekday() > 4
                or not 555 <= minute < 930 or (minute - 555) % 5
                or local.second or local.microsecond):
            raise ValueError("research strategies require regular-session, grid-aligned M5 candles")
        values = (candle.open, candle.high, candle.low, candle.close)
        if (not all(math.isfinite(v) and v > 0 for v in values)
                or candle.high < max(candle.open, candle.close)
                or candle.low > min(candle.open, candle.close) or candle.low > candle.high):
            raise ValueError("candle OHLC values must be finite, positive and consistent")
        if previous is not None:
            if candle.timestamp <= previous.timestamp:
                raise ValueError("candles must be strictly chronological")
            if candle.instrument != previous.instrument:
                raise ValueError("candles must share an instrument")
            same_day = local.date() == previous.timestamp.astimezone(IST).date()
            if same_day and candle.timestamp - previous.timestamp != M5:
                segments.append([])
        if not segments:
            segments.append([])
        segments[-1].append(candle)
        previous = candle
    return segments


def _apply_cooldown(raw: dict[str, int], at: datetime,
                    last: dict[str, datetime]) -> dict[str, int]:
    signals = dict.fromkeys(STRATEGY_IDS, 0)
    for strategy, direction in raw.items():
        if direction and (strategy not in last or at - last[strategy] >= COOLDOWN):
            signals[strategy] = direction
            last[strategy] = at
    return signals


def _segment_points(candles: list[Candle]) -> list[StrategyPoint]:
    dmi, bands, stochastic = _adx_dmi(candles), _bollinger(candles), _stochastic(candles)
    decisions, ut = calculate_decisions(candles), calculate_ut_bot(candles)
    closes = [c.close for c in candles]
    ema21, ema50 = _ema(closes, 21), _ema(closes, 50)
    higher = _higher_timeframe_directions(candles)
    points, last_signal = [], {}
    for i, candle in enumerate(candles):
        p = dmi[i]
        trend = p.adx is not None and p.adx >= 25
        ranging = p.adx is not None and p.adx < 20
        regime = "warming" if p.adx is None else "trend" if trend else "range" if ranging else "transition"
        di = (1 if p.plus_di > p.minus_di else -1 if p.minus_di > p.plus_di else 0
              ) if p.plus_di is not None and p.minus_di is not None else 0
        raw = dict.fromkeys(STRATEGY_IDS, 0)
        decision = decisions[i].decision
        directional_decision = 1 if decision == TradeDecision.BUY else -1 if decision == TradeDecision.SELL else 0
        if trend and directional_decision and directional_decision == di:
            raw["adx_confirmation"] = directional_decision
        if trend and i > 0 and ema50[i] is not None:
            if (di == 1 and ema21[i] > ema50[i]
                    and closes[i - 1] <= ema21[i - 1] and candle.close > ema21[i]):
                raw["ema_pullback"] = 1
            elif (di == -1 and ema21[i] < ema50[i]
                  and closes[i - 1] >= ema21[i - 1] and candle.close < ema21[i]):
                raw["ema_pullback"] = -1
        if trend and i >= 20:
            preceding = candles[i - 20:i]
            if di == 1 and candle.close > max(c.high for c in preceding):
                raw["donchian_breakout"] = 1
            elif di == -1 and candle.close < min(c.low for c in preceding):
                raw["donchian_breakout"] = -1
        if ranging and i > 0 and bands[i] is not None and bands[i - 1] is not None:
            previous_lower, previous_upper = bands[i - 1]
            lower, upper = bands[i]
            if closes[i - 1] < previous_lower and lower < candle.close <= upper:
                raw["bollinger_reentry"] = 1
            elif closes[i - 1] > previous_upper and lower <= candle.close < upper:
                raw["bollinger_reentry"] = -1
        k, d = stochastic[i]
        prior_k = stochastic[i - 1][0] if i else None
        if ranging and k is not None and d is not None and prior_k is not None:
            if prior_k <= 20 and k > 20 and k > d:
                raw["stochastic_reversal"] = 1
            elif prior_k >= 80 and k < 80 and k < d:
                raw["stochastic_reversal"] = -1
        ut_direction = 1 if ut[i].signal == UTBotSignal.BUY else -1 if ut[i].signal == UTBotSignal.SELL else 0
        if trend and ut_direction and ut_direction == di == higher[i]:
            raw["higher_timeframe_ut"] = ut_direction
        if trend:
            votes = [raw[name] for name in ("ema_pullback", "donchian_breakout", "higher_timeframe_ut")]
            if votes.count(1) >= 2 and -1 not in votes:
                raw["regime_consensus"] = 1
            elif votes.count(-1) >= 2 and 1 not in votes:
                raw["regime_consensus"] = -1
        elif ranging and raw["bollinger_reentry"] == raw["stochastic_reversal"] != 0:
            raw["regime_consensus"] = raw["bollinger_reentry"]
        signals = _apply_cooldown(raw, candle.timestamp + M5, last_signal)
        points.append(StrategyPoint(candle.timestamp, signals, p.adx, p.plus_di,
                                    p.minus_di, regime,
                                    "Research setups at confirmed close; independent 30-minute cooldowns."))
    return points


def calculate_strategy_points(candles: list[Candle]) -> list[StrategyPoint]:
    """Calculate frozen research setups; caller must supply only CLOSED candles."""
    return [point for segment in _validate_and_split(candles) for point in _segment_points(segment)]
