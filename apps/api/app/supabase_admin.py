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

PROFILE_COLUMNS = "id,email,role,status,created_at,pause_reason"
ACCOUNT_REQUEST_COLUMNS = (
    "id,full_name,date_of_birth,email,phone_number,whatsapp_number,"
    "request_ip,status,notification_status,auth_user_id,decided_by,"
    "created_at,receipt_sent_at,decided_at,notification_sent_at,"
    "approval_attempt,processing_started_at,notification_started_at,receipt_started_at,"
    "uses_chosen_password"
)
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
    user_token: str | None = None,
) -> Any:
    base_url, service_key = _credentials(settings)
    url = f"{base_url}/{endpoint.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"

    data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "apikey": service_key,
        "Authorization": f"Bearer {user_token or service_key}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    if method in {"PATCH", "POST", "DELETE"} and endpoint.startswith("rest/v1/"):
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


def get_profile_for_sign_in(
    user_id: str, session_id: str, client_ip: str | None, *, settings: Settings | None = None,
) -> dict[str, Any] | None:
    rows = _request_json(
        "POST",
        "rest/v1/rpc/get_profile_for_sign_in",
        payload={"p_user_id": user_id, "p_session_id": session_id, "p_client_ip": client_ip},
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def get_profile_by_email(email: str, *, settings: Settings | None = None) -> dict[str, Any] | None:
    """Return an existing profile for a normalized email, if one exists."""
    rows = _request_json(
        "GET",
        "rest/v1/profiles",
        query={"select": PROFILE_COLUMNS, "email": f"eq.{email.strip().lower()}", "limit": "1"},
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


def list_customer_sign_ins(user_id: str, *, settings: Settings | None = None) -> list[dict[str, Any]]:
    rows = _request_json(
        "GET",
        "rest/v1/customer_sign_ins",
        query={
            "select": "signed_in_at,ip_address",
            "customer_id": f"eq.{user_id}",
            "order": "signed_in_at.desc,session_id.desc",
            "limit": "10",
        },
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows


def send_customer_warning(warning_id: str, target_id: str | None, message: str) -> int:
    count = _request_json("POST", "rest/v1/rpc/send_customer_warning", payload={
        "p_id": warning_id, "p_target_id": target_id, "p_message": message,
    })
    if type(count) is not int or count < -1:
        raise SupabaseAdminAPIError(502)
    return count


def list_customer_warnings(user_id: str, before: str | None) -> list[dict[str, Any]]:
    rows = _request_json("POST", "rest/v1/rpc/get_customer_warnings", payload={
        "p_customer_id": user_id, "p_before": before,
    })
    if not isinstance(rows, list) or len(rows) > 21:
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


def create_auth_user_from_hash(email: str, password_hash: str, approval_attempt: str) -> dict[str, Any]:
    user = _request_json("POST", "auth/v1/admin/users", payload={
        "email": email,
        "password_hash": password_hash,
        "email_confirm": True,
        "app_metadata": {"allsafe_approval_attempt": approval_attempt},
    })
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


def get_auth_user(user_id: str, *, settings: Settings | None = None) -> dict[str, Any]:
    result = _request_json("GET", f"auth/v1/admin/users/{user_id}", settings=settings)
    user = result.get("user", result) if isinstance(result, dict) else None
    if not isinstance(user, dict) or user.get("id") != user_id:
        raise SupabaseAdminAPIError(502)
    return user


def revoke_temporary_session(access_token: str) -> None:
    try:
        _request_json("POST", "auth/v1/logout", query={"scope": "local"}, user_token=access_token)
    except SupabaseAdminAPIError:
        return


def verify_email_otp(token_hash: str, link_type: str) -> str:
    result = _request_json("POST", "auth/v1/verify", payload={"token_hash": token_hash, "type": link_type})
    if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
        raise SupabaseAdminAPIError(502)
    return result["access_token"]


def check_current_password(email: str, password: str, *, expected_user_id: str) -> bool:
    try:
        result = _request_json("POST", "auth/v1/token", query={"grant_type": "password"},
                               payload={"email": email, "password": password})
    except SupabaseAdminAPIError as exc:
        if exc.status_code in {400, 401, 403, 422}:
            return False
        raise
    user = result.get("user") if isinstance(result, dict) else None
    if isinstance(result, dict) and isinstance(result.get("access_token"), str):
        revoke_temporary_session(result["access_token"])
    return isinstance(user, dict) and user.get("id") == expected_user_id


def generate_account_link(
    email: str,
    *,
    link_type: str,
    redirect_to: str,
    approval_attempt: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """An invite creates the Auth user; recovery refreshes a setup link."""
    payload: dict[str, Any] = {"type": link_type, "email": email, "redirect_to": redirect_to}
    if approval_attempt:
        payload["data"] = {"allsafe_approval_attempt": approval_attempt}
    result = _request_json(
        "POST", "auth/v1/admin/generate_link",
        payload=payload,
        settings=settings,
    )
    if not isinstance(result, dict):
        raise SupabaseAdminAPIError(502)
    properties = result.get("properties", result)
    user = result.get("user", result)
    if not isinstance(properties, dict) or not isinstance(properties.get("action_link"), str):
        raise SupabaseAdminAPIError(502)
    if link_type == "invite":
        if not isinstance(user, dict) or not isinstance(user.get("id"), str):
            raise SupabaseAdminAPIError(502)
    return {"user": user, "action_link": properties["action_link"], "hashed_token": properties.get("hashed_token")}


def insert_account_request_with_password(values: dict[str, Any], password_hash: str) -> dict[str, Any]:
    row = _request_json("POST", "rest/v1/rpc/insert_account_request_with_password", payload={
        "p_application": values, "p_password_hash": password_hash,
    })
    if not isinstance(row, dict):
        raise SupabaseAdminAPIError(502)
    return row


def get_account_request_password_hash(request_id: str, approval_attempt: str) -> str:
    digest = _request_json("POST", "rest/v1/rpc/get_account_request_password_hash", payload={
        "p_request_id": request_id, "p_approval_attempt": approval_attempt,
    })
    if not isinstance(digest, str) or not digest:
        raise SupabaseAdminAPIError(502)
    return digest


def insert_account_request(values: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    rows = _request_json(
        "POST", "rest/v1/account_requests",
        query={"select": ACCOUNT_REQUEST_COLUMNS}, payload=values, settings=settings,
    )
    if not isinstance(rows, list) or len(rows) != 1:
        raise SupabaseAdminAPIError(502)
    return rows[0]


def list_account_requests(
    *, offset: int = 0, limit: int = 26, review_only: bool = True, settings: Settings | None = None,
) -> list[dict[str, Any]]:
    query = {
        "select": ACCOUNT_REQUEST_COLUMNS, "order": "created_at.desc,id.desc",
        "offset": str(offset), "limit": str(limit),
    }
    if review_only:
        query["or"] = "(status.in.(pending,processing),notification_status.in.(pending,failed))"
    rows = _request_json(
        "GET", "rest/v1/account_requests",
        query=query,
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows


def get_open_account_request(email: str) -> dict[str, Any] | None:
    rows = _request_json("GET", "rest/v1/account_requests", query={
        "select": ACCOUNT_REQUEST_COLUMNS, "email": f"eq.{email}",
        "status": "in.(pending,processing)", "limit": "1",
    })
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def get_account_request(request_id: str, *, settings: Settings | None = None) -> dict[str, Any] | None:
    rows = _request_json(
        "GET", "rest/v1/account_requests",
        query={"select": ACCOUNT_REQUEST_COLUMNS, "id": f"eq.{request_id}", "limit": "1"},
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def update_account_request(
    request_id: str,
    changes: dict[str, Any],
    *,
    expected_status: str | None = None,
    expected: dict[str, object] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    query = {"select": ACCOUNT_REQUEST_COLUMNS, "id": f"eq.{request_id}"}
    if expected_status is not None:
        query["status"] = f"eq.{expected_status}"
    query.update(_account_request_filters(expected))
    rows = _request_json(
        "PATCH", "rest/v1/account_requests", query=query, payload=changes, settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return rows[0] if rows else None


def _account_request_filters(expected: dict[str, object] | None) -> dict[str, str]:
    return {key: "is.null" if value is None else f"eq.{value}" for key, value in (expected or {}).items()}


def delete_account_request(
    request_id: str, *, expected: dict[str, object] | None = None, settings: Settings | None = None,
) -> bool:
    rows = _request_json(
        "DELETE", "rest/v1/account_requests",
        query={"id": f"eq.{request_id}", **_account_request_filters(expected)},
        settings=settings,
    )
    if not isinstance(rows, list):
        raise SupabaseAdminAPIError(502)
    return bool(rows)


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
