"""Server-only Supabase Auth Admin and profile operations.

This module uses the Supabase REST endpoints directly so the API does not need a
second client library. The service-role credential is read only from API settings;
responses and errors never include it or request payloads.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import HTTPException

from app.config import Settings, get_settings

PROFILE_COLUMNS = "id,email,role,status,allowed_ip,created_at"
_REQUEST_TIMEOUT_SECONDS = 10


class _RejectRedirects(HTTPRedirectHandler):
    """Do not forward the service-role Authorization header to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_RejectRedirects())


class SupabaseAdminAPIError(Exception):
    """A sanitized Supabase response error; it intentionally stores no response body."""

    def __init__(self, status_code: int) -> None:
        super().__init__("Supabase account API request failed.")
        self.status_code = status_code


def _credentials(settings: Settings | None = None) -> tuple[str, str]:
    config = settings or get_settings()
    url = (config.supabase_url or "").strip().rstrip("/")
    secret = config.supabase_service_role_key
    key = secret.get_secret_value().strip() if secret is not None else ""
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Supabase account administration is not configured on the API.",
        )
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
        port = parsed_url.port
    except ValueError:
        hostname = None
        port = None
        parsed_url = None
    on_render = bool(os.getenv("RENDER_SERVICE_ID"))
    local_development_http = (
        not on_render
        and config.app_env.strip().lower() == "development"
        and parsed_url is not None
        and parsed_url.scheme == "http"
        and hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if (
        parsed_url is None
        or hostname is None
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.path not in {"", "/"}
        or parsed_url.query
        or parsed_url.fragment
        or port is not None and not 1 <= port <= 65_535
        or (parsed_url.scheme != "https" and not local_development_http)
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase account administration requires a valid HTTPS project URL.",
        )
    return url, key


def _request_json(
    method: str,
    endpoint: str,
    *,
    query: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Any:
    base_url, service_key = _credentials(settings)
    url = f"{base_url}/{endpoint.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"

    data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    if method in {"PATCH", "POST"} and endpoint.startswith("rest/v1/"):
        headers["Prefer"] = "return=representation"

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            raw_body = response.read()
    except HTTPError as exc:
        status_code = exc.code
        exc.close()
        raise SupabaseAdminAPIError(status_code) from None
    except (URLError, TimeoutError, OSError):
        raise SupabaseAdminAPIError(502) from None

    if not raw_body:
        return None
    try:
        return json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SupabaseAdminAPIError(502) from None


def get_profile(user_id: str, *, settings: Settings | None = None) -> dict[str, Any] | None:
    rows = _request_json(
        "GET",
        "rest/v1/profiles",
        query={"select": PROFILE_COLUMNS, "id": f"eq.{user_id}", "limit": "1"},
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def list_customer_profiles(*, settings: Settings | None = None) -> list[dict[str, Any]]:
    rows = _request_json(
        "GET",
        "rest/v1/profiles",
        query={
            "select": PROFILE_COLUMNS,
            "role": "eq.user",
            "order": "created_at.desc",
            "limit": "1000",
        },
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows


def update_profile(
    user_id: str,
    changes: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    rows = _request_json(
        "PATCH",
        "rest/v1/profiles",
        query={
            "select": PROFILE_COLUMNS,
            "id": f"eq.{user_id}",
            "role": "eq.user",
        },
        payload=changes,
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def create_auth_user(
    email: str,
    password: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    user = _request_json(
        "POST",
        "auth/v1/admin/users",
        payload={"email": email, "password": password, "email_confirm": True},
        settings=settings,
    )
    if not isinstance(user, dict) or not isinstance(user.get("id"), str):
        raise SupabaseAdminAPIError(502)
    return user


def set_auth_user_ban(
    user_id: str,
    *,
    paused: bool,
    settings: Settings | None = None,
) -> None:
    _request_json(
        "PUT",
        f"auth/v1/admin/users/{user_id}",
        payload={"ban_duration": "876000h" if paused else "none"},
        settings=settings,
    )


def update_auth_user_password(
    user_id: str,
    password: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Update an account password after the API has checked its signed-in owner."""
    _request_json(
        "PUT",
        f"auth/v1/admin/users/{user_id}",
        payload={"password": password},
        settings=settings,
    )


def delete_auth_user(user_id: str, *, settings: Settings | None = None) -> None:
    _request_json(
        "DELETE",
        f"auth/v1/admin/users/{user_id}",
        settings=settings,
    )


def sanitized_admin_error(exc: SupabaseAdminAPIError) -> HTTPException:
    """Convert provider errors to safe HTTP messages without echoing raw details."""
    if exc.status_code in {400, 422}:
        return HTTPException(status_code=422, detail="Supabase rejected the account details.")
    if exc.status_code == 404:
        return HTTPException(status_code=404, detail="The account was not found.")
    if exc.status_code == 409:
        return HTTPException(status_code=409, detail="An account with that email already exists.")
    if exc.status_code in {401, 403}:
        return HTTPException(
            status_code=503,
            detail="Supabase account administration is not authorized on the API.",
        )
    return HTTPException(status_code=502, detail="Supabase account administration is unavailable.")
