"""Application settings, loaded from environment variables or a local .env file.

Secrets live only here on the server. Nothing in this module is sent to the browser.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Live Groww market-data streaming (disabled by default for safety).
    live_stream_enabled: bool = False
    market_data_provider: str = "groww"
    # Explicit Groww authentication mode: "access_token", "totp", or "api_key_secret"
    groww_auth_mode: str = ""
    groww_access_token: str = ""
    groww_api_key: str = ""
    groww_api_secret: str = ""
    groww_totp_secret: str = ""
    live_stale_seconds: float = 60.0
    live_max_future_skew_seconds: float = 5.0
    live_candle_buffer_size: int = 500
    live_warmup_lookback_days: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def __repr__(self) -> str:
        return (
            f"Settings(app_env={self.app_env!r}, "
            f"live_stream_enabled={self.live_stream_enabled!r}, "
            f"market_data_provider={self.market_data_provider!r}, "
            f"groww_auth_mode={self.groww_auth_mode!r}, "
            f"groww_access_token={'[REDACTED]' if self.groww_access_token.strip() else '[EMPTY]'}, "
            f"groww_api_key={'[REDACTED]' if self.groww_api_key.strip() else '[EMPTY]'}, "
            f"groww_api_secret={'[REDACTED]' if self.groww_api_secret.strip() else '[EMPTY]'}, "
            f"groww_totp_secret={'[REDACTED]' if self.groww_totp_secret.strip() else '[EMPTY]'})"
        )

    __str__ = __repr__


@lru_cache
def get_settings() -> Settings:
    return Settings()
