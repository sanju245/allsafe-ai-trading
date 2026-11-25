"""Signed-in account controls and email-proven credential recovery."""

import logging
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator

from app.config import get_settings
from app.email_notifications import (
    EmailDeliveryError, account_setup_link, ensure_email_ready, send_password_reset, setup_redirect_url,
)
from app.password_policy import require_safe_password
from app.security import (
    AccountPrincipal, SlidingWindowRateLimiter, request_client_ip, require_active_account,
    require_sign_in_account, verify_supabase_access_token,
)
from app.supabase_admin import (
    SupabaseAdminAPIError, check_current_password, generate_account_link, get_profile_by_email, list_customer_warnings,
    revoke_temporary_session, sanitized_admin_error, update_auth_user_password, verify_email_otp,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_LOGGER = logging.getLogger(__name__)
_recovery_rate = SlidingWindowRateLimiter(window_seconds=3600)
_credential_rate = SlidingWindowRateLimiter(window_seconds=60)
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_RECOVERY_REPLY = {"message": "If that email has an active AllSafe account, we will send a password reset link."}


class CurrentAccountResponse(BaseModel):
    id: str
    email: str
    role: Literal["user", "admin"]
    status: Literal["active", "paused"]


class CustomerWarning(BaseModel):
    id: UUID
    message: str
    sent_at: AwareDatetime


class CustomerWarningsResponse(BaseModel):
    warnings: list[CustomerWarning]
    next_before: UUID | None


class NewPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=8, max_length=128)


class ChangePasswordRequest(NewPasswordRequest):
    current_password: SecretStr = Field(min_length=1, max_length=128)


class SetupPasswordRequest(NewPasswordRequest):
    token_hash: SecretStr | None = Field(default=None, min_length=1, max_length=512)
    type: Literal["invite", "recovery"] | None = None
    access_token: SecretStr | None = Field(default=None, min_length=1, max_length=8192)

    @model_validator(mode="after")
    def validate_proof(self):
        if self.token_hash and self.type and not self.access_token:
            return self
        if self.access_token and not self.token_hash and not self.type:
            return self
        raise ValueError("A valid password setup link is required.")


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        return email


@router.get("/me", response_model=CurrentAccountResponse)
def get_current_account(
    response: Response,
    account: AccountPrincipal = Depends(require_sign_in_account),
) -> CurrentAccountResponse:
    response.headers["Cache-Control"] = "no-store"
    return CurrentAccountResponse(
        id=account.id, email=account.email, role=account.role, status=account.status,
    )


@router.get("/warnings", response_model=CustomerWarningsResponse)
def get_customer_warnings(
    response: Response,
    before: UUID | None = None,
    account: AccountPrincipal = Depends(require_active_account),
) -> CustomerWarningsResponse:
    response.headers["Cache-Control"] = "private, no-store"
    if account.role != "user":
        return CustomerWarningsResponse(warnings=[], next_before=None)
    try:
        rows = list_customer_warnings(account.id, str(before) if before else None)
        warnings = [CustomerWarning.model_validate(row) for row in rows[:20]]
    except (SupabaseAdminAPIError, ValidationError):
        raise HTTPException(status_code=503, detail="Account warnings are temporarily unavailable.") from None
    return CustomerWarningsResponse(warnings=warnings, next_before=warnings[-1].id if len(rows) > 20 else None)


@router.put("/password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    account: AccountPrincipal = Depends(require_active_account),
) -> Response:
    _credential_rate.check(account.id, limit=5, resource="Password change")
    try:
        if not check_current_password(account.email, body.current_password.get_secret_value(), expected_user_id=account.id):
            raise HTTPException(status_code=422, detail="The current password is incorrect.")
        password = body.password.get_secret_value()
        require_safe_password(password)
        update_auth_user_password(account.id, password)
    except SupabaseAdminAPIError as exc:
        raise sanitized_admin_error(exc) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/password/setup", status_code=204)
def set_password_from_email(body: SetupPasswordRequest, request: Request) -> Response:
    _credential_rate.check(request_client_ip(request), limit=10, resource="Account setup")
    password = body.password.get_secret_value()
    require_safe_password(password)
    try:
        if body.token_hash and body.type:
            token = verify_email_otp(body.token_hash.get_secret_value(), body.type)
        else:
            # Invitations dispatched by older releases already exchanged a Supabase
            # email proof for a session. Accept only a recent, signed email proof.
            assert body.access_token is not None
            token = body.access_token.get_secret_value()
            settings = get_settings()
            verify_supabase_access_token(
                f"Bearer {token}", supabase_url=settings.supabase_url,
                jwt_secret=settings.supabase_jwt_secret, require_recent_email=True,
            )
        account = require_active_account(f"Bearer {token}")
        update_auth_user_password(account.id, password)
        revoke_temporary_session(token)
    except SupabaseAdminAPIError as exc:
        if exc.status_code in {400, 401, 403, 404, 422}:
            raise HTTPException(status_code=400, detail="This setup link has expired or was already used. Request a new link.") from None
        raise sanitized_admin_error(exc) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def _send_recovery(email: str) -> None:
    try:
        account = get_profile_by_email(email)
        if not account or account.get("status") != "active":
            return
        generated = generate_account_link(email, link_type="recovery", redirect_to=setup_redirect_url())
        send_password_reset(email, account_setup_link(generated, "recovery"))
    except (SupabaseAdminAPIError, EmailDeliveryError, HTTPException):
        _LOGGER.warning("An AllSafe password reset email could not be sent.")


@router.post("/password/recover", status_code=202)
def request_recovery(body: RecoveryRequest, request: Request, background: BackgroundTasks) -> dict[str, str]:
    ensure_email_ready()
    _recovery_rate.check(request_client_ip(request), limit=6, resource="Password recovery")
    _recovery_rate.check("mail:" + body.email, limit=3, resource="Password recovery")
    background.add_task(_send_recovery, body.email)
    return _RECOVERY_REPLY
