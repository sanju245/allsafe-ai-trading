"""Candle-series validation.

``validate_candles`` never raises on bad market data. It returns a report listing every
problem, so callers (and the API) can show exactly what is wrong. A series is VALID
when it has no ERROR-severity issues; warnings do not make a series invalid.

Severity guide:
  ERROR    the series must not be used to compute signals.
  WARNING  usable, but the caller should know (e.g. possible exchange holiday, a
           still-forming last candle, sample data).
"""

import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.sessions import (
    SlotClass,
    candle_close_time,
    classify_timestamp,
    count_closed_slots_after,
    find_gap,
    session_slots,
    to_ist,
)
from app.market_data.timeframes import Timeframe

DEFAULT_MAX_ISSUES_PER_CODE = 20

# A run of missing weekdays longer than this cannot be explained by exchange holidays
# alone (no exchange closes for a full trading week), so it is an ERROR, not a warning.
MAX_PLAUSIBLE_HOLIDAY_RUN = 4


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class IssueCode(StrEnum):
    EMPTY_SERIES = "EMPTY_SERIES"
    INSTRUMENT_MISMATCH = "INSTRUMENT_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    INVALID_OHLC = "INVALID_OHLC"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    TIMESTAMP_NOT_ON_GRID = "TIMESTAMP_NOT_ON_GRID"
    OUTSIDE_TRADING_HOURS = "OUTSIDE_TRADING_HOURS"
    MISSING_INTERVAL = "MISSING_INTERVAL"
    MISSING_SESSION = "MISSING_SESSION"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    FORMING_CANDLE = "FORMING_CANDLE"
    STALE_DATA = "STALE_DATA"
    VOLUME_UNAVAILABLE = "VOLUME_UNAVAILABLE"
    SAMPLE_DATA = "SAMPLE_DATA"


class ValidationIssue(BaseModel):
    code: IssueCode
    severity: Severity
    message: str
    # Position in the supplied list, when the issue concerns one candle.
    index: int | None = None
    timestamp: datetime | None = None
    # How many items this issue covers (e.g. candles missing in one gap).
    count: int = 1


class ValidationReport(BaseModel):
    is_valid: bool
    instrument: InstrumentId
    timeframe: Timeframe
    source: DataSource | None
    candle_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    checked_at: datetime
    staleness_checked: bool
    error_count: int
    warning_count: int
    # Expected candles absent from the series (partial days plus whole missing days).
    missing_candle_count: int
    # Weekdays with no data at all (may be exchange holidays).
    missing_session_count: int
    # Total issues per code, counted before any truncation of ``issues``.
    issue_counts: dict[str, int]
    issues: list[ValidationIssue]
    issues_truncated: bool


class _Collector:
    def __init__(self, max_per_code: int) -> None:
        self._max = max_per_code
        self.issues: list[ValidationIssue] = []
        self.per_code: Counter[str] = Counter()
        self.errors = 0
        self.warnings = 0
        self.truncated = False

    def add(
        self,
        code: IssueCode,
        severity: Severity,
        message: str,
        *,
        index: int | None = None,
        timestamp: datetime | None = None,
        count: int = 1,
    ) -> None:
        self.per_code[code.value] += 1
        if severity is Severity.ERROR:
            self.errors += 1
        else:
            self.warnings += 1
        if self.per_code[code.value] <= self._max:
            self.issues.append(
                ValidationIssue(
                    code=code,
                    severity=severity,
                    message=message,
                    index=index,
                    timestamp=timestamp,
                    count=count,
                )
            )
        else:
            self.truncated = True


def _fmt(ts: datetime) -> str:
    return to_ist(ts).strftime("%Y-%m-%d %H:%M IST")


def _is_aware(ts: datetime) -> bool:
    return ts.tzinfo is not None and ts.utcoffset() is not None


def _check_metadata(
    candle: Candle,
    index: int,
    instrument: InstrumentId,
    timeframe: Timeframe,
    source: DataSource | None,
    out: _Collector,
) -> None:
    if candle.instrument != instrument:
        out.add(
            IssueCode.INSTRUMENT_MISMATCH,
            Severity.ERROR,
            f"Candle is for {candle.instrument.value}, expected {instrument.value}.",
            index=index,
        )
    if candle.timeframe != timeframe:
        out.add(
            IssueCode.TIMEFRAME_MISMATCH,
            Severity.ERROR,
            f"Candle timeframe is {candle.timeframe.value}, expected {timeframe.value}.",
            index=index,
        )
    if source is not None and (candle.source.name, candle.source.kind) != (
        source.name,
        source.kind,
    ):
        out.add(
            IssueCode.SOURCE_MISMATCH,
            Severity.ERROR,
            "Candle comes from a different data source than the rest of the series.",
            index=index,
        )


def _check_values(candle: Candle, index: int, out: _Collector) -> None:
    prices = (candle.open, candle.high, candle.low, candle.close)
    volume = candle.volume
    ts = candle.timestamp if _is_aware(candle.timestamp) else None

    finite = all(math.isfinite(p) for p in prices) and (volume is None or math.isfinite(volume))
    if not finite:
        out.add(
            IssueCode.NON_FINITE_VALUE,
            Severity.ERROR,
            "A price or volume is NaN or infinite.",
            index=index,
            timestamp=ts,
        )
        return

    if any(p <= 0 for p in prices):
        out.add(
            IssueCode.NON_POSITIVE_PRICE,
            Severity.ERROR,
            "Prices must be greater than zero.",
            index=index,
            timestamp=ts,
        )

    o, h, low, c = prices
    problems = []
    if h < low:
        problems.append("high is below low")
    if h < o:
        problems.append("high is below open")
    if h < c:
        problems.append("high is below close")
    if low > o:
        problems.append("low is above open")
    if low > c:
        problems.append("low is above close")
    if problems:
        out.add(
            IssueCode.INVALID_OHLC,
            Severity.ERROR,
            "Inconsistent OHLC: " + "; ".join(problems) + ".",
            index=index,
            timestamp=ts,
        )

    if volume is not None and volume < 0:
        out.add(
            IssueCode.NEGATIVE_VOLUME,
            Severity.ERROR,
            f"Volume cannot be negative (got {volume:g}).",
            index=index,
            timestamp=ts,
        )


def validate_candles(
    candles: Sequence[Candle],
    *,
    instrument: InstrumentId,
    timeframe: Timeframe,
    source: DataSource | None = None,
    as_of: datetime | None = None,
    check_staleness: bool | None = None,
    allowed_lag_candles: int = 1,
    grace_seconds: float = 30.0,
    max_issues_per_code: int = DEFAULT_MAX_ISSUES_PER_CODE,
) -> ValidationReport:
    """Validate a candle series against what the caller expects.

    ``instrument`` and ``timeframe`` are what the caller asked for; candles that differ
    are flagged. ``source`` defaults to the first candle's source.

    ``as_of`` is the reference "now" (timezone-aware; defaults to the current UTC time).
    Injecting it makes validation reproducible in tests.

    Staleness is checked when ``check_staleness`` is True, or, when it is None, only for
    LIVE and DELAYED sources. The series is stale when more than ``allowed_lag_candles``
    expected candles have already closed (allowing ``grace_seconds`` for delivery) since
    its latest candle. Weekends and the time outside 09:15 to 15:30 IST are skipped. No
    holiday calendar exists yet, so a market holiday can look stale.
    """
    now = as_of if as_of is not None else datetime.now(UTC)
    if not _is_aware(now):
        raise ValueError("as_of must be timezone-aware")
    if allowed_lag_candles < 0:
        raise ValueError("allowed_lag_candles must be >= 0")

    out = _Collector(max_issues_per_code)
    resolved_source = source if source is not None else (candles[0].source if candles else None)

    if not candles:
        out.add(IssueCode.EMPTY_SERIES, Severity.ERROR, "The candle series is empty.")
        return _report(
            out, instrument, timeframe, resolved_source, 0, None, None, now, False, 0, 0
        )

    seen: set[object] = set()
    analysis: list[tuple[datetime, int]] = []  # (IST slot, index) of on-grid candles
    previous_ts: datetime | None = None
    earliest_ts: datetime | None = None
    latest_ts: datetime | None = None
    latest_index = 0

    for i, candle in enumerate(candles):
        _check_metadata(candle, i, instrument, timeframe, resolved_source, out)
        _check_values(candle, i, out)

        ts = candle.timestamp
        if not _is_aware(ts):
            out.add(
                IssueCode.NAIVE_TIMESTAMP,
                Severity.ERROR,
                "Timestamp has no timezone. Send an ISO 8601 time with an offset, e.g. +05:30 or Z.",
                index=i,
            )
            continue

        slot_class, slot = classify_timestamp(ts, timeframe)
        key: object = to_ist(ts).date() if timeframe is Timeframe.D1 else ts
        if key in seen:
            out.add(
                IssueCode.DUPLICATE_TIMESTAMP,
                Severity.ERROR,
                f"Another candle already exists for {_fmt(ts)}.",
                index=i,
                timestamp=ts,
            )
            continue
        seen.add(key)

        if previous_ts is not None and ts < previous_ts:
            out.add(
                IssueCode.OUT_OF_ORDER,
                Severity.ERROR,
                f"Candle at {_fmt(ts)} comes after a later candle ({_fmt(previous_ts)}).",
                index=i,
                timestamp=ts,
            )
        previous_ts = ts

        if ts > now:
            out.add(
                IssueCode.FUTURE_TIMESTAMP,
                Severity.ERROR,
                f"Candle at {_fmt(ts)} is later than the reference time {_fmt(now)}.",
                index=i,
                timestamp=ts,
            )

        if earliest_ts is None or ts < earliest_ts:
            earliest_ts = ts
        if latest_ts is None or ts > latest_ts:
            latest_ts, latest_index = ts, i

        if slot_class is SlotClass.ON_GRID:
            analysis.append((slot, i))
        elif slot_class is SlotClass.OFF_GRID:
            out.add(
                IssueCode.TIMESTAMP_NOT_ON_GRID,
                Severity.ERROR,
                f"{_fmt(ts)} is not on the {timeframe.value} grid (candles open at 09:15 IST "
                f"plus whole multiples of {timeframe.value}).",
                index=i,
                timestamp=ts,
            )
        else:
            out.add(
                IssueCode.OUTSIDE_TRADING_HOURS,
                Severity.WARNING,
                f"{_fmt(ts)} is outside regular trading hours (Mon-Fri 09:15-15:30 IST). "
                "This may be a special session; it is ignored for gap and freshness checks.",
                index=i,
                timestamp=ts,
            )

    # --- gaps (analysed on a sorted copy so one misplaced candle does not cascade) ---
    analysis.sort(key=lambda item: item[0])
    missing_candles = 0
    missing_sessions = 0
    for (prev_slot, _), (next_slot, _) in pairwise(analysis):
        gap = find_gap(prev_slot, next_slot, timeframe)
        if gap.missing_slots:
            missing_candles += gap.missing_slots
            out.add(
                IssueCode.MISSING_INTERVAL,
                Severity.ERROR,
                f"{gap.missing_slots} expected {timeframe.value} candle(s) missing between "
                f"{_fmt(prev_slot)} and {_fmt(next_slot)}.",
                timestamp=gap.first_missing,
                count=gap.missing_slots,
            )
        if gap.missing_days:
            days = len(gap.missing_days)
            missing_sessions += days
            missing_candles += sum(len(session_slots(d, timeframe)) for d in gap.missing_days)
            first = gap.missing_days[0].isoformat()
            last = gap.missing_days[-1].isoformat()
            if days > MAX_PLAUSIBLE_HOLIDAY_RUN:
                out.add(
                    IssueCode.MISSING_INTERVAL,
                    Severity.ERROR,
                    f"{days} consecutive trading days are missing ({first} to {last}). That is "
                    "too long to be explained by exchange holidays.",
                    count=days,
                )
            else:
                out.add(
                    IssueCode.MISSING_SESSION,
                    Severity.WARNING,
                    f"{days} weekday(s) have no data ({first} to {last}). They may be exchange "
                    "holidays; no holiday calendar is bundled yet.",
                    count=days,
                )

    # --- the most recent candle: still forming? ---
    if latest_ts is not None and latest_ts <= now < candle_close_time(latest_ts, timeframe):
        out.add(
            IssueCode.FORMING_CANDLE,
            Severity.WARNING,
            f"The latest candle ({_fmt(latest_ts)}) has not closed yet. Treat any signal based "
            "on it as provisional.",
            index=latest_index,
            timestamp=latest_ts,
        )

    # --- staleness ---
    if check_staleness is None:
        should_check = resolved_source is not None and resolved_source.kind in (
            DataSourceKind.LIVE,
            DataSourceKind.DELAYED,
        )
    else:
        should_check = check_staleness
    staleness_checked = False
    if should_check and analysis:
        staleness_checked = True
        last_slot = analysis[-1][0]
        behind = count_closed_slots_after(
            last_slot,
            timeframe,
            now - timedelta(seconds=grace_seconds),
            allowed_lag_candles,
        )
        if behind > allowed_lag_candles:
            out.add(
                IssueCode.STALE_DATA,
                Severity.ERROR,
                f"Latest candle is {_fmt(last_slot)}, but more than {allowed_lag_candles} "
                f"{timeframe.value} candle(s) should have closed since. If the market is closed "
                "for an exchange holiday this is expected (no holiday calendar is bundled).",
                timestamp=last_slot,
            )

    # --- series-level notes ---
    if resolved_source is not None and resolved_source.kind is DataSourceKind.SAMPLE:
        out.add(
            IssueCode.SAMPLE_DATA,
            Severity.WARNING,
            "Series is labelled SAMPLE. It is not market data and must never be shown as live.",
        )
    without_volume = sum(1 for c in candles if c.volume is None)
    if without_volume:
        out.add(
            IssueCode.VOLUME_UNAVAILABLE,
            Severity.WARNING,
            f"{without_volume} candle(s) have no volume. Volume-based indicators (such as "
            "VWAP) cannot be computed from them.",
            count=without_volume,
        )

    return _report(
        out,
        instrument,
        timeframe,
        resolved_source,
        len(candles),
        earliest_ts,
        latest_ts,
        now,
        staleness_checked,
        missing_candles,
        missing_sessions,
    )


def _report(
    out: _Collector,
    instrument: InstrumentId,
    timeframe: Timeframe,
    source: DataSource | None,
    candle_count: int,
    first_ts: datetime | None,
    last_ts: datetime | None,
    checked_at: datetime,
    staleness_checked: bool,
    missing_candles: int,
    missing_sessions: int,
) -> ValidationReport:
    return ValidationReport(
        is_valid=out.errors == 0,
        instrument=instrument,
        timeframe=timeframe,
        source=source,
        candle_count=candle_count,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        checked_at=checked_at,
        staleness_checked=staleness_checked,
        error_count=out.errors,
        warning_count=out.warnings,
        missing_candle_count=missing_candles,
        missing_session_count=missing_sessions,
        issue_counts=dict(out.per_code),
        issues=out.issues,
        issues_truncated=out.truncated,
    )
