"""Unit tests for Groww authentication flows, single-mode enforcement, secret redaction,
and authoritative instrument resolution for NIFTY 50 and BANK NIFTY.
"""

import hashlib
import pytest

from app.market_data.instruments import InstrumentId
from app.providers.base import ProviderAuthError, ProviderUnavailableError
from app.providers.groww_auth import (
    GrowwAuthMode,
    GrowwCredentials,
    authenticate_groww_client,
    generate_groww_checksum,
    redact_groww_secrets,
    verify_groww_sdk_compatibility,
)
from app.providers.groww_instruments import GrowwInstrumentResolver


class FakeGrowwAPI:
    EXCHANGE_NSE = "NSE"
    SEGMENT_CASH = "CASH"
    CANDLE_INTERVAL_MIN_5 = "5minute"

    auth_calls: list[tuple[str, dict]] = []

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    @classmethod
    def get_access_token(cls, **kwargs) -> str:
        cls.auth_calls.append(("get_access_token", dict(kwargs)))
        if kwargs.get("totp") == "BAD_TOTP" or kwargs.get("secret") == "BAD_SECRET":
            raise RuntimeError("GrowwAPIAuthenticationException: Invalid credentials GA005")
        return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJncm93dyJ9.token_sig"

    def get_quote(self, **kwargs):
        return {}

    def get_ltp(self, **kwargs):
        return {}

    def get_ohlc(self, **kwargs):
        return {}

    def get_historical_candles(self, **kwargs):
        return {"candles": []}

    def get_instrument_by_groww_symbol(self, groww_symbol: str):
        mapping = {
            "NSE-NIFTY": {
                "exchange": "NSE",
                "segment": "CASH",
                "exchange_token": "NIFTY",
                "trading_symbol": "NIFTY",
                "groww_symbol": "NSE-NIFTY",
                "instrument_type": "IDX",
                "name": "NIFTY 50",
            },
            "NSE-BANKNIFTY": {
                "exchange": "NSE",
                "segment": "CASH",
                "exchange_token": "26009",
                "trading_symbol": "BANKNIFTY",
                "groww_symbol": "NSE-BANKNIFTY",
                "instrument_type": "IDX",
                "name": "BANK NIFTY",
            },
        }
        return mapping.get(groww_symbol)

    def get_instrument_by_exchange_and_trading_symbol(self, exchange: str, trading_symbol: str):
        if exchange == "NSE" and trading_symbol == "NIFTY":
            return self.get_instrument_by_groww_symbol("NSE-NIFTY")
        if exchange == "NSE" and trading_symbol == "BANKNIFTY":
            return self.get_instrument_by_groww_symbol("NSE-BANKNIFTY")
        return None


class FakeGrowwFeed:
    def __init__(self, groww_client: FakeGrowwAPI) -> None:
        self.client = groww_client

    def subscribe_index_value(self, instruments_list, on_data_received=None):
        pass

    def get_index_value(self):
        return {}

    def unsubscribe_index_value(self, instruments_list):
        pass

    def consume(self):
        pass


def test_direct_access_token_mode():
    creds = GrowwCredentials(
        auth_mode="access_token",
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiMSJ9.direct_tok",
    )
    assert creds.select_auth_mode() == GrowwAuthMode.ACCESS_TOKEN
    client, mode = authenticate_groww_client(creds, api_cls=FakeGrowwAPI)
    assert mode == GrowwAuthMode.ACCESS_TOKEN
    assert client.access_token.endswith(".direct_tok")


def test_totp_auth_mode_and_no_fallback_on_failure():
    FakeGrowwAPI.auth_calls.clear()
    creds = GrowwCredentials(
        auth_mode="totp",
        api_key="GROWW_TOTP_API_KEY_SECRET",
        totp_secret="JBSWY3DPEHPK3PXP",
    )
    assert creds.select_auth_mode() == GrowwAuthMode.TOTP
    client, mode = authenticate_groww_client(
        creds,
        api_cls=FakeGrowwAPI,
        totp_generator=lambda secret: "123456",
    )
    assert mode == GrowwAuthMode.TOTP
    assert len(FakeGrowwAPI.auth_calls) == 1
    assert FakeGrowwAPI.auth_calls[0][1] == {"api_key": "GROWW_TOTP_API_KEY_SECRET", "totp": "123456"}

    # Verify NO fallback to access_token or api_key_secret if TOTP fails!
    FakeGrowwAPI.auth_calls.clear()
    failing_creds = GrowwCredentials(
        auth_mode="totp",
        access_token="SHOULD_NEVER_BE_USED_AS_FALLBACK",
        api_key="GROWW_TOTP_API_KEY_SECRET",
        api_secret="SHOULD_NEVER_BE_USED_AS_FALLBACK",
        totp_secret="JBSWY3DPEHPK3PXP",
    )
    with pytest.raises(ProviderAuthError, match="totp"):
        authenticate_groww_client(
            failing_creds,
            api_cls=FakeGrowwAPI,
            totp_generator=lambda secret: "BAD_TOTP",
        )
    # Exactly 1 call was attempted (no fallback!)
    assert len(FakeGrowwAPI.auth_calls) == 1


def test_api_key_secret_auth_mode_and_checksum():
    FakeGrowwAPI.auth_calls.clear()
    creds = GrowwCredentials(
        auth_mode="api_key_secret",
        api_key="MY_GROWW_API_KEY",
        api_secret="MY_GROWW_API_SECRET",
    )
    assert creds.select_auth_mode() == GrowwAuthMode.API_KEY_SECRET
    client, mode = authenticate_groww_client(creds, api_cls=FakeGrowwAPI)
    assert mode == GrowwAuthMode.API_KEY_SECRET
    assert FakeGrowwAPI.auth_calls[0][1] == {"api_key": "MY_GROWW_API_KEY", "secret": "MY_GROWW_API_SECRET"}

    expected_sha = hashlib.sha256(b"MY_GROWW_API_SECRET1719830400").hexdigest()
    assert generate_groww_checksum("MY_GROWW_API_SECRET", "1719830400") == expected_sha


def test_ambiguous_multi_mode_without_selector_is_rejected():
    creds = GrowwCredentials(
        access_token="SOME_TOKEN",
        api_key="SOME_KEY",
        api_secret="SOME_SECRET",
    )
    with pytest.raises(ProviderAuthError, match="Multiple Groww authentication modes"):
        creds.select_auth_mode()


def test_secret_redaction_strips_all_groww_credentials():
    creds = GrowwCredentials(
        auth_mode="totp",
        access_token="SECRET_ACCESS_TOK_111",
        api_key="SECRET_API_KEY_222",
        api_secret="SECRET_API_SEC_333",
        totp_secret="SECRET_TOTP_444",
    )
    assert "SECRET_" not in repr(creds)
    raw = f"Failed for api_key={creds.api_key} secret={creds.api_secret} totp_secret={creds.totp_secret} Bearer {creds.access_token}"
    redacted = redact_groww_secrets(raw, secrets=creds.secret_values())
    for s in creds.secret_values():
        assert s not in redacted
    assert "[REDACTED]" in redacted


def test_sdk_compatibility_check():
    rep = verify_groww_sdk_compatibility(api_cls=FakeGrowwAPI, feed_cls=FakeGrowwFeed)
    assert rep.installed is True
    assert rep.compatible is True


def test_authoritative_instrument_resolution_from_sdk_and_csv():
    client = FakeGrowwAPI("tok")
    resolver = GrowwInstrumentResolver(groww_client=client)
    nifty = resolver.resolve(InstrumentId.NIFTY50)
    bank = resolver.resolve(InstrumentId.BANKNIFTY)

    assert nifty.groww_symbol == "NSE-NIFTY"
    assert nifty.trading_symbol == "NIFTY"
    assert nifty.exchange_token == "NIFTY"
    assert nifty.to_feed_subscription_dict() == {
        "exchange": "NSE",
        "segment": "CASH",
        "exchange_token": "NIFTY",
    }

    assert bank.groww_symbol == "NSE-BANKNIFTY"
    assert bank.trading_symbol == "BANKNIFTY"
    assert bank.exchange_token == "26009"
    assert bank.to_feed_subscription_dict() == {
        "exchange": "NSE",
        "segment": "CASH",
        "exchange_token": "26009",
    }

    # Also test resolving from official Groww instrument.csv format
    sample_csv = (
        "exchange,exchange_token,trading_symbol,groww_symbol,name,instrument_type,segment,underlying_symbol,underlying_exchange_token\n"
        "NSE,26000,NIFTY,NSE-NIFTY,NIFTY 50,IDX,CASH,,\n"
        "NSE,49445,BANKNIFTY25DEC27000PE,NSE-BANKNIFTY-24Dec25-27000-PE,,PE,FNO,BANKNIFTY,26009\n"
    )
    csv_resolver = GrowwInstrumentResolver(csv_text=sample_csv)
    assert csv_resolver.resolve("NIFTY50").exchange_token == "26000"
    assert csv_resolver.resolve("BANKNIFTY").exchange_token == "26009"

    # Empty resolver with no authoritative source must raise ProviderUnavailableError (never guess!)
    empty_resolver = GrowwInstrumentResolver()
    with pytest.raises(ProviderUnavailableError):
        empty_resolver.resolve("NIFTY50")
