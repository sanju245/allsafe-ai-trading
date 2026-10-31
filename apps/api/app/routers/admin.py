"""Administrative customer-account operations backed by Supabase Auth Admin API."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, SecretStr, field_validator

from app.security import AccountPrincipal, require_admin_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    create_auth_user,
    delete_auth_user,
    get_profile,
    list_customer_profiles,
    sanitized_admin_error,
    set_auth_user_ban,
    update_profile,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
AccountStatus = Literal["active", "paused"]
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr
    allowed_ip: IPvAnyAddress

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

    status: AccountStatus | None = None
    allowed_ip: IPvAnyAddress | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: Literal["user", "admin"]
    status: AccountStatus
    allowed_ip: str | None
    created_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]


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
    try:
        auth_user = create_auth_user(
            body.email,
            body.password.get_secret_value(),
        )
        user_id = UUID(auth_user["id"])
        profile = update_profile(
            str(user_id),
            {"allowed_ip": body.allowed_ip.compressed},
        )
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


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    _: AccountPrincipal = Depends(require_admin_account),
) -> UserResponse:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Set status and/or allowed_ip.")
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=422, detail="status cannot be null.")
    if "allowed_ip" in changes and changes["allowed_ip"] is None:
        raise HTTPException(status_code=422, detail="allowed_ip must be one exact IP address.")
    if "allowed_ip" in changes:
        changes["allowed_ip"] = changes["allowed_ip"].compressed

    profile = _customer_profile(user_id)
    status_change = changes.get("status")
    try:
        if status_change == "active":
            # Remove the Auth ban first; the DB status remains paused if the next call fails.
            set_auth_user_ban(str(user_id), paused=False)
        updated = update_profile(str(user_id), changes)
        if updated is None:
            raise HTTPException(status_code=404, detail="The account was not found.")
        if status_change == "paused":
            # The profile is already paused, so existing JWTs fail closed even if Auth fails.
            set_auth_user_ban(str(user_id), paused=True)
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
