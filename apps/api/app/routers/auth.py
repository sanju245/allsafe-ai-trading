"""Signed-in account endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.security import AccountPrincipal, request_client_ip, require_active_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    record_login_event,
    sanitized_admin_error,
    update_auth_user_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class CurrentAccountResponse(BaseModel):
    id: str
    email: str
    role: Literal["user", "admin"]
    status: Literal["active", "paused"]

class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: SecretStr) -> SecretStr:
        if not 8 <= len(value.get_secret_value()) <= 128:
            raise ValueError("password must be between 8 and 128 characters")
        return value


@router.get("/me", response_model=CurrentAccountResponse)
def get_current_account(
    response: Response,
    account: AccountPrincipal = Depends(require_active_account),
) -> CurrentAccountResponse:
    """Return the profile after verifying its role and active account status."""
    response.headers["Cache-Control"] = "no-store"
    return CurrentAccountResponse(
        id=account.id,
        email=account.email,
        role=account.role,  # type: ignore[arg-type]
        status=account.status,  # type: ignore[arg-type]
    )


@router.post("/login-events", status_code=204)
def record_current_login(
    request: Request,
    account: AccountPrincipal = Depends(require_active_account),
) -> Response:
    """Record one successfully authenticated sign-in without using IP as a gate."""
    client_ip: str | None = None
    try:
        client_ip = request_client_ip(request)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
    try:
        record_login_event(
            account.id,
            account.email,
            client_ip,
            request.headers.get("user-agent"),
        )
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.put("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    account: AccountPrincipal = Depends(require_active_account),
) -> Response:
    """Change the signed-in user's password after rechecking active account status."""
    try:
        update_auth_user_password(account.id, body.password.get_secret_value())
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return Response(status_code=204)
