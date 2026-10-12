"""SAMPLE FIXTURES. FOR UNIT TESTS ONLY.

Everything here is synthetic. The prices are arbitrary numbers around 1000 and bear no
relation to any real market. Nothing in ``app/`` imports this module, and none of this
data may ever be returned by an endpoint or shown to a user as market data.

The IST offset and all timestamps are written out by hand on purpose, independent of
the application's own session code, so tests do not just check the code against itself.

Calendar used by the tests (2026):
  Mon 5 Jan, Tue 6, Wed 7, Thu 8, Fri 9, Sat 10, Sun 11, Mon 12, Tue 13 Jan.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone

from app.market_data import (
    Candle,
    DataSource,
    DataSourceKind,
    InstrumentId,
    Timeframe,
    ValidationReport,
    validate_candles,
)

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

NIFTY50 = InstrumentId.NIFTY50
BANKNIFTY = InstrumentId.BANKNIFTY

SAMPLE_SOURCE = DataSource(name="SAMPLE-FIXTURE-NOT-MARKET-DATA", kind=DataSourceKind.SAMPLE)
HISTORICAL_TEST_SOURCE = DataSource(name="TEST-ONLY-HISTORICAL", kind=DataSourceKind.HISTORICAL)
# Carries a LIVE label only so staleness rules can be exercised. Values are still synthetic.
LIVE_LABELLED_TEST_SOURCE = DataSource(name="TEST-ONLY-LIVE-LABEL", kind=DataSourceKind.LIVE)

# A reference time safely after every fixture date.
AS_OF_PAST = datetime(2026, 2, 2, tzinfo=UTC)


def ist(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=IST)


def make_candle(
    ts: datetime,
    *,
    o: float = 1000.0,
    h: float = 1002.0,
    low: float = 998.0,
    c: float = 1001.0,
    volume: float | None = 100.0,
    instrument: InstrumentId = NIFTY50,
    timeframe: Timeframe = Timeframe.M1,
    source: DataSource = SAMPLE_SOURCE,
) -> Candle:
    return Candle(
        timestamp=ts,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=volume,
        instrument=instrument,
        timeframe=timeframe,
        source=source,
    )


def series(
    times: Iterable[datetime],
    *,
    instrument: InstrumentId = NIFTY50,
    timeframe: Timeframe = Timeframe.M1,
    source: DataSource = SAMPLE_SOURCE,
) -> list[Candle]:
    """Internally consistent synthetic candles at the given times."""
    out = []
    for i, ts in enumerate(times):
        base = 1000.0 + 0.5 * i
        out.append(
            make_candle(
                ts,
                o=base,
                h=base + 2,
                low=base - 2,
                c=base + 1,
                volume=100.0 + i,
                instrument=instrument,
                timeframe=timeframe,
                source=source,
            )
        )
    return out


def minutes_from(start: datetime, count: int, step: int = 1) -> list[datetime]:
    return [start + timedelta(minutes=step * i) for i in range(count)]


def run_validation(candles: Sequence[Candle], **kwargs) -> ValidationReport:
    """validate_candles with test defaults: NIFTY50, 1m, and a fixed reference time."""
    kwargs.setdefault("instrument", NIFTY50)
    kwargs.setdefault("timeframe", Timeframe.M1)
    kwargs.setdefault("as_of", AS_OF_PAST)
    return validate_candles(candles, **kwargs)


def codes(report: ValidationReport) -> set[str]:
    return set(report.issue_counts)


def error_codes(report: ValidationReport) -> set[str]:
    return {i.code.value for i in report.issues if i.severity.value == "error"}


def issues_with(report: ValidationReport, code: str):
    return [i for i in report.issues if i.code.value == code]
