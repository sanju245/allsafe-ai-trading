"""Signed-in account endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.security import AccountPrincipal, request_client_ip, require_active_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    sanitized_admin_error,
    update_auth_user_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class ClientIPResponse(BaseModel):
    client_ip: str


class CurrentAccountResponse(BaseModel):
    id: str
    email: str
    role: Literal["user", "admin"]
    status: Literal["active", "paused"]
    allowed_ip: str
    client_ip: str


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: SecretStr) -> SecretStr:
        if not 8 <= len(value.get_secret_value()) <= 128:
            raise ValueError("password must be between 8 and 128 characters")
        return value


@router.get("/client-ip", response_model=ClientIPResponse)
def get_client_ip(request: Request, response: Response) -> ClientIPResponse:
    """Return the trusted source IP for first-admin bootstrap and allowlisting."""
    response.headers["Cache-Control"] = "no-store"
    return ClientIPResponse(client_ip=request_client_ip(request))


@router.get("/me", response_model=CurrentAccountResponse)
def get_current_account(
    response: Response,
    account: AccountPrincipal = Depends(require_active_account),
) -> CurrentAccountResponse:
    """Return a profile only when its current active status and IP allowlist pass."""
    response.headers["Cache-Control"] = "no-store"
    # require_active_account rejects profiles without a single assigned IP.
    assert account.allowed_ip is not None
    return CurrentAccountResponse(
        id=account.id,
        email=account.email,
        role=account.role,  # type: ignore[arg-type]
        status=account.status,  # type: ignore[arg-type]
        allowed_ip=account.allowed_ip,
        client_ip=account.client_ip,
    )


@router.put("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    account: AccountPrincipal = Depends(require_active_account),
) -> Response:
    """Change the signed-in user's password after rechecking active status and IP."""
    try:
        update_auth_user_password(account.id, body.password.get_secret_value())
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return Response(status_code=204)
