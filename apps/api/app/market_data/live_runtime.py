"""Provider-agnostic Live Market-Data & 5-Indicator Decision Runtime.

Coordinates:
* Historical 5-minute candle warm-up from `GrowwHistoricalProvider`.
* Live 5-minute session-aligned candle aggregation from `GrowwLiveStreamManager`.
* Strict separation between forming (in-progress) and confirmed (closed) candles.
* Connection of validated, complete, confirmed candles to the existing 5-indicator
  decision engine (`calculate_decisions`), ensuring:
  - Incomplete candles are never treated as confirmed signals.
  - Series with validation errors (such as missing-interval gaps) report `DATA_UNAVAILABLE`.
  - Stale, disconnected, closed, or unavailable feeds prevent claiming a live/current signal.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.indicators.decision import DecisionPoint, TradeDecision, calculate_decisions
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import (
    FeedState,
)
from app.market_data.models import Candle, DataSource
from app.market_data.sessions import IST, to_ist
from app.market_data.timeframes import Timeframe
from app.market_data.validation import ValidationReport, validate_candles
from app.providers.base import CandleRequest
from app.providers.groww_historical import GrowwHistoricalProvider
from app.providers.groww_stream import (
    GrowwLiveStreamManager,
)


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


class LiveMarketDataRuntime:
    """High-level coordinator uniting historical warm-up, live streaming, and 5-indicator evaluation."""

    def __init__(
        self,
        *,
        stream_manager: GrowwLiveStreamManager,
        historical_provider: GrowwHistoricalProvider | None = None,
        warmup_lookback_days: int = 5,
    ) -> None:
        self.stream_manager = stream_manager
        self.historical_provider = historical_provider
        self.warmup_lookback_days = warmup_lookback_days
        self._historical_candles: dict[InstrumentId, list[Candle]] = {
            inst: [] for inst in InstrumentId
        }

    def seed_historical_candles(self, instrument: InstrumentId, candles: list[Candle]) -> None:
        """Seed validated historical closed 5m candles for indicator warm-up."""
        five_min_closed = [
            c for c in candles if c.instrument == instrument and c.timeframe == Timeframe.M5
        ]
        five_min_closed.sort(key=lambda c: c.timestamp)
        self._historical_candles[instrument] = five_min_closed
        self.stream_manager.set_historical_candle_count(instrument, len(five_min_closed))

    def warmup_from_historical_provider(
        self,
        *,
        as_of: datetime | None = None,
    ) -> dict[InstrumentId, int]:
        """Fetch historical 5m candles from Groww to warm up the 5-indicator engine."""
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
                timeframe=Timeframe.M5,
                start=start_dt,
                end=now_ist,
                limit=300,
            )
            fetched = provider.fetch_candles(req)
            closed_only = [c for c in fetched if c.is_closed(now_ist)]
            self.seed_historical_candles(inst, closed_only)
            counts[inst] = len(closed_only)
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
        """Return chronological, complete, confirmed 5m candles (historical + live) for indicators.

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

    def evaluate_decision_for_instrument(
        self,
        instrument: InstrumentId,
        *,
        as_of: datetime | None = None,
    ) -> LiveDecisionSummary:
        """Evaluate the 5-indicator decision engine strictly on valid, complete, confirmed candles."""
        now_ist = to_ist(as_of) if as_of is not None else datetime.now(IST)
        inst_status = self.stream_manager.evaluate_instrument_state(instrument, as_of=now_ist)
        live_confirmed = self.stream_manager.aggregator.get_confirmed_candles(
            instrument, as_of=now_ist
        )
        missing_intervals = self.stream_manager.aggregator.get_missing_intervals(instrument)

        # If the latest confirmed live candle is incomplete, do not emit a confirmed signal from it
        if live_confirmed and live_confirmed[-1].is_incomplete:
            return LiveDecisionSummary(
                instrument=instrument,
                timeframe=Timeframe.M5,
                decision=TradeDecision.DATA_UNAVAILABLE,
                is_current_signal=False,
                feed_state=inst_status.feed_state,
                is_stale=inst_status.is_stale,
                candle_timestamp=live_confirmed[-1].timestamp,
                evaluated_at=now_ist,
                source=live_confirmed[-1].source,
                ut_bot_signal=None,
                ema_bullish=None,
                rsi_bullish=None,
                macd_bullish=None,
                supertrend_bullish=None,
                reason=(
                    "Latest confirmed 5m candle is marked incomplete ("
                    + ", ".join(r.value for r in live_confirmed[-1].incomplete_reasons)
                    + "); refusing to treat incomplete interval as a confirmed signal."
                ),
                confirmed_candle_count=len(live_confirmed),
            )

        if missing_intervals:
            return LiveDecisionSummary(
                instrument=instrument,
                timeframe=Timeframe.M5,
                decision=TradeDecision.DATA_UNAVAILABLE,
                is_current_signal=False,
                feed_state=inst_status.feed_state,
                is_stale=inst_status.is_stale,
                candle_timestamp=live_confirmed[-1].timestamp if live_confirmed else None,
                evaluated_at=now_ist,
                source=live_confirmed[-1].source if live_confirmed else None,
                ut_bot_signal=None,
                ema_bullish=None,
                rsi_bullish=None,
                macd_bullish=None,
                supertrend_bullish=None,
                reason=(
                    f"Live 5m series contains {len(missing_intervals)} missing interval gap(s); "
                    "indicators require a contiguous validated candle series."
                ),
                confirmed_candle_count=len(live_confirmed),
            )

        candles = self.merged_complete_confirmed_candles(instrument, as_of=now_ist)
        if not candles:
            return LiveDecisionSummary(
                instrument=instrument,
                timeframe=Timeframe.M5,
                decision=TradeDecision.DATA_UNAVAILABLE,
                is_current_signal=False,
                feed_state=inst_status.feed_state,
                is_stale=inst_status.is_stale,
                candle_timestamp=None,
                evaluated_at=now_ist,
                source=None,
                ut_bot_signal=None,
                ema_bullish=None,
                rsi_bullish=None,
                macd_bullish=None,
                supertrend_bullish=None,
                reason="No confirmed 5m candles available yet.",
                confirmed_candle_count=0,
            )

        # Validate values and ordering on the merged series
        report: ValidationReport = validate_candles(
            candles,
            instrument=instrument,
            timeframe=Timeframe.M5,
            source=candles[-1].source,
            as_of=now_ist,
            check_staleness=False,
        )
        # Disallow any value/ordering/intraday-gap errors (allow SOURCE_MISMATCH when merging historical+live)
        blocking_errors = [
            issue
            for issue in report.issues
            if issue.severity.value == "error" and issue.code.value != "SOURCE_MISMATCH"
        ]
        if blocking_errors:
            codes_str = ", ".join(sorted({i.code.value for i in blocking_errors}))
            return LiveDecisionSummary(
                instrument=instrument,
                timeframe=Timeframe.M5,
                decision=TradeDecision.DATA_UNAVAILABLE,
                is_current_signal=False,
                feed_state=inst_status.feed_state,
                is_stale=inst_status.is_stale,
                candle_timestamp=candles[-1].timestamp,
                evaluated_at=now_ist,
                source=candles[-1].source,
                ut_bot_signal=None,
                ema_bullish=None,
                rsi_bullish=None,
                macd_bullish=None,
                supertrend_bullish=None,
                reason=f"Candle series failed validation ({codes_str}); signal evaluation blocked.",
                confirmed_candle_count=len(candles),
            )

        points: list[DecisionPoint] = calculate_decisions(candles)
        last_pt = points[-1]
        is_live_and_fresh = (
            inst_status.feed_state == FeedState.LIVE and not inst_status.is_stale
        )
        reason = last_pt.reason
        if not is_live_and_fresh:
            reason = (
                f"[Feed state: {inst_status.feed_state.value}] {last_pt.reason} "
                "(Do not treat as a current live trigger while feed is not live.)"
            )

        return LiveDecisionSummary(
            instrument=instrument,
            timeframe=Timeframe.M5,
            decision=last_pt.decision,
            is_current_signal=is_live_and_fresh and last_pt.decision in (TradeDecision.BUY, TradeDecision.SELL),
            feed_state=inst_status.feed_state,
            is_stale=inst_status.is_stale,
            candle_timestamp=last_pt.timestamp,
            evaluated_at=now_ist,
            source=candles[-1].source,
            ut_bot_signal=last_pt.ut_bot_signal.value if last_pt.ut_bot_signal is not None else None,
            ema_bullish=last_pt.ema_bullish,
            rsi_bullish=last_pt.rsi_bullish,
            macd_bullish=last_pt.macd_bullish,
            supertrend_bullish=last_pt.supertrend_bullish,
            reason=reason,
            confirmed_candle_count=len(candles),
        )
