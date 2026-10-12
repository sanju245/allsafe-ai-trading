"""The contract every market-data provider must satisfy.

No real provider exists yet and none is chosen. A real adapter will subclass
``MarketDataProvider`` once a provider with suitable terms of use is selected.

Rules for adapters:

* Credentials come from server-side settings only (``app.config``). Never accept them
  from a request, never log them, never include them in ``repr`` or error messages.
* Return candles labelled with an honest ``DataSourceKind``. Anything not genuinely
  streamed from a live feed must not be labelled LIVE.
* Do not fix up or invent data. Return what the provider gave you; validation decides
  whether it is usable.
* Raise the exceptions below instead of returning empty or partial data silently.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSourceKind
from app.market_data.timeframes import Timeframe

MAX_CANDLES_PER_REQUEST = 10_000


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or returned a server error."""


class ProviderAuthError(ProviderError):
    """Credentials are missing, invalid or expired. Never include the credential."""


class ProviderRateLimitError(ProviderError):
    """The provider's rate limit was hit."""


class UnsupportedRequestError(ProviderError):
    """The provider cannot serve this instrument or timeframe."""


class CandleRequest(BaseModel):
    """What the application asks a provider for."""

    instrument: InstrumentId
    timeframe: Timeframe
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_CANDLES_PER_REQUEST)

    @model_validator(mode="after")
    def _check_range(self) -> "CandleRequest":
        for name in ("start", "end"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class MarketDataProvider(ABC):
    """Abstract source of candles."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short, stable provider name, used in ``DataSource.name``."""

    @property
    @abstractmethod
    def source_kind(self) -> DataSourceKind:
        """Honest label for the data this provider returns."""

    @property
    def supported_instruments(self) -> frozenset[InstrumentId]:
        return frozenset(InstrumentId)

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset(Timeframe)

    @abstractmethod
    def fetch_candles(self, request: CandleRequest) -> list[Candle]:
        """Return candles oldest to newest, each carrying instrument, timeframe, source.

        Raise a ``ProviderError`` subclass on failure.
        """
