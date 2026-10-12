"""Market-data endpoints.

These endpoints describe what the system supports and validate a series the caller
supplies. They do not fetch, store or return market prices.
"""

from fastapi import APIRouter

from app.market_data.instruments import Instrument, list_instruments
from app.market_data.schemas import ValidateSeriesRequest
from app.market_data.service import validate_series_request
from app.market_data.timeframes import TimeframeInfo, list_timeframes
from app.market_data.validation import ValidationReport

router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])


@router.get("/instruments", response_model=list[Instrument])
def get_instruments() -> list[Instrument]:
    """Supported instruments and their session metadata."""
    return list_instruments()


@router.get("/timeframes", response_model=list[TimeframeInfo])
def get_timeframes() -> list[TimeframeInfo]:
    """Supported candle timeframes."""
    return list_timeframes()


@router.post("/validate", response_model=ValidationReport)
def validate_series(request: ValidateSeriesRequest) -> ValidationReport:
    """Validate a supplied candle series and report every problem found.

    Returns 200 with ``is_valid: false`` for bad market data. A 422 means the request
    itself is malformed (unknown field, unsupported timeframe, too many candles).
    The supplied data is not stored and is never treated as live market data.
    """
    return validate_series_request(request)
