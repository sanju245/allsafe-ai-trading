"""Transactional account email through the Gmail HTTPS API."""

from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.config import Settings, get_settings


class EmailDeliveryError(Exception):
    """A notification could not be delivered; do not expose provider internals."""


def _email_config(settings: Settings | None = None) -> tuple[str, str, str, str]:
    config = settings or get_settings()
    client_id = (config.gmail_client_id or "").strip()
    client_secret = config.gmail_client_secret.get_secret_value() if config.gmail_client_secret else ""
    refresh_token = config.gmail_refresh_token.get_secret_value() if config.gmail_refresh_token else ""
    sender = config.gmail_from_email.strip().lower()
    if not all((client_id, client_secret, refresh_token, sender)) or "@" not in sender:
        raise HTTPException(status_code=503, detail="Account request email is not configured.")
    return client_id, client_secret, refresh_token, sender


def setup_redirect_url(settings: Settings | None = None) -> str:
    config = settings or get_settings()
    url = config.public_site_url.strip().rstrip("/")
    parsed = urlsplit(url)
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed.scheme != "https" and not (
            config.app_env.lower() == "development"
            and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1"}
        ))
    ):
        raise HTTPException(status_code=503, detail="The public site URL is not configured correctly.")
    return url + "/set-password"


def account_setup_link(result: dict, link_type: str) -> str:
    """Keep the one-time token out of HTTP URLs, access logs, and referrers."""
    hashed_token = result.get("hashed_token")
    if isinstance(hashed_token, str) and hashed_token:
        return f"{setup_redirect_url()}#{urlencode({'token_hash': hashed_token, 'type': link_type})}"
    return result["action_link"]


def send_password_reset(email: str, setup_link: str) -> None:
    send_email(
        email, "Reset your AllSafe password",
        f"Open this one-time link to choose a new password for AllSafe AI Trading:\n\n{setup_link}\n\n"
        "If you did not request a password reset, you can ignore this message.",
    )


def send_password_changed(email: str) -> None:
    send_email(
        email,
        "Your AllSafe password has changed",
        "The password for your AllSafe AI Trading account has been changed.\n\n"
        "If you did not make this change, please contact the AllSafe administrator right away.\n\n"
        "AllSafe AI Trading",
    )


def ensure_email_ready() -> None:
    _email_config()
    setup_redirect_url()


def send_email(to_email: str, subject: str, body: str) -> None:
    client_id, client_secret, refresh_token, sender = _email_config()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        token_body = urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("ascii")
        token_request = Request(
            "https://oauth2.googleapis.com/token",
            data=token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(token_request, timeout=10) as response:
            access_token = json.load(response)["access_token"]
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Google returned no access token")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        send_request = Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=json.dumps({"raw": raw}).encode("utf-8"),
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
        with urlopen(send_request, timeout=10) as response:
            result = json.load(response)
        if not isinstance(result.get("id"), str) or not result["id"]:
            raise ValueError("Gmail did not confirm the message")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise EmailDeliveryError() from exc


def send_request_received(email: str, name: str) -> None:
    send_email(
        email,
        "Thank you for requesting an AllSafe account",
        f"Hello {name},\n\nThank you for signing up with AllSafe AI Trading. "
        "We received your account request and an administrator will review it. "
        "An account has not been created yet. We will email you when a decision is made.\n\n"
        "AllSafe AI Trading",
    )


def send_admin_request_notification(
    *,
    name: str,
    email: str,
    date_of_birth: str,
    phone_number: str,
    whatsapp_number: str,
) -> None:
    """Email the configured sender/admin the submitted application details."""
    config = get_settings()
    send_email(
        config.gmail_from_email,
        "New AllSafe account request",
        "A new customer account request is waiting for review.\n\n"
        f"Name: {name}\nEmail: {email}\nDate of birth: {date_of_birth}\n"
        f"Phone: {phone_number}\nWhatsApp: {whatsapp_number}\n\n"
        "Review the request in the AllSafe admin portal. The account has not been created yet.",
    )


def send_approved(email: str, name: str, setup_link: str) -> None:
    send_email(
        email,
        "Your AllSafe account request was approved",
        f"Hello {name},\n\nYour AllSafe AI Trading account request was approved. "
        "Set your password using this one-time link:\n\n"
        f"{setup_link}\n\nIf the link expires, contact the administrator for a new one. "
        "After setting your password, sign in from any network.\n\n"
        "AllSafe AI Trading",
    )


def send_declined(email: str, name: str) -> None:
    send_email(
        email,
        "Your AllSafe account request was declined",
        f"Hello {name},\n\nYour AllSafe AI Trading account request was declined. "
        "No customer account was created. If you think this is a mistake, "
        "please contact the administrator.\n\nAllSafe AI Trading",
    )
