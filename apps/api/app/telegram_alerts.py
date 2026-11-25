"""Account links and publication of neutral alerts from the chart runtime."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from hashlib import sha256
import logging
import re
from threading import Event
from typing import Any

from fastapi import HTTPException

from app.config import Settings
from app.indicators.decision import TradeDecision
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState
from app.market_data.live_runtime import LiveDecisionSummary, LiveMarketDataRuntime, latest_closed_slot
from app.market_data.models import DataSourceKind
from app.market_data.sessions import IST, slot_close_time
from app.market_data.timeframes import Timeframe
from app.supabase_admin import SupabaseAdminAPIError, _request_json

logger = logging.getLogger("uvicorn.error")
ALERT_WINDOW = timedelta(minutes=2)
BOT_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,28}bot", re.IGNORECASE | re.ASCII)


def configured_bot(settings: Settings) -> str | None:
    name = settings.telegram_bot_username.strip().removeprefix("@")
    if settings.telegram_alerts_enabled and BOT_USERNAME.fullmatch(name):
        return name
    return None


def link_digest(code: str) -> str:
    return sha256(code.encode("ascii")).hexdigest()


def telegram_rpc(settings: Settings, action: str, **payload: Any) -> Any:
    return _request_json("POST", f"rest/v1/rpc/telegram_{action}", payload=payload, settings=settings)


def alertable_signal(summary: LiveDecisionSummary, slot: datetime) -> bool:
    return (
        summary.candle_timestamp == slot
        and summary.is_current_signal
        and summary.feed_state == FeedState.LIVE
        and not summary.is_stale
        and summary.decision in (TradeDecision.BUY, TradeDecision.SELL)
        and summary.source is not None
        and summary.source.kind in (DataSourceKind.LIVE, DataSourceKind.HISTORICAL)
    )


def publish_signals(settings: Settings, runtimes: Mapping[str, LiveMarketDataRuntime], stop: Event) -> None:
    """Check the site's configured feed after each close, even without browser traffic."""
    provider = settings.market_data_provider.strip().lower()
    runtime = runtimes.get(provider)
    if runtime is None or not runtime.stream_manager.streaming_enabled:
        logger.warning("Telegram alerts require an enabled live market-data feed.")
        return

    published: dict[InstrumentId, datetime] = {}
    while not stop.is_set():
        now = datetime.now(IST)
        slot = latest_closed_slot(now)
        if slot is not None:
            expires = slot_close_time(slot, Timeframe.M15) + ALERT_WINDOW
            if now < expires:
                for instrument in InstrumentId:
                    if stop.is_set() or published.get(instrument) == slot:
                        continue
                    state = runtime.stream_manager.evaluate_instrument_state(instrument, as_of=now)
                    if state.feed_state != FeedState.LIVE or state.is_stale:
                        continue
                    summary = runtime.evaluate_decision_for_instrument(instrument, as_of=now)
                    if alertable_signal(summary, slot):
                        try:
                            telegram_rpc(
                                settings, "enqueue_signal", p_symbol=instrument.value,
                                p_candle_at=slot.isoformat(), p_provider=provider,
                                p_expires_at=expires.isoformat(),
                            )
                        except (SupabaseAdminAPIError, HTTPException):
                            logger.warning("Could not queue a Telegram alert. Will retry while current.")
                        else:
                            published[instrument] = slot
        stop.wait(5)
