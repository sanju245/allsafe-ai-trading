"""Authentication and session management endpoints (`/api/v1/auth/*`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.models import (
    AdminActionResponse,
    AppUserSchema,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    SessionInfoSchema,
)
from app.auth.security import extract_client_ip
from app.auth.store import AuthStore, StoredSession, get_auth_store

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

SESSION_COOKIE_NAME = "allsafe_session"
CSRF_COOKIE_NAME = "allsafe_csrf"


def extract_request_token(request: Request) -> str:
    """Extract session token from Authorization: Bearer header or HttpOnly session cookie."""
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        tok = auth_header[7:].strip()
        if tok:
            return tok
    cookie_tok = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    if cookie_tok:
        return cookie_tok
    raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")


def get_current_user_and_session(
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> tuple[AppUserSchema, StoredSession]:
    token = extract_request_token(request)
    client_ip = extract_client_ip(request)
    user, session = store.verify_request_session(token, client_ip=client_ip)

    # Enforce CSRF verification when authenticating via browser cookie on state-changing methods
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        auth_header = request.headers.get("authorization", "").strip()
        if not auth_header.lower().startswith("bearer "):
            csrf_header = request.headers.get("x-csrf-token", "").strip()
            if not csrf_header or csrf_header != session.csrf_token:
                raise HTTPException(status_code=403, detail="CSRF token validation failed.")

    return user, session


def get_current_user(
    pair: tuple[AppUserSchema, StoredSession] = Depends(get_current_user_and_session),
) -> AppUserSchema:
    return pair[0]


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> LoginResponse:
    """Authenticate an administrator or user from any legitimate IP address globally."""
    response.headers["Cache-Control"] = "no-store"
    identifier = (payload.email or payload.username or "").strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="Email address or username is required.")

    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent", "unknown")
    result = store.authenticate(
        identifier=identifier,
        password=payload.password,
        totp_code=payload.totp_code,
        client_ip=client_ip,
        user_agent=user_agent,
        portal=payload.portal,
    )

    is_prod = store.settings.app_env.lower() == "production"
    cookie_samesite = "none" if is_prod else "lax"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.access_token,
        max_age=result.expires_in,
        httponly=True,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=result.csrf_token,
        max_age=result.expires_in,
        httponly=False,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    return result


@router.post("/admin/login", response_model=LoginResponse)
def admin_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> LoginResponse:
    """Dedicated Admin Portal authentication endpoint (exempt from customer IP allowlists; blocks non-admins)."""
    response.headers["Cache-Control"] = "no-store"
    identifier = (payload.email or payload.username or "").strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="Administrator username or email is required.")

    client_ip = extract_client_ip(request)
    user_agent = request.headers.get("user-agent", "unknown")
    result = store.authenticate(
        identifier=identifier,
        password=payload.password,
        totp_code=payload.totp_code,
        client_ip=client_ip,
        user_agent=user_agent,
        portal="admin",
    )

    is_prod = store.settings.app_env.lower() == "production"
    cookie_samesite = "none" if is_prod else "lax"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.access_token,
        max_age=result.expires_in,
        httponly=True,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=result.csrf_token,
        max_age=result.expires_in,
        httponly=False,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    return result


@router.post("/refresh", response_model=LoginResponse)
def refresh_auth_session(
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> LoginResponse:
    """Rotate the caller's session token after verifying active status, CSRF (if cookie), and IP policy."""
    response.headers["Cache-Control"] = "no-store"
    token = extract_request_token(request)
    client_ip = extract_client_ip(request)
    _, session = store.verify_request_session(token, client_ip=client_ip)

    auth_header = request.headers.get("authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        csrf_header = request.headers.get("x-csrf-token", "").strip()
        if not csrf_header or csrf_header != session.csrf_token:
            raise HTTPException(status_code=403, detail="CSRF token validation failed.")

    result = store.refresh_session(
        token,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent", "unknown"),
    )
    is_prod = store.settings.app_env.lower() == "production"
    cookie_samesite = "none" if is_prod else "lax"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.access_token,
        max_age=result.expires_in,
        httponly=True,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=result.csrf_token,
        max_age=result.expires_in,
        httponly=False,
        secure=is_prod,
        samesite=cookie_samesite,
        path="/",
    )
    return result


@router.post("/logout", response_model=AdminActionResponse)
def logout(
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> AdminActionResponse:
    """Revoke the active session token and clear authentication cookies."""
    response.headers["Cache-Control"] = "no-store"
    client_ip = extract_client_ip(request)
    try:
        user, session = get_current_user_and_session(request, store)
        store.revoke_session(session.jti, actor_email=user.email, ip_address=client_ip)
    except HTTPException:
        pass
    is_prod = store.settings.app_env.lower() == "production"
    cookie_samesite = "none" if is_prod else "lax"
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=is_prod,
        samesite=cookie_samesite,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        secure=is_prod,
        samesite=cookie_samesite,
    )
    return AdminActionResponse(ok=True, message="Signed out and session revoked.")


@router.get("/me", response_model=AppUserSchema)
def get_me(
    response: Response,
    current_user: AppUserSchema = Depends(get_current_user),
) -> AppUserSchema:
    """Return the authenticated user's profile, role, permissions, and IP policy."""
    response.headers["Cache-Control"] = "no-store"
    return current_user


@router.post("/change-password", response_model=AdminActionResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: AppUserSchema = Depends(get_current_user),
    store: AuthStore = Depends(get_auth_store),
) -> AdminActionResponse:
    """Rotate the authenticated user's password after verifying current credentials."""
    response.headers["Cache-Control"] = "no-store"
    try:
        store.change_password(
            user_id=current_user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            ip_address=extract_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AdminActionResponse(ok=True, message="Password updated successfully.")


@router.get("/sessions", response_model=list[SessionInfoSchema])
def list_my_sessions(
    response: Response,
    pair: tuple[AppUserSchema, StoredSession] = Depends(get_current_user_and_session),
    store: AuthStore = Depends(get_auth_store),
) -> list[SessionInfoSchema]:
    """List active sessions for the authenticated user (or all sessions if admin)."""
    response.headers["Cache-Control"] = "no-store"
    user, session = pair
    all_sessions = store.list_active_sessions(current_jti=session.jti)
    if user.role == "admin" or user.is_super_admin:
        return all_sessions
    return [s for s in all_sessions if s.user_id == user.id]
