"""Authoritative Groww instrument resolution for NIFTY 50 and BANK NIFTY.

Resolves exact Groww identifiers (`exchange_token`, `trading_symbol`, `groww_symbol`)
from Groww's instrument registry (`get_instrument_by_groww_symbol`,
`get_instrument_by_exchange_and_trading_symbol`, or `instrument.csv`) rather than
guessing exchange tokens or reusing FYERS symbols.
"""

import csv
import io
from dataclasses import dataclass
from typing import Any

from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import resolve_instrument_symbol
from app.providers.base import ProviderUnavailableError, UnsupportedRequestError


@dataclass(frozen=True)
class GrowwInstrumentDescriptor:
    """Authoritative Groww identifiers for one supported NSE index."""

    instrument: InstrumentId
    exchange: str
    segment: str
    exchange_token: str
    trading_symbol: str
    groww_symbol: str
    exchange_trading_symbol: str
    instrument_type: str
    name: str
    resolution_source: str

    def to_feed_subscription_dict(self) -> dict[str, str]:
        """Format required by `GrowwFeed.subscribe_index_value`."""
        return {
            "exchange": self.exchange,
            "segment": self.segment,
            "exchange_token": self.exchange_token,
        }


# Expected canonical Groww symbols and trading symbols per official Groww documentation:
# - Live Data docs: trading_symbol="NIFTY", exchange_trading_symbols="NSE_NIFTY"
# - Backtesting / Instruments docs: groww_symbol="NSE-NIFTY", underlying_symbol="BANKNIFTY"
EXPECTED_INDEX_KEYS: dict[InstrumentId, dict[str, str]] = {
    InstrumentId.NIFTY50: {
        "exchange": "NSE",
        "segment": "CASH",
        "groww_symbol": "NSE-NIFTY",
        "trading_symbol": "NIFTY",
        "exchange_trading_symbol": "NSE_NIFTY",
        "name": "NIFTY 50",
    },
    InstrumentId.BANKNIFTY: {
        "exchange": "NSE",
        "segment": "CASH",
        "groww_symbol": "NSE-BANKNIFTY",
        "trading_symbol": "BANKNIFTY",
        "exchange_trading_symbol": "NSE_BANKNIFTY",
        "name": "BANK NIFTY",
    },
}


def _normalize_row(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "to_dict"):
        d = raw.to_dict()
        if isinstance(d, dict):
            return d
    return None


def _validate_and_build_descriptor(
    instrument: InstrumentId,
    row: dict[str, Any],
    *,
    resolution_source: str,
) -> GrowwInstrumentDescriptor:
    expected = EXPECTED_INDEX_KEYS[instrument]
    exchange = str(row.get("exchange") or "").strip().upper()
    segment = str(row.get("segment") or "").strip().upper()
    raw_token = row.get("exchange_token")
    exchange_token = "" if raw_token is None else str(raw_token).strip()
    if exchange_token.lower() == "nan":
        exchange_token = ""

    trading_symbol = str(row.get("trading_symbol") or expected["trading_symbol"]).strip().upper()
    groww_symbol = str(row.get("groww_symbol") or expected["groww_symbol"]).strip()
    inst_type = str(row.get("instrument_type") or "IDX").strip().upper()
    name = str(row.get("name") or expected["name"]).strip()

    if exchange != "NSE":
        raise UnsupportedRequestError(
            f"Resolved {instrument.value} record has unexpected exchange {exchange!r} (expected 'NSE')."
        )
    if segment != "CASH":
        raise UnsupportedRequestError(
            f"Resolved {instrument.value} record has unexpected segment {segment!r} (expected 'CASH')."
        )
    if not exchange_token:
        raise ProviderUnavailableError(
            f"Authoritative Groww instrument record for {instrument.value} is missing exchange_token."
        )

    return GrowwInstrumentDescriptor(
        instrument=instrument,
        exchange="NSE",
        segment="CASH",
        exchange_token=exchange_token,
        trading_symbol=trading_symbol,
        groww_symbol=groww_symbol,
        exchange_trading_symbol=f"NSE_{trading_symbol}",
        instrument_type=inst_type,
        name=name,
        resolution_source=resolution_source,
    )


class GrowwInstrumentResolver:
    """Resolves and caches authoritative Groww instrument metadata for NIFTY 50 and BANK NIFTY."""

    def __init__(
        self,
        *,
        groww_client: Any = None,
        csv_text: str | None = None,
        preloaded: dict[InstrumentId, GrowwInstrumentDescriptor] | None = None,
    ) -> None:
        self._client = groww_client
        self._csv_text = csv_text
        self._cache: dict[InstrumentId, GrowwInstrumentDescriptor] = dict(preloaded or {})

    def resolve(self, symbol_or_instrument: str | InstrumentId) -> GrowwInstrumentDescriptor:
        instrument = resolve_instrument_symbol(symbol_or_instrument)
        if instrument in self._cache:
            return self._cache[instrument]

        descriptor = self._lookup_authoritative(instrument)
        self._cache[instrument] = descriptor
        return descriptor

    def resolve_all(self) -> dict[InstrumentId, GrowwInstrumentDescriptor]:
        for inst in InstrumentId:
            self.resolve(inst)
        return dict(self._cache)

    def instrument_for_exchange_token(self, exchange_token: str) -> InstrumentId | None:
        token_clean = str(exchange_token).strip()
        for inst, desc in self._cache.items():
            if desc.exchange_token == token_clean or desc.trading_symbol == token_clean.upper():
                return inst
        return None

    def _lookup_authoritative(self, instrument: InstrumentId) -> GrowwInstrumentDescriptor:
        expected = EXPECTED_INDEX_KEYS[instrument]

        # 1. Try SDK get_instrument_by_groww_symbol
        if self._client is not None:
            by_groww = getattr(self._client, "get_instrument_by_groww_symbol", None)
            if callable(by_groww):
                try:
                    row = _normalize_row(by_groww(groww_symbol=expected["groww_symbol"]))
                    if row:
                        return _validate_and_build_descriptor(
                            instrument, row, resolution_source="sdk:get_instrument_by_groww_symbol"
                        )
                except Exception:  # noqa: BLE001, S110 - try the next supported SDK lookup
                    pass

            # 2. Try SDK get_instrument_by_exchange_and_trading_symbol
            by_trading = getattr(
                self._client, "get_instrument_by_exchange_and_trading_symbol", None
            )
            if callable(by_trading):
                try:
                    row = _normalize_row(
                        by_trading(
                            exchange="NSE",
                            trading_symbol=expected["trading_symbol"],
                        )
                    )
                    if row:
                        return _validate_and_build_descriptor(
                            instrument,
                            row,
                            resolution_source="sdk:get_instrument_by_exchange_and_trading_symbol",
                        )
                except Exception:  # noqa: BLE001, S110 - try the next supported SDK lookup
                    pass

        # 3. Try parsing provided instrument.csv text
        if self._csv_text:
            descriptor = self._lookup_from_csv(instrument, self._csv_text)
            if descriptor is not None:
                return descriptor

        raise ProviderUnavailableError(
            f"Could not resolve authoritative Groww instrument metadata (exchange_token) for "
            f"{instrument.value} ({expected['groww_symbol']}). Verify Groww instrument catalog access."
        )

    @staticmethod
    def _lookup_from_csv(
        instrument: InstrumentId, csv_text: str
    ) -> GrowwInstrumentDescriptor | None:
        expected = EXPECTED_INDEX_KEYS[instrument]
        reader = csv.DictReader(io.StringIO(csv_text))
        fallback_underlying_token: str | None = None

        for row in reader:
            exch = str(row.get("exchange") or "").strip().upper()
            seg = str(row.get("segment") or "").strip().upper()
            gsym = str(row.get("groww_symbol") or "").strip()
            tsym = str(row.get("trading_symbol") or "").strip().upper()

            if exch == "NSE" and seg == "CASH" and (
                gsym == expected["groww_symbol"] or tsym == expected["trading_symbol"]
            ):
                return _validate_and_build_descriptor(
                    instrument, row, resolution_source="instruments_csv:cash_row"
                )

            # Also inspect FNO row underlying_symbol + underlying_exchange_token if CASH row is absent in a partial CSV
            usym = str(row.get("underlying_symbol") or "").strip().upper()
            utok = str(row.get("underlying_exchange_token") or "").strip()
            if exch == "NSE" and usym == expected["trading_symbol"] and utok and utok.lower() != "nan":
                fallback_underlying_token = utok

        if fallback_underlying_token:
            synthetic_row = {
                "exchange": "NSE",
                "segment": "CASH",
                "exchange_token": fallback_underlying_token,
                "trading_symbol": expected["trading_symbol"],
                "groww_symbol": expected["groww_symbol"],
                "instrument_type": "IDX",
                "name": expected["name"],
            }
            return _validate_and_build_descriptor(
                instrument,
                synthetic_row,
                resolution_source="instruments_csv:underlying_exchange_token",
            )
        return None
