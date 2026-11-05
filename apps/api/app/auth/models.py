"""Pydantic request and response models for Authentication and Admin Control Center."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppUserSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    username: str = "user"
    email: str
    role: Literal["admin", "user", "operator", "auditor"] = "user"
    is_super_admin: bool = False
    status: Literal["active", "paused", "locked"] = "active"
    allowed_ip: str | None = None
    permissions: list[str] = Field(default_factory=list)
    mfa_enabled: bool = False
    last_login_at: str | None = None
    last_login_ip: str | None = None
    created_at: str
    updated_at: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(default="", max_length=254, description="Email address or administrator username")
    username: str | None = Field(default=None, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=12)
    portal: Literal["customer", "admin"] | None = Field(default=None, description="Optional portal scope")

    @field_validator("email")
    @classmethod
    def _strip_email(cls, v: str) -> str:
        return v.strip()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    csrf_token: str
    user: AppUserSchema


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=10, max_length=128)


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(..., min_length=3, max_length=254)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "user", "operator", "auditor"] = "user"
    status: Literal["active", "paused"] = "active"
    allowed_ip: str | None = Field(default=None, max_length=256)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            raise ValueError("Provide a valid email address.")
        return cleaned


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str | None = Field(default=None, max_length=64)
    role: Literal["admin", "user", "operator", "auditor"] | None = None
    status: Literal["active", "paused"] | None = None
    allowed_ip: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=128)


class SessionInfoSchema(BaseModel):
    jti: str
    user_id: str
    username: str
    email: str
    role: str
    ip_address: str
    user_agent: str
    created_at: str
    expires_at: str
    is_current: bool = False


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    paused_users: int
    locked_users: int
    admin_users: int
    super_admin_id: str
    super_admin_username: str
    global_ip_access_enabled: bool
    active_sessions: int
    audit_events_count: int
    error_events_count: int
    read_only_mode: bool = True
    execution_disabled: bool = True
    market_feed_state: str
    market_session_open: bool
    api_version: str
    environment: str
    checked_at: str


class AdminRoleDefinitionSchema(BaseModel):
    role: str
    label: str
    description: str
    is_system_role: bool = True
    permissions: list[str]
    user_count: int = 0


class UpdateRolePermissionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=280)
    permissions: list[str] = Field(..., min_length=1, max_length=32)


class AdminContentConfigSchema(BaseModel):
    announcement_banner: str
    announcement_enabled: bool
    featured_instruments: list[str]
    default_timeframe: str
    default_capital_inr: int
    default_risk_pct: float
    max_risk_pct_cap: float
    min_risk_reward_ratio: float
    educational_disclaimer: str
    read_only_safety_lock: bool = True
    updated_at: str
    updated_by: str


class UpdateContentConfigRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    announcement_banner: str | None = Field(default=None, max_length=500)
    announcement_enabled: bool | None = None
    featured_instruments: list[str] | None = None
    default_capital_inr: int | None = Field(default=None, ge=25000, le=50000000)
    default_risk_pct: float | None = Field(default=None, ge=0.1, le=2.0)
    min_risk_reward_ratio: float | None = Field(default=None, ge=1.2, le=5.0)
    educational_disclaimer: str | None = Field(default=None, max_length=1000)


class AdminSystemSettingsSchema(BaseModel):
    admin_global_ip_access: bool = True
    session_ttl_seconds: int = 28800
    login_rate_limit_per_minute: int = 12
    max_failed_login_attempts: int = 5
    lockout_duration_seconds: int = 900
    live_poll_interval_seconds: int = 15
    off_hours_poll_interval_seconds: int = 60
    require_strong_passwords: bool = True
    csrf_protection_enabled: bool = True
    maintenance_mode: bool = False
    read_only_trading_invariant: bool = True
    updated_at: str
    updated_by: str


class UpdateSystemSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    admin_global_ip_access: bool | None = None
    session_ttl_seconds: int | None = Field(default=None, ge=300, le=86400)
    login_rate_limit_per_minute: int | None = Field(default=None, ge=3, le=120)
    max_failed_login_attempts: int | None = Field(default=None, ge=3, le=20)
    lockout_duration_seconds: int | None = Field(default=None, ge=60, le=7200)
    live_poll_interval_seconds: int | None = Field(default=None, ge=5, le=120)
    off_hours_poll_interval_seconds: int | None = Field(default=None, ge=15, le=300)
    maintenance_mode: bool | None = None


class AdminAuditLogSchema(BaseModel):
    id: str
    timestamp: str
    actor_id: str
    actor_email: str
    action: str
    target_type: str
    target_id: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"
    ip_address: str
    status: Literal["success", "denied", "error"] = "success"
    details: str


class AdminErrorEntrySchema(BaseModel):
    id: str
    timestamp: str
    component: str
    severity: Literal["warning", "error", "critical"] = "error"
    message: str
    resolved: bool = False


class AdminHealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "offline"]
    service: str
    version: str
    environment: str
    checked_at: str
    uptime_seconds: float
    database_mode: str
    supabase_configured: bool
    super_admin_provisioned: bool
    global_ip_access_enabled: bool
    market_feed: dict[str, object]
    security_posture: dict[str, object]
    recent_errors: list[AdminErrorEntrySchema]


class AdminActionResponse(BaseModel):
    ok: bool = True
    message: str
