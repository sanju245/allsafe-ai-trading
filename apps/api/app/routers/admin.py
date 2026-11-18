"""Administrative customer-account operations backed by Supabase Auth Admin API."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.security import AccountPrincipal, require_admin_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    create_auth_user,
    delete_auth_user,
    get_profile,
    list_customer_login_ip_daily_summaries,
    list_customer_login_ip_events,
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


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: Literal["user", "admin"]
    status: AccountStatus
    created_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]


class LoginIPEventResponse(BaseModel):
    user_id: UUID
    email: str
    client_ip: str
    logged_at: datetime


class MultipleIPDayResponse(BaseModel):
    user_id: UUID
    email: str
    login_date: str
    login_count: int
    distinct_ip_count: int
    ip_addresses: list[str]


class LoginIPAuditResponse(BaseModel):
    events: list[LoginIPEventResponse]
    multiple_ip_days: list[MultipleIPDayResponse]
    limit: int
    offset: int


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


@router.get("/login-ip-audit", response_model=LoginIPAuditResponse)
def get_login_ip_audit(
    _: AccountPrincipal = Depends(require_admin_account),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> LoginIPAuditResponse:
    """Return server-recorded customer sign-ins and days with multiple IPs."""
    try:
        profiles = list_customer_profiles()
        events = list_customer_login_ip_events(limit=limit, offset=offset)
        multiple_ip_days = list_customer_login_ip_daily_summaries()
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None

    emails = {str(profile.get("id")): profile.get("email") for profile in profiles}
    try:
        visible_events = [
            LoginIPEventResponse(
                user_id=row["user_id"],
                email=emails[str(row["user_id"])],
                client_ip=str(row["client_ip"]),
                logged_at=row["logged_at"],
            )
            for row in events
            if str(row.get("user_id")) in emails and isinstance(emails[str(row["user_id"])], str)
        ]
        flagged_days = [
            MultipleIPDayResponse(
                user_id=row["user_id"],
                email=emails[str(row["user_id"])],
                login_date=str(row["login_date"]),
                login_count=int(row["login_count"]),
                distinct_ip_count=int(row["distinct_ip_count"]),
                ip_addresses=[str(ip) for ip in row["ip_addresses"]],
            )
            for row in multiple_ip_days
            if str(row.get("user_id")) in emails and isinstance(emails[str(row["user_id"])], str)
        ]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="Supabase returned incomplete sign-in audit data.") from None
    return LoginIPAuditResponse(
        events=visible_events,
        multiple_ip_days=flagged_days,
        limit=limit,
        offset=offset,
    )


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


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    _: AccountPrincipal = Depends(require_admin_account),
) -> UserResponse:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Set a new account status.")
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=422, detail="status cannot be null.")

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
