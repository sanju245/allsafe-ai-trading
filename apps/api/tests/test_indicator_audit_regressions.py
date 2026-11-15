from types import SimpleNamespace
import pytest

from app.indicators import decision
from app.indicators.ema import calculate_ema_trend
from app.indicators.ut_bot import calculate_ut_bot
from tests.test_confirmation_indicators import candles_from_closes


def test_mixed_and_flat_ema_are_not_bearish():
    mixed = calculate_ema_trend(candles_from_closes(list(range(100,200))+[150,150]))[-1]
    assert mixed.ema21 > mixed.ema9 > mixed.ema50
    assert mixed.bullish is False and mixed.bearish is False
    flat = calculate_ema_trend(candles_from_closes([100]*60))[-1]
    assert flat.bullish is False and flat.bearish is False
    assert calculate_ema_trend(candles_from_closes(list(range(200,100,-1))))[-1].bearish is True


@pytest.mark.parametrize("ema_bearish,rsi,hist,expected", [
    (True,49,-1,"SELL"), (False,49,-1,"WAIT"),
    (True,50,-1,"WAIT"), (True,49,0,"WAIT"),
])
def test_sell_requires_explicit_bearish_confirmations(monkeypatch, ema_bearish, rsi, hist, expected):
    monkeypatch.setattr(decision,"calculate_ut_bot",lambda *a,**k:[SimpleNamespace(signal="SELL",atr=1,trailing_stop=101)])
    monkeypatch.setattr(decision,"calculate_ema_trend",lambda *a:[SimpleNamespace(bullish=False,bearish=ema_bearish)])
    monkeypatch.setattr(decision,"calculate_rsi",lambda *a:[SimpleNamespace(bullish=False,rsi=rsi)])
    monkeypatch.setattr(decision,"calculate_macd",lambda *a:[SimpleNamespace(bullish=False,histogram=hist)])
    monkeypatch.setattr(decision,"calculate_supertrend",lambda *a:[SimpleNamespace(bullish=False)])
    assert decision.calculate_decisions(candles_from_closes([100]))[0].decision == expected


def test_decision_prefix_does_not_depend_on_future_prices():
    candles = candles_from_closes([100 + i*.1 + (-1 if i%7 else 3) for i in range(160)])
    full=decision.calculate_decisions(candles)
    assert decision.calculate_decisions(candles[:100]) == full[:100]


def test_ut_bot_expected_reversal_signals():
    candles = candles_from_closes([100,103,99,105])
    points=calculate_ut_bot(candles,atr_period=1)
    assert points[0].signal is None
    assert [p.atr for p in points] == [2,4,5,7]
    assert [p.trailing_stop for p in points] == [98,99,104,98]
    assert [p.signal for p in points] == [None,None,"SELL","BUY"]
