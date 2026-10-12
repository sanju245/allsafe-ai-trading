"""Core market-data models.

``Candle`` is a plain data container. Constructing one does NOT mean the data is
sound: it can hold a high below its low, a NaN, or a naive timestamp. Soundness is
decided by ``app.market_data.validation.validate_candles``. This lets the API accept
bad data and report exactly what is wrong instead of failing with a generic error.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.market_data.instruments import InstrumentId
from app.market_data.sessions import candle_close_time
from app.market_data.timeframes import Timeframe


class DataSourceKind(StrEnum):
    """How trustworthy and current a data source claims to be.

    Only LIVE and DELAYED sources are ever checked for staleness. SAMPLE data exists
    for tests only and must never be presented as market data.
    """

    LIVE = "live"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    SAMPLE = "sample"


class DataSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=64)
    kind: DataSourceKind
    retrieved_at: datetime | None = None


class Candle(BaseModel):
    """One OHLCV candle.

    ``timestamp`` is the candle OPEN time. ``volume`` is None when the source does not
    provide it (common for index data); that is different from a real volume of 0.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    instrument: InstrumentId
    timeframe: Timeframe
    source: DataSource

    @property
    def close_time(self) -> datetime:
        """When this candle finishes (IST). Requires a timezone-aware timestamp."""
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return candle_close_time(self.timestamp, self.timeframe)

    def is_closed(self, as_of: datetime) -> bool:
        """True once the candle has finished, so it can drive a confirmed signal."""
        return self.close_time <= as_of
