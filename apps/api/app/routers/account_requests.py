"""Public account applications and administrator decisions."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.email_notifications import (
    EmailDeliveryError,
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
    get_auth_user,
    get_account_request,
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
    notification_status_saved: bool | None = None


class RequestListResponse(BaseModel):
    requests: list[AccountRequestResponse]


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


def _notify_decision(row: dict[str, object], *, link: str | None = None) -> dict[str, object]:
    try:
        if row["status"] == "approved":
            if not link:
                raise _admin_request_error()
            send_approved(str(row["email"]), str(row["full_name"]), link)
        else:
            send_declined(str(row["email"]), str(row["full_name"]))
        notification_status = "sent"
    except EmailDeliveryError:
        notification_status = "failed"
    sent_at = datetime.now(timezone.utc).isoformat() if notification_status == "sent" else None
    try:
        updated = update_account_request(
            str(row["id"]),
            {
                "notification_status": notification_status,
                "notification_sent_at": sent_at,
            },
        )
    except SupabaseAdminAPIError:
        updated = None
    if updated is None:
        # The account decision is already durable. Do not report that approval
        # failed just because the separate email-status write was unavailable.
        _LOGGER.error("Account decision was saved, but its email status could not be recorded.")
        updated = dict(row)
        updated.update({
            "notification_status": notification_status,
            "notification_sent_at": sent_at,
            "notification_status_saved": False,
        })
        return updated
    updated["notification_status_saved"] = True
    return updated


def _normalized_email(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_recoverable_request(
    request_row: dict[str, object],
    profile: dict[str, object],
    auth_user: dict[str, object],
) -> bool:
    """Accept only a matching customer identity created by this request attempt."""
    request_id = str(request_row.get("id", ""))
    email = _normalized_email(request_row.get("email"))
    if (
        not request_id
        or not email
        or str(profile.get("id", "")) != str(auth_user.get("id", ""))
        or _normalized_email(profile.get("email")) != email
        or _normalized_email(auth_user.get("email")) != email
        or profile.get("role") != "user"
        or profile.get("status") != "active"
    ):
        return False

    metadata = auth_user.get("user_metadata")
    if isinstance(metadata, dict) and metadata.get("allsafe_account_request_id") == request_id:
        return True

    # Compatibility for users left behind by the earlier approval handler,
    # which did not attach request metadata. Only adopt an unconfirmed account
    # with no sign-in whose profile/Auth creation both followed this request.
    request_created = _parse_datetime(request_row.get("created_at"))
    profile_created = _parse_datetime(profile.get("created_at"))
    auth_created = _parse_datetime(auth_user.get("created_at"))
    if not request_created or not profile_created or not auth_created:
        return False
    return (
        profile_created >= request_created
        and auth_created >= request_created
        and not auth_user.get("email_confirmed_at")
        and not auth_user.get("last_sign_in_at")
    )


def _validate_approval_identity(
    request_row: dict[str, object],
    profile: dict[str, object] | None,
    auth_user: dict[str, object],
) -> None:
    if (
        profile is None
        or str(profile.get("id", "")) != str(auth_user.get("id", ""))
        or _normalized_email(profile.get("email")) != _normalized_email(request_row.get("email"))
        or _normalized_email(auth_user.get("email")) != _normalized_email(request_row.get("email"))
        or profile.get("role") != "user"
        or profile.get("status") != "active"
    ):
        raise HTTPException(
            status_code=409,
            detail="The matching customer account could not be verified. No approval changes were made.",
        )


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_account_request(body: AccountApplication, request: Request) -> dict[str, str]:
    ensure_email_ready()
    # This server-observed address is retained for form abuse limiting and the
    # existing audit column only. It is never used to authorize an account.
    client_ip = request_client_ip(request)
    _request_rate_limiter.check(
        client_ip, limit=get_settings().account_request_limit_per_hour, resource="Account application"
    )
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
        if exc.status_code == 409:
            # A request for this address is already pending; do not reveal it publicly.
            return {"message": "If this is a new request, we will email you after submission."}
        raise _admin_request_error() from None
    try:
        send_request_received(body.email, body.full_name)
    except EmailDeliveryError:
        try:
            delete_account_request(str(row["id"]))
        except SupabaseAdminAPIError:
            pass
        raise HTTPException(status_code=503, detail="We could not email your receipt. Please try again later.") from None
    try:
        send_admin_request_notification(
            name=body.full_name,
            email=body.email,
            date_of_birth=body.date_of_birth.isoformat(),
            phone_number=body.phone_number,
            whatsapp_number=body.whatsapp_number,
        )
    except EmailDeliveryError:
        # The application and applicant receipt are already durable. Keep them
        # available in the admin queue and log only a safe, PII-free failure.
        _LOGGER.error("Account request was saved, but the administrator email notification failed.")
    try:
        update_account_request(str(row["id"]), {"receipt_sent_at": datetime.now(timezone.utc).isoformat()})
    except SupabaseAdminAPIError:
        # The request and receipt already exist; avoid inviting a duplicate submission.
        pass
    return {"message": "Thank you. Your request is awaiting administrator review; please check your email."}


@admin_router.get("", response_model=RequestListResponse)
def get_requests(_: AccountPrincipal = Depends(require_admin_account)) -> RequestListResponse:
    try:
        rows = list_account_requests()
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    return RequestListResponse(requests=[_serialize(row) for row in rows])


@admin_router.post("/{request_id}/approve", response_model=AccountRequestResponse)
def approve_request(
    request_id: UUID,
    admin: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    redirect_url = setup_redirect_url()
    request_row = _load_request(request_id)
    request_status = request_row.get("status")
    if request_status not in {"pending", "processing"}:
        raise HTTPException(
            status_code=409,
            detail="This request is already decided. Refresh the request list to see its current status.",
        )

    # A prior attempt may have created an Auth user but failed before saving the
    # approval. Preserve and resume that identity instead of deleting it or
    # trying to create a duplicate.
    try:
        row = request_row
        user_id = str(row["auth_user_id"]) if row.get("auth_user_id") else None
        if request_status == "pending":
            existing_profile = get_profile_by_email(str(row["email"]))
            if existing_profile is not None:
                existing_id = str(existing_profile.get("id", ""))
                try:
                    existing_user = get_auth_user(existing_id)
                except SupabaseAdminAPIError:
                    raise
                if not existing_user or not _matches_recoverable_request(row, existing_profile, existing_user):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "This email already belongs to an AllSafe account that cannot be safely matched to this request. "
                            "No account was changed."
                        ),
                    )
                user_id = str(UUID(existing_id))
                row = update_account_request(
                    str(request_id), {"status": "processing", "auth_user_id": user_id},
                    expected_status="pending",
                )
            else:
                row = update_account_request(
                    str(request_id), {"status": "processing"}, expected_status="pending"
                )
            if row is None:
                raise HTTPException(status_code=409, detail="This request changed while approval was starting. Refresh and retry.")
        elif not user_id:
            # This covers older processing rows whose previous attempt did not
            # persist the Auth id. A matching metadata marker or the narrow
            # unconfirmed/no-sign-in legacy check above is required to adopt it.
            existing_profile = get_profile_by_email(str(row["email"]))
            if existing_profile is not None:
                existing_id = str(existing_profile.get("id", ""))
                existing_user = get_auth_user(existing_id)
                if not _matches_recoverable_request(row, existing_profile, existing_user):
                    raise HTTPException(
                        status_code=409,
                        detail="An existing account could not be safely matched to this request. No account was changed.",
                    )
                user_id = str(UUID(existing_id))
                row = update_account_request(
                    str(request_id), {"auth_user_id": user_id}, expected_status="processing"
                )
                if row is None:
                    raise SupabaseAdminAPIError(502)

        approval_stage = "creating or resuming the account invitation"
        if user_id:
            auth_user = get_auth_user(user_id)
            existing_profile = get_profile(user_id)
            _validate_approval_identity(row, existing_profile, auth_user)
            link_type = "recovery" if auth_user.get("email_confirmed_at") else "invite"
            try:
                invitation = generate_account_link(
                    str(row["email"]), link_type=link_type, redirect_to=redirect_url
                )
            except SupabaseAdminAPIError as exc:
                # Some Supabase projects reject a second invite for an existing
                # unconfirmed user. A recovery link is still bound to that same
                # verified identity and lets the applicant finish password setup.
                if link_type != "invite" or exc.status_code not in {409, 422}:
                    raise
                invitation = generate_account_link(
                    str(row["email"]), link_type="recovery", redirect_to=redirect_url
                )
        else:
            invitation = generate_account_link(
                str(row["email"]),
                link_type="invite",
                redirect_to=redirect_url,
                data={"allsafe_account_request_id": str(request_id)},
            )
            user_id = str(UUID(invitation["user"]["id"]))
            # Save the identity immediately. Any later failure leaves a visible,
            # recoverable processing row for the admin's Resume approval action.
            row = update_account_request(
                str(request_id), {"auth_user_id": user_id}, expected_status="processing"
            )
            if row is None:
                raise SupabaseAdminAPIError(502)
            auth_user = get_auth_user(user_id)
            existing_profile = get_profile(user_id)
            _validate_approval_identity(row, existing_profile, auth_user)

        approval_stage = "saving the approval"
        completed = update_account_request(
            str(request_id),
            {
                "status": "approved", "auth_user_id": user_id, "decided_by": admin.id,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            },
            expected_status="processing",
        )
        if completed is None:
            raise SupabaseAdminAPIError(502)
    except HTTPException:
        raise
    except SupabaseAdminAPIError as exc:
        _LOGGER.warning(
            "Account request approval failed while %s (Supabase HTTP %s).",
            locals().get("approval_stage", "checking the existing account"),
            exc.status_code,
        )
        raise HTTPException(status_code=502, detail="Account approval could not be completed. The request is saved for retry.") from None
    except (ValueError, KeyError, TypeError):
        _LOGGER.warning(
            "Account request approval received an invalid response while %s.",
            locals().get("approval_stage", "checking the existing account"),
        )
        raise HTTPException(status_code=502, detail="Account approval could not be completed. The request is saved for retry.") from None
    return _serialize(_notify_decision(completed, link=invitation["action_link"]))


@admin_router.post("/{request_id}/decline", response_model=AccountRequestResponse)
def decline_request(
    request_id: UUID,
    admin: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    try:
        row = update_account_request(
            str(request_id),
            {"status": "declined", "decided_by": admin.id, "decided_at": datetime.now(timezone.utc).isoformat()},
            expected_status="pending",
        )
    except SupabaseAdminAPIError:
        raise _admin_request_error() from None
    if row is None:
        _load_request(request_id)
        raise HTTPException(status_code=409, detail="This request has already been handled.")
    return _serialize(_notify_decision(row))


@admin_router.post("/{request_id}/retry-email", response_model=AccountRequestResponse)
def retry_decision_email(
    request_id: UUID,
    _: AccountPrincipal = Depends(require_admin_account),
) -> AccountRequestResponse:
    ensure_email_ready()
    row = _load_request(request_id)
    if row.get("notification_status") not in {"failed", "pending"} or row.get("status") not in {"approved", "declined"}:
        raise HTTPException(status_code=409, detail="There is no unsent or unconfirmed decision email to retry.")
    link = None
    if row["status"] == "approved":
        try:
            result = generate_account_link(
                str(row["email"]), link_type="recovery", redirect_to=setup_redirect_url()
            )
            link = result["action_link"]
        except SupabaseAdminAPIError:
            raise HTTPException(status_code=502, detail="Could not create a new setup link.") from None
    return _serialize(_notify_decision(row, link=link))
