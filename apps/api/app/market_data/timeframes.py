"""Supported candle timeframes.

A timeframe is the length of one candle. Identifiers are the strings used in the API.
"""

from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel


class Timeframe(StrEnum):
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"

    @property
    def interval(self) -> timedelta:
        return _INTERVALS[self]

    @property
    def is_intraday(self) -> bool:
        return self is not Timeframe.D1

    @property
    def label(self) -> str:
        return _LABELS[self]


_INTERVALS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M3: timedelta(minutes=3),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.D1: timedelta(days=1),
}

_LABELS: dict[Timeframe, str] = {
    Timeframe.M1: "1 minute",
    Timeframe.M3: "3 minutes",
    Timeframe.M5: "5 minutes",
    Timeframe.M15: "15 minutes",
    Timeframe.H1: "1 hour",
    Timeframe.D1: "1 day",
}


class TimeframeInfo(BaseModel):
    """Public description of a timeframe, returned by the API."""

    id: Timeframe
    label: str
    seconds: int
    is_intraday: bool


def list_timeframes() -> list[TimeframeInfo]:
    return [
        TimeframeInfo(
            id=tf,
            label=tf.label,
            seconds=int(tf.interval.total_seconds()),
            is_intraday=tf.is_intraday,
        )
        for tf in Timeframe
    ]
