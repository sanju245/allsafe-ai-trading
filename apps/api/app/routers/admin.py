"""Administrative customer-account operations backed by Supabase Auth Admin API."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, SecretStr, StringConstraints, ValidationError, field_validator

from app.security import AccountPrincipal, require_admin_account
from app.password_policy import require_safe_password
from app.supabase_admin import (
    SupabaseAdminAPIError,
    create_auth_user,
    delete_auth_user,
    get_profile,
    list_customer_profiles,
    list_customer_sign_ins,
    sanitized_admin_error,
    send_customer_warning,
    set_auth_user_ban,
    update_profile,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
AccountStatus = Literal["active", "paused"]
NoticeText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("email must be a valid email address")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 8 <= len(password) <= 128:
            raise ValueError("password must be between 8 and 128 characters")
        return value


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AccountStatus
    pause_reason: NoticeText | None = None


class SendWarningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_id: UUID
    target_id: UUID | None
    message: NoticeText


class SendWarningResponse(BaseModel):
    recipient_count: int


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: Literal["user", "admin"]
    status: AccountStatus
    created_at: datetime
    pause_reason: str | None = None


class UserListResponse(BaseModel):
    users: list[UserResponse]


class CustomerSignIn(BaseModel):
    signed_in_at: AwareDatetime
    ip_address: IPvAnyAddress | None


class CustomerSignInHistory(BaseModel):
    sign_ins: list[CustomerSignIn] = Field(max_length=10)


def _user_response(profile: dict[str, object]) -> UserResponse:
    try:
        return UserResponse.model_validate(profile)
    except Exception:
        # Do not include provider bodies or credentials in the public response.
        raise HTTPException(
            status_code=502,
            detail="Supabase returned an incomplete account profile.",
        ) from None


def _customer_profile(user_id: UUID) -> dict[str, object]:
    try:
        profile = get_profile(str(user_id))
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    if profile is None:
        raise HTTPException(status_code=404, detail="The account was not found.")
    if profile.get("role") != "user":
        raise HTTPException(
            status_code=409,
            detail="Only customer accounts can be managed through this endpoint.",
        )
    return profile


@router.get("/users", response_model=UserListResponse)
def get_users(
    _: AccountPrincipal = Depends(require_admin_account),
) -> UserListResponse:
    try:
        profiles = list_customer_profiles()
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return UserListResponse(users=[_user_response(profile) for profile in profiles])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    body: CreateUserRequest,
    _: AccountPrincipal = Depends(require_admin_account),
) -> UserResponse:
    user_id: UUID | None = None
    password = body.password.get_secret_value()
    require_safe_password(password)
    try:
        auth_user = create_auth_user(
            body.email,
            password,
        )
        user_id = UUID(auth_user["id"])
        profile = get_profile(str(user_id))
        if profile is None:
            raise SupabaseAdminAPIError(502)
    except SupabaseAdminAPIError as exc:
        if user_id is not None:
            try:
                delete_auth_user(str(user_id))
            except SupabaseAdminAPIError:
                pass
        raise sanitized_admin_error(exc) from None
    except ValueError:
        if user_id is not None:
            try:
                delete_auth_user(str(user_id))
            except SupabaseAdminAPIError:
                pass
        raise HTTPException(
            status_code=502,
            detail="Supabase returned an invalid user id.",
        ) from None
    return _user_response(profile)


@router.get("/users/{user_id}/sign-ins", response_model=CustomerSignInHistory)
def get_customer_sign_ins(
    user_id: UUID,
    response: Response,
    _: AccountPrincipal = Depends(require_admin_account),
) -> CustomerSignInHistory:
    _customer_profile(user_id)
    try:
        rows = list_customer_sign_ins(str(user_id))
        history = CustomerSignInHistory(sign_ins=rows)
    except SupabaseAdminAPIError:
        raise HTTPException(status_code=503, detail="Sign-in history is temporarily unavailable.") from None
    except ValidationError:
        raise HTTPException(status_code=502, detail="The account service returned invalid sign-in history.") from None
    response.headers["Cache-Control"] = "private, no-store"
    return history


@router.post("/warnings", response_model=SendWarningResponse)
def post_customer_warning(
    body: SendWarningRequest,
    _: AccountPrincipal = Depends(require_admin_account),
) -> SendWarningResponse:
    try:
        count = send_customer_warning(
            str(body.warning_id), str(body.target_id) if body.target_id else None, body.message,
        )
    except SupabaseAdminAPIError:
        raise HTTPException(status_code=503, detail="Could not confirm that the warning was sent. Try again.") from None
    if count == -1:
        raise HTTPException(status_code=409, detail="This send was already used for a different warning.")
    if count == 0:
        raise HTTPException(status_code=404, detail="There are no matching customer accounts.")
    return SendWarningResponse(recipient_count=count)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    _: AccountPrincipal = Depends(require_admin_account),
) -> UserResponse:
    if body.status == "paused" and not body.pause_reason:
        raise HTTPException(status_code=422, detail="Enter a reason for pausing this account.")
    if body.status == "active" and body.pause_reason is not None:
        raise HTTPException(status_code=422, detail="A pause reason is only needed when pausing an account.")
    profile = _customer_profile(user_id)
    try:
        if body.status == "active" and profile.get("status") == "paused" and profile.get("pause_reason") is None:
            # Legacy pauses also set an Auth ban. New pauses gate the app after identity verification.
            set_auth_user_ban(str(user_id), paused=False)
        updated = update_profile(str(user_id), {"status": body.status, "pause_reason": body.pause_reason})
        if updated is None:
            raise HTTPException(status_code=404, detail="The account was not found.")
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return _user_response(updated)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    _: AccountPrincipal = Depends(require_admin_account),
) -> Response:
    _customer_profile(user_id)
    try:
        # Supabase cascades the profile; backend profile checks then reject outstanding JWTs.
        delete_auth_user(str(user_id))
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
