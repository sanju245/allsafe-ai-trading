"""Read-only Groww live market-data & historical warm-up smoke test.

Guarantees:
* Strictly read-only (fetches historical candles and subscribes to index values only; never places orders).
* Selects a single explicit authentication mode and never silently falls back on auth failure.
* Never prints or logs secret values (`GROWW_ACCESS_TOKEN`, `GROWW_API_KEY`, `GROWW_API_SECRET`, `GROWW_TOTP_SECRET`).
* Distinguishes configuration errors (exit 2), SDK compatibility errors (exit 3),
  authentication failures (exit 4), market closed / empty feed (exit 5), and live success (exit 0).
"""

import argparse
import sys
import time
from datetime import datetime

from app.config import get_settings
from app.market_data.instruments import InstrumentId
from app.market_data.live_aggregator import is_regular_session_ist
from app.market_data.live_models import FeedState
from app.market_data.live_runtime import LiveMarketDataRuntime
from app.market_data.sessions import IST
from app.providers.base import ProviderAuthError
from app.providers.groww_auth import (
    GrowwAuthMode,
    GrowwCredentials,
    redact_groww_secrets,
    verify_groww_sdk_compatibility,
)
from app.providers.groww_stream import GrowwLiveStreamManager


def run_smoke_test(duration_seconds: float = 15.0, allow_closed_session: bool = False) -> int:
    settings = get_settings()
    creds = GrowwCredentials(
        auth_mode=settings.groww_auth_mode,
        access_token=settings.groww_access_token,
        api_key=settings.groww_api_key,
        api_secret=settings.groww_api_secret,
        totp_secret=settings.groww_totp_secret,
    )

    try:
        mode = creds.select_auth_mode()
    except ProviderAuthError as exc:
        msg = redact_groww_secrets(str(exc), secrets=creds.secret_values())
        print(f"[SMOKE FAIL] Invalid Groww credential configuration: {msg}", file=sys.stderr)
        return 2

    if mode is GrowwAuthMode.NONE:
        print(
            "[SMOKE FAIL] Groww credentials are not configured in environment/.env.",
            file=sys.stderr,
        )
        return 2

    sdk_report = verify_groww_sdk_compatibility()
    if not sdk_report.installed or not sdk_report.compatible:
        print(
            f"[SMOKE FAIL] Groww SDK compatibility check failed: {sdk_report.detail}",
            file=sys.stderr,
        )
        return 3

    now_ist = datetime.now(IST)
    session_open = is_regular_session_ist(now_ist)
    if not session_open and not allow_closed_session:
        print(
            f"[SMOKE FAIL] Current time ({now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}) is outside "
            "regular NSE trading hours (Mon-Fri 09:15-15:30 IST). Re-run during an active session "
            "or pass --allow-closed-session to test authentication and historical warm-up only.",
            file=sys.stderr,
        )
        return 5

    mgr = GrowwLiveStreamManager(
        credentials=creds,
        streaming_enabled=True,
        stale_after_seconds=settings.live_stale_seconds,
        max_future_skew_seconds=settings.live_max_future_skew_seconds,
        spawn_consume_thread=True,
    )
    runtime = LiveMarketDataRuntime(
        stream_manager=mgr,
        warmup_lookback_days=settings.live_warmup_lookback_days,
    )

    print(
        f"[SMOKE INFO] Starting read-only Groww smoke test (auth_mode={mode.value}, "
        f"duration={duration_seconds:.1f}s)..."
    )
    started = runtime.start(as_of=now_ist, run_warmup=True)
    if not started:
        snap = mgr.status_snapshot()
        err = redact_groww_secrets(snap.last_error or "Failed to start Groww stream.", secrets=creds.secret_values())
        print(f"[SMOKE FAIL] Groww stream failed to start: {err}", file=sys.stderr)
        return 4 if snap.feed_state == FeedState.FAILED else 5

    deadline = time.monotonic() + max(1.0, duration_seconds)
    try:
        while time.monotonic() < deadline:
            snap = mgr.status_snapshot()
            if snap.feed_state == FeedState.FAILED:
                err = redact_groww_secrets(snap.last_error or "Stream failure.", secrets=creds.secret_values())
                print(f"[SMOKE FAIL] Groww stream reported failure: {err}", file=sys.stderr)
                return 4
            nifty_q = mgr.aggregator.get_latest_quote(InstrumentId.NIFTY50)
            bank_q = mgr.aggregator.get_latest_quote(InstrumentId.BANKNIFTY)
            if nifty_q is not None and bank_q is not None:
                break
            time.sleep(0.5)
    finally:
        runtime.stop()

    snap = mgr.status_snapshot()
    nifty_q = mgr.aggregator.get_latest_quote(InstrumentId.NIFTY50)
    bank_q = mgr.aggregator.get_latest_quote(InstrumentId.BANKNIFTY)

    if nifty_q is None and bank_q is None:
        if allow_closed_session and snap.authenticated:
            print("[SMOKE WARN] Authenticated and resolved instruments outside trading hours (0 live ticks received).")
            return 0
        print(
            "[SMOKE FAIL] Connected but received 0 validated index updates for NIFTY50 and BANKNIFTY.",
            file=sys.stderr,
        )
        return 5

    for inst, q in ((InstrumentId.NIFTY50, nifty_q), (InstrumentId.BANKNIFTY, bank_q)):
        if q is not None:
            print(
                f"[SMOKE OK] {inst.value} ({q.provider_symbol}): value={q.ltp:.2f} "
                f"tick_time={q.timestamp.isoformat()}"
            )
        else:
            print(f"[SMOKE WARN] No index update received yet for {inst.value} within window.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Groww live smoke test.")
    parser.add_argument("--duration-seconds", type=float, default=15.0)
    parser.add_argument("--allow-closed-session", action="store_true")
    args = parser.parse_args()
    return run_smoke_test(
        duration_seconds=args.duration_seconds,
        allow_closed_session=args.allow_closed_session,
    )


if __name__ == "__main__":
    raise SystemExit(main())
