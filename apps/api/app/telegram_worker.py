"""Run as a separate process with `python -m app.telegram_worker`."""

from datetime import UTC, datetime, timedelta
import json
import logging
import re
from signal import SIGINT, SIGTERM, signal
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import HTTPException

from app.config import Settings, get_settings
from app.market_data.instruments import InstrumentId
from app.supabase_admin import SupabaseAdminAPIError, _request_json
from app.telegram_alerts import configured_bot, link_digest, telegram_rpc

logger = logging.getLogger(__name__)
ALERT_TEXT = (
    "There’s a new signal on your AllSafe chart. "
    "Sign in to your AllSafe account to check it."
)


class TelegramError(Exception):
    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__("Telegram rejected the request or could not be reached.")
        self.retry_after = retry_after


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(RejectRedirects())


class TelegramClient:
    def __init__(self, token: str) -> None:
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise ValueError("Configure a valid TELEGRAM_BOT_TOKEN on the delivery worker.")
        self._base_url = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, **payload: Any) -> Any:
        request = Request(self._base_url + method, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with OPENER.open(request, timeout=12) as response:
                reply = json.load(response)
        except HTTPError as exc:
            retry_after = None
            with exc:
                if exc.code == 429:
                    try:
                        value = json.load(exc)
                        retry_after = max(1, int(value["parameters"]["retry_after"]))
                    except (ValueError, KeyError, TypeError):
                        retry_after = 5
            raise TelegramError(retry_after) from None
        except (URLError, OSError, ValueError):
            raise TelegramError() from None
        if not isinstance(reply, dict) or reply.get("ok") is not True:
            raise TelegramError()
        return reply.get("result")

    def send(self, chat_id: int, text: str) -> None:
        self.call("sendMessage", chat_id=chat_id, text=text,
                  link_preview_options={"is_disabled": True}, protect_content=True)


def site_origin(site_url: str) -> str:
    parsed = urlsplit(site_url.strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ValueError("Set PUBLIC_SITE_URL to the HTTPS AllSafe website origin.")
    return f"https://{parsed.netloc}"


def alert_message(origin: str, symbol: str, provider: str) -> str:
    destination = f"/chart/{InstrumentId(symbol).value}?{urlencode({'provider': provider})}"
    return f"{ALERT_TEXT}\n\n{origin}/login?{urlencode({'next': destination})}"


def handle_update(settings: Settings, bot: TelegramClient, update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = message.get("text")
    chat_id = chat.get("id")
    if chat.get("type") != "private" or type(chat_id) is not int or not isinstance(text, str):
        return
    if text == "/stop":
        _request_json("DELETE", "rest/v1/telegram_subscriptions",
                      query={"chat_id": f"eq.{chat_id}"}, settings=settings)
        reply = "AllSafe alerts are off. You can reconnect from your AllSafe account."
    elif text == "/start" or text.startswith("/start "):
        code = text.removeprefix("/start").strip()
        linked = re.fullmatch(r"[A-Za-z0-9_-]{43}", code) and telegram_rpc(
            settings, "redeem_link", p_digest=link_digest(code), p_chat=chat_id,
        ) is True
        reply = (
            "Telegram alerts are connected. Send /stop to turn them off."
            if linked else "Open your AllSafe account and use Connect Telegram to link this chat."
        )
    else:
        return
    try:
        bot.send(chat_id, reply)
    except TelegramError:
        logger.warning("Could not send a Telegram account confirmation.")


def drain_deliveries(settings: Settings, bot: TelegramClient, origin: str, stop: Event) -> bool:
    """Return true when there may be more due jobs in the queue."""
    for _ in range(20):
        if stop.is_set():
            return False
        rows = telegram_rpc(settings, "claim_delivery")
        if not rows:
            return False
        job = rows[0]
        expiry = datetime.fromisoformat(job["expires_at"])
        if datetime.now(UTC) >= expiry:
            continue
        try:
            bot.send(job["chat_id"], alert_message(origin, job["symbol"], job["provider"]))
        except TelegramError as error:
            if error.retry_after is None:
                # Telegram may have accepted a request before a timeout. Avoid double sends.
                logger.warning("Telegram alert delivery was rejected or could not be confirmed.")
                continue
            retry_at = datetime.now(UTC) + timedelta(seconds=error.retry_after)
            if retry_at < expiry:
                _request_json("PATCH", "rest/v1/telegram_signal_deliveries", query={
                    "symbol": f"eq.{job['symbol']}", "candle_at": f"eq.{job['candle_at']}",
                    "user_id": f"eq.{job['user_id']}",
                }, payload={"claimed": False, "available_at": retry_at.isoformat()}, settings=settings)
            stop.wait(min(error.retry_after, 30))
            return True
        stop.wait(0.05)
    return True


def run(settings: Settings, stop: Event) -> None:
    username = configured_bot(settings)
    if username is None:
        raise ValueError("Enable Telegram alerts and configure TELEGRAM_BOT_USERNAME on the worker.")
    origin = site_origin(settings.public_site_url)
    bot = TelegramClient(settings.telegram_bot_token.get_secret_value().strip())
    identity = bot.call("getMe")
    if not isinstance(identity, dict) or str(identity.get("username")).lower() != username.lower():
        raise ValueError("The Telegram worker token does not match TELEGRAM_BOT_USERNAME.")
    logger.info("AllSafe Telegram delivery worker is running.")
    offset = 0
    busy = True
    while not stop.is_set():
        try:
            updates = bot.call("getUpdates", offset=offset, timeout=0 if busy else 5,
                               limit=20, allowed_updates=["message"])
            for update in updates:
                if stop.is_set():
                    break
                handle_update(settings, bot, update)
                offset = update["update_id"] + 1
            busy = drain_deliveries(settings, bot, origin, stop)
            if not stop.is_set() and not busy:
                stop.wait(0.25)
        except (TelegramError, SupabaseAdminAPIError, HTTPException) as error:
            logger.warning("Telegram worker could not reach Telegram or its queue. Retrying.")
            stop.wait(min(error.retry_after or 5, 30) if isinstance(error, TelegramError) else 5)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    signal(SIGTERM, lambda *_: stop.set())
    signal(SIGINT, lambda *_: stop.set())
    try:
        run(get_settings(), stop)
    except (TelegramError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
