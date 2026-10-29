"""Response schemas for read-only Groww live market-data endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.indicators.decision import TradeDecision
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import (
    FeedState,
    IncompleteReason,
)
from app.market_data.models import DataSource
from app.market_data.timeframes import Timeframe


class InstrumentStatusSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    groww_symbol: str
    trading_symbol: str
    exchange_token: str | None = None
    feed_state: FeedState
    last_tick_at: datetime | None = None
    age_seconds: float | None = None
    is_stale: bool
    historical_candle_count: int
    confirmed_candle_count: int
    has_forming_candle: bool
    missing_interval_count: int
    rejected_tick_count: int


class LiveStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    feed_state: FeedState
    streaming_enabled: bool
    connected: bool
    authenticated: bool
    auth_mode: str
    provider: str
    session_open: bool
    sdk_installed: bool
    sdk_compatible: bool
    subscribed_symbols: list[str]
    reconnect_attempts: int
    next_reconnect_delay_seconds: float | None = None
    last_connected_at: datetime | None = None
    last_message_at: datetime | None = None
    last_error: str | None = None
    checked_at: datetime
    instruments: dict[str, InstrumentStatusSchema]


class LiveQuotePayloadSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    symbol: str
    provider_symbol: str
    ltp: float
    timestamp: datetime
    received_at: datetime
    volume: float | None = None
    open_interest: float | None = None
    source: DataSource


class LiveQuoteResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    symbol: str
    groww_symbol: str
    trading_symbol: str
    available: bool
    feed_state: FeedState
    is_stale: bool
    age_seconds: float | None = None
    quote: LiveQuotePayloadSchema | None = None
    message: str
    checked_at: datetime


class ConfirmedCandleSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe
    timestamp: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    tick_count: int
    first_tick_at: datetime
    last_tick_at: datetime
    is_forming: bool = False
    is_confirmed: bool = True
    is_incomplete: bool = False
    incomplete_reasons: list[IncompleteReason]
    source: DataSource


class MissingIntervalSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe
    previous_slot: datetime
    next_slot: datetime
    first_missing_slot: datetime
    last_missing_slot: datetime
    missing_slot_count: int
    missing_slots: list[datetime]
    detected_at: datetime


class IndicatorDecisionSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: TradeDecision
    is_current_signal: bool
    feed_state: FeedState
    is_stale: bool
    candle_timestamp: datetime | None = None
    evaluated_at: datetime
    source: DataSource | None = None
    ut_bot_signal: str | None = None
    ema_bullish: bool | None = None
    rsi_bullish: bool | None = None
    macd_bullish: bool | None = None
    supertrend_bullish: bool | None = None
    reason: str
    confirmed_candle_count: int


class LiveCandlesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    symbol: str
    groww_symbol: str
    trading_symbol: str
    timeframe: Timeframe
    feed_state: FeedState
    is_stale: bool
    candle_count: int
    candles: list[ConfirmedCandleSchema]
    has_forming_candle: bool
    forming_candle_timestamp: datetime | None = None
    incomplete_candle_count: int
    missing_interval_count: int
    missing_intervals: list[MissingIntervalSchema]
    indicator_decision: IndicatorDecisionSchema
    message: str
    checked_at: datetime


class FormingCandleSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    timeframe: Timeframe
    timestamp: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    tick_count: int
    first_tick_at: datetime
    last_tick_at: datetime
    is_forming: bool = True
    is_confirmed: bool = False
    is_incomplete: bool = False
    incomplete_reasons: list[IncompleteReason]
    source: DataSource


class LiveFormingCandleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: InstrumentId
    symbol: str
    groww_symbol: str
    trading_symbol: str
    timeframe: Timeframe
    available: bool
    feed_state: FeedState
    is_stale: bool
    forming_candle: FormingCandleSchema | None = None
    message: str
    checked_at: datetime
