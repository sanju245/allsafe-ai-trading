"""Read-only Upstox Historical Candle V3 adapter for 15-minute index candles."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle, DataSource, DataSourceKind
from app.market_data.timeframes import Timeframe
from app.providers.base import (
    CandleRequest,
    MarketDataProvider,
    ProviderUnavailableError,
    UnsupportedRequestError,
)

_IST = ZoneInfo("Asia/Kolkata")
_UPSTOX_BASE_URL = "https://api.upstox.com/v3/historical-candle"
# Match the identified client used for Upstox's authorized feed endpoint; the
# provider has returned Cloudflare 1010 blocks for urllib's default User-Agent.
_UPSTOX_USER_AGENT = "AllSafeAITrading/0.2"
_TIMEOUT_SECONDS = 12
MAX_RANGE_DAYS = 30
_INSTRUMENT_KEYS: dict[InstrumentId, str] = {
    InstrumentId.NIFTY50: "NSE_INDEX|Nifty 50",
    InstrumentId.BANKNIFTY: "NSE_INDEX|Nifty Bank",
}


class UpstoxHistoryError(Exception):
    """A safe error for the browser; never stores provider response bodies or tokens."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def fetch_15m_candles(
    instrument: InstrumentId,
    *,
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
    as_of: datetime | None = None,
) -> list[Candle]:
    """Fetch a bounded inclusive date range, returning completed candles oldest first."""
    if start_date > end_date or (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
        raise UpstoxHistoryError(
            422,
            f"Choose a date range of {MAX_RANGE_DAYS} days or less.",
        )

    config = settings or get_settings()
    token_secret = config.upstox_access_token
    token = token_secret.get_secret_value().strip() if token_secret is not None else ""
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise UpstoxHistoryError(
            503,
            "Upstox historical charts are not configured on the API. Add UPSTOX_ACCESS_TOKEN to the server environment.",
        )

    instrument_key = quote(_INSTRUMENT_KEYS[instrument], safe="")
    url = (
        f"{_UPSTOX_BASE_URL}/{instrument_key}/minutes/15/"
        f"{end_date.isoformat()}/{start_date.isoformat()}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": _UPSTOX_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
    except HTTPError as exc:
        status_code = exc.code
        gateway_block = False
        # Upstox may return a Cloudflare 1010 diagnostic for client policy
        # blocks. Inspect only the known boolean/code fields and never echo or
        # log the response body, which can contain sensitive diagnostics.
        try:
            error_payload = json.loads(exc.read(4096).decode("utf-8"))
            gateway_block = (
                isinstance(error_payload, dict)
                and error_payload.get("cloudflare_error") is True
                and error_payload.get("error_code") in (1010, "1010")
            )
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            pass
        exc.close()
        if gateway_block:
            raise UpstoxHistoryError(
                502,
                "Upstox's gateway blocked the API service request (Cloudflare 1010).",
            ) from None
        if status_code in {401, 403}:
            raise UpstoxHistoryError(
                502,
                "Upstox rejected the configured access token. Check the server token and its read-only market-data permission.",
            ) from None
        if status_code == 429:
            raise UpstoxHistoryError(
                503,
                "Upstox is rate-limiting historical chart requests. Try again shortly.",
            ) from None
        raise UpstoxHistoryError(502, "Upstox historical candle service returned an error.") from None
    except (URLError, TimeoutError, OSError):
        raise UpstoxHistoryError(502, "Upstox historical candle service could not be reached.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise UpstoxHistoryError(502, "Upstox returned an unreadable historical candle response.") from None

    if not isinstance(body, dict) or body.get("status") != "success":
        raise UpstoxHistoryError(502, "Upstox returned an invalid historical candle response.")
    data = body.get("data")
    rows = data.get("candles") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise UpstoxHistoryError(502, "Upstox returned an invalid historical candle response.")

    retrieved_at = (as_of or datetime.now(_IST)).astimezone(_IST)
    source = DataSource(
        name="Upstox Historical Candle V3",
        kind=DataSourceKind.HISTORICAL,
        retrieved_at=retrieved_at,
    )
    candles_by_timestamp: dict[datetime, Candle] = {}
    for row in rows:
        candle = _parse_candle_row(row, instrument=instrument, source=source)
        local_date = candle.timestamp.astimezone(_IST).date()
        if not start_date <= local_date <= end_date:
            continue
        if candle.timestamp + Timeframe.M15.interval > retrieved_at:
            continue
        candles_by_timestamp[candle.timestamp] = candle
    return [candles_by_timestamp[key] for key in sorted(candles_by_timestamp)]


class UpstoxHistoricalProvider(MarketDataProvider):
    """Provide recent Upstox history to the shared live/indicator runtime."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    @property
    def name(self) -> str:
        return "Upstox Historical Candle V3"

    @property
    def source_kind(self) -> DataSourceKind:
        return DataSourceKind.HISTORICAL

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset({Timeframe.M15})

    def fetch_candles(self, request: CandleRequest) -> list[Candle]:
        if request.timeframe is not Timeframe.M15:
            raise UnsupportedRequestError("Upstox history supports only 15-minute candles.")

        end = (request.end or datetime.now(_IST)).astimezone(_IST)
        start = (request.start or end - timedelta(days=4)).astimezone(_IST)
        start_date = start.date()
        end_date = end.date()
        if start_date > end_date:
            raise UnsupportedRequestError("Upstox history start must not follow its end.")
        # The provider accepts at most 30 inclusive calendar dates. Keep the most
        # recent supported part of a wider runtime warm-up window.
        if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
            start_date = end_date - timedelta(days=MAX_RANGE_DAYS - 1)

        try:
            candles = fetch_15m_candles(
                request.instrument,
                start_date=start_date,
                end_date=end_date,
                settings=self.settings,
                as_of=end,
            )
        except UpstoxHistoryError as exc:
            if exc.status_code == 422:
                raise UnsupportedRequestError(exc.detail) from None
            raise ProviderUnavailableError(exc.detail) from None

        if request.limit is not None:
            candles = candles[-request.limit:]
        return candles


def _parse_candle_row(
    row: Any,
    *,
    instrument: InstrumentId,
    source: DataSource,
) -> Candle:
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        raise UpstoxHistoryError(502, "Upstox returned a malformed candle.")
    timestamp_value = row[0]
    if not isinstance(timestamp_value, str):
        raise UpstoxHistoryError(502, "Upstox returned a malformed candle timestamp.")
    try:
        timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
    except ValueError:
        raise UpstoxHistoryError(502, "Upstox returned a malformed candle timestamp.") from None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise UpstoxHistoryError(502, "Upstox returned a candle timestamp without a timezone.")
    timestamp = timestamp.astimezone(_IST)

    try:
        open_price, high, low, close = (float(value) for value in row[1:5])
    except (TypeError, ValueError, OverflowError):
        raise UpstoxHistoryError(502, "Upstox returned invalid candle prices.") from None
    prices = (open_price, high, low, close)
    if (
        not all(math.isfinite(price) and price > 0 for price in prices)
        or high < max(open_price, close, low)
        or low > min(open_price, close, high)
    ):
        raise UpstoxHistoryError(502, "Upstox returned invalid OHLC values.")
    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        # Index volume is not meaningful as traded quantity.
        volume=None,
        instrument=instrument,
        timeframe=Timeframe.M15,
        source=source,
    )
