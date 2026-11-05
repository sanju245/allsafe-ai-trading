"""Admin Control Center endpoints (`/api/v1/admin/*`).

Provides:
* GET /api/v1/admin/stats — Key platform, user, session, and market-feed statistics
* GET /api/v1/admin/users — Searchable, filterable account directory
* POST /api/v1/admin/users — Create user or administrator account
* PATCH|PUT /api/v1/admin/users/{user_id} — Update role, status, global/CIDR IP rules, or password
* DELETE /api/v1/admin/users/{user_id} — Delete customer account (Super Admin protected)
* POST /api/v1/admin/users/{user_id}/unlock — Clear brute-force lockout
* POST /api/v1/admin/users/{user_id}/revoke-sessions — Revoke all active sessions for a user
* GET|PATCH /api/v1/admin/roles — Role and permission management
* GET|PATCH /api/v1/admin/content — Content and application configuration management
* GET /api/v1/admin/audit-logs — Immutable system activity & security audit trail
* GET|PATCH /api/v1/admin/settings — System & security settings management
* GET /api/v1/admin/health & POST /api/v1/admin/errors/clear — System health & error diagnostics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.auth.models import (
    AdminActionResponse,
    AdminAuditLogSchema,
    AdminContentConfigSchema,
    AdminHealthResponse,
    AdminRoleDefinitionSchema,
    AdminStatsResponse,
    AdminSystemSettingsSchema,
    AppUserSchema,
    CreateUserRequest,
    SessionInfoSchema,
    UpdateContentConfigRequest,
    UpdateRolePermissionsRequest,
    UpdateSystemSettingsRequest,
    UpdateUserRequest,
)
from app.auth.security import extract_client_ip
from app.auth.store import AuthStore, StoredSession, get_auth_store
from app.routers.auth import get_current_user_and_session
from app.routers.live import get_live_runtime

router = APIRouter(prefix="/api/v1/admin", tags=["admin-control-center"])


def require_admin_user(
    request: Request,
    pair: tuple[AppUserSchema, StoredSession] = Depends(get_current_user_and_session),
    store: AuthStore = Depends(get_auth_store),
) -> AppUserSchema:
    """Enforce that the caller is an authenticated, active Administrator or Super Admin."""
    user, _ = pair
    if not (user.is_super_admin or user.role in {"admin", "operator", "auditor"}):
        store.record_audit_log(
            actor_id=user.id,
            actor_email=user.email,
            action="admin.access.denied",
            target_type="endpoint",
            target_id=request.url.path,
            severity="warning",
            ip_address=extract_client_ip(request),
            status="denied",
            details=f"Non-admin user (role={user.role}) attempted to access {request.method} {request.url.path}.",
        )
        raise HTTPException(
            status_code=403,
            detail="Administrator permissions are required to access the Admin Control Center.",
        )
    # Write operations require full admin or super_admin (unless operator updating content)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if user.role == "auditor":
            raise HTTPException(status_code=403, detail="Auditor role has read-only access.")
        if user.role == "operator" and not request.url.path.endswith("/content"):
            raise HTTPException(status_code=403, detail="Operator role can only modify content settings.")
    return user


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    request: Request,
    response: Response,
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminStatsResponse:
    response.headers["Cache-Control"] = "no-store"
    rt = get_live_runtime(request)
    snap = rt.stream_manager.status_snapshot()
    return store.get_stats(
        feed_state=snap.feed_state.value,
        session_open=snap.session_open,
    )


@router.get("/users", response_model=list[AppUserSchema])
def list_users(
    response: Response,
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> list[AppUserSchema]:
    response.headers["Cache-Control"] = "no-store"
    return store.list_users(search=search, role=role, status=status)


@router.post("/users", response_model=AppUserSchema, status_code=201)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AppUserSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.create_user(
        payload,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.patch("/users/{user_id}", response_model=AppUserSchema)
@router.put("/users/{user_id}", response_model=AppUserSchema)
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AppUserSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.update_user(
        user_id,
        payload,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.delete("/users/{user_id}", response_model=AdminActionResponse)
def delete_user(
    user_id: str,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminActionResponse:
    response.headers["Cache-Control"] = "no-store"
    store.delete_user(
        user_id,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )
    return AdminActionResponse(ok=True, message=f"User '{user_id}' deleted.")


@router.post("/users/{user_id}/unlock", response_model=AppUserSchema)
def unlock_user(
    user_id: str,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AppUserSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.unlock_user(
        user_id,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.post("/users/{user_id}/revoke-sessions", response_model=AdminActionResponse)
def revoke_user_sessions(
    user_id: str,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminActionResponse:
    response.headers["Cache-Control"] = "no-store"
    cnt = store.revoke_all_user_sessions(
        user_id,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )
    return AdminActionResponse(ok=True, message=f"Revoked {cnt} active session(s).")


@router.get("/sessions", response_model=list[SessionInfoSchema])
def list_sessions(
    response: Response,
    pair: tuple[AppUserSchema, StoredSession] = Depends(get_current_user_and_session),
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> list[SessionInfoSchema]:
    response.headers["Cache-Control"] = "no-store"
    return store.list_active_sessions(current_jti=pair[1].jti)


@router.get("/roles", response_model=list[AdminRoleDefinitionSchema])
def get_roles(
    response: Response,
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> list[AdminRoleDefinitionSchema]:
    response.headers["Cache-Control"] = "no-store"
    return store.list_roles()


@router.patch("/roles/{role_name}", response_model=AdminRoleDefinitionSchema)
def update_role(
    role_name: str,
    payload: UpdateRolePermissionsRequest,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminRoleDefinitionSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.update_role_permissions(
        role_name,
        payload,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.get("/content", response_model=AdminContentConfigSchema)
def get_content(
    response: Response,
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminContentConfigSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.get_content_config()


@router.patch("/content", response_model=AdminContentConfigSchema)
def update_content(
    payload: UpdateContentConfigRequest,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminContentConfigSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.update_content_config(
        payload,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.get("/audit-logs", response_model=list[AdminAuditLogSchema])
def get_audit_logs(
    response: Response,
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> list[AdminAuditLogSchema]:
    response.headers["Cache-Control"] = "no-store"
    return store.list_audit_logs(search=search, severity=severity, status=status, limit=limit)


@router.get("/settings", response_model=AdminSystemSettingsSchema)
def get_settings_config(
    response: Response,
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminSystemSettingsSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.get_system_settings()


@router.patch("/settings", response_model=AdminSystemSettingsSchema)
def update_settings_config(
    payload: UpdateSystemSettingsRequest,
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminSystemSettingsSchema:
    response.headers["Cache-Control"] = "no-store"
    return store.update_system_settings(
        payload,
        actor=admin_user,
        ip_address=extract_client_ip(request),
    )


@router.get("/health", response_model=AdminHealthResponse)
def get_admin_health(
    request: Request,
    response: Response,
    _: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminHealthResponse:
    response.headers["Cache-Control"] = "no-store"
    rt = get_live_runtime(request)
    snap = rt.stream_manager.status_snapshot()
    market_feed_info = {
        "provider": snap.provider,
        "feed_state": snap.feed_state.value,
        "streaming_enabled": snap.streaming_enabled,
        "connected": snap.connected,
        "session_open": snap.session_open,
        "reconnect_attempts": snap.reconnect_attempts,
        "last_error": snap.last_error,
        "instruments": {
            inst.value: {
                "feed_state": status.feed_state.value,
                "confirmed_candle_count": status.confirmed_candle_count,
                "has_forming_candle": status.has_forming_candle,
                "is_stale": status.is_stale,
            }
            for inst, status in snap.instruments.items()
        },
    }
    return store.get_health_report(market_feed_info=market_feed_info)


@router.post("/errors/clear", response_model=AdminActionResponse)
def clear_admin_errors(
    request: Request,
    response: Response,
    admin_user: AppUserSchema = Depends(require_admin_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminActionResponse:
    response.headers["Cache-Control"] = "no-store"
    cnt = store.clear_errors(actor=admin_user, ip_address=extract_client_ip(request))
    return AdminActionResponse(ok=True, message=f"Cleared {cnt} error entry(ies).")
