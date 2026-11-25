"""NSE trading-session helpers used by validation.

Conventions (all documented in the README):

* A candle's ``timestamp`` is its OPEN time. It closes at ``timestamp + interval``,
  capped at the session close (so the last 1h candle, 15:15, closes at 15:30).
* Regular session is Monday to Friday, 09:15 to 15:30 IST.
* Intraday candles sit on a grid that starts at 09:15 IST. A 1h candle therefore
  opens at 09:15, 10:15, ... 15:15.
* A daily candle is identified by its IST calendar date; its time of day is ignored.
* Published NSE cash-market closures apply in verified years. Weekday hours
  outside those years are provisional and cannot prove a missing full session.

IST is a fixed UTC+05:30 offset (India has no daylight saving), so no tz database
is needed. That also avoids a ``tzdata`` requirement on Windows.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from functools import lru_cache

from app.market_data.timeframes import Timeframe

IST = timezone(timedelta(hours=5, minutes=30), "IST")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

_ONE_DAY = timedelta(days=1)


def to_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST)


def is_weekday(day: date) -> bool:
    return day.weekday() < 5


# Published NSE equity calendars. Keep future years provisional until the exchange publishes them.
VERIFIED_CALENDAR_YEARS = (2025, 2026)
NSE_HOLIDAYS = {
    '2025-02-26': 'Mahashivratri',
    '2025-03-14': 'Holi',
    '2025-03-31': 'Id-Ul-Fitr (Ramzan Id)',
    '2025-04-10': 'Shri Mahavir Jayanti',
    '2025-04-14': 'Dr. Baba Saheb Ambedkar Jayanti',
    '2025-04-18': 'Good Friday',
    '2025-05-01': 'Maharashtra Day',
    '2025-08-15': 'Independence Day',
    '2025-08-27': 'Ganesh Chaturthi',
    '2025-10-02': 'Mahatma Gandhi Jayanti / Dussehra',
    '2025-10-21': 'Diwali Laxmi Pujan',
    '2025-10-22': 'Diwali Balipratipada',
    '2025-11-05': 'Prakash Gurpurb Sri Guru Nanak Dev',
    '2025-12-25': 'Christmas',
    '2026-01-15': 'Municipal Corporation Election - Maharashtra',
    '2026-01-26': 'Republic Day',
    '2026-03-03': 'Holi',
    '2026-03-26': 'Shri Ram Navami',
    '2026-03-31': 'Shri Mahavir Jayanti',
    '2026-04-03': 'Good Friday',
    '2026-04-14': 'Dr. Baba Saheb Ambedkar Jayanti',
    '2026-05-01': 'Maharashtra Day',
    '2026-05-28': 'Bakri Id (Eid al-Adha)',
    '2026-06-26': 'Muharram',
    '2026-09-14': 'Ganesh Chaturthi',
    '2026-10-02': 'Mahatma Gandhi Jayanti',
    '2026-10-20': 'Dussehra',
    '2026-11-08': 'Diwali Laxmi Pujan (Muhurat Trading Session)',
    '2026-11-10': 'Diwali Balipratipada',
    '2026-11-24': 'Prakash Gurpurb Sri Guru Nanak Dev',
    '2026-12-25': 'Christmas',
}


def is_regular_trading_day(day: date) -> bool:
    return is_weekday(day) and day.isoformat() not in NSE_HOLIDAYS


def _at(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=IST)


@lru_cache(maxsize=256)
def session_slots(day: date, timeframe: Timeframe) -> tuple[datetime, ...]:
    """Expected candle OPEN times (IST) for one calendar day. Empty on weekends."""
    if not is_regular_trading_day(day):
        return ()
    open_dt = _at(day, SESSION_OPEN)
    if timeframe is Timeframe.D1:
        return (open_dt,)
    close_dt = _at(day, SESSION_CLOSE)
    step = timeframe.interval
    slots: list[datetime] = []
    current = open_dt
    while current < close_dt:
        slots.append(current)
        current += step
    return tuple(slots)


def slot_close_time(slot: datetime, timeframe: Timeframe) -> datetime:
    """Close time of the candle that opens at ``slot`` (an IST datetime)."""
    return min(slot + timeframe.interval, _at(slot.date(), SESSION_CLOSE))


class SlotClass(StrEnum):
    ON_GRID = "on_grid"
    OFF_GRID = "off_grid"
    OUTSIDE_SESSION = "outside_session"


def classify_timestamp(ts: datetime, timeframe: Timeframe) -> tuple[SlotClass, datetime]:
    """Classify an aware timestamp against the session grid.

    Returns the class and the canonical IST slot (for daily candles, the 09:15 slot of
    the IST date; otherwise the timestamp converted to IST).
    """
    local = to_ist(ts)
    day = local.date()
    if not is_regular_trading_day(day):
        return SlotClass.OUTSIDE_SESSION, local
    if timeframe is Timeframe.D1:
        return SlotClass.ON_GRID, _at(day, SESSION_OPEN)
    open_dt = _at(day, SESSION_OPEN)
    close_dt = _at(day, SESSION_CLOSE)
    if local < open_dt or local >= close_dt:
        return SlotClass.OUTSIDE_SESSION, local
    if (local - open_dt) % timeframe.interval != timedelta(0):
        return SlotClass.OFF_GRID, local
    return SlotClass.ON_GRID, local


def candle_close_time(ts: datetime, timeframe: Timeframe) -> datetime:
    """Close time of the candle opening at the aware timestamp ``ts``."""
    kind, slot = classify_timestamp(ts, timeframe)
    if kind is SlotClass.ON_GRID:
        return slot_close_time(slot, timeframe)
    return to_ist(ts) + timeframe.interval


@dataclass(frozen=True)
class Gap:
    """What is missing between two consecutive present candles."""

    # Expected candles missing on days that DO have data (a partial day).
    missing_slots: int
    first_missing: datetime | None
    # Weekdays with no data at all between the two candles.
    missing_days: tuple[date, ...]


def find_gap(prev_slot: datetime, next_slot: datetime, timeframe: Timeframe) -> Gap:
    """Describe the hole between two consecutive on-grid candles (IST slots)."""
    prev_day, next_day = prev_slot.date(), next_slot.date()
    if prev_day == next_day:
        partial = [s for s in session_slots(prev_day, timeframe) if prev_slot < s < next_slot]
        return Gap(len(partial), partial[0] if partial else None, ())

    partial = [s for s in session_slots(prev_day, timeframe) if s > prev_slot]
    partial += [s for s in session_slots(next_day, timeframe) if s < next_slot]
    missing_days: list[date] = []
    day = prev_day + _ONE_DAY
    while day < next_day:
        if day.year in VERIFIED_CALENDAR_YEARS and is_regular_trading_day(day):
            missing_days.append(day)
        day += _ONE_DAY
    return Gap(len(partial), partial[0] if partial else None, tuple(missing_days))


def count_closed_slots_after(
    last_slot: datetime, timeframe: Timeframe, as_of: datetime, limit: int
) -> int:
    """Count expected candles that opened after ``last_slot`` and had closed by ``as_of``.

    Stops counting once ``limit`` is exceeded, so very old data is cheap to evaluate.
    """
    count = 0
    day = last_slot.date()
    end_day = to_ist(as_of).date()
    while day <= end_day:
        for slot in session_slots(day, timeframe):
            if slot > last_slot and slot_close_time(slot, timeframe) <= as_of:
                count += 1
                if count > limit:
                    return count
        day += _ONE_DAY
    return count
