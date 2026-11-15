"""Read-only Upstox V3 index feed adapter with verified TLS.

Upstox issues a single-use authorized WebSocket URL. The bearer token is sent only to
the HTTPS authorization endpoint; the WebSocket connects to the returned Upstox URL
with certificate and hostname verification enabled. Only the SDK's protobuf decoder
is reused; its WebSocket connector disables TLS verification and is not used here.
"""

import importlib
import json
import logging
import re
import ssl
import threading
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import (
    LiveSessionAggregator,
    is_regular_session_ist,
)
from app.market_data.live_models import FeedState
from app.market_data.models import DataSource, DataSourceKind
from app.market_data.sessions import IST, to_ist
from app.providers.groww_stream import InstrumentFeedStatus, StreamStatusSnapshot

logger = logging.getLogger(__name__)

UPSTOX_INDEX_KEYS = {
    InstrumentId.NIFTY50: "NSE_INDEX|Nifty 50",
    InstrumentId.BANKNIFTY: "NSE_INDEX|Nifty Bank",
}
AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"


def _timestamp_from_millis(value: Any) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        millis = int(value)
        if millis <= 0:
            return None
        return datetime.fromtimestamp(millis / 1000, tz=UTC).astimezone(IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _validate_authorized_uri(uri: str) -> str:
    """Accept only an Upstox-owned secure WebSocket URL containing its one-time code."""
    parsed = urlparse(uri)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "wss"
        or not hostname
        or not (hostname == "upstox.com" or hostname.endswith(".upstox.com"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
        or not parsed.query
        or not any(part.startswith("code=") for part in parsed.query.split("&"))
    ):
        raise ValueError("Upstox returned an invalid authorized feed URL.")
    return uri


def _request_authorized_uri(access_token: str) -> str:
    # Render values are normally the raw token. Accept a pasted header value too,
    # without accidentally sending `Bearer Bearer ...` to Upstox.
    token = access_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise PermissionError("Upstox Analytics token is empty.")
    request = Request(
        AUTHORIZE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = json.load(response)
    except HTTPError as exc:
        # Upstox's response may contain provider diagnostics. Read only a known
        # error-code field and never log the raw response body or token.
        error_code = None
        try:
            payload = json.loads(exc.read(4096).decode("utf-8"))
            if isinstance(payload, dict):
                error_code = payload.get("errorCode") or payload.get("error_code")
                errors = payload.get("errors")
                if not error_code and isinstance(errors, list) and errors:
                    first_error = errors[0]
                    if isinstance(first_error, dict):
                        error_code = first_error.get("errorCode") or first_error.get(
                            "error_code"
                        )
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            pass
        safe_code = (
            error_code
            if isinstance(error_code, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", error_code)
            else None
        )
        if exc.code in (401, 403):
            detail = f"; Upstox error code {safe_code}" if safe_code else ""
            raise PermissionError(
                f"Upstox authorization was rejected (HTTP {exc.code}{detail})."
            ) from None
        raise RuntimeError(
            f"Upstox authorization endpoint returned HTTP {exc.code}."
        ) from None
    if not isinstance(body, dict):
        raise RuntimeError("Upstox authorization returned an invalid response.")  # noqa: TRY004
    data = body.get("data")
    uri = data.get("authorized_redirect_uri") if isinstance(data, dict) else None
    if not isinstance(uri, str):
        raise RuntimeError("Upstox authorization response did not include a feed URL.")  # noqa: TRY004
    return _validate_authorized_uri(uri)


class UpstoxLiveStreamManager:
    """Interface-compatible manager for Upstox V3's read-only market data feed."""

    provider = "upstox"

    def __init__(
        self,
        *,
        access_token: str = "",
        streaming_enabled: bool = False,
        stale_after_seconds: float = 60.0,
        max_future_skew_seconds: float = 5.0,
        max_confirmed_candles: int = 500,
        authorizer: Any = None,
        websocket_factory: Any = None,
    ) -> None:
        self.access_token = access_token
        self.streaming_enabled = bool(streaming_enabled)
        self.stale_after_seconds = float(stale_after_seconds)
        self.aggregator = LiveSessionAggregator(
            source=DataSource(name="upstox", kind=DataSourceKind.LIVE),
            max_confirmed_candles=max_confirmed_candles,
            max_future_skew_seconds=max_future_skew_seconds,
            max_staleness_seconds=None,
        )
        self._authorizer = authorizer or _request_authorized_uri
        self._websocket_factory = websocket_factory
        self._ws: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._connected = False
        self._authenticated = False
        self._failed = False
        self._disconnected = False
        self._sdk_installed = False
        self._sdk_compatible = False
        self._last_error: str | None = None
        self._last_message_at: datetime | None = None
        self._last_connected_at: datetime | None = None
        self._reconnect_attempts = 0
        self._next_reconnect_delay: float | None = None

    @property
    def groww_client(self) -> None:
        return None

    @property
    def instrument_resolver(self) -> None:
        return None

    def set_historical_candle_count(
        self, _instrument: InstrumentId, _count: int
    ) -> None:
        return

    def _record_error(self, message: Any, *, permanent: bool = False) -> None:
        safe_message = (
            str(message).replace(self.access_token, "[REDACTED]")
            if self.access_token
            else str(message)
        )
        self._last_error = safe_message[:300]
        if permanent:
            self._failed = True
            self._connected = False
            self._authenticated = False
        logger.warning("Upstox live feed error: %s", self._last_error)

    def start(self, *, as_of: datetime | None = None) -> bool:
        if not self.streaming_enabled:
            return False
        if not self.access_token.strip():
            self._record_error(
                "Upstox feed is enabled but its server-side Analytics token is missing.",
                permanent=True,
            )
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._failed = False
        self._reconnect_attempts = 0
        self._thread = threading.Thread(
            target=self._connection_loop, name="upstox-market-feed", daemon=True
        )
        self._thread.start()
        return True

    def _decode_message(self, payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            return payload
        if not isinstance(payload, (bytes, bytearray)):
            return None
        try:
            proto_module = importlib.import_module(
                "upstox_client.feeder.proto.MarketDataFeedV3_pb2"
            )
            from google.protobuf.json_format import MessageToDict

            decoded = proto_module.FeedResponse.FromString(bytes(payload))
            value = MessageToDict(decoded)
            return value if isinstance(value, dict) else None
        except Exception as exc:  # noqa: BLE001 - never expose payload contents or credentials
            self._record_error(
                f"Upstox protobuf message could not be decoded ({type(exc).__name__})."
            )
            return None

    def _connection_loop(self) -> None:
        try:
            import websocket

            proto_module = importlib.import_module(
                "upstox_client.feeder.proto.MarketDataFeedV3_pb2"
            )
            if not hasattr(proto_module, "FeedResponse"):
                raise ImportError("Upstox V3 feed decoder is unavailable.")

            self._websocket_factory = (
                self._websocket_factory or websocket.create_connection
            )
            self._sdk_installed = True
            self._sdk_compatible = True
        except ImportError:
            self._record_error(
                "Upstox feed dependencies are not installed.", permanent=True
            )
            return

        while not self._stop_event.is_set() and not self._failed:
            try:
                # The long-lived bearer token is sent only over verified HTTPS. The
                # returned URL is one-time and already authorized, so it gets no bearer header.
                authorized_uri = self._authorizer(self.access_token)
                _validate_authorized_uri(authorized_uri)
                ws = self._websocket_factory(
                    authorized_uri,
                    timeout=10,
                    header={"Accept": "*/*"},
                    sslopt={"context": ssl.create_default_context()},
                    redirect_limit=0,
                    enable_multithread=True,
                )
                self._ws = ws
                self._connected = True
                self._authenticated = True
                self._disconnected = False
                self._last_error = None
                self._last_connected_at = datetime.now(IST)
                self._reconnect_attempts = 0
                self._next_reconnect_delay = None
                self._send_subscription(ws)
                ws.settimeout(5)
                while not self._stop_event.is_set():
                    try:
                        payload = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if payload is None:
                        break
                    self.handle_message(payload)
            except PermissionError as exc:
                self._record_error(exc, permanent=True)
            except Exception as exc:  # noqa: BLE001 - vendor/socket errors are intentionally redacted
                if not self._stop_event.is_set():
                    self._record_error(
                        f"Upstox secure feed connection failed ({type(exc).__name__})."
                    )
            finally:
                ws = self._ws
                self._ws = None
                self._connected = False
                self._authenticated = False
                if ws is not None:
                    try:
                        ws.close()
                    except Exception as exc:  # noqa: BLE001 - shutdown continues after close errors
                        logger.debug(
                            "Upstox socket close failed (%s).", type(exc).__name__
                        )
                if not self._stop_event.is_set():
                    self._disconnected = True
                    self.aggregator.mark_disconnection(datetime.now(IST))

            if self._stop_event.is_set() or self._failed:
                break
            self._reconnect_attempts += 1
            if self._reconnect_attempts > 8:
                self._record_error(
                    "Upstox feed exhausted automatic reconnect attempts.",
                    permanent=True,
                )
                break
            delay = min(60.0, float(2 ** (self._reconnect_attempts - 1)))
            self._next_reconnect_delay = delay
            self._stop_event.wait(delay)
        self._next_reconnect_delay = None

    def _send_subscription(self, ws: Any) -> None:
        import websocket

        request = {
            "guid": str(uuid.uuid4()),
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": list(UPSTOX_INDEX_KEYS.values()),
            },
        }
        ws.send(
            json.dumps(request).encode("utf-8"), opcode=websocket.ABNF.OPCODE_BINARY
        )

    def handle_message(self, payload: Any, *, as_of: datetime | None = None) -> int:
        message = self._decode_message(payload)
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        feeds = message.get("feeds") if isinstance(message, dict) else None
        if not isinstance(feeds, dict):
            return 0
        accepted = 0
        self._last_message_at = now
        for instrument, key in UPSTOX_INDEX_KEYS.items():
            feed = feeds.get(key)
            if not isinstance(feed, dict):
                continue
            full = feed.get("fullFeed")
            index_feed = full.get("indexFF") if isinstance(full, dict) else None
            ltpc = (
                index_feed.get("ltpc")
                if isinstance(index_feed, dict)
                else feed.get("ltpc")
            )
            if not isinstance(ltpc, dict):
                continue
            try:
                price = float(ltpc.get("ltp"))
            except (TypeError, ValueError):
                continue
            timestamp = _timestamp_from_millis(ltpc.get("ltt"))
            result = self.aggregator.process_tick(
                symbol=instrument,
                price=price,
                timestamp=timestamp,
                volume=None,
                provider_symbol=key,
                as_of=now,
            )
            accepted += int(result.accepted)
        return accepted

    def evaluate_instrument_state(
        self, instrument: InstrumentId, *, as_of: datetime | None = None
    ) -> InstrumentFeedStatus:
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self.aggregator.finalize_closed(now)
        quote = self.aggregator.get_latest_quote(instrument)
        candles = self.aggregator.get_confirmed_candles(instrument)
        forming = self.aggregator.get_forming_candle(instrument)
        age = max(0.0, (now - quote.timestamp).total_seconds()) if quote else None
        if self._failed:
            state = FeedState.FAILED
        elif not is_regular_session_ist(now):
            state = FeedState.CLOSED
        elif self._disconnected and not self._connected:
            state = FeedState.DISCONNECTED
        elif quote is None:
            state = FeedState.UNAVAILABLE
        elif not self._connected or (
            age is not None and age > self.stale_after_seconds
        ):
            state = FeedState.STALE
        else:
            state = FeedState.LIVE
        return InstrumentFeedStatus(
            instrument=instrument,
            groww_symbol=UPSTOX_INDEX_KEYS[instrument],
            trading_symbol="NIFTY"
            if instrument is InstrumentId.NIFTY50
            else "BANKNIFTY",
            exchange_token=UPSTOX_INDEX_KEYS[instrument],
            feed_state=state,
            last_tick_at=quote.timestamp if quote else None,
            age_seconds=round(age, 3) if age is not None else None,
            is_stale=state in {FeedState.STALE, FeedState.DISCONNECTED},
            historical_candle_count=0,
            confirmed_candle_count=len(candles),
            has_forming_candle=forming is not None,
            missing_interval_count=len(
                self.aggregator.get_missing_intervals(instrument)
            ),
            rejected_tick_count=self.aggregator.get_rejected_count(instrument),
        )

    def status_snapshot(self, *, as_of: datetime | None = None) -> StreamStatusSnapshot:
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        states = {
            inst: self.evaluate_instrument_state(inst, as_of=now)
            for inst in InstrumentId
        }
        if self._failed:
            overall = FeedState.FAILED
        elif not is_regular_session_ist(now):
            overall = FeedState.CLOSED
        elif self._disconnected and not self._connected:
            overall = FeedState.DISCONNECTED
        elif any(item.feed_state is FeedState.LIVE for item in states.values()):
            overall = FeedState.LIVE
        elif any(item.feed_state is FeedState.STALE for item in states.values()):
            overall = FeedState.STALE
        else:
            overall = FeedState.UNAVAILABLE
        return StreamStatusSnapshot(
            feed_state=overall,
            streaming_enabled=self.streaming_enabled,
            connected=self._connected,
            authenticated=self._authenticated,
            auth_mode="analytics_token" if self.access_token.strip() else "none",
            provider="upstox",
            session_open=is_regular_session_ist(now),
            sdk_installed=self._sdk_installed,
            sdk_compatible=self._sdk_compatible,
            subscribed_symbols=tuple(UPSTOX_INDEX_KEYS.values()),
            reconnect_attempts=self._reconnect_attempts,
            next_reconnect_delay_seconds=self._next_reconnect_delay,
            last_connected_at=self._last_connected_at,
            last_message_at=self._last_message_at,
            last_error=self._last_error,
            checked_at=now,
            instruments=states,
        )

    def stop(self, *, as_of: datetime | None = None) -> None:
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self._stop_event.set()
        self.aggregator.mark_disconnection(now)
        self._connected = False
        self._authenticated = False
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception as exc:  # noqa: BLE001 - shutdown continues after close errors
                logger.debug(
                    "Upstox socket close failed during stop (%s).", type(exc).__name__
                )
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2)
