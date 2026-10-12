"""Supported instruments.

Both are NSE *indices*. An index is a calculated number, not something you can buy
directly; people trade them through derivatives or index funds. Mapping an instrument
to a provider-specific symbol belongs to the provider adapter, not here.
"""

from datetime import time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class InstrumentId(StrEnum):
    NIFTY50 = "NIFTY50"
    BANKNIFTY = "BANKNIFTY"


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: InstrumentId
    name: str
    exchange: str
    asset_class: str
    currency: str
    timezone: str
    session_open: time
    session_close: time
    note: str


_NOTE = (
    "Index, not directly tradable. Regular session hours only; no exchange holiday "
    "calendar is bundled yet."
)

INSTRUMENTS: dict[InstrumentId, Instrument] = {
    InstrumentId.NIFTY50: Instrument(
        id=InstrumentId.NIFTY50,
        name="NIFTY 50",
        exchange="NSE",
        asset_class="index",
        currency="INR",
        timezone="Asia/Kolkata",
        session_open=time(9, 15),
        session_close=time(15, 30),
        note=_NOTE,
    ),
    InstrumentId.BANKNIFTY: Instrument(
        id=InstrumentId.BANKNIFTY,
        name="BANK NIFTY",
        exchange="NSE",
        asset_class="index",
        currency="INR",
        timezone="Asia/Kolkata",
        session_open=time(9, 15),
        session_close=time(15, 30),
        note=_NOTE,
    ),
}


def list_instruments() -> list[Instrument]:
    return list(INSTRUMENTS.values())
