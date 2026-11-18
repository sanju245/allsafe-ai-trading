"""Score the 15-minute five-indicator rules from an OHLC CSV export.

CSV columns: symbol,timestamp,open,high,low,close
Timestamp must be ISO 8601 with a timezone. Only regular NSE 15-minute bars are used.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.indicators.decision import TradeDecision, calculate_decisions
from app.indicators.ema import calculate_ema_trend
from app.indicators.macd import calculate_macd
from app.indicators.rsi import calculate_rsi
from app.indicators.supertrend import calculate_supertrend
from app.indicators.ut_bot import UTBotSignal, calculate_ut_bot
from app.market_data import Candle, DataSource, DataSourceKind, InstrumentId, Timeframe


IST = ZoneInfo("Asia/Kolkata")
SOURCE = DataSource(name="CSV-15M-AUDIT", kind=DataSourceKind.HISTORICAL)
SYMBOLS = {
    "^NSEI": InstrumentId.NIFTY50,
    "NIFTY50": InstrumentId.NIFTY50,
    "NIFTY 50": InstrumentId.NIFTY50,
    "^NSEBANK": InstrumentId.BANKNIFTY,
    "BANKNIFTY": InstrumentId.BANKNIFTY,
    "BANK NIFTY": InstrumentId.BANKNIFTY,
}
HOLDING_BARS = 4
BAR_SIZE = timedelta(minutes=15)


def read_bars(path: Path) -> dict[InstrumentId, list[Candle]]:
    grouped: dict[InstrumentId, list[Candle]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"symbol", "timestamp", "open", "high", "low", "close"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            key = row["symbol"].strip().upper()
            instrument = SYMBOLS.get(key)
            if instrument is None:
                raise ValueError(f"Unknown symbol {row['symbol']!r} on CSV row {row_number}")
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError(f"Timestamp on CSV row {row_number} has no timezone")
            stamp = stamp.astimezone(IST)
            if stamp.weekday() >= 5 or not time(9, 15) <= stamp.time() < time(15, 30):
                continue
            if (stamp.hour * 60 + stamp.minute - (9 * 60 + 15)) % 15:
                continue
            grouped[instrument].append(
                Candle(
                    timestamp=stamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    instrument=instrument,
                    timeframe=Timeframe.M15,
                    source=SOURCE,
                )
            )
    for bars in grouped.values():
        bars.sort(key=lambda bar: bar.timestamp)
        if len({bar.timestamp for bar in bars}) != len(bars):
            raise ValueError("CSV contains duplicate timestamps for an index")
    return grouped


def outcome(bars: list[Candle], signal_index: int, side: int) -> bool | None:
    """Next-bar-open entry, close of the fourth following bar, same NSE session."""
    exit_index = signal_index + HOLDING_BARS
    if exit_index >= len(bars):
        return None
    signal_day = bars[signal_index].timestamp.astimezone(IST).date()
    for index in range(signal_index, exit_index + 1):
        current = bars[index].timestamp.astimezone(IST)
        if current.date() != signal_day:
            return None
        if index > signal_index and bars[index].timestamp - bars[index - 1].timestamp != BAR_SIZE:
            return None
    entry = bars[signal_index + 1].open
    exit_price = bars[exit_index].close
    movement = exit_price - entry
    return movement > 0 if side == 1 else movement < 0


def summarize(
    bars: list[Candle],
    signal_sides: dict[int, int],
    start: date,
    end: date,
) -> tuple[int, int, float]:
    wins = count = 0
    for index, side in signal_sides.items():
        stamp = bars[index].timestamp.astimezone(IST)
        if not start <= stamp.date() <= end:
            continue
        correct = outcome(bars, index, side)
        if correct is None:
            continue
        count += 1
        wins += correct
    return wins, count, wins / count if count else 0.0


def wilson_interval(wins: int, count: int) -> tuple[float, float] | None:
    if not count:
        return None
    z = 1.959963984540054
    p = wins / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    radius = z * ((p * (1 - p) / count + z * z / (4 * count * count)) ** 0.5) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def side_for_ut(signal: UTBotSignal | None) -> int | None:
    if signal == UTBotSignal.BUY:
        return 1
    if signal == UTBotSignal.SELL:
        return -1
    return None


def legacy_signals(bars: list[Candle]) -> dict[int, int]:
    ut = calculate_ut_bot(bars)
    ema = calculate_ema_trend(bars)
    rsi = calculate_rsi(bars)
    macd = calculate_macd(bars)
    supertrend = calculate_supertrend(bars)
    signals: dict[int, int] = {}
    for i, trigger in enumerate(ut):
        side = side_for_ut(trigger.signal)
        if side is None:
            continue
        if any(
            value is None
            for value in (
                ema[i].ema9, ema[i].ema21, ema[i].ema50,
                rsi[i].rsi, macd[i].histogram, supertrend[i].direction,
            )
        ):
            continue
        votes = (
            ema[i].ema9 > ema[i].ema21 > ema[i].ema50,
            rsi[i].rsi > 50,
            macd[i].macd > macd[i].signal_line and macd[i].histogram > 0,
            supertrend[i].bullish is True,
        )
        if side == 1 and all(votes):
            signals[i] = side
        elif side == -1 and not any(votes):
            signals[i] = side
    return signals


def ut_gate_signals(bars: list[Candle], gate: str | None) -> dict[int, int]:
    ut = calculate_ut_bot(bars)
    ema = calculate_ema_trend(bars)
    rsi = calculate_rsi(bars)
    macd = calculate_macd(bars)
    supertrend = calculate_supertrend(bars)
    points = {"ema": ema, "rsi": rsi, "macd": macd, "supertrend": supertrend}
    signals: dict[int, int] = {}
    for i, trigger in enumerate(ut):
        side = side_for_ut(trigger.signal)
        if side is None or gate is None:
            if side is not None:
                signals[i] = side
            continue
        point = points[gate][i]
        if point.bullish is None or (side == -1 and point.bearish is None):
            continue
        if point.bullish is True if side == 1 else point.bearish is True:
            signals[i] = side
    return signals


def format_score(wins: int, count: int, rate: float) -> str:
    if not count:
        return "0/0 (n/a)"
    return f"{wins}/{count} ({rate:.1%})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="authorized OHLC CSV export")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 10, 19))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 11, 18))
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must be on or after --start")

    grouped = read_bars(args.csv)
    print(f"Scoring {args.start.isoformat()} through {args.end.isoformat()} (inclusive)")
    print("Rule/index                Correct signals")
    print("-" * 53)
    rule_sides: dict[str, dict[InstrumentId, dict[int, int]]] = defaultdict(dict)
    for instrument, bars in grouped.items():
        revised = calculate_decisions(bars)
        rule_sides["Old unanimous"][instrument] = legacy_signals(bars)
        rule_sides["Revised 15m"][instrument] = {
            i: 1 if point.decision == TradeDecision.BUY else -1
            for i, point in enumerate(revised)
            if point.decision in (TradeDecision.BUY, TradeDecision.SELL)
        }
        rule_sides["UT Bot only"][instrument] = ut_gate_signals(bars, None)
        for gate in ("ema", "rsi", "macd", "supertrend"):
            rule_sides[f"UT Bot + {gate.upper()}"][instrument] = ut_gate_signals(bars, gate)

    for rule, per_index in rule_sides.items():
        total_wins = total_count = 0
        for instrument in (InstrumentId.BANKNIFTY, InstrumentId.NIFTY50):
            bars = grouped.get(instrument, [])
            if not bars:
                continue
            wins, count, rate = summarize(bars, per_index.get(instrument, {}), args.start, args.end)
            print(f"{rule:22s} {instrument.value:10s} {format_score(wins, count, rate)}")
            total_wins += wins
            total_count += count
        if total_count:
            rate = total_wins / total_count
            suffix = ""
            if rule == "Revised 15m":
                interval = wilson_interval(total_wins, total_count)
                suffix = f"; Wilson 95% CI {interval[0]:.1%}-{interval[1]:.1%}"
            print(f"{'':22s} {'Combined':10s} {format_score(total_wins, total_count, rate)}{suffix}")


if __name__ == "__main__":
    main()
