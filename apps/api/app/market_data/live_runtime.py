"""Provider-agnostic Live Market-Data & 5-Indicator Decision Runtime.

Coordinates:
* Historical 15-minute candle warm-up when the selected provider supports it.
* Live 15-minute session-aligned candle aggregation from the selected feed manager.
* Strict separation between forming (in-progress) and confirmed (closed) candles.
* Connection of validated, complete, confirmed candles to the existing 5-indicator
  decision engine (`calculate_decisions`), ensuring:
  - Incomplete candles are never treated as confirmed signals.
  - Series with validation errors (such as missing-interval gaps) report `DATA_UNAVAILABLE`.
  - Stale, disconnected, closed, or unavailable feeds prevent claiming a live/current signal.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from threading import Lock
from time import monotonic
from typing import Any, Protocol

from app.indicators.decision import DecisionPoint, OpeningRangeState, TradeDecision, calculate_decisions
from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import LiveSessionAggregator
from app.market_data.live_models import (
    FeedState,
)
from app.market_data.models import Candle, DataSource
from app.market_data.sessions import IST, SlotClass, classify_timestamp, find_gap, session_slots, slot_close_time, to_ist
from app.market_data.timeframes import Timeframe
from app.market_data.validation import IssueCode, validate_candles
from app.providers.base import CandleRequest, MarketDataProvider, ProviderError
from app.providers.groww_historical import GrowwHistoricalProvider

logger = logging.getLogger("uvicorn.error")


def latest_closed_slot(as_of: datetime) -> datetime | None:
    return next((s for s in reversed(session_slots(as_of.date(), Timeframe.M15))
                 if slot_close_time(s, Timeframe.M15) <= as_of), None)


def validated_decisions(
    candles: list[Candle], *, instrument: InstrumentId, as_of: datetime,
) -> tuple[list[DecisionPoint], int]:
    """Restart warm-up at an actual missing interval and keep earlier confirmed events."""
    runs: list[list[Candle]] = []
    for candle in candles:
        if not runs:
            runs.append([])
        elif runs[-1]:
            gap = find_gap(to_ist(runs[-1][-1].timestamp), to_ist(candle.timestamp), Timeframe.M15)
            if gap.missing_slots or gap.missing_days:
                runs.append([])
        runs[-1].append(candle)
    points: list[DecisionPoint] = []
    last_count = 0
    for run in runs:
        report = validate_candles(run, instrument=instrument, timeframe=Timeframe.M15,
                                  as_of=as_of, check_staleness=False)
        # A complete live candle and a historical candle from the selected broker
        # have distinct source labels. Both belong in this calculation.
        if report.error_count > report.issue_counts.get(IssueCode.SOURCE_MISMATCH.value, 0):
            last_count = 0
            continue
        points.extend(calculate_decisions(run))
        last_count = len(run)
    return points, last_count


@dataclass
class _HistoryRefresh:
    day: date | None = None
    slot: datetime | None = None
    retry_at: float = 0
    warning: str | None = None


class LiveStreamManager(Protocol):
    """Minimum read-only feed interface consumed by the shared market runtime."""

    aggregator: LiveSessionAggregator
    streaming_enabled: bool
    groww_client: Any
    instrument_resolver: Any

    def start(self, *, as_of: datetime | None = None) -> bool: ...

    def stop(self, *, as_of: datetime | None = None) -> None: ...

    def set_historical_candle_count(self, instrument: InstrumentId, count: int) -> None: ...

    def _record_error(self, message: Any, *, permanent: bool = False) -> None: ...


@dataclass(frozen=True)
class LiveDecisionSummary:
    """Confirmed 5-indicator signal evaluation with feed-freshness and source attribution."""

    instrument: InstrumentId
    timeframe: Timeframe
    decision: TradeDecision
    is_current_signal: bool
    feed_state: FeedState
    is_stale: bool
    candle_timestamp: datetime | None
    evaluated_at: datetime
    source: DataSource | None
    ut_bot_signal: str | None
    ema_bullish: bool | None
    rsi_bullish: bool | None
    macd_bullish: bool | None
    supertrend_bullish: bool | None
    reason: str
    confirmed_candle_count: int
    opening_range_state: OpeningRangeState | None = None
    ut_bot_position: int | None = None


class LiveMarketDataRuntime:
    """High-level coordinator uniting historical warm-up, live streaming, and 5-indicator evaluation."""

    def __init__(
        self,
        *,
        stream_manager: LiveStreamManager,
        historical_provider: MarketDataProvider | None = None,
        warmup_lookback_days: int = 5,
    ) -> None:
        self.stream_manager = stream_manager
        self.historical_provider = historical_provider
        self.warmup_lookback_days = warmup_lookback_days
        self._historical_candles: dict[InstrumentId, list[Candle]] = {
            inst: [] for inst in InstrumentId
        }
        self._history_locks = {inst: Lock() for inst in InstrumentId}
        self._history_refresh = {inst: _HistoryRefresh() for inst in InstrumentId}

    def seed_historical_candles(self, instrument: InstrumentId, candles: list[Candle]) -> None:
        """Seed validated historical closed 15m candles for indicator warm-up."""
        closed = [
            c for c in candles if c.instrument == instrument and c.timeframe == Timeframe.M15
            and classify_timestamp(c.timestamp, Timeframe.M15)[0] == SlotClass.ON_GRID
        ]
        closed.sort(key=lambda c: c.timestamp)
        self._historical_candles[instrument] = closed
        self.stream_manager.set_historical_candle_count(instrument, len(closed))

    def refresh_chart_history(self, instrument: InstrumentId, *, as_of: datetime) -> str | None:
        """Share one broker backfill per index and close across chart viewers."""
        provider = self.historical_provider
        if provider is None:
            return "Broker history is unavailable for this feed."
        expected = latest_closed_slot(as_of)
        state = self._history_refresh[instrument]
        with self._history_locks[instrument]:
            now = monotonic()
            if now < state.retry_at:
                return state.warning
            if state.day == as_of.date() and state.slot == expected and state.warning is None:
                return None
            # Fetch the full window once per session. Subsequent requests only need
            # today's finalized broker bars (including a close missed on restart).
            start_day = as_of.date() if state.day == as_of.date() else as_of.date() - timedelta(days=29)
            try:
                fetched = provider.fetch_candles(CandleRequest(
                    instrument=instrument, timeframe=Timeframe.M15,
                    start=datetime.combine(start_day, time.min, tzinfo=IST), end=as_of,
                ))
            except ProviderError:
                state.warning = "Broker history could not be refreshed."
                state.retry_at = now + 30
                return state.warning
            cutoff = as_of.date() - timedelta(days=29)
            by_slot = {c.timestamp: c for c in self._historical_candles[instrument]
                       if to_ist(c.timestamp).date() >= cutoff}
            for candle in fetched:
                if (candle.instrument == instrument and candle.timeframe == Timeframe.M15
                        and candle.is_closed(as_of) and to_ist(candle.timestamp).date() >= cutoff):
                    by_slot[candle.timestamp] = candle
            self.seed_historical_candles(instrument, list(by_slot.values()))
            if any(to_ist(c.timestamp).date() < as_of.date() for c in by_slot.values()):
                state.day = as_of.date()
            state.slot = expected
            state.warning = None
            if state.day != as_of.date() or (expected and expected not in by_slot):
                state.warning = "Waiting for the broker's completed candles."
                state.retry_at = now + 30
            else:
                state.retry_at = 0
            return state.warning

    def warmup_from_historical_provider(
        self,
        *,
        as_of: datetime | None = None,
    ) -> dict[InstrumentId, int]:
        """Fetch closed 15m candles to warm up the 5-indicator engine."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        provider = self.historical_provider
        if provider is None and self.stream_manager.groww_client is not None and self.stream_manager.instrument_resolver is not None:
            provider = GrowwHistoricalProvider(
                groww_client=self.stream_manager.groww_client,
                instrument_resolver=self.stream_manager.instrument_resolver,
                credentials=self.stream_manager.credentials,
            )
            self.historical_provider = provider

        counts: dict[InstrumentId, int] = {inst: 0 for inst in InstrumentId}
        if provider is None:
            return counts

        start_dt = now_ist - timedelta(days=self.warmup_lookback_days)
        for inst in InstrumentId:
            req = CandleRequest(
                instrument=inst,
                timeframe=Timeframe.M15,
                start=start_dt,
                end=now_ist,
                limit=300,
            )
            with self._history_locks[inst]:
                if self._history_refresh[inst].day == now_ist.date():
                    counts[inst] = len(self._historical_candles[inst])
                    continue
                fetched = provider.fetch_candles(req)
                by_slot = {c.timestamp: c for c in self._historical_candles[inst]}
                by_slot.update({c.timestamp: c for c in fetched if c.is_closed(now_ist)})
                self.seed_historical_candles(inst, list(by_slot.values()))
                counts[inst] = len(self._historical_candles[inst])
            logger.info(
                "%s historical warm-up loaded %s completed 15-minute candles for %s.",
                provider.name,
                counts[inst],
                inst.value,
            )
        return counts

    def start(self, *, as_of: datetime | None = None, run_warmup: bool = True) -> bool:
        started = self.stream_manager.start(as_of=as_of)
        if started and run_warmup:
            try:
                self.warmup_from_historical_provider(as_of=as_of)
            except Exception as exc:  # noqa: BLE001 - warm-up failure must not disable live ticks
                self.stream_manager._record_error(
                    f"Historical warm-up warning: {exc}", permanent=False
                )
        return started

    def stop(self, *, as_of: datetime | None = None) -> None:
        self.stream_manager.stop(as_of=as_of)

    def merged_complete_confirmed_candles(
        self,
        instrument: InstrumentId,
        *,
        as_of: datetime | None = None,
    ) -> list[Candle]:
        """Return chronological, complete, confirmed 15m candles (historical + live) for indicators.

        Incomplete live candles (`is_incomplete=True`) and forming candles (`is_forming=True`)
        are NEVER included in confirmed indicator series.
        """
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        by_ts: dict[datetime, Candle] = {}

        for hc in self._historical_candles.get(instrument, []):
            if hc.is_closed(now_ist):
                by_ts[hc.timestamp] = hc

        live_confirmed = self.stream_manager.aggregator.get_confirmed_candles(
            instrument, as_of=now_ist
        )
        for lc in live_confirmed:
            if not lc.is_incomplete:
                by_ts[lc.timestamp] = lc.to_candle()

        return [by_ts[k] for k in sorted(by_ts.keys())]

    def evaluate_series(
        self, instrument: InstrumentId, candles: list[Candle], *,
        as_of: datetime, incomplete_tail: datetime | None = None,
    ) -> tuple[LiveDecisionSummary, list[DecisionPoint]]:
        status = self.stream_manager.evaluate_instrument_state(instrument, as_of=as_of)
        points, confirmed_count = validated_decisions(candles, instrument=instrument, as_of=as_of)
        last = candles[-1] if candles else None
        point = points[-1] if points and last and points[-1].timestamp == last.timestamp else None
        stamp = last.timestamp if last else None
        if incomplete_tail is not None and (stamp is None or incomplete_tail > stamp):
            stamp = incomplete_tail
            point = None
            reason = "Waiting for the broker to complete the interrupted 15-minute candle."
        elif point is None:
            reason = ("The completed candles failed validation." if candles
                      else "Waiting for completed 15-minute candles.")
        else:
            reason = point.reason
        fresh = status.feed_state == FeedState.LIVE and not status.is_stale
        latest = stamp is not None and stamp == latest_closed_slot(as_of)
        if point and fresh and not latest:
            reason += " The latest session candle is not available."
        summary = LiveDecisionSummary(
            instrument=instrument, timeframe=Timeframe.M15, evaluated_at=as_of,
            feed_state=status.feed_state, is_stale=status.is_stale, candle_timestamp=stamp,
            source=last.source if last else None, confirmed_candle_count=confirmed_count,
            decision=point.decision if point else TradeDecision.DATA_UNAVAILABLE,
            is_current_signal=bool(point and fresh and latest and point.decision in (TradeDecision.BUY, TradeDecision.SELL)),
            ut_bot_signal=point.ut_bot_signal.value if point and point.ut_bot_signal else None,
            ema_bullish=point.ema_bullish if point else None,
            rsi_bullish=point.rsi_bullish if point else None,
            macd_bullish=point.macd_bullish if point else None,
            supertrend_bullish=point.supertrend_bullish if point else None,
            reason=reason,
            opening_range_state=point.opening_range_state if point else None,
            ut_bot_position=point.ut_bot_position if point else None,
        )
        return summary, points

    def evaluate_decision_for_instrument(
        self, instrument: InstrumentId, *, as_of: datetime | None = None,
    ) -> LiveDecisionSummary:
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        live = self.stream_manager.aggregator.get_confirmed_candles(instrument, as_of=now)
        candles = self.merged_complete_confirmed_candles(instrument, as_of=now)
        tail = live[-1].timestamp if live and live[-1].is_incomplete else None
        return self.evaluate_series(instrument, candles, as_of=now, incomplete_tail=tail)[0]

    def decision_history_for_instrument(
        self, instrument: InstrumentId, *, as_of: datetime | None = None,
    ) -> list[DecisionPoint]:
        now = to_ist(as_of) if as_of is not None else datetime.now(IST)
        candles = self.merged_complete_confirmed_candles(instrument, as_of=now)
        return validated_decisions(candles, instrument=instrument, as_of=now)[0]
