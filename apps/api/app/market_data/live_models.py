"""Domain models for live market data, index/price updates, forming/confirmed candles, and feed health.

All timestamps represent timezone-aware instants normalized to IST (UTC+05:30).
Source timestamps are never invented when missing.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource
from app.market_data.timeframes import Timeframe


class FeedState(StrEnum):
    """Operational state of the live market-data feed."""

    LIVE = "live"
    STALE = "stale"
    CLOSED = "closed"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class TickRejectionReason(StrEnum):
    """Explicit reason why an incoming live update was rejected by validation."""

    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_VOLUME = "INVALID_VOLUME"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    STALE_TICK = "STALE_TICK"
    DUPLICATE_TICK = "DUPLICATE_TICK"
    OUT_OF_ORDER_TICK = "OUT_OF_ORDER_TICK"


class IncompleteReason(StrEnum):
    """Reason a 5-minute candle interval did not observe the full continuous slot."""

    STREAM_STARTED_MID_SLOT = "stream_started_mid_slot"
    FEED_INTERRUPTED_DURING_SLOT = "feed_interrupted_during_slot"


class LiveTick(BaseModel):
    """A validated live index/price update from the market-data stream."""

    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    provider_symbol: str
    price: float
    timestamp: datetime
    received_at: datetime
    volume: float | None = None
    source: DataSource


class RejectedTick(BaseModel):
    """Diagnostic record of an invalid or out-of-policy update that was rejected."""

    model_config = ConfigDict(frozen=True)

    reason: TickRejectionReason
    message: str
    instrument: InstrumentId | None = None
    provider_symbol: str | None = None
    price: float | None = None
    timestamp: datetime | None = None
    received_at: datetime


class LiveQuote(BaseModel):
    """Latest validated quote for a subscribed instrument."""

    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    symbol: str
    provider_symbol: str
    ltp: float
    timestamp: datetime
    received_at: datetime
    volume: float | None = None
    open_interest: float | None = None
    source: DataSource


class FormingCandle(BaseModel):
    """An in-progress (unconfirmed) 5-minute candle bucket."""

    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe = Timeframe.M5
    timestamp: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    tick_count: int = Field(ge=1)
    first_tick_at: datetime
    last_tick_at: datetime
    is_forming: bool = True
    is_confirmed: bool = False
    is_incomplete: bool = False
    incomplete_reasons: tuple[IncompleteReason, ...] = ()
    source: DataSource


class ConfirmedCandle(BaseModel):
    """A completed (confirmed) 5-minute candle bucket."""

    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe = Timeframe.M5
    timestamp: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    tick_count: int = Field(ge=1)
    first_tick_at: datetime
    last_tick_at: datetime
    is_forming: bool = False
    is_confirmed: bool = True
    is_incomplete: bool = False
    incomplete_reasons: tuple[IncompleteReason, ...] = ()
    source: DataSource

    def to_candle(self) -> Candle:
        """Convert to core Candle model for validation and indicator calculation."""
        return Candle(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            instrument=self.instrument,
            timeframe=self.timeframe,
            source=self.source,
        )


class MissingInterval(BaseModel):
    """Explicit record of one or more skipped 5-minute session slots between candles."""

    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe = Timeframe.M5
    previous_slot: datetime
    next_slot: datetime
    first_missing_slot: datetime
    last_missing_slot: datetime
    missing_slot_count: int = Field(ge=1)
    missing_slots: tuple[datetime, ...]
    detected_at: datetime
