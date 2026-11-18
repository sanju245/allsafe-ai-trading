"""Authenticated, read-only 15-minute historical charts from Upstox."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.market_data.instruments import InstrumentId
from app.market_data.models import Candle
from app.market_data.timeframes import Timeframe
from app.providers.upstox_history import MAX_RANGE_DAYS, UpstoxHistoryError, fetch_15m_candles
from app.security import AccountPrincipal, require_active_account

router = APIRouter(prefix="/api/v1/market-data/upstox", tags=["market-data"])
_IST = ZoneInfo("Asia/Kolkata")


class UpstoxCandlesResponse(BaseModel):
    provider: str
    instrument: InstrumentId
    timeframe: Timeframe
    start_date: date
    end_date: date
    retrieved_at: datetime
    last_candle_at: datetime | None
    candles: list[Candle]
    message: str


@router.get("/candles", response_model=UpstoxCandlesResponse)
def get_upstox_15m_candles(
    response: Response,
    symbol: InstrumentId = Query(default=InstrumentId.NIFTY50),
    days: int = Query(default=7, ge=1, le=MAX_RANGE_DAYS),
    _: AccountPrincipal = Depends(require_active_account),
) -> UpstoxCandlesResponse:
    """Return completed 15-minute candles for a bounded calendar-day range."""
    response.headers["Cache-Control"] = "private, no-store"
    retrieved_at = datetime.now(_IST)
    end_date = retrieved_at.date()
    start_date = end_date - timedelta(days=days - 1)
    try:
        candles = fetch_15m_candles(
            symbol,
            start_date=start_date,
            end_date=end_date,
            as_of=retrieved_at,
        )
    except UpstoxHistoryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    last_candle_at = candles[-1].timestamp if candles else None
    message = (
        "Completed historical 15-minute candles from Upstox. This is not a live quote."
        if candles
        else "Upstox returned no completed candles for this date range."
    )
    return UpstoxCandlesResponse(
        provider="Upstox",
        instrument=symbol,
        timeframe=Timeframe.M15,
        start_date=start_date,
        end_date=end_date,
        retrieved_at=retrieved_at,
        last_candle_at=last_candle_at,
        candles=candles,
        message=message,
    )
