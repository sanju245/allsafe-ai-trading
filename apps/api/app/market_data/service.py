"""Glue between providers, validation and the API. Contains no FastAPI code."""

from dataclasses import dataclass
from datetime import datetime

from app.market_data.models import Candle, DataSource
from app.market_data.schemas import ValidateSeriesRequest
from app.market_data.validation import ValidationReport, validate_candles
from app.providers.base import (
    CandleRequest,
    MarketDataProvider,
    UnsupportedRequestError,
)


class InvalidMarketDataError(Exception):
    """Raised by ``FetchResult.require_valid`` when the series has errors."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__(
            f"Market data failed validation with {report.error_count} error(s): "
            + ", ".join(sorted(code for code in report.issue_counts))
        )
        self.report = report


@dataclass(frozen=True)
class FetchResult:
    candles: list[Candle]
    report: ValidationReport

    def require_valid(self) -> list[Candle]:
        """Return the candles, or raise. Use this before computing any signal."""
        if not self.report.is_valid:
            raise InvalidMarketDataError(self.report)
        return self.candles


def validate_series_request(
    request: ValidateSeriesRequest, *, now: datetime | None = None
) -> ValidationReport:
    """Validate a series supplied through the API. Nothing is stored."""
    candles = [
        Candle(
            timestamp=c.timestamp,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            instrument=request.instrument,
            timeframe=request.timeframe,
            source=request.source,
        )
        for c in request.candles
    ]
    return validate_candles(
        candles,
        instrument=request.instrument,
        timeframe=request.timeframe,
        source=request.source,
        as_of=request.as_of if request.as_of is not None else now,
        check_staleness=request.check_staleness,
        allowed_lag_candles=request.allowed_lag_candles,
    )


def fetch_and_validate(
    provider: MarketDataProvider,
    request: CandleRequest,
    *,
    as_of: datetime | None = None,
    check_staleness: bool | None = None,
    allowed_lag_candles: int = 1,
) -> FetchResult:
    """Fetch candles from a provider and validate them against what was asked for.

    Provider failures propagate as ``ProviderError`` subclasses. Invalid data is NOT
    dropped or repaired: the report says what is wrong and the caller decides.
    """
    if request.instrument not in provider.supported_instruments:
        raise UnsupportedRequestError(
            f"{provider.name} does not support instrument {request.instrument.value}"
        )
    if request.timeframe not in provider.supported_timeframes:
        raise UnsupportedRequestError(
            f"{provider.name} does not support timeframe {request.timeframe.value}"
        )

    candles = provider.fetch_candles(request)
    report = validate_candles(
        candles,
        instrument=request.instrument,
        timeframe=request.timeframe,
        source=DataSource(name=provider.name, kind=provider.source_kind),
        as_of=as_of,
        check_staleness=check_staleness,
        allowed_lag_candles=allowed_lag_candles,
    )
    return FetchResult(candles=candles, report=report)
