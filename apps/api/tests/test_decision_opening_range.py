from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.indicators import decision as decision_module
from app.indicators.decision import OpeningRangeState, TradeDecision, calculate_decisions
from app.indicators.ut_bot import UTBotSignal
from app.market_data import Candle, DataSource, DataSourceKind, InstrumentId, Timeframe
from tests.fixtures.sample_data import ist


SOURCE = DataSource(name="TEST-SAMPLE", kind=DataSourceKind.SAMPLE)


def make_candles(times, closes, *, timeframe=Timeframe.M15):
    candles = []
    for timestamp, close in zip(times, closes):
        candles.append(
            Candle(
                timestamp=timestamp,
                open=close - 0.1,
                high=close + 0.4,
                low=close - 0.4,
                close=close,
                instrument=InstrumentId.NIFTY50,
                timeframe=timeframe,
                source=SOURCE,
            )
        )
    return candles


def mock_indicators(monkeypatch, *, ema_bullish=True, rsi_bullish=True,
                    macd_bullish=True, supertrend_bullish=True, position=1,
                    signal=None):
    def aligned_points(candles, series_name):
        bullish = {
            "ema": ema_bullish,
            "rsi": rsi_bullish,
            "macd": macd_bullish,
            "supertrend": supertrend_bullish,
        }.get(series_name, True)
        bearish = None if bullish is None else not bullish
        return [
            SimpleNamespace(
                timestamp=candle.timestamp,
                ema9=1.0,
                ema21=0.9,
                ema50=0.8,
                rsi=60.0,
                histogram=1.0,
                direction=1 if supertrend_bullish else -1,
                bullish=bullish,
                bearish=bearish,
                atr=1.0,
                value=1.0,
                trailing_stop=1.0,
                position=position,
                signal=signal,
            )
            for candle in candles
        ]

    for fn_name in ("ema", "rsi", "macd", "supertrend", "ut"):
        function_name = {
            "ema": "calculate_ema_trend",
            "rsi": "calculate_rsi",
            "macd": "calculate_macd",
            "supertrend": "calculate_supertrend",
            "ut": "calculate_ut_bot",
        }[fn_name]
        monkeypatch.setattr(
            decision_module,
            function_name,
            lambda candles, *args, _series=fn_name, **kwargs: aligned_points(candles, _series),
        )


def test_15m_first_confirmed_opening_range_break_is_signal(monkeypatch):
    mock_indicators(monkeypatch)
    base = ist(2026, 1, 5, 9, 15)
    candles = make_candles(
        [base + timedelta(minutes=15 * i) for i in range(5)],
        [100.0, 100.5, 102.0, 103.0, 104.0],
    )
    # Keep the first candle's opening range explicit and narrow.
    candles[0] = candles[0].model_copy(update={"high": 101.0, "low": 99.0})

    points = calculate_decisions(candles)

    assert points[0].opening_range_state == OpeningRangeState.SET
    assert points[1].opening_range_state == OpeningRangeState.INSIDE
    assert points[2].decision == TradeDecision.BUY
    assert points[2].opening_range_state == OpeningRangeState.ABOVE_HIGH
    assert "opening-range BUY" in points[2].reason
    assert points[3].decision == TradeDecision.WAIT
    assert "already evaluated" in points[3].reason


def test_15m_breakout_needs_the_0915_candle(monkeypatch):
    mock_indicators(monkeypatch)
    base = ist(2026, 1, 5, 9, 30)
    candles = make_candles([base, base + timedelta(minutes=15)], [100.0, 102.0])

    points = calculate_decisions(candles)

    assert all(point.decision == TradeDecision.WAIT for point in points)
    assert all(point.opening_range_state == OpeningRangeState.MISSING for point in points)
    assert all("No 09:15 opening candle" in point.reason for point in points)


@pytest.mark.parametrize(("position", "breakout_close"), [(1, 102.0), (-1, 98.0)])
def test_15m_neutral_confirmation_does_not_count_as_sell_or_buy(monkeypatch, position, breakout_close):
    bullish = position == 1
    mock_indicators(monkeypatch, ema_bullish=None, rsi_bullish=bullish, macd_bullish=bullish,
                    supertrend_bullish=bullish, position=position)
    base = ist(2026, 1, 5, 9, 15)
    candles = make_candles(
        [base + timedelta(minutes=15 * i) for i in range(3)],
        [100.0, 100.5, breakout_close],
    )
    candles[0] = candles[0].model_copy(update={"high": 101.0, "low": 99.0})

    points = calculate_decisions(candles)

    assert points[2].decision == TradeDecision.WAIT
    assert points[2].ema_bullish is None
    assert "Trend check A did not confirm" in points[2].reason


@pytest.mark.parametrize(("minute", "close", "range_state", "decision"), [
    (15, 98.0, OpeningRangeState.BELOW_LOW, TradeDecision.SELL),
    (30, 98.0, OpeningRangeState.BELOW_LOW, TradeDecision.WAIT),
    (30, 100.0, OpeningRangeState.INSIDE, TradeDecision.WAIT),
])
def test_15m_reports_actual_range_state_at_and_after_cutoff(monkeypatch, minute, close, range_state, decision):
    mock_indicators(monkeypatch, ema_bullish=False, rsi_bullish=False, supertrend_bullish=False, position=-1)
    opening = ist(2026, 1, 5, 9, 15)
    late = ist(2026, 1, 5, 14, minute)
    candles = make_candles([opening, late], [100.0, close])
    candles[0] = candles[0].model_copy(update={"high": 101.0, "low": 99.0})

    points = calculate_decisions(candles)

    assert points[1].decision == decision
    assert points[1].opening_range_state == range_state
    if minute > 15:
        assert "opened after the last eligible slot at 14:15 IST" in points[1].reason
        assert "breakout" not in points[1].reason.lower()


def test_non_15m_neutral_confirmation_does_not_vote_bearish(monkeypatch):
    mock_indicators(
        monkeypatch,
        ema_bullish=None,
        rsi_bullish=False,
        macd_bullish=False,
        supertrend_bullish=False,
        position=-1,
        signal=UTBotSignal.SELL,
    )
    base = ist(2026, 1, 5, 9, 15)
    candles = make_candles([base], [100.0], timeframe=Timeframe.M1)

    point = calculate_decisions(candles)[0]

    assert point.decision == TradeDecision.WAIT


@pytest.mark.parametrize("sensitivity", [True, "1"])
def test_ut_bot_rejects_non_numeric_or_boolean_sensitivity(sensitivity):
    from app.indicators.ut_bot import calculate_ut_bot

    with pytest.raises(ValueError):
        calculate_ut_bot([], sensitivity=sensitivity)


def test_ut_bot_requires_boolean_heikin_ashi_flag():
    from app.indicators.ut_bot import calculate_ut_bot

    with pytest.raises(ValueError, match="boolean"):
        calculate_ut_bot([], use_heikin_ashi=1)


def test_sell_reference_levels_and_first_breakout_survive_wait(monkeypatch):
    mock_indicators(monkeypatch, ema_bullish=False, rsi_bullish=False,
                    macd_bullish=False, supertrend_bullish=False, position=-1)
    base = ist(2026, 11, 25, 9, 15)
    candles = make_candles([base + timedelta(minutes=15 * i) for i in range(3)], [100.0, 98.0, 97.0])
    candles[0] = candles[0].model_copy(update={"high": 101.0, "low": 99.0})
    points = calculate_decisions(candles)
    assert points[1].decision is TradeDecision.SELL
    assert points[1].levels is not None
    assert (points[1].levels.entry, points[1].levels.stop_loss, points[1].levels.target) == (98, 101, 92)
    assert points[2].decision is TradeDecision.WAIT
    assert points[2].levels is None
    assert points[2].first_breakout == points[1].first_breakout
    assert (points[2].opening_range_low, points[2].opening_range_high) == (99, 101)
