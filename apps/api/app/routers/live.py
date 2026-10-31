"""Read-only Groww live market-data endpoints (`/api/v1/live/*`).

Endpoints:
* GET /api/v1/live/status
* GET /api/v1/live/quote?symbol=...
* GET /api/v1/live/candles?symbol=...&timeframe=5m&limit=...
* GET /api/v1/live/forming-candle?symbol=...

Safety guarantees:
* Strictly read-only; no order placement or broker execution exists.
* Every response carries Cache-Control: no-store.
* Confirmed candles and forming candles are never mixed.
* Indicator decisions are computed only from complete, confirmed candles and are marked
  `is_current_signal=False` whenever the feed is stale, disconnected, closed, or unavailable.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.config import Settings, get_settings
from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import (
    resolve_instrument_symbol,
)
from app.market_data.live_models import FeedState
from app.market_data.live_runtime import LiveMarketDataRuntime
from app.market_data.live_schemas import (
    ConfirmedCandleSchema,
    FormingCandleSchema,
    IndicatorDecisionSchema,
    InstrumentStatusSchema,
    LiveCandlesResponse,
    LiveFormingCandleResponse,
    LiveQuotePayloadSchema,
    LiveQuoteResponse,
    LiveStatusResponse,
    MissingIntervalSchema,
)
from app.market_data.sessions import IST
from app.market_data.timeframes import Timeframe
from app.providers.groww_auth import GrowwCredentials
from app.providers.groww_stream import GrowwLiveStreamManager
from app.security import AccountPrincipal, require_active_account

router = APIRouter(prefix="/api/v1/live", tags=["live-market-data"])

_default_runtime: LiveMarketDataRuntime | None = None


def build_runtime_from_settings(settings: Settings | None = None) -> LiveMarketDataRuntime:
    cfg = settings or get_settings()
    creds = GrowwCredentials(
        auth_mode=cfg.groww_auth_mode,
        access_token=cfg.groww_access_token,
        api_key=cfg.groww_api_key,
        api_secret=cfg.groww_api_secret,
        totp_secret=cfg.groww_totp_secret,
    )
    mgr = GrowwLiveStreamManager(
        credentials=creds,
        streaming_enabled=cfg.live_stream_enabled,
        stale_after_seconds=cfg.live_stale_seconds,
        max_future_skew_seconds=cfg.live_max_future_skew_seconds,
        max_confirmed_candles=cfg.live_candle_buffer_size,
    )
    return LiveMarketDataRuntime(
        stream_manager=mgr,
        warmup_lookback_days=cfg.live_warmup_lookback_days,
    )


def get_live_runtime(request: Request) -> LiveMarketDataRuntime:
    global _default_runtime
    rt = getattr(request.app.state, "live_runtime", None)
    if isinstance(rt, LiveMarketDataRuntime):
        return rt
    if _default_runtime is None:
        _default_runtime = build_runtime_from_settings()
    return _default_runtime


def set_live_runtime(app: object, runtime: LiveMarketDataRuntime | None) -> None:
    """Attach or reset a custom LiveMarketDataRuntime on app.state (used by lifecycle and tests)."""
    global _default_runtime
    _default_runtime = runtime
    state = getattr(app, "state", None)
    if state is not None:
        state.live_runtime = runtime


def _resolve_symbol_or_422(symbol: str) -> InstrumentId:
    try:
        return resolve_instrument_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported symbol {symbol!r}. Supported symbols: NIFTY50 (NSE-NIFTY), BANKNIFTY (NSE-BANKNIFTY).",
        ) from exc


def _resolve_live_timeframe_or_422(timeframe: str) -> Timeframe:
    normalized = timeframe.strip().lower()
    if normalized != Timeframe.M5.value:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported live candle timeframe {timeframe!r}. Only '5m' is supported for live streaming aggregation.",
        )
    return Timeframe.M5


def _status_message(feed_state: FeedState, streaming_enabled: bool, has_data: bool) -> str:
    if feed_state == FeedState.FAILED:
        return "Groww live market-data stream encountered an authentication or connection failure."
    if not streaming_enabled and not has_data:
        return "Live streaming is disabled by configuration (LIVE_STREAM_ENABLED=false)."
    if feed_state == FeedState.CLOSED:
        return "NSE regular trading session is closed (regular hours: Mon-Fri 09:15-15:30 IST)."
    if feed_state == FeedState.DISCONNECTED:
        return "Groww live market-data stream is disconnected; awaiting reconnection."
    if feed_state == FeedState.UNAVAILABLE:
        return "Live market-data feed is unavailable; no validated index updates have been received yet."
    if feed_state == FeedState.STALE:
        return "Live market-data feed is stale; latest validated index update exceeded the freshness threshold."
    return "Live market-data feed is active and within freshness bounds."


@router.get("/status", response_model=LiveStatusResponse)
def get_live_status(
    request: Request,
    response: Response,
    _: AccountPrincipal = Depends(require_active_account),
) -> LiveStatusResponse:
    """Return operational status of the Groww live stream and per-instrument health."""
    response.headers["Cache-Control"] = "no-store"
    rt = get_live_runtime(request)
    now_ist = datetime.now(IST)
    snap = rt.stream_manager.status_snapshot(as_of=now_ist)

    instruments_out = {
        inst.value: InstrumentStatusSchema(
            instrument=status.instrument,
            groww_symbol=status.groww_symbol,
            trading_symbol=status.trading_symbol,
            exchange_token=status.exchange_token,
            feed_state=status.feed_state,
            last_tick_at=status.last_tick_at,
            age_seconds=status.age_seconds,
            is_stale=status.is_stale,
            historical_candle_count=status.historical_candle_count,
            confirmed_candle_count=status.confirmed_candle_count,
            has_forming_candle=status.has_forming_candle,
            missing_interval_count=status.missing_interval_count,
            rejected_tick_count=status.rejected_tick_count,
        )
        for inst, status in snap.instruments.items()
    }

    return LiveStatusResponse(
        feed_state=snap.feed_state,
        streaming_enabled=snap.streaming_enabled,
        connected=snap.connected,
        authenticated=snap.authenticated,
        auth_mode=snap.auth_mode,
        provider=snap.provider,
        session_open=snap.session_open,
        sdk_installed=snap.sdk_installed,
        sdk_compatible=snap.sdk_compatible,
        subscribed_symbols=list(snap.subscribed_symbols),
        reconnect_attempts=snap.reconnect_attempts,
        next_reconnect_delay_seconds=snap.next_reconnect_delay_seconds,
        last_connected_at=snap.last_connected_at,
        last_message_at=snap.last_message_at,
        last_error=snap.last_error,
        checked_at=snap.checked_at,
        instruments=instruments_out,
    )


@router.get("/quote", response_model=LiveQuoteResponse)
def get_live_quote(
    request: Request,
    response: Response,
    symbol: str = Query(..., min_length=1, description="Instrument symbol, e.g. NIFTY50 or BANKNIFTY"),
    _: AccountPrincipal = Depends(require_active_account),
) -> LiveQuoteResponse:
    """Return the latest validated live quote for a subscribed index, never inventing prices or volume."""
    response.headers["Cache-Control"] = "no-store"
    instrument = _resolve_symbol_or_422(symbol)
    rt = get_live_runtime(request)
    mgr = rt.stream_manager
    now_ist = datetime.now(IST)
    inst_status = mgr.evaluate_instrument_state(instrument, as_of=now_ist)
    quote = mgr.aggregator.get_latest_quote(instrument)

    quote_schema: LiveQuotePayloadSchema | None = None
    if quote is not None:
        quote_schema = LiveQuotePayloadSchema(
            instrument=quote.instrument,
            symbol=quote.symbol,
            provider_symbol=quote.provider_symbol,
            ltp=quote.ltp,
            timestamp=quote.timestamp,
            received_at=quote.received_at,
            volume=quote.volume,
            open_interest=quote.open_interest,
            source=quote.source,
        )

    return LiveQuoteResponse(
        instrument=instrument,
        symbol=instrument.value,
        groww_symbol=inst_status.groww_symbol,
        trading_symbol=inst_status.trading_symbol,
        available=quote_schema is not None,
        feed_state=inst_status.feed_state,
        is_stale=inst_status.is_stale,
        age_seconds=inst_status.age_seconds,
        quote=quote_schema,
        message=_status_message(
            inst_status.feed_state,
            mgr.streaming_enabled,
            quote_schema is not None,
        ),
        checked_at=now_ist,
    )


@router.get("/candles", response_model=LiveCandlesResponse)
def get_live_candles(
    request: Request,
    response: Response,
    symbol: str = Query(..., min_length=1, description="Instrument symbol, e.g. NIFTY50 or BANKNIFTY"),
    timeframe: str = Query(default="5m", description="Candle timeframe (must be 5m)"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of confirmed candles to return"),
    _: AccountPrincipal = Depends(require_active_account),
) -> LiveCandlesResponse:
    """Return confirmed 5-minute candles only (never mixed with the forming candle) plus indicator decision."""
    response.headers["Cache-Control"] = "no-store"
    instrument = _resolve_symbol_or_422(symbol)
    tf = _resolve_live_timeframe_or_422(timeframe)

    rt = get_live_runtime(request)
    mgr = rt.stream_manager
    now_ist = datetime.now(IST)
    inst_status = mgr.evaluate_instrument_state(instrument, as_of=now_ist)
    confirmed = mgr.aggregator.get_confirmed_candles(instrument, limit=limit, as_of=now_ist)
    forming = mgr.aggregator.get_forming_candle(instrument, as_of=now_ist)
    missing = mgr.aggregator.get_missing_intervals(instrument)
    decision_summary = rt.evaluate_decision_for_instrument(instrument, as_of=now_ist)

    candle_schemas = [
        ConfirmedCandleSchema(
            instrument=c.instrument,
            timeframe=c.timeframe,
            timestamp=c.timestamp,
            close_time=c.close_time,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            tick_count=c.tick_count,
            first_tick_at=c.first_tick_at,
            last_tick_at=c.last_tick_at,
            is_forming=False,
            is_confirmed=True,
            is_incomplete=c.is_incomplete,
            incomplete_reasons=list(c.incomplete_reasons),
            source=c.source,
        )
        for c in confirmed
    ]

    missing_schemas = [
        MissingIntervalSchema(
            instrument=m.instrument,
            timeframe=m.timeframe,
            previous_slot=m.previous_slot,
            next_slot=m.next_slot,
            first_missing_slot=m.first_missing_slot,
            last_missing_slot=m.last_missing_slot,
            missing_slot_count=m.missing_slot_count,
            missing_slots=list(m.missing_slots),
            detected_at=m.detected_at,
        )
        for m in missing
    ]

    incomplete_count = sum(1 for c in candle_schemas if c.is_incomplete)

    decision_schema = IndicatorDecisionSchema(
        decision=decision_summary.decision,
        is_current_signal=decision_summary.is_current_signal,
        feed_state=decision_summary.feed_state,
        is_stale=decision_summary.is_stale,
        candle_timestamp=decision_summary.candle_timestamp,
        evaluated_at=decision_summary.evaluated_at,
        source=decision_summary.source,
        ut_bot_signal=decision_summary.ut_bot_signal,
        ema_bullish=decision_summary.ema_bullish,
        rsi_bullish=decision_summary.rsi_bullish,
        macd_bullish=decision_summary.macd_bullish,
        supertrend_bullish=decision_summary.supertrend_bullish,
        reason=decision_summary.reason,
        confirmed_candle_count=decision_summary.confirmed_candle_count,
    )

    return LiveCandlesResponse(
        instrument=instrument,
        symbol=instrument.value,
        groww_symbol=inst_status.groww_symbol,
        trading_symbol=inst_status.trading_symbol,
        timeframe=tf,
        feed_state=inst_status.feed_state,
        is_stale=inst_status.is_stale,
        candle_count=len(candle_schemas),
        candles=candle_schemas,
        has_forming_candle=forming is not None,
        forming_candle_timestamp=forming.timestamp if forming is not None else None,
        incomplete_candle_count=incomplete_count,
        missing_interval_count=len(missing_schemas),
        missing_intervals=missing_schemas,
        indicator_decision=decision_schema,
        message=_status_message(
            inst_status.feed_state,
            mgr.streaming_enabled,
            bool(candle_schemas),
        ),
        checked_at=now_ist,
    )


@router.get("/forming-candle", response_model=LiveFormingCandleResponse)
def get_live_forming_candle(
    request: Request,
    response: Response,
    symbol: str = Query(..., min_length=1, description="Instrument symbol, e.g. NIFTY50 or BANKNIFTY"),
    _: AccountPrincipal = Depends(require_active_account),
) -> LiveFormingCandleResponse:
    """Return the currently forming (unconfirmed) 5-minute candle, separated from confirmed history."""
    response.headers["Cache-Control"] = "no-store"
    instrument = _resolve_symbol_or_422(symbol)
    rt = get_live_runtime(request)
    mgr = rt.stream_manager
    now_ist = datetime.now(IST)
    inst_status = mgr.evaluate_instrument_state(instrument, as_of=now_ist)
    forming = mgr.aggregator.get_forming_candle(instrument, as_of=now_ist)

    forming_schema: FormingCandleSchema | None = None
    if forming is not None:
        forming_schema = FormingCandleSchema(
            instrument=forming.instrument,
            timeframe=forming.timeframe,
            timestamp=forming.timestamp,
            close_time=forming.close_time,
            open=forming.open,
            high=forming.high,
            low=forming.low,
            close=forming.close,
            volume=forming.volume,
            tick_count=forming.tick_count,
            first_tick_at=forming.first_tick_at,
            last_tick_at=forming.last_tick_at,
            is_forming=True,
            is_confirmed=False,
            is_incomplete=forming.is_incomplete,
            incomplete_reasons=list(forming.incomplete_reasons),
            source=forming.source,
        )

    msg = (
        "Forming candle is in progress and unconfirmed; do not treat as a closed candle signal."
        if forming_schema is not None
        else _status_message(inst_status.feed_state, mgr.streaming_enabled, False)
    )

    return LiveFormingCandleResponse(
        instrument=instrument,
        symbol=instrument.value,
        groww_symbol=inst_status.groww_symbol,
        trading_symbol=inst_status.trading_symbol,
        timeframe=Timeframe.M5,
        available=forming_schema is not None,
        feed_state=inst_status.feed_state,
        is_stale=inst_status.is_stale,
        forming_candle=forming_schema,
        message=msg,
        checked_at=now_ist,
    )
