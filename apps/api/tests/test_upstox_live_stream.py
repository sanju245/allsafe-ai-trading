import json
import ssl
import threading
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState
from app.providers.upstox_stream import (
    UPSTOX_INDEX_KEYS,
    UpstoxLiveStreamManager,
    _request_authorized_uri,
    _validate_authorized_uri,
)
from tests.fixtures.sample_data import ist


def test_upstox_live_feed_normalizes_only_real_timestamped_index_prices():
    as_of = ist(2026, 1, 5, 9, 16, 10)
    feed_time = ist(2026, 1, 5, 9, 16, 3)
    manager = UpstoxLiveStreamManager(
        access_token="server-only-test-token",
        streaming_enabled=True,
    )
    manager._connected = True
    manager._authenticated = True
    result_count = manager.handle_message(
        {
            "feeds": {
                UPSTOX_INDEX_KEYS[InstrumentId.NIFTY50]: {
                    "fullFeed": {
                        "indexFF": {
                            "ltpc": {
                                "ltp": 24567.8,
                                "ltt": str(int(feed_time.timestamp() * 1000)),
                            }
                        }
                    }
                }
            }
        },
        as_of=as_of,
    )

    quote = manager.aggregator.get_latest_quote(InstrumentId.NIFTY50)
    assert result_count == 1
    assert quote is not None
    assert quote.ltp == 24567.8
    assert quote.volume is None
    assert quote.timestamp == feed_time
    assert quote.source.name == "upstox"
    assert manager.status_snapshot(as_of=as_of).feed_state is FeedState.LIVE
    assert (
        manager.evaluate_instrument_state(
            InstrumentId.BANKNIFTY, as_of=as_of
        ).feed_state
        is FeedState.UNAVAILABLE
    )


def test_upstox_rejects_missing_timestamp_and_redacts_token_in_error():
    as_of = ist(2026, 1, 5, 9, 16, 10)
    manager = UpstoxLiveStreamManager(
        access_token="private-token", streaming_enabled=True
    )
    assert (
        manager.handle_message(
            {
                "feeds": {
                    UPSTOX_INDEX_KEYS[InstrumentId.NIFTY50]: {
                        "fullFeed": {"indexFF": {"ltpc": {"ltp": 25000}}}
                    }
                }
            },
            as_of=as_of,
        )
        == 0
    )
    assert manager.aggregator.get_latest_quote(InstrumentId.NIFTY50) is None
    manager._record_error("vendor said private-token")
    assert "private-token" not in (
        manager.status_snapshot(as_of=as_of).last_error or ""
    )


def test_upstox_feed_stays_disabled_without_explicit_setting():
    manager = UpstoxLiveStreamManager(access_token="configured-token")
    assert manager.start(as_of=ist(2026, 1, 5, 9, 16)) is False
    assert manager.status_snapshot(as_of=ist(2026, 1, 5, 9, 16)).connected is False


def test_upstox_v3_protobuf_decoder_loads_from_official_sdk_package():
    import importlib

    proto = importlib.import_module("upstox_client.feeder.proto.MarketDataFeedV3_pb2")
    manager = UpstoxLiveStreamManager(access_token="test-only")
    encoded = proto.FeedResponse().SerializeToString()
    assert manager._decode_message(encoded) == {}


def test_upstox_connect_uses_verified_tls_and_refuses_redirects():
    authorized_url = "wss://feed.upstox.com/market-data?code=single-use"
    connected = threading.Event()
    closed = threading.Event()
    captured = {}

    class FakeConnection:
        def send(self, _payload, *, opcode):
            captured["opcode"] = opcode

        def settimeout(self, _timeout):
            return

        def recv(self):
            connected.set()
            closed.wait(timeout=2)

        def close(self):
            closed.set()

    def fake_connect(url, **options):
        captured["url"] = url
        captured.update(options)
        return FakeConnection()

    manager = UpstoxLiveStreamManager(
        access_token="server-secret",
        streaming_enabled=True,
        authorizer=lambda _token: authorized_url,
        websocket_factory=fake_connect,
    )
    assert manager.start() is True
    assert connected.wait(timeout=2)
    context = captured["sslopt"]["context"]
    assert captured["url"] == authorized_url
    assert captured["redirect_limit"] == 0
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert captured["header"] == {"Accept": "*/*"}
    assert "Authorization" not in captured["header"]
    manager.stop()


def test_authorized_websocket_url_must_be_tls_and_upstox_owned():
    valid = "wss://feed.upstox.com/market-data?code=single-use&requestId=abc"
    assert _validate_authorized_uri(valid) == valid
    for invalid in (
        "ws://feed.upstox.com/market-data?code=abc",
        "wss://feed.evil.test/market-data?code=abc",
        "wss://feed.upstox.com/market-data",
        "wss://user:pass@feed.upstox.com/market-data?code=abc",
        "wss://feed.upstox.com:444/market-data?code=abc",
    ):
        try:
            _validate_authorized_uri(invalid)
        except ValueError:
            continue
        raise AssertionError(f"Unsafe Upstox redirect URL was accepted: {invalid}")


def test_authorizer_normalizes_bearer_prefix_and_sends_expected_headers(monkeypatch):
    authorized_url = "wss://feed.upstox.com/market-data?code=single-use"
    captured = {}

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, *, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["accept"] = request.get_header("Accept")
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return Response(
            json.dumps(
                {
                    "status": "success",
                    "data": {"authorized_redirect_uri": authorized_url},
                }
            ).encode()
        )

    monkeypatch.setattr("app.providers.upstox_stream.urlopen", fake_urlopen)
    assert _request_authorized_uri(" Bearer private-token ") == authorized_url
    assert captured == {
        "authorization": "Bearer private-token",
        "accept": "application/json",
        "user_agent": "AllSafeAITrading/0.2",
        "timeout": 10,
    }


def test_authorizer_reports_only_safe_upstox_error_code(monkeypatch):
    def fake_urlopen(_request, *, timeout):
        raise HTTPError(
            "https://api.upstox.com/v3/feed/market-data-feed/authorize",
            403,
            "Forbidden",
            None,
            BytesIO(
                b'{"errors":[{"errorCode":"UDAPI100050",'
                b'"message":"private-token must never be logged"}]}'
            ),
        )

    monkeypatch.setattr("app.providers.upstox_stream.urlopen", fake_urlopen)
    with pytest.raises(PermissionError, match="UDAPI100050") as error:
        _request_authorized_uri("private-token")
    assert "private-token" not in str(error.value)
    assert "message" not in str(error.value)


def test_authorizer_distinguishes_gateway_block_from_token_rejection(monkeypatch):
    def fake_urlopen(_request, *, timeout):
        raise HTTPError(
            "https://api.upstox.com/v3/feed/market-data-feed/authorize",
            403, "Forbidden", None,
            BytesIO(b'{"cloudflare_error":true,"error_code":1010,"detail":"private-token"}'),
        )

    monkeypatch.setattr("app.providers.upstox_stream.urlopen", fake_urlopen)
    with pytest.raises(PermissionError, match="gateway blocked") as error:
        _request_authorized_uri("private-token")
    assert "private-token" not in str(error.value)
    assert "authorization was rejected" not in str(error.value)
