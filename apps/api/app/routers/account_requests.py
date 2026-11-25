"""Public account applications and administrator decisions."""

from __future__ import annotations

import hmac
import logging
import re
from base64 import b32encode
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.config import get_settings
from app.email_notifications import (
    EmailDeliveryError,
    account_setup_link,
    ensure_email_ready,
    send_admin_request_notification,
    send_application_email_code,
    send_approved,
    send_chosen_password_approval,
    send_declined,
    send_request_received,
    setup_redirect_url,
)
from app.password_policy import require_safe_password
from app.security import AccountPrincipal, SlidingWindowRateLimiter, request_client_ip, require_admin_account
from app.supabase_admin import (
    SupabaseAdminAPIError,
    create_auth_user_from_hash,
    delete_account_request,
    generate_account_link,
    get_account_request,
    get_account_request_password_hash,
    get_auth_user,
    get_open_account_request,
    get_profile,
    get_profile_by_email,
    insert_account_request,
    insert_account_request_with_password,
    list_account_requests,
    update_account_request,
)

public_router = APIRouter(prefix="/api/v1/account-requests", tags=["accounts"])
admin_router = APIRouter(prefix="/api/v1/admin/account-requests", tags=["admin"])
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{6,18}$")
_LOGGER = logging.getLogger(__name__)
_request_rate_limiter = SlidingWindowRateLimiter(window_seconds=3600)
_email_code_rate_limiter = SlidingWindowRateLimiter(window_seconds=3600)
_EMAIL_CODE_WINDOW_SECONDS = 600
RequestStatus = Literal["pending", "processing", "approved", "declined"]
NotificationStatus = Literal["pending", "sent", "failed"]


class AccountApplicationEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email


class AccountApplication(AccountApplicationEmail):
    full_name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    phone_number: str = Field(min_length=7, max_length=20)
    whatsapp_number: str = Field(min_length=7, max_length=20)
    password: SecretStr | None = Field(default=None, min_length=8, max_length=72)
    email_code: str | None = Field(default=None, pattern=r"^[A-Z2-7]{8}$")

    @model_validator(mode="after")
    def validate_password(self) -> AccountApplication:
        if (self.password is None) != (self.email_code is None):
            raise ValueError("Provide a password and an email verification code together.")
        if self.password is not None and len(self.password.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Choose a shorter password. Some characters use more than one byte.")
        return self

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
    uses_chosen_password: bool = False


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


def _email_code_key() -> bytes:
    key = get_settings().supabase_service_role_key
    if key is None or not key.get_secret_value().strip():
        raise HTTPException(status_code=503, detail="Email verification is temporarily unavailable.")
    return key.get_secret_value().strip().encode("utf-8")


def _email_code_window() -> int:
    return int(_now().timestamp()) // _EMAIL_CODE_WINDOW_SECONDS


def _email_code(email: str, window: int, key: bytes) -> str:
    message = f"allsafe-account-request-email:{window}:{email}".encode("utf-8")
    return b32encode(hmac.digest(key, message, "sha256"))[:8].decode("ascii")


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


def _matches_approval(row: dict[str, object], profile: dict[str, object]) -> bool:
    attempt = row.get("approval_attempt")
    if not attempt or profile.get("role") != "user":
        return False
    user = get_auth_user(str(profile["id"]))
    metadata = user.get("app_metadata" if row.get("uses_chosen_password") else "user_metadata")
    return isinstance(metadata, dict) and metadata.get("allsafe_approval_attempt") == str(attempt)


def _require_no_created_customer(row: dict[str, object]) -> None:
    if not row.get("uses_chosen_password") or row["status"] != "processing" or not row.get("approval_attempt"):
        return
    try:
        profile = get_profile_by_email(str(row["email"]))
        created = profile is not None and _matches_approval(row, profile)
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if created:
        raise HTTPException(status_code=409, detail="The customer was already created. Resume approval to finish this request.")


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
            if row.get("uses_chosen_password"):
                send_chosen_password_approval(str(row["email"]), str(row["full_name"]))
            else:
                if link is None:
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


@public_router.post("/email-code", status_code=status.HTTP_202_ACCEPTED)
def send_account_request_email_code(body: AccountApplicationEmail, request: Request) -> dict[str, str]:
    ensure_email_ready()
    limit = get_settings().account_request_limit_per_hour
    _email_code_rate_limiter.check(f"ip:{request_client_ip(request)}", limit=limit, resource="Email verification")
    _email_code_rate_limiter.check(f"email:{body.email}", limit=limit, resource="Email verification")
    code = _email_code(body.email, _email_code_window(), _email_code_key())
    try:
        send_application_email_code(body.email, code)
    except EmailDeliveryError:
        raise HTTPException(status_code=503, detail="We could not send your verification code. Try again shortly.") from None
    return {"message": "Check your email for the verification code."}


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_account_request(body: AccountApplication, request: Request) -> dict[str, str]:
    ensure_email_ready()
    client_ip = request_client_ip(request)
    _request_rate_limiter.check(
        client_ip, limit=get_settings().account_request_limit_per_hour, resource="Account application"
    )
    reply = {"message": "Thank you. If a receipt is due for this request, check your email."}
    values = {
        "full_name": body.full_name,
        "date_of_birth": body.date_of_birth.isoformat(),
        "email": body.email,
        "phone_number": body.phone_number,
        "whatsapp_number": body.whatsapp_number,
        "request_ip": client_ip,
    }
    password_hash = None
    if body.password is not None and body.email_code is not None:
        window = _email_code_window()
        key = _email_code_key()
        if not any(hmac.compare_digest(body.email_code, _email_code(body.email, slot, key))
                   for slot in (window, window - 1)):
            raise HTTPException(status_code=422, detail="The email code is invalid or expired. Check it or send a new code.")
        password = body.password.get_secret_value()
        require_safe_password(password)
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")
    try:
        try:
            row = insert_account_request_with_password(values, password_hash) if password_hash else insert_account_request(values)
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
    row = _load_request(request_id)
    if row["status"] not in {"pending", "processing"} or _claim_active(row.get("processing_started_at")):
        raise HTTPException(status_code=409, detail="This request has been handled or is being processed.")
    email = str(row["email"])
    attempt = row.get("approval_attempt")
    try:
        existing = get_profile_by_email(email)
        if existing is not None and not _matches_approval(row, existing):
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
        link = None
        if existing is not None:
            user_id = str(UUID(str(existing["id"])))
        elif row.get("uses_chosen_password"):
            password_hash = get_account_request_password_hash(str(request_id), attempt)
            user = create_auth_user_from_hash(email, password_hash, attempt)
            user_id = str(UUID(user["id"]))
            _linked_customer({**row, "auth_user_id": user_id})
        else:
            invitation = generate_account_link(
                email, link_type="invite", redirect_to=setup_redirect_url(), approval_attempt=attempt,
            )
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
    _require_no_created_customer(row)
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
    _require_no_created_customer(row)
    try:
        deleted = delete_account_request(str(request_id), expected={key: row.get(key) for key in (*claims, "status")})
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if not deleted:
        raise HTTPException(status_code=409, detail="This request changed. Refresh the queue and try again.")
    return Response(status_code=204)
