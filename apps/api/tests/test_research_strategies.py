"""Synthetic regression fixtures verify math/causality, not historical accuracy."""

import math
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.indicators.strategies import (
    STRATEGY_IDS,
    _adx_dmi,
    _apply_cooldown,
    _bollinger,
    _higher_timeframe_directions,
    _stochastic,
    calculate_strategy_points,
)
from app.indicators import strategies
from app.indicators.decision import TradeDecision
from app.indicators.ut_bot import UTBotSignal
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.instruments import InstrumentId
from app.market_data.sessions import IST
from app.market_data.timeframes import Timeframe


def candles(closes):
    result, at = [], datetime(2026, 1, 5, 9, 15, tzinfo=IST)
    for close in closes:
        if at.hour == 15 and at.minute == 30:
            at = (at + timedelta(days=1)).replace(hour=9, minute=15)
            while at.weekday() > 4:
                at += timedelta(days=1)
        result.append(Candle(timestamp=at, open=close, close=close,
                             high=close + 1, low=close - 1,
                             instrument=InstrumentId.NIFTY50, timeframe=Timeframe.M5,
                             source=DataSource(name="SYNTHETIC-TEST", kind=DataSourceKind.SAMPLE)))
        at += timedelta(minutes=5)
    return result


def test_dmi_wilder_hand_calculated_two_period_fixture():
    bars = candles([10, 12, 13, 10, 14])
    bars = [bar.model_copy(update={"high": high, "low": low})
            for bar, high, low in zip(bars, [11, 13, 14, 13, 15], [9, 10, 11, 9, 10])]
    points = _adx_dmi(bars, period=2)
    assert points[1].plus_di is None
    assert points[2].plus_di == pytest.approx(50)
    assert points[2].minus_di == 0
    assert points[2].adx is None
    assert points[3].plus_di == pytest.approx(100 * 0.75 / 3.5)
    assert points[3].minus_di == pytest.approx(100 / 3.5)
    assert points[3].adx == pytest.approx((100 + 100 / 7) / 2)
    assert points[4].adx == pytest.approx(((100 + 100 / 7) / 2 + 100 * 0.875 / 1.875) / 2)


def test_flat_series_is_finite_neutral_and_emits_no_setups():
    bars = [bar.model_copy(update={"high": 100.0, "low": 100.0}) for bar in candles([100.0] * 100)]
    points = calculate_strategy_points(bars)
    assert all(p.adx is None for p in points[:27])
    assert points[27].adx == 0
    assert points[-1].plus_di == points[-1].minus_di == 0
    assert points[-1].regime == "range"
    assert all(not any(p.signals.values()) for p in points)
    assert _stochastic(bars)[-1] == (50, 50)


def test_bollinger_uses_population_deviation_and_stochastic_fast_k_sma_d():
    bars = candles(list(range(1, 21)))
    assert _bollinger(bars)[18] is None
    low, high = _bollinger(bars)[19]
    assert low == pytest.approx(10.5 - 2 * math.sqrt(33.25))
    assert high == pytest.approx(10.5 + 2 * math.sqrt(33.25))
    osc_bars = [bar.model_copy(update={"high": 20.0, "low": 0.0}) for bar in bars]
    osc = _stochastic(osc_bars)
    assert osc[12] == (None, None)
    assert osc[13] == (70, None)
    assert osc[14] == (75, None)
    assert osc[15] == (80, 75)


def test_prefix_invariance_at_every_close_including_gap_and_overnight():
    bars = candles([100 + i * 0.05 + 4 * math.sin(i / 4) for i in range(160)])
    bars.pop(43)
    full = calculate_strategy_points(bars)
    for length in (1, 14, 27, 28, 42, 43, 44, 62, 74, 75, 100, 159):
        assert calculate_strategy_points(bars[:length]) == full[:length]
    assert all(set(p.signals) == set(STRATEGY_IDS) for p in full)


def test_intraday_gap_resets_warmup_but_overnight_preserves_it():
    original = candles([100 + i * 0.1 for i in range(110)])
    gap = original[:40] + original[41:]
    points = calculate_strategy_points(gap)
    assert points[39].adx is not None
    assert points[40].adx is None
    assert all(p.adx is None for p in points[40:67])
    assert points[67].adx is not None
    complete = calculate_strategy_points(original)
    assert complete[74].adx is not None
    assert complete[75].adx is not None


def test_m15_direction_waits_for_21_complete_groups_and_current_group_close():
    bars = candles([100 + i for i in range(66)])
    direction = _higher_timeframe_directions(bars)
    assert direction[:62] == [0] * 62
    assert direction[62:] == [1] * 4
    # The 21st group cannot be used while only its first two M5 bars exist.
    assert _higher_timeframe_directions(bars[:62])[-1] == 0
    changed = list(bars)
    changed[62] = changed[62].model_copy(update={"open": 1.0, "close": 1.0, "high": 2.0, "low": 0.5})
    assert _higher_timeframe_directions(changed)[:62] == direction[:62]
    # Starting mid-group discards those initial partial bars; only20 groups remain.
    assert _higher_timeframe_directions(bars[1:63]) == [0] * 62


def test_cooldowns_are_independent_and_allow_exact_30_minutes():
    at = datetime(2026, 1, 5, 10, tzinfo=IST)
    last = {}
    raw = dict.fromkeys(STRATEGY_IDS, 1)
    assert _apply_cooldown(raw, at, last) == raw
    assert not any(_apply_cooldown(raw, at + timedelta(minutes=25), last).values())
    assert _apply_cooldown(raw, at + timedelta(minutes=30), last) == raw
    isolated = {"ema_pullback": at}
    at_five = _apply_cooldown(raw, at + timedelta(minutes=5), isolated)
    assert at_five["ema_pullback"] == 0
    assert at_five["donchian_breakout"] == 1
    assert at_five["regime_consensus"] == 1


def force_trend(monkeypatch, length, ut_events=None):
    """Pin regime inputs to isolate setup rules without using market outcomes."""
    monkeypatch.setattr(strategies, "_adx_dmi", lambda _bars: [
        strategies.DMIPoint(30.0, 40.0, 10.0) for _ in range(length)])
    monkeypatch.setattr(strategies, "calculate_decisions", lambda _bars: [
        SimpleNamespace(decision=TradeDecision.WAIT) for _ in range(length)])
    monkeypatch.setattr(strategies, "calculate_ut_bot", lambda _bars: [
        SimpleNamespace(signal=(ut_events or {}).get(i)) for i in range(length)])
    monkeypatch.setattr(strategies, "_higher_timeframe_directions", lambda _bars: [1] * length)


def test_donchian_excludes_current_high_low_and_requires_actual_breakout(monkeypatch):
    bars = candles([100.0] * 31)
    bars[30] = bars[30].model_copy(update={"open": 102.0, "close": 102.0, "high": 103.0})
    force_trend(monkeypatch, len(bars))
    points = calculate_strategy_points(bars)
    assert points[29].signals["donchian_breakout"] == 0
    # Current high103 is excluded; close102 beats preceding20 highs101.
    assert points[30].signals["donchian_breakout"] == 1


def test_consensus_votes_use_raw_events_despite_constituent_cooldown(monkeypatch):
    bars = candles([100.0] * 56)
    bars[55] = bars[55].model_copy(update={"open": 103.0, "close": 103.0, "high": 104.0})
    force_trend(monkeypatch, len(bars), {50: UTBotSignal.BUY, 55: UTBotSignal.BUY})
    points = calculate_strategy_points(bars)
    assert points[50].signals["higher_timeframe_ut"] == 1
    assert points[50].signals["regime_consensus"] == 0
    # HTF-UT's output is suppressed25minutes later. Composite must still see
    # its underlying current setup and combine it with the new breakout.
    assert points[55].signals["higher_timeframe_ut"] == 0
    assert points[55].signals["donchian_breakout"] == 1
    assert points[55].signals["regime_consensus"] == 1


@pytest.mark.parametrize("change", [
    {"timestamp": datetime(2026, 1, 5, 9, 15)},
    {"timeframe": Timeframe.M1},
    {"timestamp": datetime(2026, 1, 5, 9, 16, tzinfo=IST)},
    {"timestamp": datetime(2026, 1, 5, 15, 30, tzinfo=IST)},
    {"close": math.nan},
    {"high": 2.0},
])
def test_malformed_inputs_are_rejected(change):
    bars = candles([100.0])
    with pytest.raises(ValueError):
        calculate_strategy_points([bars[0].model_copy(update=change)])


def test_unsorted_and_mixed_instruments_rejected_and_empty_valid():
    bars = candles([100, 101])
    with pytest.raises(ValueError, match="chronological"):
        calculate_strategy_points(bars[::-1])
    with pytest.raises(ValueError, match="instrument"):
        calculate_strategy_points([bars[0], bars[1].model_copy(update={"instrument": InstrumentId.BANKNIFTY})])
    assert calculate_strategy_points([]) == []
