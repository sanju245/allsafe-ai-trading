"""Request schema for validating a caller-supplied candle series.

The input is deliberately lenient about values (so bad data produces a validation
report, not a bare 422) but strict about shape: unknown fields are rejected, and an
unsupported instrument or timeframe is rejected outright.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.market_data.instruments import InstrumentId
from app.market_data.models import DataSource
from app.market_data.timeframes import Timeframe

# Public endpoint: bound the work one request can ask for.
MAX_CANDLES_PER_VALIDATION = 10_000


class CandleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class ValidateSeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: InstrumentId
    timeframe: Timeframe
    source: DataSource
    candles: list[CandleInput] = Field(max_length=MAX_CANDLES_PER_VALIDATION)
    # Reference "now". Defaults to the server clock; set it to validate old data
    # reproducibly. Must include a timezone.
    as_of: datetime | None = None
    # None means: check staleness only for LIVE and DELAYED sources.
    check_staleness: bool | None = None
    allowed_lag_candles: int = Field(default=1, ge=0, le=100)

    @field_validator("as_of")
    @classmethod
    def _as_of_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("as_of must include a timezone")
        return value
