"""Groww live index feed adapter (`GrowwFeed.subscribe_index_value` / `get_index_value`).

Responsibilities:
* Authenticate using the single selected `GrowwAuthMode` without silent fallback.
* Resolve NIFTY 50 and BANK NIFTY `exchange_token` values from authoritative Groww instrument metadata.
* Subscribe via `GrowwFeed.subscribe_index_value` and read updates via `GrowwFeed.get_index_value`.
* Parse `tsInMillis` and `value` into timezone-aware IST updates with `volume=None` (never fabricating volume or time).
* Manage bounded exponential reconnect backoff, feed states (`live`, `stale`, `disconnected`, `closed`, `failed`, `unavailable`),
  and strict credential redaction.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import math
import threading
from typing import Any

from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import (
    LiveSessionAggregator,
    TickProcessResult,
    groww_symbol_for,
    is_regular_session_ist,
)
from app.market_data.live_models import FeedState
from app.market_data.models import DataSource, DataSourceKind
from app.market_data.sessions import IST, to_ist
from app.providers.base import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.providers.groww_auth import (
    GrowwAuthMode,
    GrowwCredentials,
    authenticate_groww_client,
    is_groww_auth_exception,
    redact_groww_secrets,
    verify_groww_sdk_compatibility,
)
from app.providers.groww_instruments import (
    GrowwInstrumentDescriptor,
    GrowwInstrumentResolver,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedGrowwIndexUpdate:
    """Normalized fields extracted from `GrowwFeed.get_index_value()` or `GrowwAPI.get_quote()`."""

    exchange: str
    segment: str
    exchange_token: str
    value: float
    timestamp: datetime | None


def _parse_millis_timestamp(raw_ts: Any) -> datetime | None:
    """Convert Groww `tsInMillis` (or epoch seconds) to timezone-aware IST datetime; never invent time."""
    if raw_ts is None or isinstance(raw_ts, bool):
        return None
    if isinstance(raw_ts, datetime):
        if raw_ts.tzinfo is None or raw_ts.utcoffset() is None:
            return raw_ts
        return to_ist(raw_ts)
    if isinstance(raw_ts, (int, float)):
        if not math.isfinite(raw_ts) or raw_ts <= 0:
            return None
        epoch_sec = float(raw_ts) / 1000.0 if raw_ts > 1e11 else float(raw_ts)
        return datetime.fromtimestamp(epoch_sec, tz=timezone.utc).astimezone(IST)
    if isinstance(raw_ts, str) and raw_ts.strip():
        text = raw_ts.strip()
        try:
            num = float(text)
            return _parse_millis_timestamp(num)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text)
                return dt if (dt.tzinfo is None or dt.utcoffset() is None) else to_ist(dt)
            except ValueError:
                return None
    return None


def parse_groww_index_feed_Snapshot(
    payload: Any,
    *,
    filter_exchange_token: str | None = None,
) -> list[ParsedGrowwIndexUpdate]:
    """Parse the nested dictionary returned by `GrowwFeed.get_index_value()`.

    Official Groww format:
    `{"NSE": {"CASH": {"NIFTY": {"tsInMillis": 1746174582295.0, "value": 24386.7}}}}`
    (Also handles an outer `{"index_value": ...}` wrapper if present).
    """
    if not isinstance(payload, dict):
        return []

    root_map = payload.get("index_value") if isinstance(payload.get("index_value"), dict) else payload
    updates: list[ParsedGrowwIndexUpdate] = []

    for exchange, seg_map in root_map.items():
        if not isinstance(seg_map, dict):
            continue
        for segment, token_map in seg_map.items():
            if not isinstance(token_map, dict):
                continue
            for token, entry in token_map.items():
                if not isinstance(entry, dict):
                    continue
                if filter_exchange_token is not None and str(token) != str(filter_exchange_token):
                    continue
                if "value" not in entry and "ltp" not in entry:
                    continue
                raw_val = entry.get("value", entry.get("ltp"))
                try:
                    val = float(raw_val) if not isinstance(raw_val, bool) else float("nan")
                except (TypeError, ValueError):
                    val = float("nan")
                ts = _parse_millis_timestamp(entry.get("tsInMillis", entry.get("timestamp")))
                updates.append(
                    ParsedGrowwIndexUpdate(
                        exchange=str(exchange).upper(),
                        segment=str(segment).upper(),
                        exchange_token=str(token).strip(),
                        value=val,
                        timestamp=ts,
                    )
                )
    return updates


@dataclass(frozen=True)
class ReconnectBackoffPolicy:
    """Deterministic exponential reconnect backoff policy."""

    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    multiplier: float = 2.0
    max_attempts: int = 8

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        raw = self.base_delay_seconds * (self.multiplier ** (attempt - 1))
        return float(min(self.max_delay_seconds, raw))

    def can_retry(self, attempt: int) -> bool:
        return 1 <= attempt <= self.max_attempts


@dataclass
class InstrumentFeedStatus:
    """Health snapshot for one subscribed instrument."""

    instrument: InstrumentId
    groww_symbol: str
    trading_symbol: str
    exchange_token: str | None
    feed_state: FeedState
    last_tick_at: datetime | None
    age_seconds: float | None
    is_stale: bool
    historical_candle_count: int
    confirmed_candle_count: int
    has_forming_candle: bool
    missing_interval_count: int
    rejected_tick_count: int


@dataclass
class StreamStatusSnapshot:
    """Overall operational snapshot of the Groww live market-data stream."""

    feed_state: FeedState
    streaming_enabled: bool
    connected: bool
    authenticated: bool
    auth_mode: str
    provider: str
    session_open: bool
    sdk_installed: bool
    sdk_compatible: bool
    subscribed_symbols: tuple[str, ...]
    reconnect_attempts: int
    next_reconnect_delay_seconds: float | None
    last_connected_at: datetime | None
    last_message_at: datetime | None
    last_error: str | None
    checked_at: datetime
    instruments: dict[InstrumentId, InstrumentFeedStatus] = field(default_factory=dict)


class GrowwLiveStreamManager:
    """Manages Groww authentication, authoritative index resolution, `GrowwFeed` subscription,
    reconnect backoff, and 5-minute IST session candle aggregation.
    """

    def __init__(
        self,
        *,
        credentials: GrowwCredentials | None = None,
        streaming_enabled: bool = False,
        stale_after_seconds: float = 60.0,
        max_future_skew_seconds: float = 5.0,
        max_confirmed_candles: int = 500,
        backoff_policy: ReconnectBackoffPolicy | None = None,
        api_cls: type | None = None,
        feed_cls: type | None = None,
        totp_generator: Callable[[str], str] | None = None,
        instrument_resolver: GrowwInstrumentResolver | None = None,
        spawn_consume_thread: bool = False,
    ) -> None:
        self.credentials = credentials or GrowwCredentials()
        self.streaming_enabled = bool(streaming_enabled)
        self.stale_after_seconds = float(stale_after_seconds)
        self.backoff_policy = backoff_policy or ReconnectBackoffPolicy()
        self._api_cls = api_cls
        self._feed_cls = feed_cls
        self._totp_generator = totp_generator
        self._resolver = instrument_resolver
        self._spawn_consume_thread = spawn_consume_thread

        self.aggregator = LiveSessionAggregator(
            source=DataSource(name="groww", kind=DataSourceKind.LIVE),
            max_confirmed_candles=max_confirmed_candles,
            max_future_skew_seconds=max_future_skew_seconds,
            max_staleness_seconds=None,
        )

        self._client: Any = None
        self._feed: Any = None
        self._auth_mode: GrowwAuthMode = GrowwAuthMode.NONE
        self._descriptors: dict[InstrumentId, GrowwInstrumentDescriptor] = {}
        self._subscription_list: list[dict[str, str]] = []
        self._consume_thread: threading.Thread | None = None

        self._connected: bool = False
        self._authenticated: bool = False
        self._disconnected_mid_session: bool = False
        self._failed_permanently: bool = False
        self._reconnect_attempts: int = 0
        self._last_connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_error: str | None = None
        self._historical_counts: dict[InstrumentId, int] = {inst: 0 for inst in InstrumentId}

    @property
    def groww_client(self) -> Any:
        return self._client

    @property
    def instrument_resolver(self) -> GrowwInstrumentResolver | None:
        return self._resolver

    def set_historical_candle_count(self, instrument: InstrumentId, count: int) -> None:
        self._historical_counts[instrument] = max(0, int(count))

    def _redact(self, message: Any) -> str:
        return redact_groww_secrets(str(message), secrets=self.credentials.secret_values())

    def _record_error(self, message: Any, *, permanent: bool = False) -> None:
        redacted = self._redact(message)
        self._last_error = redacted
        if permanent:
            self._failed_permanently = True
            self._connected = False
            self._authenticated = False
        logger.warning("Groww live stream error: %s", redacted)

    def start(self, *, as_of: datetime | None = None) -> bool:
        """Authenticate using the single configured mode, resolve index tokens, and subscribe."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        if not self.streaming_enabled:
            logger.info("Groww live streaming is disabled by configuration (LIVE_STREAM_ENABLED=false).")
            return False

        try:
            self._auth_mode = self.credentials.select_auth_mode()
        except ProviderAuthError as exc:
            self._record_error(exc, permanent=True)
            return False

        if self._auth_mode is GrowwAuthMode.NONE:
            self._record_error(
                "Groww credentials are required when LIVE_STREAM_ENABLED=true.",
                permanent=True,
            )
            return False

        sdk_report = verify_groww_sdk_compatibility(
            api_cls=self._api_cls,
            feed_cls=self._feed_cls,
        )
        if not sdk_report.compatible:
            self._record_error(sdk_report.detail, permanent=True)
            return False

        try:
            self._client, self._auth_mode = authenticate_groww_client(
                self.credentials,
                api_cls=self._api_cls,
                totp_generator=self._totp_generator,
            )
            self._authenticated = True
        except ProviderAuthError as exc:
            self._record_error(exc, permanent=True)
            return False
        except Exception as exc:
            self._record_error(exc, permanent=is_groww_auth_exception(exc))
            return False

        # Resolve authoritative instrument descriptors for NIFTY50 and BANKNIFTY
        try:
            if self._resolver is None:
                self._resolver = GrowwInstrumentResolver(groww_client=self._client)
            self._descriptors = self._resolver.resolve_all()
            self._subscription_list = [
                self._descriptors[InstrumentId.NIFTY50].to_feed_subscription_dict(),
                self._descriptors[InstrumentId.BANKNIFTY].to_feed_subscription_dict(),
            ]
        except Exception as exc:
            self._record_error(exc, permanent=True)
            return False

        # Instantiate GrowwFeed and subscribe_index_value
        try:
            feed_cls = self._feed_cls
            if feed_cls is None:
                from growwapi import GrowwFeed  # type: ignore[import-not-found]

                feed_cls = GrowwFeed

            self._feed = feed_cls(self._client)
            self.aggregator.set_stream_started_at(now_ist)
            self._feed.subscribe_index_value(
                self._subscription_list,
                on_data_received=self._on_data_received,
            )
            self._connected = True
            self._disconnected_mid_session = False
            self._failed_permanently = False
            self._reconnect_attempts = 0
            self._last_connected_at = now_ist

            if self._spawn_consume_thread and callable(getattr(self._feed, "consume", None)):
                self._consume_thread = threading.Thread(
                    target=self._consume_worker,
                    name="groww-index-feed-consumer",
                    daemon=True,
                )
                self._consume_thread.start()
            return True
        except Exception as exc:
            if is_groww_auth_exception(exc):
                self._record_error(exc, permanent=True)
            else:
                self._record_error(exc, permanent=False)
                self._schedule_or_record_reconnect()
            return False

    def _consume_worker(self) -> None:
        if self._feed is None:
            return
        try:
            self._feed.consume()
        except Exception as exc:
            self.handle_feed_error(exc)

    def stop(self, *, as_of: datetime | None = None) -> None:
        """Unsubscribe from index feed and cleanly tear down connection state."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self.aggregator.mark_disconnection(now_ist)
        feed = self._feed
        self._feed = None
        self._connected = False
        if feed is not None and self._subscription_list:
            try:
                unsub = getattr(feed, "unsubscribe_index_value", None)
                if callable(unsub):
                    unsub(self._subscription_list)
            except Exception as exc:
                self._record_error(exc, permanent=False)

    def _on_data_received(self, meta: Any = None) -> list[TickProcessResult]:
        """Callback invoked by `GrowwFeed` when new index data arrives."""
        if self._feed is None:
            return []
        try:
            snapshot = self._feed.get_index_value()
        except Exception as exc:
            self.handle_feed_error(exc)
            return []

        feed_key: str | None = None
        if isinstance(meta, dict):
            raw_key = meta.get("feed_key") or meta.get("exchange_token")
            if raw_key is not None:
                feed_key = str(raw_key)
        return self.handle_index_feed_payload(snapshot, filter_exchange_token=feed_key)

    def handle_index_feed_payload(
        self,
        payload: Any,
        *,
        filter_exchange_token: str | None = None,
        as_of: datetime | None = None,
    ) -> list[TickProcessResult]:
        """Process a `get_index_value()` payload into validated 5-minute IST session candles."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self._last_message_at = now_ist

        updates = parse_groww_index_feed_Snapshot(
            payload,
            filter_exchange_token=filter_exchange_token,
        )
        results: list[TickProcessResult] = []

        for u in updates:
            instrument: InstrumentId | None = None
            if self._resolver is not None:
                instrument = self._resolver.instrument_for_exchange_token(u.exchange_token)
            if instrument is None:
                token_upper = u.exchange_token.upper()
                if token_upper in {"NIFTY", "26000"}:
                    instrument = InstrumentId.NIFTY50
                elif token_upper in {"BANKNIFTY", "26009"}:
                    instrument = InstrumentId.BANKNIFTY

            symbol_key: str | InstrumentId = instrument if instrument is not None else u.exchange_token
            provider_sym = (
                self._descriptors[instrument].groww_symbol
                if instrument is not None and instrument in self._descriptors
                else (groww_symbol_for(instrument) if instrument is not None else u.exchange_token)
            )
            res = self.aggregator.process_tick(
                symbol=symbol_key,
                price=u.value,
                timestamp=u.timestamp,
                volume=None,  # Spot indices do not have traded volume; never fabricate volume
                provider_symbol=provider_sym,
                as_of=now_ist,
            )
            results.append(res)
        return results

    def handle_feed_error(self, exc_or_message: Any, *, as_of: datetime | None = None) -> float | None:
        """Handle a feed disconnect or error, marking forming candles incomplete and applying backoff."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self._connected = False
        self._disconnected_mid_session = True
        self.aggregator.mark_disconnection(now_ist)

        if is_groww_auth_exception(exc_or_message):
            self._record_error(
                f"Groww feed authentication/authorization error: {exc_or_message}",
                permanent=True,
            )
            return None

        self._record_error(f"Groww feed connection error: {exc_or_message}", permanent=False)
        if self.streaming_enabled and not self._failed_permanently:
            return self._schedule_or_record_reconnect()
        return None

    def _schedule_or_record_reconnect(self) -> float | None:
        next_attempt = self._reconnect_attempts + 1
        if not self.backoff_policy.can_retry(next_attempt):
            self._record_error(
                f"Exhausted maximum Groww feed reconnect attempts ({self.backoff_policy.max_attempts}).",
                permanent=True,
            )
            return None
        self._reconnect_attempts = next_attempt
        return self.backoff_policy.delay_for_attempt(next_attempt)

    def evaluate_instrument_state(
        self,
        instrument: InstrumentId,
        *,
        as_of: datetime | None = None,
    ) -> InstrumentFeedStatus:
        """Evaluate current FeedState and metrics for one instrument."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        self.aggregator.finalize_closed(now_ist)

        quote = self.aggregator.get_latest_quote(instrument)
        confirmed = self.aggregator.get_confirmed_candles(instrument)
        forming = self.aggregator.get_forming_candle(instrument)
        missing = self.aggregator.get_missing_intervals(instrument)
        rejected_count = self.aggregator.get_rejected_count(instrument)
        desc = self._descriptors.get(instrument)

        age_seconds: float | None = None
        if quote is not None:
            age_seconds = max(0.0, (now_ist - quote.timestamp).total_seconds())

        session_open = is_regular_session_ist(now_ist)

        if self._failed_permanently:
            state = FeedState.FAILED
        elif not self.streaming_enabled and quote is None:
            state = FeedState.UNAVAILABLE
        elif not session_open:
            state = FeedState.CLOSED
        elif self._disconnected_mid_session and not self._connected:
            state = FeedState.DISCONNECTED
        elif quote is None:
            state = FeedState.UNAVAILABLE
        elif not self._connected or (age_seconds is not None and age_seconds > self.stale_after_seconds):
            state = FeedState.STALE
        else:
            state = FeedState.LIVE

        is_stale = state in {FeedState.STALE, FeedState.DISCONNECTED} or (
            age_seconds is not None and age_seconds > self.stale_after_seconds
        )

        return InstrumentFeedStatus(
            instrument=instrument,
            groww_symbol=desc.groww_symbol if desc else groww_symbol_for(instrument),
            trading_symbol=desc.trading_symbol if desc else ("NIFTY" if instrument is InstrumentId.NIFTY50 else "BANKNIFTY"),
            exchange_token=desc.exchange_token if desc else None,
            feed_state=state,
            last_tick_at=quote.timestamp if quote is not None else None,
            age_seconds=round(age_seconds, 3) if age_seconds is not None else None,
            is_stale=is_stale,
            historical_candle_count=self._historical_counts.get(instrument, 0),
            confirmed_candle_count=len(confirmed),
            has_forming_candle=forming is not None,
            missing_interval_count=len(missing),
            rejected_tick_count=rejected_count,
        )

    def status_snapshot(self, *, as_of: datetime | None = None) -> StreamStatusSnapshot:
        """Return a complete, secret-redacted operational status snapshot."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        session_open = is_regular_session_ist(now_ist)
        sdk_report = verify_groww_sdk_compatibility(
            api_cls=self._api_cls,
            feed_cls=self._feed_cls,
        )

        inst_statuses = {
            inst: self.evaluate_instrument_state(inst, as_of=now_ist)
            for inst in InstrumentId
        }
        states = {s.feed_state for s in inst_statuses.values()}

        if self._failed_permanently:
            overall = FeedState.FAILED
        elif not self.streaming_enabled and all(s == FeedState.UNAVAILABLE for s in states):
            overall = FeedState.UNAVAILABLE
        elif not session_open:
            overall = FeedState.CLOSED
        elif self._disconnected_mid_session and not self._connected:
            overall = FeedState.DISCONNECTED
        elif FeedState.LIVE in states:
            overall = FeedState.LIVE
        elif FeedState.STALE in states:
            overall = FeedState.STALE
        else:
            overall = FeedState.UNAVAILABLE

        next_delay: float | None = None
        if self._reconnect_attempts > 0 and not self._failed_permanently:
            if self.backoff_policy.can_retry(self._reconnect_attempts):
                next_delay = self.backoff_policy.delay_for_attempt(self._reconnect_attempts)

        subscribed = tuple(
            desc.groww_symbol for desc in self._descriptors.values()
        ) or ("NSE-NIFTY", "NSE-BANKNIFTY")

        return StreamStatusSnapshot(
            feed_state=overall,
            streaming_enabled=self.streaming_enabled,
            connected=self._connected,
            authenticated=self._authenticated,
            auth_mode=self._auth_mode.value,
            provider="groww",
            session_open=session_open,
            sdk_installed=sdk_report.installed,
            sdk_compatible=sdk_report.compatible,
            subscribed_symbols=subscribed,
            reconnect_attempts=self._reconnect_attempts,
            next_reconnect_delay_seconds=next_delay,
            last_connected_at=self._last_connected_at,
            last_message_at=self._last_message_at,
            last_error=self._last_error,
            checked_at=now_ist,
            instruments=inst_statuses,
        )
