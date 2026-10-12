"""Market-data providers.

Phase 2 defines only the interface (``base``). No real provider is connected.
"""

from app.providers.base import (
    CandleRequest,
    MarketDataProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    UnsupportedRequestError,
)

__all__ = [
    "CandleRequest",
    "MarketDataProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "UnsupportedRequestError",
]
