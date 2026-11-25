"""Link or disconnect Telegram from the signed-in AllSafe account."""

from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.config import get_settings
from app.security import AccountPrincipal, require_active_account
from app.supabase_admin import SupabaseAdminAPIError, _request_json
from app.telegram_alerts import configured_bot, link_digest, telegram_rpc

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])
Account = Annotated[AccountPrincipal, Depends(require_active_account)]


class TelegramStatus(BaseModel):
    available: bool
    connected: bool


@router.get("/subscription", response_model=TelegramStatus)
def subscription(account: Account, response: Response) -> TelegramStatus:
    response.headers["Cache-Control"] = "private, no-store"
    settings = get_settings()
    if not configured_bot(settings):
        return TelegramStatus(available=False, connected=False)
    try:
        rows = _request_json("GET", "rest/v1/telegram_subscriptions", query={
            "select": "user_id", "user_id": f"eq.{account.id}", "chat_id": "not.is.null", "limit": "1",
        }, settings=settings)
    except SupabaseAdminAPIError:
        raise HTTPException(503, "Telegram alerts are temporarily unavailable.") from None
    return TelegramStatus(available=True, connected=bool(rows))


@router.post("/subscription/link")
def new_link(account: Account, response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "private, no-store"
    settings = get_settings()
    bot = configured_bot(settings)
    if not bot:
        raise HTTPException(503, "Telegram alerts are unavailable.")
    code = token_urlsafe(32)
    try:
        created = telegram_rpc(settings, "create_link", p_user=account.id, p_digest=link_digest(code))
    except SupabaseAdminAPIError:
        raise HTTPException(503, "Could not create a Telegram link. Try again.") from None
    if created is not True:
        raise HTTPException(409, "This account is already connected to Telegram.")
    return {"url": f"https://t.me/{bot}?start={code}"}


@router.delete("/subscription", status_code=204)
def disconnect(account: Account) -> Response:
    try:
        _request_json("DELETE", "rest/v1/telegram_subscriptions",
                      query={"user_id": f"eq.{account.id}"}, settings=get_settings())
    except SupabaseAdminAPIError:
        raise HTTPException(503, "Could not disconnect Telegram. Try again.") from None
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
