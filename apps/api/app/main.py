"""FastAPI entry point for AllSafe AI Trading.

Phase 1: only a health endpoint. No market data, indicators or signals exist yet.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AllSafe AI Trading API",
    version=__version__,
    description="Market analysis API. Analysis only; no broker order placement.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
