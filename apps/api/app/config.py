"""Application settings, loaded from environment variables or a local .env file.

Secrets live only here on the server. Nothing in this module is sent to the browser.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # Comma-separated list of allowed browser origins (supports local dev and Vercel production).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,https://allsafe-ai-trading.vercel.app"
    # Regex matching authorized Vercel production & branch preview origins plus localhost.
    cors_origin_regex: str = r"^https://allsafe-ai-trading(-[a-z0-9-]+)?\.vercel\.app$|^http://(localhost|127\.0\.0\.1)(:\d+)?$"

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
    live_warmup_background: bool = True

    # Authentication, Session & Permanent Super Admin settings (server-side only).
    auth_secret_key: str = ""
    auth_session_ttl_seconds: int = 28800
    auth_login_rate_limit_per_minute: int = 12
    auth_max_failed_attempts: int = 5
    auth_lockout_seconds: int = 900
    super_admin_id: str = "00000000-0000-4000-a000-000000000001"
    super_admin_username: str = "superadmin"
    super_admin_email: str = "admin@allsafe.ai"
    super_admin_password_hash: str = ""
    super_admin_initial_password: str = ""
    super_admin_totp_secret: str = ""
    admin_global_ip_access: bool = True
    trust_proxy_headers: bool = True
    trusted_proxy_hops: int = 1
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fc00::/7"
    jwks_cache_ttl_seconds: int = 3600
    jwks_refresh_cooldown_seconds: int = 30

    # AllSafe Universal AI Agent Hub settings (server-side only).
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    hub_supervised_mode: bool = True
    hub_allow_autonomous_live_trading: bool = False
    hub_admin_api_key_hash: str = ""
    hub_rate_limit_per_minute: int = 120
    hub_max_request_bytes: int = 262144
    gemini_api_key: str = ""
    gemini_daily_budget_usd: float = 0.0
    openai_daily_budget_usd: float = 0.0
    qwen_colab_worker_token_hash: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origin_list_raw if o.strip()]

    @property
    def cors_origin_list_raw(self) -> list[str]:
        return self.cors_origins.split(",")

    def __repr__(self) -> str:
        return (
            f"Settings(app_env={self.app_env!r}, "
            f"live_stream_enabled={self.live_stream_enabled!r}, "
            f"market_data_provider={self.market_data_provider!r}, "
            f"groww_auth_mode={self.groww_auth_mode!r}, "
            f"groww_access_token={'[REDACTED]' if self.groww_access_token.strip() else '[EMPTY]'}, "
            f"groww_api_key={'[REDACTED]' if self.groww_api_key.strip() else '[EMPTY]'}, "
            f"groww_api_secret={'[REDACTED]' if self.groww_api_secret.strip() else '[EMPTY]'}, "
            f"groww_totp_secret={'[REDACTED]' if self.groww_totp_secret.strip() else '[EMPTY]'}, "
            f"auth_secret_key={'[REDACTED]' if self.auth_secret_key.strip() else '[EPHEMERAL]'}, "
            f"super_admin_id={self.super_admin_id!r}, "
            f"super_admin_username={self.super_admin_username!r}, "
            f"super_admin_email={self.super_admin_email!r}, "
            f"super_admin_password_hash={'[REDACTED]' if self.super_admin_password_hash.strip() else '[EMPTY]'}, "
            f"super_admin_initial_password={'[REDACTED]' if self.super_admin_initial_password.strip() else '[EMPTY]'}, "
            f"super_admin_totp_secret={'[REDACTED]' if self.super_admin_totp_secret.strip() else '[EMPTY]'}, "
            f"supabase_url={self.supabase_url!r}, "
            f"supabase_service_role_key={'[REDACTED]' if self.supabase_service_role_key.strip() else '[EMPTY]'}, "
            f"supabase_jwt_secret={'[REDACTED]' if self.supabase_jwt_secret.strip() else '[EMPTY]'}, "
            f"hub_admin_api_key_hash={'[REDACTED]' if self.hub_admin_api_key_hash.strip() else '[EMPTY]'}, "
            f"gemini_api_key={'[REDACTED]' if self.gemini_api_key.strip() else '[EMPTY]'})"
        )

    __str__ = __repr__


@lru_cache
def get_settings() -> Settings:
    return Settings()
