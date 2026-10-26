"""FastAPI entry point for AllSafe AI Trading.

Endpoints:
* /health (Phase 1)
* /api/v1/market-data/* (Phase 2: describe supported instruments and timeframes,
  validate a supplied candle series)
* /api/v1/live/* (Groww read-only live market-data status, quote, confirmed 5m
  candles + 5-indicator decision summary, and forming 5m candle; disabled by default).
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import inspect

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import live, market_data
from app.routers.live import build_runtime_from_settings, set_live_runtime

settings = get_settings()


def startup_live_runtime(application: FastAPI) -> None:
    """Initialize the Groww live runtime on app.state and start only if enabled."""
    existing = getattr(application.state, "live_runtime", None)
    if existing is None:
        rt = build_runtime_from_settings(get_settings())
        set_live_runtime(application, rt)
    else:
        rt = existing
    if rt.stream_manager.streaming_enabled:
        rt.start(run_warmup=True)


def shutdown_live_runtime(application: FastAPI) -> None:
    """Cleanly stop any active Groww live stream connection on application shutdown."""
    rt = getattr(application.state, "live_runtime", None)
    if rt is not None:
        rt.stop()


@asynccontextmanager
async def lifespan(application: FastAPI):
    startup_live_runtime(application)
    try:
        yield
    finally:
        shutdown_live_runtime(application)


_fastapi_kwargs: dict[str, object] = {
    "title": "AllSafe AI Trading API",
    "version": __version__,
    "description": "Market analysis API. Analysis only; no broker order placement.",
}
if "lifespan" in inspect.signature(FastAPI.__init__).parameters:
    _fastapi_kwargs["lifespan"] = lifespan

app = FastAPI(**_fastapi_kwargs)
if "lifespan" not in _fastapi_kwargs:
    app.router.on_startup.append(lambda: startup_live_runtime(app))
    app.router.on_shutdown.append(lambda: shutdown_live_runtime(app))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(market_data.router)
app.include_router(live.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness check. Reports service status only, never market data."""
    return {
        "status": "ok",
        "service": "allsafe-ai-trading-api",
        "version": __version__,
        "environment": settings.app_env,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }
