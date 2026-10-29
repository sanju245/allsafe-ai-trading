"""Groww historical candle provider implementing MarketDataProvider.

Uses `GrowwAPI.get_historical_candles` (the official non-deprecated API in growwapi>=1.0.0)
to fetch historical OHLC candles for NIFTY 50 (`NSE-NIFTY`) and BANK NIFTY (`NSE-BANKNIFTY`)
and normalize them into `app.market_data.models.Candle` for validation and 5-indicator warm-up.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.sessions import IST, to_ist
from app.market_data.timeframes import Timeframe
from app.providers.base import (
    CandleRequest,
    MarketDataProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    UnsupportedRequestError,
)
from app.providers.groww_auth import (
    GrowwCredentials,
    is_groww_auth_exception,
    redact_groww_secrets,
)
from app.providers.groww_instruments import GrowwInstrumentResolver

GROWW_CANDLE_INTERVAL_BY_TIMEFRAME: dict[Timeframe, str] = {
    Timeframe.M1: "1minute",
    Timeframe.M3: "3minute",
    Timeframe.M5: "5minute",
    Timeframe.M15: "15minute",
    Timeframe.H1: "1hour",
    Timeframe.D1: "1day",
}

GROWW_INTERVAL_MINUTES_BY_TIMEFRAME: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M3: 3,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
    Timeframe.D1: 1440,
}

# Official per-request duration limits from Groww Backtesting / Historical Data docs
MAX_DAYS_PER_REQUEST_BY_TIMEFRAME: dict[Timeframe, int] = {
    Timeframe.M1: 30,
    Timeframe.M3: 30,
    Timeframe.M5: 30,
    Timeframe.M15: 90,
    Timeframe.H1: 180,
    Timeframe.D1: 180,
}


def _parse_groww_candle_timestamp(raw_ts: Any) -> datetime:
    """Parse a Groww historical candle timestamp into a timezone-aware IST datetime.

    Never invents a timestamp if raw_ts is missing or unparseable.
    """
    if raw_ts is None or isinstance(raw_ts, bool):
        raise ProviderUnavailableError("Groww historical candle is missing a timestamp.")

    if isinstance(raw_ts, datetime):
        if raw_ts.tzinfo is None or raw_ts.utcoffset() is None:
            return raw_ts.replace(tzinfo=IST)
        return to_ist(raw_ts)

    if isinstance(raw_ts, (int, float)):
        if not math.isfinite(raw_ts) or raw_ts <= 0:
            raise ProviderUnavailableError(f"Invalid numeric candle timestamp from Groww: {raw_ts!r}")
        epoch_sec = float(raw_ts) / 1000.0 if raw_ts > 1e11 else float(raw_ts)
        return datetime.fromtimestamp(epoch_sec, tz=UTC).astimezone(IST)

    if isinstance(raw_ts, str) and raw_ts.strip():
        text = raw_ts.strip()
        if text.isdigit():
            return _parse_groww_candle_timestamp(int(text))
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None or dt.utcoffset() is None:
                # Groww historical candle string timestamps ("YYYY-MM-DDTHH:MM:SS" / "YYYY-MM-DD HH:MM:SS")
                # represent NSE local time (IST).
                return dt.replace(tzinfo=IST)
            return to_ist(dt)
        except ValueError as exc:
            raise ProviderUnavailableError(
                f"Unparseable candle timestamp string from Groww: {text!r}"
            ) from exc

    raise ProviderUnavailableError(f"Unsupported candle timestamp type from Groww: {type(raw_ts).__name__}")


def _format_ist_for_groww(dt: datetime) -> str:
    """Format a timezone-aware datetime as 'YYYY-MM-DD HH:MM:SS' in IST for Groww API requests."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return to_ist(dt).strftime("%Y-%m-%d %H:%M:%S")


class GrowwHistoricalProvider(MarketDataProvider):
    """Fetches historical candles from Groww Trading API and normalizes them into Candle models."""

    def __init__(
        self,
        *,
        groww_client: Any,
        instrument_resolver: GrowwInstrumentResolver,
        credentials: GrowwCredentials | None = None,
    ) -> None:
        self._client = groww_client
        self._resolver = instrument_resolver
        self._credentials = credentials or GrowwCredentials()

    @property
    def name(self) -> str:
        return "groww"

    @property
    def source_kind(self) -> DataSourceKind:
        return DataSourceKind.HISTORICAL

    @property
    def supported_instruments(self) -> frozenset[InstrumentId]:
        return frozenset((InstrumentId.NIFTY50, InstrumentId.BANKNIFTY))

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset(GROWW_CANDLE_INTERVAL_BY_TIMEFRAME.keys())

    def _redact(self, text: Any) -> str:
        return redact_groww_secrets(str(text), secrets=self._credentials.secret_values())

    def _translate_exception(self, exc: BaseException) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        msg = self._redact(exc)
        cls_name = exc.__class__.__name__.lower()
        if is_groww_auth_exception(exc):
            return ProviderAuthError(f"Groww historical API authentication error: {msg}")
        if "ratelimit" in cls_name or "rate limit" in msg.lower() or "429" in msg:
            return ProviderRateLimitError(f"Groww historical API rate limit exceeded: {msg}")
        return ProviderUnavailableError(f"Groww historical API request failed: {msg}")

    def fetch_candles(self, request: CandleRequest) -> list[Candle]:
        """Fetch historical candles from Groww and return oldest-to-newest Candle objects."""
        if request.instrument not in self.supported_instruments:
            raise UnsupportedRequestError(
                f"Groww provider does not support instrument {request.instrument.value}"
            )
        if request.timeframe not in self.supported_timeframes:
            raise UnsupportedRequestError(
                f"Groww provider does not support timeframe {request.timeframe.value}"
            )

        now_ist = datetime.now(IST)
        end_dt = to_ist(request.end) if request.end is not None else now_ist
        max_days = MAX_DAYS_PER_REQUEST_BY_TIMEFRAME[request.timeframe]
        default_lookback_days = min(5, max_days) if request.timeframe != Timeframe.D1 else 60
        start_dt = (
            to_ist(request.start)
            if request.start is not None
            else (end_dt - timedelta(days=default_lookback_days))
        )

        if (end_dt - start_dt).total_seconds() > max_days * 86400:
            raise UnsupportedRequestError(
                f"Groww maximum historical duration for {request.timeframe.value} is {max_days} days per request."
            )

        descriptor = self._resolver.resolve(request.instrument)
        start_str = _format_ist_for_groww(start_dt)
        end_str = _format_ist_for_groww(end_dt)

        try:
            get_candles_fn = getattr(self._client, "get_historical_candles", None)
            if callable(get_candles_fn):
                raw_resp = get_candles_fn(
                    exchange=descriptor.exchange,
                    segment=descriptor.segment,
                    groww_symbol=descriptor.groww_symbol,
                    start_time=start_str,
                    end_time=end_str,
                    candle_interval=GROWW_CANDLE_INTERVAL_BY_TIMEFRAME[request.timeframe],
                )
            else:
                legacy_fn = getattr(self._client, "get_historical_candle_data", None)
                if not callable(legacy_fn):
                    raise ProviderUnavailableError(
                        "Groww client does not expose get_historical_candles or get_historical_candle_data."
                    )
                raw_resp = legacy_fn(
                    trading_symbol=descriptor.trading_symbol,
                    exchange=descriptor.exchange,
                    segment=descriptor.segment,
                    start_time=start_str,
                    end_time=end_str,
                    interval_in_minutes=GROWW_INTERVAL_MINUTES_BY_TIMEFRAME[request.timeframe],
                )
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        if not isinstance(raw_resp, dict) or "candles" not in raw_resp:
            raise ProviderUnavailableError(
                "Groww historical API returned a malformed response (missing 'candles' key)."
            )

        raw_candles = raw_resp.get("candles")
        if not isinstance(raw_candles, list):
            raise ProviderUnavailableError(
                "Groww historical API 'candles' field is not a list."
            )

        source = DataSource(
            name=self.name,
            kind=self.source_kind,
            retrieved_at=now_ist,
        )
        is_index = descriptor.instrument_type == "IDX"
        candles: list[Candle] = []

        for row in raw_candles:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                raise ProviderUnavailableError(
                    "Groww historical candle row must have at least [timestamp, open, high, low, close]."
                )
            ts = _parse_groww_candle_timestamp(row[0])
            open_p = float(row[1])
            high_p = float(row[2])
            low_p = float(row[3])
            close_p = float(row[4])

            raw_vol = row[5] if len(row) > 5 else None
            # Spot indices (NIFTY 50, BANK NIFTY) have no real traded volume; do not fabricate volume=0
            if is_index and (raw_vol is None or raw_vol == 0):
                vol: float | None = None
            elif raw_vol is None:
                vol = None
            else:
                vol = float(raw_vol)

            candles.append(
                Candle(
                    timestamp=ts,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=vol,
                    instrument=request.instrument,
                    timeframe=request.timeframe,
                    source=source,
                )
            )

        candles.sort(key=lambda c: c.timestamp)
        if request.limit is not None:
            candles = candles[-request.limit :]
        return candles
