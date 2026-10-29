"""Build five-minute OHLC candles from timestamped price updates."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource
from app.market_data.sessions import SESSION_CLOSE, SESSION_OPEN, to_ist
from app.market_data.timeframes import Timeframe

CANDLE_DURATION = timedelta(minutes=5)


@dataclass
class _WorkingCandle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    instrument: InstrumentId
    source: DataSource
    last_update_timestamp: datetime

    def update(self, price: float, timestamp: datetime) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.last_update_timestamp = timestamp

    def freeze(self) -> Candle:
        return Candle(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=None,
            instrument=self.instrument,
            timeframe=Timeframe.M5,
            source=self.source,
        )


class FiveMinuteCandleBuilder:
    """Aggregate price updates into five-minute candles aligned to NSE hours."""

    def __init__(self, source: DataSource) -> None:
        self.source = source
        self._working: dict[InstrumentId, _WorkingCandle] = {}
        self._finalized_through: dict[InstrumentId, datetime] = {}

    @staticmethod
    def _slot(timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        local = to_ist(timestamp)
        if local.weekday() >= 5:
            raise ValueError("timestamp is outside the regular NSE session")

        local_time = local.time().replace(tzinfo=None)
        if not (SESSION_OPEN <= local_time < SESSION_CLOSE):
            raise ValueError("timestamp is outside the regular NSE session")

        session_open = local.replace(
            hour=9, minute=15, second=0, microsecond=0
        )
        elapsed_seconds = (local - session_open).total_seconds()
        slot_number = int(elapsed_seconds // 300)
        return session_open + timedelta(minutes=5 * slot_number)

    def add_price(
        self,
        instrument: InstrumentId,
        timestamp: datetime,
        price: float,
    ) -> Candle | None:
        """Add a price; return a prior candle when a later slot arrives."""
        if not math.isfinite(price) or price <= 0:
            raise ValueError("price must be finite and greater than zero")

        slot = self._slot(timestamp)
        previous_finalized = self._finalized_through.get(instrument)
        if previous_finalized is not None and slot <= previous_finalized:
            raise ValueError("out-of-order price update for a finalized candle")

        current = self._working.get(instrument)

        if current is None:
            self._working[instrument] = _WorkingCandle(
                timestamp=slot,
                open=price,
                high=price,
                low=price,
                close=price,
                instrument=instrument,
                source=self.source,
                last_update_timestamp=timestamp,
            )
            return None

        if timestamp < current.last_update_timestamp:
            raise ValueError("out-of-order price update")

        if slot < current.timestamp:
            raise ValueError("out-of-order price update")

        if slot == current.timestamp:
            current.update(price, timestamp)
            return None

        completed = current.freeze()
        self._finalized_through[instrument] = current.timestamp
        self._working[instrument] = _WorkingCandle(
            timestamp=slot,
            open=price,
            high=price,
            low=price,
            close=price,
            instrument=instrument,
            source=self.source,
            last_update_timestamp=timestamp,
        )
        return completed

    def finalize_closed(self, as_of: datetime) -> list[Candle]:
        """Finalize working candles whose five-minute period has ended."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")

        now = to_ist(as_of)
        completed: list[Candle] = []

        for instrument, current in list(self._working.items()):
            close_time = current.timestamp + CANDLE_DURATION
            if now >= close_time:
                completed.append(current.freeze())
                self._finalized_through[instrument] = current.timestamp
                del self._working[instrument]

        return completed

    def current_candle(self, instrument: InstrumentId) -> Candle | None:
        """Return the current candle snapshot, which may be unfinished."""
        current = self._working.get(instrument)
        return current.freeze() if current is not None else None

