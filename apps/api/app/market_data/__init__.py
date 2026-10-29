"""Market-data foundation: candle model, timeframes, instruments and validation.

Nothing here fetches data or calculates indicators. Data providers (Phase 2 interface,
real adapters later) feed candles in; ``validate_candles`` decides whether they are
sound enough to use.
"""

from app.market_data.instruments import INSTRUMENTS, Instrument, InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.timeframes import Timeframe
from app.market_data.validation import (
    IssueCode,
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_candles,
)

__all__ = [
    "INSTRUMENTS",
    "Candle",
    "DataSource",
    "DataSourceKind",
    "Instrument",
    "InstrumentId",
    "IssueCode",
    "Severity",
    "Timeframe",
    "ValidationIssue",
    "ValidationReport",
    "validate_candles",
]
