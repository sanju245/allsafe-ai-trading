"""Tests for GrowwLiveStreamManager (`subscribe_index_value`, `get_index_value`,
reconnect backoff, feed states) and LiveMarketDataRuntime (historical warm-up +
5-indicator integration, incomplete candle blocking, and stale signal protection).
"""

from datetime import timedelta

from app.indicators.decision import TradeDecision
from app.market_data.instruments import InstrumentId
from app.market_data.live_models import FeedState, IncompleteReason
from app.market_data.live_runtime import LiveMarketDataRuntime
from app.providers.groww_auth import GrowwCredentials
from app.providers.groww_stream import (
    GrowwLiveStreamManager,
    parse_groww_index_feed_Snapshot,
)
from tests.fixtures.sample_data import ist
from tests.test_groww_auth_and_instruments import FakeGrowwAPI, FakeGrowwFeed


class StatefulFakeGrowwFeed(FakeGrowwFeed):
    def __init__(self, groww_client: FakeGrowwAPI) -> None:
        super().__init__(groww_client)
        self.subscribed_instruments = []
        self.callback = None
        self.unsubscribed = False
        self.current_payload = {}

    def subscribe_index_value(self, instruments_list, on_data_received=None):
        self.subscribed_instruments = list(instruments_list)
        self.callback = on_data_received

    def get_index_value(self):
        return self.current_payload

    def unsubscribe_index_value(self, instruments_list):
        self.unsubscribed = True


def test_parse_groww_index_feed_snapshot():
    ts = ist(2026, 1, 5, 9, 15, 10)
    ms = float(int(ts.timestamp() * 1000))
    payload = {
        "NSE": {
            "CASH": {
                "NIFTY": {"tsInMillis": ms, "value": 24386.7},
                "26009": {"tsInMillis": ms, "value": 51234.5},
            }
        }
    }
    updates = parse_groww_index_feed_Snapshot(payload)
    assert len(updates) == 2
    by_tok = {u.exchange_token: u for u in updates}
    assert by_tok["NIFTY"].value == 24386.7
    assert by_tok["NIFTY"].timestamp == ts
    assert by_tok["26009"].value == 51234.5
    assert by_tok["26009"].timestamp == ts


def test_groww_stream_subscribes_both_indices_and_tracks_feed_states():
    feeds: list[StatefulFakeGrowwFeed] = []

    def feed_factory(client):
        f = StatefulFakeGrowwFeed(client)
        feeds.append(f)
        return f

    # Add required methods on factory for verify_groww_sdk_compatibility
    for m in ("subscribe_index_value", "get_index_value", "unsubscribe_index_value", "consume"):
        setattr(feed_factory, m, getattr(StatefulFakeGrowwFeed, m))

    creds = GrowwCredentials(auth_mode="access_token", access_token="VALID_GROWW_TOKEN_12345")
    mgr = GrowwLiveStreamManager(
        credentials=creds,
        streaming_enabled=True,
        stale_after_seconds=30.0,
        api_cls=FakeGrowwAPI,
        feed_cls=feed_factory,
    )

    t0 = ist(2026, 1, 5, 9, 15, 0)
    assert mgr.start(as_of=t0) is True
    assert len(feeds) == 1
    assert feeds[0].subscribed_instruments == [
        {"exchange": "NSE", "segment": "CASH", "exchange_token": "NIFTY"},
        {"exchange": "NSE", "segment": "CASH", "exchange_token": "26009"},
    ]

    # Push index update for both NIFTY and BANKNIFTY at 09:15:05
    t1 = ist(2026, 1, 5, 9, 15, 5)
    ms1 = float(int(t1.timestamp() * 1000))
    feeds[0].current_payload = {
        "NSE": {
            "CASH": {
                "NIFTY": {"tsInMillis": ms1, "value": 24500.0},
                "26009": {"tsInMillis": ms1, "value": 51000.0},
            }
        }
    }
    res = mgr.handle_index_feed_payload(feeds[0].current_payload, as_of=t1)
    assert len(res) == 2 and all(r.accepted for r in res)

    # Quote volume must be None (never fabricated 0)
    q_nifty = mgr.aggregator.get_latest_quote(InstrumentId.NIFTY50)
    assert q_nifty is not None and q_nifty.ltp == 24500.0 and q_nifty.volume is None

    # Check LIVE state at 09:15:15
    snap_live = mgr.status_snapshot(as_of=ist(2026, 1, 5, 9, 15, 15))
    assert snap_live.feed_state == FeedState.LIVE
    assert snap_live.auth_mode == "access_token"
    assert snap_live.instruments[InstrumentId.NIFTY50].feed_state == FeedState.LIVE
    assert snap_live.instruments[InstrumentId.BANKNIFTY].feed_state == FeedState.LIVE

    # Check STALE state at 09:16:00 (>30s old)
    snap_stale = mgr.status_snapshot(as_of=ist(2026, 1, 5, 9, 16, 0))
    assert snap_stale.feed_state == FeedState.STALE
    assert snap_stale.instruments[InstrumentId.NIFTY50].is_stale is True

    # Simulate GrowwFeedConnectionException -> DISCONNECTED + incomplete forming candle + backoff
    delay = mgr.handle_feed_error(RuntimeError("GrowwFeedConnectionException: NATS socket lost"), as_of=ist(2026, 1, 5, 9, 16, 5))
    assert delay == 1.0
    snap_disc = mgr.status_snapshot(as_of=ist(2026, 1, 5, 9, 16, 5))
    assert snap_disc.feed_state == FeedState.DISCONNECTED
    forming = mgr.aggregator.get_forming_candle(InstrumentId.NIFTY50)
    assert forming is not None and forming.is_incomplete is True
    assert IncompleteReason.FEED_INTERRUPTED_DURING_SLOT in forming.incomplete_reasons

    mgr.stop(as_of=ist(2026, 1, 5, 9, 16, 10))
    assert feeds[0].unsubscribed is True


def test_runtime_historical_warmup_and_indicator_protection_rules():
    from tests.test_groww_historical import HistoricalFakeGrowwAPI

    # Create 55 historical 5m candles on Mon Jan 5, 2026 (09:15 to 13:45 IST)
    base = ist(2026, 1, 5, 9, 15)
    rows = []
    for i in range(55):
        slot = base + timedelta(minutes=5 * i)
        p = 24000.0 + 5.0 * i
        rows.append([slot.strftime("%Y-%m-%dT%H:%M:%S"), p, p + 10.0, p - 5.0, p + 3.0, None, None])

    class RuntimeFakeAPI(HistoricalFakeGrowwAPI):
        def __init__(self, token: str):
            super().__init__(rows)

    for m in ("subscribe_index_value", "get_index_value", "unsubscribe_index_value", "consume"):
        setattr(StatefulFakeGrowwFeed, m, getattr(StatefulFakeGrowwFeed, m))

    creds = GrowwCredentials(auth_mode="access_token", access_token="TOK_RUNTIME")
    mgr = GrowwLiveStreamManager(
        credentials=creds,
        streaming_enabled=True,
        stale_after_seconds=60.0,
        api_cls=RuntimeFakeAPI,
        feed_cls=StatefulFakeGrowwFeed,
    )
    runtime = LiveMarketDataRuntime(stream_manager=mgr)

    # Start and warm up at 13:50 IST (right after the 55th candle [13:45-13:50] closed!)
    t_now = ist(2026, 1, 5, 13, 50, 2)
    assert runtime.start(as_of=t_now, run_warmup=True) is True

    # Feed a live update in the 13:50 slot
    mgr.handle_index_feed_payload(
        {"NSE": {"CASH": {"NIFTY": {"tsInMillis": float(int(t_now.timestamp() * 1000)), "value": 24300.0}}}},
        as_of=t_now,
    )

    # Evaluate decision at 13:50:05 IST:
    # - 55 historical closed candles are used; the 13:50 forming candle is excluded from confirmed series
    summary = runtime.evaluate_decision_for_instrument(InstrumentId.NIFTY50, as_of=ist(2026, 1, 5, 13, 50, 5))
    assert summary.confirmed_candle_count == 55
    assert summary.candle_timestamp == ist(2026, 1, 5, 13, 45)
    assert summary.decision in (TradeDecision.BUY, TradeDecision.SELL, TradeDecision.WAIT)
    assert summary.feed_state == FeedState.LIVE

    # Now advance time by 5 minutes without ticks -> feed becomes STALE, is_current_signal must be False!
    stale_summary = runtime.evaluate_decision_for_instrument(InstrumentId.NIFTY50, as_of=ist(2026, 1, 5, 13, 52, 0))
    assert stale_summary.is_stale is True
    assert stale_summary.is_current_signal is False
