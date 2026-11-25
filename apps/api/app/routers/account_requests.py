"""Public account applications and administrator decisions."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.email_notifications import (
    EmailDeliveryError,
    account_setup_link,
    ensure_email_ready,
    send_admin_request_notification,
    send_approved,
    send_declined,
    send_request_received,
    setup_redirect_url,
)
from app.security import AccountPrincipal, SlidingWindowRateLimiter, request_client_ip, require_admin_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    delete_account_request,
    generate_account_link,
    get_account_request,
    get_auth_user,
    get_open_account_request,
    get_profile,
    get_profile_by_email,
    insert_account_request,
    list_account_requests,
    update_account_request,
)

public_router = APIRouter(prefix="/api/v1/account-requests", tags=["accounts"])
admin_router = APIRouter(prefix="/api/v1/admin/account-requests", tags=["admin"])
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{6,18}$")
_LOGGER = logging.getLogger(__name__)
_request_rate_limiter = SlidingWindowRateLimiter(window_seconds=3600)
RequestStatus = Literal["pending", "processing", "approved", "declined"]
NotificationStatus = Literal["pending", "sent", "failed"]


class AccountApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    email: str = Field(min_length=3, max_length=254)
    phone_number: str = Field(min_length=7, max_length=20)
    whatsapp_number: str = Field(min_length=7, max_length=20)

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if len(name) < 2 or len(name) > 120 or any(ord(char) < 32 for char in name):
            raise ValueError("Enter a valid name.")
        return name

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        if value > datetime.now(timezone.utc).date():
            raise ValueError("Date of birth cannot be in the future.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email

    @field_validator("phone_number", "whatsapp_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        phone = value.strip()
        if not _PHONE_PATTERN.fullmatch(phone):
            raise ValueError("Enter a valid phone number.")
        return phone


class AccountRequestResponse(BaseModel):
    id: UUID
    full_name: str
    date_of_birth: date
    email: str
    phone_number: str
    whatsapp_number: str
    request_ip: str | None
    status: RequestStatus
    notification_status: NotificationStatus
    auth_user_id: UUID | None
    created_at: datetime
    decided_at: datetime | None
    receipt_sent_at: datetime | None
    notification_sent_at: datetime | None
    processing_started_at: datetime | None = None
    notification_started_at: datetime | None = None


class RequestListResponse(BaseModel):
    requests: list[AccountRequestResponse]
    has_more: bool


def _admin_request_error() -> HTTPException:
    return HTTPException(status_code=502, detail="Account request storage is unavailable.")


def _serialize(row: dict[str, object]) -> AccountRequestResponse:
    try:
        return AccountRequestResponse.model_validate(row)
    except Exception:
        raise _admin_request_error() from None


def _load_request(request_id: UUID) -> dict[str, object]:
    try:
        row = get_account_request(str(request_id))
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if row is None:
        raise HTTPException(status_code=404, detail="The account request was not found.")
    return row


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim_active(value: object) -> bool:
    if not isinstance(value, (str, datetime)):
        return False
    started = datetime.fromisoformat(value) if isinstance(value, str) else value
    return started > _now() - timedelta(minutes=3)


def _write_request(
    row: dict[str, object], changes: dict[str, object], *, compare: tuple[str, ...] = (),
) -> dict[str, object]:
    try:
        updated = update_account_request(
            str(row["id"]), changes, expected={key: row.get(key) for key in compare},
        )
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if updated is None:
        raise HTTPException(status_code=409, detail="This request changed. Refresh the queue and try again.")
    return updated


def _release_claim(row: dict[str, object], key: str) -> None:
    try:
        _write_request(row, {key: None}, compare=(key,))
    except HTTPException:
        # The timestamp allows recovery after a process or service interruption.
        _LOGGER.warning("Could not release an account request claim. It will expire.")


def _linked_customer(row: dict[str, object]) -> dict[str, object]:
    user_id = row.get("auth_user_id")
    profile = get_profile(str(user_id)) if user_id else None
    if not profile or profile.get("role") != "user" or profile.get("status") != "active" or profile.get("email") != row["email"]:
        raise HTTPException(status_code=409, detail="The linked active customer could not be verified.")
    return profile


def _notify_decision(row: dict[str, object], *, link: str | None = None) -> dict[str, object]:
    if _claim_active(row.get("notification_started_at")):
        raise HTTPException(status_code=409, detail="A decision email is already being sent. Try again shortly.")
    row = _write_request(row, {
        "notification_started_at": _now().isoformat(),
    }, compare=("status", "notification_status", "notification_started_at"))
    sent_at = None
    try:
        if row["status"] == "approved":
            if link is None:
                _linked_customer(row)
                generated = generate_account_link(str(row["email"]), link_type="recovery", redirect_to=setup_redirect_url())
                link = account_setup_link(generated, "recovery")
            send_approved(str(row["email"]), str(row["full_name"]), link)
        else:
            send_declined(str(row["email"]), str(row["full_name"]))
        sent_at = _now().isoformat()
    except (EmailDeliveryError, SupabaseAdminAPIError):
        _LOGGER.warning("A decision email could not be sent. It can be retried from the queue.")
    except HTTPException:
        _release_claim(row, "notification_started_at")
        raise
    return _write_request(row, {
        "notification_status": "sent" if sent_at else "failed",
        "notification_sent_at": sent_at,
        "notification_started_at": None,
    }, compare=("notification_started_at",))


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_account_request(body: AccountApplication, request: Request) -> dict[str, str]:
    ensure_email_ready()
    client_ip = request_client_ip(request)
    _request_rate_limiter.check(
        client_ip, limit=get_settings().account_request_limit_per_hour, resource="Account application"
    )
    reply = {"message": "Thank you. If a receipt is due for this request, check your email."}
    try:
        try:
            row = insert_account_request({
                "full_name": body.full_name,
                "date_of_birth": body.date_of_birth.isoformat(),
                "email": body.email,
                "phone_number": body.phone_number,
                "whatsapp_number": body.whatsapp_number,
                "request_ip": client_ip,
            })
        except SupabaseAdminAPIError as exc:
            if exc.status_code != 409:
                raise
            row = get_open_account_request(body.email)
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if row is None or row.get("receipt_sent_at") or _claim_active(row.get("receipt_started_at")):
        return reply
    try:
        row = _write_request(row, {"receipt_started_at": _now().isoformat()},
                             compare=("receipt_sent_at", "receipt_started_at"))
    except HTTPException as exc:
        if exc.status_code == 409:
            return reply
        raise
    try:
        send_request_received(str(row["email"]), str(row["full_name"]))
    except EmailDeliveryError:
        _release_claim(row, "receipt_started_at")
        raise HTTPException(status_code=503, detail="We saved your request. Submit again to retry the email receipt.") from None
    try:
        _write_request(row, {"receipt_sent_at": _now().isoformat(), "receipt_started_at": None},
                       compare=("receipt_started_at",))
    except HTTPException:
        _LOGGER.warning("The account request receipt was sent without a recorded acknowledgement.")
    try:
        send_admin_request_notification(
            name=str(row["full_name"]),
            email=str(row["email"]),
            date_of_birth=str(row["date_of_birth"]),
            phone_number=str(row["phone_number"]),
            whatsapp_number=str(row["whatsapp_number"]),
        )
    except EmailDeliveryError:
        _LOGGER.error("Account request was saved, but the administrator email notification failed.")
    return reply


@admin_router.get("", response_model=RequestListResponse)
def get_requests(
    _: AccountPrincipal = Depends(require_admin_account),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    history: bool = False,
) -> RequestListResponse:
    try:
        rows = list_account_requests(offset=offset, limit=limit + 1, review_only=not history)
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    return RequestListResponse(requests=[_serialize(row) for row in rows[:limit]], has_more=len(rows) > limit)


@admin_router.post("/{request_id}/approve", response_model=AccountRequestResponse)
def approve_request(
    request_id: UUID,
    admin: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    redirect_url = setup_redirect_url()
    row = _load_request(request_id)
    if row["status"] not in {"pending", "processing"} or _claim_active(row.get("processing_started_at")):
        raise HTTPException(status_code=409, detail="This request has been handled or is being processed.")
    email = str(row["email"])
    attempt = row.get("approval_attempt")
    try:
        existing = get_profile_by_email(email)
        if existing is not None:
            user = get_auth_user(str(existing["id"])) if attempt and existing.get("role") == "user" else {}
            metadata = user.get("user_metadata")
            if not isinstance(metadata, dict) or metadata.get("allsafe_approval_attempt") != str(attempt):
                raise HTTPException(
                    status_code=409,
                    detail="This email already belongs to an AllSafe account. Use the existing account, or decline this duplicate request.",
                )
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None

    attempt = str(attempt or uuid4())
    row = _write_request(row, {
        "status": "processing", "approval_attempt": attempt, "processing_started_at": _now().isoformat(),
    }, compare=("status", "processing_started_at"))
    try:
        if existing is not None:
            user_id = str(UUID(str(existing["id"])))
            link = None
        else:
            invitation = generate_account_link(email, link_type="invite", redirect_to=redirect_url,
                                               approval_attempt=attempt)
            user_id = str(UUID(invitation["user"]["id"]))
            if get_profile(user_id) is None:
                raise SupabaseAdminAPIError(502)
            link = account_setup_link(invitation, "invite")
        completed = _write_request(row, {
            "status": "approved", "auth_user_id": user_id, "decided_by": admin.id,
            "decided_at": _now().isoformat(), "processing_started_at": None,
        }, compare=("status", "processing_started_at"))
    except (HTTPException, SupabaseAdminAPIError, ValueError, KeyError, TypeError):
        _release_claim(row, "processing_started_at")
        raise HTTPException(status_code=502, detail="Approval did not finish. Refresh the queue and resume this request.") from None
    return _serialize(_notify_decision(completed, link=link))


@admin_router.post("/{request_id}/decline", response_model=AccountRequestResponse)
def decline_request(
    request_id: UUID,
    admin: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    row = _load_request(request_id)
    if row["status"] not in {"pending", "processing"} or _claim_active(row.get("processing_started_at")):
        raise HTTPException(status_code=409, detail="This request has been handled or is being processed.")
    row = _write_request(row, {
        "status": "declined", "decided_by": admin.id, "decided_at": _now().isoformat(),
        "processing_started_at": None,
    }, compare=("status", "processing_started_at"))
    return _serialize(_notify_decision(row))


@admin_router.post("/{request_id}/retry-email", response_model=AccountRequestResponse)
def retry_decision_email(
    request_id: UUID,
    _: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    row = _load_request(request_id)
    if row["status"] not in {"approved", "declined"} or (
        row["status"] == "declined" and row["notification_status"] == "sent"
    ):
        raise HTTPException(status_code=409, detail="This request has no decision email to resend.")
    sent_at = row.get("notification_sent_at")
    if row["notification_status"] == "sent" and _claim_active(sent_at):
        raise HTTPException(status_code=429, detail="An email was just sent. Wait a few minutes before resending.")
    return _serialize(_notify_decision(row))


@admin_router.delete("/{request_id}", status_code=204)
def remove_request(
    request_id: UUID,
    _: AccountPrincipal = Depends(require_admin_account),
) -> Response:
    row = _load_request(request_id)
    claims = ("processing_started_at", "receipt_started_at", "notification_started_at")
    if any(_claim_active(row.get(key)) for key in claims):
        raise HTTPException(status_code=409, detail="Wait for this request to finish processing.")
    try:
        deleted = delete_account_request(str(request_id), expected={key: row.get(key) for key in (*claims, "status")})
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if not deleted:
        raise HTTPException(status_code=409, detail="This request changed. Refresh the queue and try again.")
    return Response(status_code=204)
