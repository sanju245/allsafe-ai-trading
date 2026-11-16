"""FastAPI entry point for AllSafe AI Trading.

Endpoints:
* /health (Phase 1)
* /api/v1/market-data/* (Phase 2: describe supported instruments and timeframes,
  validate a supplied candle series)
* /api/v1/live/* (Groww read-only live market-data status, quote, confirmed 5m
  candles + 5-indicator decision summary, and forming 5m candle; disabled by default).
"""

import asyncio
import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.routers import account_requests, admin, auth, live, market_data
from app.routers.live import build_runtimes_from_settings, set_live_runtimes

settings = get_settings()


def startup_live_runtime(application: FastAPI) -> None:
    """Initialize configured read-only Groww and Upstox market-data runtimes."""
    runtimes = getattr(application.state, "live_runtimes", None)
    if not isinstance(runtimes, dict):
        runtimes = build_runtimes_from_settings(get_settings())
        set_live_runtimes(application, runtimes)
    for runtime in runtimes.values():
        if runtime.stream_manager.streaming_enabled:
            runtime.start(run_warmup=True)


def shutdown_live_runtime(application: FastAPI) -> None:
    """Cleanly stop configured provider feed connections on application shutdown."""
    runtimes = getattr(application.state, "live_runtimes", None)
    if isinstance(runtimes, dict):
        for runtime in runtimes.values():
            runtime.stop()
    else:
        rt = getattr(application.state, "live_runtime", None)
        if rt is not None:
            rt.stop()


@asynccontextmanager
async def lifespan(application: FastAPI):
    # The Groww SDK creates and runs its own asyncio loop during feed startup.
    # Keep that blocking SDK work off the ASGI loop to avoid nested-loop errors.
    await asyncio.to_thread(startup_live_runtime, application)
    try:
        yield
    finally:
        await asyncio.to_thread(shutdown_live_runtime, application)


_fastapi_kwargs: dict[str, object] = {
    "title": "AllSafe AI Trading API",
    "version": __version__,
    "description": "Market analysis API. Analysis only; no broker order placement.",
}
if "lifespan" in inspect.signature(FastAPI.__init__).parameters:
    _fastapi_kwargs["lifespan"] = lifespan

app = FastAPI(**cast(Any, _fastapi_kwargs))
if "lifespan" not in _fastapi_kwargs:
    app.router.on_startup.append(lambda: startup_live_runtime(app))
    app.router.on_shutdown.append(lambda: shutdown_live_runtime(app))


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation paths/messages without echoing submitted field values."""
    safe_errors = [
        {
            "type": error.get("type", "value_error"),
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid request value."),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # PUT is required by PUT /api/v1/auth/password; without it browsers block the preflight.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(market_data.router)
app.include_router(live.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(account_requests.public_router)
app.include_router(account_requests.admin_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness check. Reports service status only, never market data."""
    return {
        "status": "ok",
        "service": "allsafe-ai-trading-api",
        "version": __version__,
        "environment": settings.app_env,
        "time_utc": datetime.now(UTC).isoformat(),
    }
