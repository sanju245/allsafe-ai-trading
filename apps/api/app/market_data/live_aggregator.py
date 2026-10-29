"""Strict live update validation and Asia/Kolkata 5-minute session candle aggregation.

Rules enforced:
* Never invent a source timestamp when an update has none or is timezone-naive.
* Align all 5-minute buckets to the NSE regular session grid (Mon-Fri 09:15-15:30 IST).
* Maintain strict separation between forming (in-progress) and confirmed (closed) candles.
* Never fabricate synthetic flat candles across missing intervals; record MissingInterval gaps explicitly.
* Never fabricate volume for index instruments (NIFTY 50 and BANK NIFTY have volume=None).
* Flag candles as incomplete when streaming starts mid-slot or a feed disconnect interrupts a slot.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.market_data.instruments import InstrumentId
from app.market_data.live_models import (
    ConfirmedCandle,
    FormingCandle,
    IncompleteReason,
    LiveQuote,
    LiveTick,
    MissingInterval,
    RejectedTick,
    TickRejectionReason,
)
from app.market_data.models import DataSource, DataSourceKind
from app.market_data.sessions import (
    IST,
    SESSION_CLOSE,
    SESSION_OPEN,
    is_weekday,
    session_slots,
    to_ist,
)
from app.market_data.timeframes import Timeframe

CANDLE_DURATION = timedelta(minutes=5)

GROWW_SYMBOL_BY_INSTRUMENT: dict[InstrumentId, str] = {
    InstrumentId.NIFTY50: "NSE-NIFTY",
    InstrumentId.BANKNIFTY: "NSE-BANKNIFTY",
}

_SYMBOL_ALIASES: dict[str, InstrumentId] = {
    "NIFTY50": InstrumentId.NIFTY50,
    "NIFTY 50": InstrumentId.NIFTY50,
    "NIFTY_50": InstrumentId.NIFTY50,
    "NIFTY": InstrumentId.NIFTY50,
    "NSE-NIFTY": InstrumentId.NIFTY50,
    "NSE_NIFTY": InstrumentId.NIFTY50,
    "NSE:NIFTY50-INDEX": InstrumentId.NIFTY50,
    "BANKNIFTY": InstrumentId.BANKNIFTY,
    "BANK NIFTY": InstrumentId.BANKNIFTY,
    "BANK_NIFTY": InstrumentId.BANKNIFTY,
    "NIFTY BANK": InstrumentId.BANKNIFTY,
    "NIFTY_BANK": InstrumentId.BANKNIFTY,
    "NIFTYBANK": InstrumentId.BANKNIFTY,
    "NSE-BANKNIFTY": InstrumentId.BANKNIFTY,
    "NSE_BANKNIFTY": InstrumentId.BANKNIFTY,
    "NSE:NIFTYBANK-INDEX": InstrumentId.BANKNIFTY,
    "NSE:BANKNIFTY-INDEX": InstrumentId.BANKNIFTY,
}


def resolve_instrument_symbol(symbol: str | InstrumentId) -> InstrumentId:
    """Resolve an instrument identifier or provider symbol string to InstrumentId."""
    if isinstance(symbol, InstrumentId):
        return symbol
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    normalized = " ".join(symbol.strip().upper().split())
    instrument = _SYMBOL_ALIASES.get(normalized)
    if instrument is None:
        raise ValueError(f"Unsupported symbol: {symbol!r}")
    return instrument


def groww_symbol_for(instrument: InstrumentId) -> str:
    """Return the canonical Groww symbol (e.g. 'NSE-NIFTY') for an InstrumentId."""
    return GROWW_SYMBOL_BY_INSTRUMENT[instrument]


def is_regular_session_ist(ts: datetime) -> bool:
    """Return True if timezone-aware timestamp falls within Mon-Fri 09:15-15:30 IST."""
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    local = to_ist(ts)
    if not is_weekday(local.date()):
        return False
    t = local.time().replace(tzinfo=None)
    return SESSION_OPEN <= t < SESSION_CLOSE


def slot_for_ist(ts: datetime) -> datetime:
    """Return the 5-minute NSE session slot open time (IST) for a valid session timestamp."""
    local = to_ist(ts)
    if not is_regular_session_ist(local):
        raise ValueError("timestamp is outside regular NSE trading hours (Mon-Fri 09:15-15:30 IST)")
    session_open = local.replace(hour=9, minute=15, second=0, microsecond=0)
    elapsed_seconds = (local - session_open).total_seconds()
    slot_index = int(elapsed_seconds // 300)
    return session_open + timedelta(minutes=5 * slot_index)


@dataclass
class _ActiveBucket:
    instrument: InstrumentId
    slot: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    tick_count: int
    first_tick_at: datetime
    last_tick_at: datetime
    source: DataSource
    incomplete_reasons: list[IncompleteReason] = field(default_factory=list)

    def mark_incomplete(self, reason: IncompleteReason) -> None:
        if reason not in self.incomplete_reasons:
            self.incomplete_reasons.append(reason)

    def update(self, price: float, timestamp: datetime, volume: float | None) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.last_tick_at = timestamp
        self.tick_count += 1
        if volume is not None:
            self.volume = (self.volume or 0.0) + volume

    def to_forming(self) -> FormingCandle:
        return FormingCandle(
            instrument=self.instrument,
            timeframe=Timeframe.M5,
            timestamp=self.slot,
            close_time=self.slot + CANDLE_DURATION,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            tick_count=self.tick_count,
            first_tick_at=self.first_tick_at,
            last_tick_at=self.last_tick_at,
            is_forming=True,
            is_confirmed=False,
            is_incomplete=bool(self.incomplete_reasons),
            incomplete_reasons=tuple(self.incomplete_reasons),
            source=self.source,
        )

    def to_confirmed(self) -> ConfirmedCandle:
        return ConfirmedCandle(
            instrument=self.instrument,
            timeframe=Timeframe.M5,
            timestamp=self.slot,
            close_time=self.slot + CANDLE_DURATION,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            tick_count=self.tick_count,
            first_tick_at=self.first_tick_at,
            last_tick_at=self.last_tick_at,
            is_forming=False,
            is_confirmed=True,
            is_incomplete=bool(self.incomplete_reasons),
            incomplete_reasons=tuple(self.incomplete_reasons),
            source=self.source,
        )


@dataclass(frozen=True)
class TickProcessResult:
    """Outcome of processing one incoming live update."""

    accepted: bool
    tick: LiveTick | None = None
    rejection: RejectedTick | None = None
    confirmed_candle: ConfirmedCandle | None = None
    forming_candle: FormingCandle | None = None
    missing_interval: MissingInterval | None = None


class LiveSessionAggregator:
    """Validates live index/price updates and aggregates them into forming and confirmed 5m candles."""

    def __init__(
        self,
        *,
        source: DataSource | None = None,
        max_confirmed_candles: int = 500,
        max_rejected_ticks: int = 200,
        max_future_skew_seconds: float = 5.0,
        max_staleness_seconds: float | None = 300.0,
        mid_slot_grace_seconds: float = 30.0,
        stream_started_at: datetime | None = None,
    ) -> None:
        if max_confirmed_candles < 1:
            raise ValueError("max_confirmed_candles must be >= 1")
        self.source = source or DataSource(name="groww", kind=DataSourceKind.LIVE)
        self.max_confirmed_candles = max_confirmed_candles
        self.max_rejected_ticks = max_rejected_ticks
        self.max_future_skew_seconds = max_future_skew_seconds
        self.max_staleness_seconds = max_staleness_seconds
        self.mid_slot_grace_seconds = mid_slot_grace_seconds
        self.stream_started_at = to_ist(stream_started_at) if stream_started_at is not None else None

        self._active: dict[InstrumentId, _ActiveBucket] = {}
        self._confirmed: dict[InstrumentId, deque[ConfirmedCandle]] = {
            inst: deque(maxlen=max_confirmed_candles) for inst in InstrumentId
        }
        self._finalized_through: dict[InstrumentId, datetime] = {}
        self._last_tick: dict[InstrumentId, LiveTick] = {}
        self._quotes: dict[InstrumentId, LiveQuote] = {}
        self._missing_intervals: dict[InstrumentId, list[MissingInterval]] = {
            inst: [] for inst in InstrumentId
        }
        self._rejected_ticks: deque[RejectedTick] = deque(maxlen=max_rejected_ticks)
        self._rejected_counts_by_instrument: dict[InstrumentId, int] = {
            inst: 0 for inst in InstrumentId
        }
        self._pending_interruption: dict[InstrumentId, bool] = {
            inst: False for inst in InstrumentId
        }

    def set_stream_started_at(self, started_at: datetime) -> None:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        self.stream_started_at = to_ist(started_at)

    def mark_disconnection(self, as_of: datetime | None = None) -> None:
        """Mark all active forming candles as interrupted by a feed disconnect."""
        for inst, bucket in self._active.items():
            bucket.mark_incomplete(IncompleteReason.FEED_INTERRUPTED_DURING_SLOT)
            self._pending_interruption[inst] = True

    def _reject(
        self,
        reason: TickRejectionReason,
        message: str,
        *,
        received_at: datetime,
        instrument: InstrumentId | None = None,
        provider_symbol: str | None = None,
        price: float | None = None,
        timestamp: datetime | None = None,
    ) -> TickProcessResult:
        rejection = RejectedTick(
            reason=reason,
            message=message,
            instrument=instrument,
            provider_symbol=provider_symbol,
            price=price if (price is not None and math.isfinite(price)) else None,
            timestamp=timestamp,
            received_at=received_at,
        )
        self._rejected_ticks.append(rejection)
        if instrument is not None:
            self._rejected_counts_by_instrument[instrument] += 1
        return TickProcessResult(accepted=False, rejection=rejection)

    def process_tick(
        self,
        *,
        symbol: str | InstrumentId,
        price: float,
        timestamp: datetime | None,
        volume: float | None = None,
        provider_symbol: str | None = None,
        as_of: datetime | None = None,
    ) -> TickProcessResult:
        """Validate a single price/index update and update forming/confirmed candle state."""
        if as_of is not None:
            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware")
            now_ist = to_ist(as_of)
        elif timestamp is not None and timestamp.tzinfo is not None and timestamp.utcoffset() is None:
            now_ist = to_ist(timestamp)
        else:
            now_ist = datetime.now(IST)

        raw_symbol_str = symbol.value if isinstance(symbol, InstrumentId) else str(symbol)
        try:
            instrument = resolve_instrument_symbol(symbol)
        except ValueError as exc:
            return self._reject(
                TickRejectionReason.UNSUPPORTED_SYMBOL,
                str(exc),
                received_at=now_ist,
                provider_symbol=provider_symbol or raw_symbol_str,
                price=price if isinstance(price, (int, float)) else None,
            )

        resolved_provider_symbol = provider_symbol or groww_symbol_for(instrument)

        if timestamp is None:
            return self._reject(
                TickRejectionReason.MISSING_TIMESTAMP,
                "Update is missing a source timestamp; refusing to invent server timestamp.",
                received_at=now_ist,
                instrument=instrument,
                provider_symbol=resolved_provider_symbol,
                price=price if isinstance(price, (int, float)) else None,
            )

        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return self._reject(
                TickRejectionReason.NAIVE_TIMESTAMP,
                "Update timestamp must be a timezone-aware datetime.",
                received_at=now_ist,
                instrument=instrument,
                provider_symbol=resolved_provider_symbol,
                price=price if isinstance(price, (int, float)) else None,
            )

        tick_ist = to_ist(timestamp)

        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            return self._reject(
                TickRejectionReason.INVALID_PRICE,
                "Update price/value must be a finite number greater than zero.",
                received_at=now_ist,
                instrument=instrument,
                provider_symbol=resolved_provider_symbol,
                timestamp=tick_ist,
            )
        price_val = float(price)

        if volume is not None:
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume < 0:
                return self._reject(
                    TickRejectionReason.INVALID_VOLUME,
                    "Update volume must be finite and non-negative.",
                    received_at=now_ist,
                    instrument=instrument,
                    provider_symbol=resolved_provider_symbol,
                    price=price_val,
                    timestamp=tick_ist,
                )
            volume_val: float | None = float(volume)
        else:
            volume_val = None

        if as_of is not None:
            skew_seconds = (tick_ist - now_ist).total_seconds()
            if skew_seconds > self.max_future_skew_seconds:
                return self._reject(
                    TickRejectionReason.FUTURE_TIMESTAMP,
                    f"Update timestamp {tick_ist.isoformat()} is {skew_seconds:.1f}s ahead of reference time.",
                    received_at=now_ist,
                    instrument=instrument,
                    provider_symbol=resolved_provider_symbol,
                    price=price_val,
                    timestamp=tick_ist,
                )
            if self.max_staleness_seconds is not None:
                age_seconds = (now_ist - tick_ist).total_seconds()
                if age_seconds > self.max_staleness_seconds:
                    return self._reject(
                        TickRejectionReason.STALE_TICK,
                        f"Update timestamp {tick_ist.isoformat()} is stale ({age_seconds:.1f}s old).",
                        received_at=now_ist,
                        instrument=instrument,
                        provider_symbol=resolved_provider_symbol,
                        price=price_val,
                        timestamp=tick_ist,
                    )

        if not is_regular_session_ist(tick_ist):
            return self._reject(
                TickRejectionReason.OUTSIDE_SESSION,
                f"Update timestamp {tick_ist.isoformat()} is outside regular NSE trading hours (Mon-Fri 09:15-15:30 IST).",
                received_at=now_ist,
                instrument=instrument,
                provider_symbol=resolved_provider_symbol,
                price=price_val,
                timestamp=tick_ist,
            )

        slot = slot_for_ist(tick_ist)

        last_tick = self._last_tick.get(instrument)
        if last_tick is not None:
            if tick_ist == last_tick.timestamp and price_val == last_tick.price and volume_val == last_tick.volume:
                return self._reject(
                    TickRejectionReason.DUPLICATE_TICK,
                    f"Duplicate update at {tick_ist.isoformat()} with identical value.",
                    received_at=now_ist,
                    instrument=instrument,
                    provider_symbol=resolved_provider_symbol,
                    price=price_val,
                    timestamp=tick_ist,
                )
            if tick_ist < last_tick.timestamp:
                return self._reject(
                    TickRejectionReason.OUT_OF_ORDER_TICK,
                    f"Out-of-order update at {tick_ist.isoformat()} earlier than latest update {last_tick.timestamp.isoformat()}.",
                    received_at=now_ist,
                    instrument=instrument,
                    provider_symbol=resolved_provider_symbol,
                    price=price_val,
                    timestamp=tick_ist,
                )

        finalized_slot = self._finalized_through.get(instrument)
        if finalized_slot is not None and slot <= finalized_slot:
            return self._reject(
                TickRejectionReason.OUT_OF_ORDER_TICK,
                f"Update at {tick_ist.isoformat()} belongs to already finalized slot {slot.isoformat()}.",
                received_at=now_ist,
                instrument=instrument,
                provider_symbol=resolved_provider_symbol,
                price=price_val,
                timestamp=tick_ist,
            )

        live_tick = LiveTick(
            instrument=instrument,
            provider_symbol=resolved_provider_symbol,
            price=price_val,
            timestamp=tick_ist,
            received_at=now_ist,
            volume=volume_val,
            source=self.source,
        )
        self._last_tick[instrument] = live_tick
        self._quotes[instrument] = LiveQuote(
            instrument=instrument,
            symbol=instrument.value,
            provider_symbol=resolved_provider_symbol,
            ltp=price_val,
            timestamp=tick_ist,
            received_at=now_ist,
            volume=volume_val,
            open_interest=None,
            source=self.source,
        )

        active = self._active.get(instrument)
        confirmed: ConfirmedCandle | None = None
        missing_interval: MissingInterval | None = None

        if active is not None and slot == active.slot:
            active.update(price_val, tick_ist, volume_val)
            self._pending_interruption[instrument] = False
            return TickProcessResult(
                accepted=True,
                tick=live_tick,
                forming_candle=active.to_forming(),
            )

        prev_reference_slot: datetime | None = finalized_slot
        if active is not None and slot > active.slot:
            confirmed = active.to_confirmed()
            self._confirmed[instrument].append(confirmed)
            self._finalized_through[instrument] = active.slot
            prev_reference_slot = active.slot
            del self._active[instrument]

        if prev_reference_slot is not None and slot > prev_reference_slot:
            missing_slots = self._compute_missing_slots(prev_reference_slot, slot)
            if missing_slots:
                missing_interval = MissingInterval(
                    instrument=instrument,
                    timeframe=Timeframe.M5,
                    previous_slot=prev_reference_slot,
                    next_slot=slot,
                    first_missing_slot=missing_slots[0],
                    last_missing_slot=missing_slots[-1],
                    missing_slot_count=len(missing_slots),
                    missing_slots=missing_slots,
                    detected_at=now_ist,
                )
                self._missing_intervals[instrument].append(missing_interval)

        incomplete_reasons: list[IncompleteReason] = []
        elapsed_in_slot = (tick_ist - slot).total_seconds()
        is_first_observed_slot = (prev_reference_slot is None) or (missing_interval is not None)
        if is_first_observed_slot and elapsed_in_slot > self.mid_slot_grace_seconds or self.stream_started_at is not None and self.stream_started_at > slot + timedelta(seconds=self.mid_slot_grace_seconds) and prev_reference_slot is None:
            incomplete_reasons.append(IncompleteReason.STREAM_STARTED_MID_SLOT)

        if (
            self._pending_interruption.get(instrument)
            and elapsed_in_slot > self.mid_slot_grace_seconds
            and IncompleteReason.FEED_INTERRUPTED_DURING_SLOT not in incomplete_reasons
        ):
            incomplete_reasons.append(IncompleteReason.FEED_INTERRUPTED_DURING_SLOT)
        self._pending_interruption[instrument] = False

        new_bucket = _ActiveBucket(
            instrument=instrument,
            slot=slot,
            open=price_val,
            high=price_val,
            low=price_val,
            close=price_val,
            volume=volume_val,
            tick_count=1,
            first_tick_at=tick_ist,
            last_tick_at=tick_ist,
            source=self.source,
            incomplete_reasons=incomplete_reasons,
        )
        self._active[instrument] = new_bucket

        return TickProcessResult(
            accepted=True,
            tick=live_tick,
            confirmed_candle=confirmed,
            forming_candle=new_bucket.to_forming(),
            missing_interval=missing_interval,
        )

    @staticmethod
    def _compute_missing_slots(prev_slot: datetime, next_slot: datetime) -> tuple[datetime, ...]:
        """Return all expected 5m NSE session slots strictly between prev_slot and next_slot."""
        missing: list[datetime] = []
        day = prev_slot.date()
        end_day = next_slot.date()
        one_day = timedelta(days=1)
        while day <= end_day:
            for s in session_slots(day, Timeframe.M5):
                if prev_slot < s < next_slot:
                    missing.append(s)
            day += one_day
        return tuple(missing)

    def finalize_closed(self, as_of: datetime) -> list[ConfirmedCandle]:
        """Finalize any forming candles whose 5-minute window has closed by as_of."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        now_ist = to_ist(as_of)
        emitted: list[ConfirmedCandle] = []
        for instrument, bucket in list(self._active.items()):
            if now_ist >= bucket.slot + CANDLE_DURATION:
                confirmed = bucket.to_confirmed()
                self._confirmed[instrument].append(confirmed)
                self._finalized_through[instrument] = bucket.slot
                del self._active[instrument]
                emitted.append(confirmed)
        return emitted

    def get_forming_candle(self, instrument: InstrumentId, *, as_of: datetime | None = None) -> FormingCandle | None:
        if as_of is not None:
            self.finalize_closed(as_of)
        bucket = self._active.get(instrument)
        return bucket.to_forming() if bucket is not None else None

    def get_confirmed_candles(
        self,
        instrument: InstrumentId,
        *,
        limit: int | None = None,
        as_of: datetime | None = None,
    ) -> list[ConfirmedCandle]:
        if as_of is not None:
            self.finalize_closed(as_of)
        items = list(self._confirmed[instrument])
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            return items[-limit:]
        return items

    def get_latest_quote(self, instrument: InstrumentId) -> LiveQuote | None:
        return self._quotes.get(instrument)

    def get_missing_intervals(self, instrument: InstrumentId) -> list[MissingInterval]:
        return list(self._missing_intervals[instrument])

    def get_rejected_ticks(self, instrument: InstrumentId | None = None) -> list[RejectedTick]:
        if instrument is None:
            return list(self._rejected_ticks)
        return [r for r in self._rejected_ticks if r.instrument == instrument]

    def get_rejected_count(self, instrument: InstrumentId) -> int:
        return self._rejected_counts_by_instrument.get(instrument, 0)
