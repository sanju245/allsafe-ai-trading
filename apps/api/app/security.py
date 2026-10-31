"""Authentication and request limits for provider-backed market-data access."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request as URLRequest, build_opener
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Request
from pydantic import SecretStr

from app.config import get_settings
from app.supabase_admin import SupabaseAdminAPIError, get_profile

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_TOKEN_MAX_LENGTH = 8192
_CLOCK_SKEW_SECONDS = 30
_JWKS_TTL_SECONDS = 600
_JWKS_MAX_BYTES = 65_536
_JWKS_MAX_KEYS = 50
_ASYMMETRIC_ALGORITHMS = {"ES256", "RS256"}
_JWKS_CACHE: dict[str, tuple[float, list[dict[str, object]]]] = {}
_JWKS_LOCK = threading.Lock()


class _RejectJwksRedirects(HTTPRedirectHandler):
    """Avoid following a redirect while retrieving public verification keys."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_JWKS_OPENER = build_opener(_RejectJwksRedirects())


@dataclass(frozen=True)
class AccountPrincipal:
    id: str
    email: str
    role: str
    status: str
    allowed_ip: str | None
    client_ip: str


def request_client_ip(request: Request) -> str:
    """Return the trusted client IP; production trusts only Render's edge header."""
    settings = get_settings()
    on_render = bool(os.getenv("RENDER_SERVICE_ID"))
    production = settings.app_env.strip().lower() == "production" or on_render
    if production:
        candidate = request.headers.get("cf-connecting-ip")
    else:
        candidate = request.client.host if request.client is not None else None

    if not candidate or "," in candidate:
        raise HTTPException(
            status_code=503,
            detail="The API could not verify the request IP address.",
        )
    try:
        return ipaddress.ip_address(candidate.strip()).compressed
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="The API could not verify the request IP address.",
        ) from None


def _normalize_stored_ip(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        # PostgreSQL may serialize an inet value with its host prefix (/32 or /128).
        interface = ipaddress.ip_interface(value.strip())
        if interface.network.prefixlen != interface.max_prefixlen:
            return None
        return interface.ip.compressed
    except ValueError:
        return None


def require_active_account(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AccountPrincipal:
    """Verify the JWT and enforce the current profile status and exact IP allowlist."""
    settings = get_settings()
    user_id = verify_supabase_access_token(
        authorization,
        supabase_url=settings.supabase_url,
        jwt_secret=settings.supabase_jwt_secret,
    )
    client_ip = request_client_ip(request)
    try:
        profile = get_profile(user_id, settings=settings)
    except SupabaseAdminAPIError:
        raise HTTPException(
            status_code=503,
            detail="The API could not verify the account status.",
        ) from None

    if not isinstance(profile, dict):
        raise HTTPException(
            status_code=403,
            detail={"code": "account_unavailable", "message": "This account is not available."},
        )

    role = profile.get("role")
    status = profile.get("status")
    email = profile.get("email")
    raw_allowed_ip = profile.get("allowed_ip")
    allowed_ip = _normalize_stored_ip(raw_allowed_ip)
    if role not in {"user", "admin"} or not isinstance(email, str):
        raise HTTPException(
            status_code=403,
            detail={"code": "account_unavailable", "message": "This account is not available."},
        )
    if status == "paused":
        raise HTTPException(
            status_code=403,
            detail={"code": "account_paused", "message": "This login is paused."},
        )
    if status != "active":
        raise HTTPException(
            status_code=403,
            detail={"code": "account_inactive", "message": "This account is not active."},
        )
    if raw_allowed_ip is None or (
        isinstance(raw_allowed_ip, str) and not raw_allowed_ip.strip()
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ip_not_configured",
                "message": "An approved IP address has not been configured for this account.",
            },
        )
    if allowed_ip is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ip_configuration_invalid",
                "message": "The IP restriction for this account is invalid.",
            },
        )
    if allowed_ip != client_ip:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ip_not_allowed",
                "message": "This IP address is not approved for this account.",
            },
        )

    return AccountPrincipal(
        id=user_id,
        email=email,
        role=role,
        status=status,
        allowed_ip=allowed_ip,
        client_ip=client_ip,
    )


def require_admin_account(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AccountPrincipal:
    """Require a currently active, IP-allowed Supabase admin account."""
    account = require_active_account(request, authorization)
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return account


def _decode_base64url(value: str) -> bytes:
    if not value or not _BASE64URL.fullmatch(value):
        raise ValueError("invalid base64url segment")
    padded = value + ("=" * (-len(value) % 4))
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _decode_json_object(value: str) -> dict[str, object]:
    decoded = json.loads(_decode_base64url(value))
    if not isinstance(decoded, dict):
        raise ValueError("JWT segment must contain a JSON object")
    return decoded


def _numeric_date(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def verify_supabase_access_token(
    authorization: str | None,
    *,
    supabase_url: str | None,
    jwt_secret: SecretStr | None,
) -> str:
    """Verify a Supabase access token and return its canonical user id.

    Legacy HS256 tokens use the server-only JWT secret. Supabase asymmetric ES256 and
    RS256 tokens use the project's public JWKS endpoint. Every algorithm is pinned;
    key selection, issuer, audience, and required claims are validated.
    """
    if not supabase_url:
        raise HTTPException(
            status_code=503,
            detail="Provider-backed market-data authentication is not configured.",
        )

    if (
        authorization is None
        or len(authorization) > _TOKEN_MAX_LENGTH + 7
        or not authorization.startswith("Bearer ")
    ):
        raise HTTPException(
            status_code=401,
            detail="Sign in to request provider-backed market data.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]
    parts = token.split(".")
    if len(parts) != 3:
        _invalid_token()

    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = _decode_json_object(encoded_header)
        algorithm = header.get("alg")
        if algorithm not in {"HS256", *_ASYMMETRIC_ALGORITHMS}:
            _invalid_token()
        claims = _decode_json_object(encoded_claims)
    except (ValueError, UnicodeError, json.JSONDecodeError, binascii.Error):
        _invalid_token()

    normalized_url = _validated_supabase_url(supabase_url)
    expected_issuer = f"{normalized_url}/auth/v1"
    if algorithm == "HS256":
        if jwt_secret is None or not jwt_secret.get_secret_value():
            raise HTTPException(
                status_code=503,
                detail="HS256 Supabase token verification is not configured on the API.",
            )
        expected_signature = hmac.new(
            jwt_secret.get_secret_value().encode("utf-8"),
            f"{encoded_header}.{encoded_claims}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        try:
            supplied_signature = _decode_base64url(encoded_signature)
        except (ValueError, binascii.Error):
            _invalid_token()
        if not hmac.compare_digest(expected_signature, supplied_signature):
            _invalid_token()
        now = time.time()
        expires = _numeric_date(claims.get("exp"))
        issued_at = _numeric_date(claims.get("iat"))
        not_before = _numeric_date(claims.get("nbf"))
        audience = claims.get("aud")
        audience_matches = audience == "authenticated" or (
            isinstance(audience, list) and "authenticated" in audience
        )
        if (
            claims.get("iss") != expected_issuer
            or claims.get("role") != "authenticated"
            or not audience_matches
            or expires is None
            or expires <= now
            or issued_at is None
            or issued_at > now + _CLOCK_SKEW_SECONDS
            or ("nbf" in claims and (
                not_before is None or not_before > now + _CLOCK_SKEW_SECONDS
            ))
        ):
            _invalid_token()
    else:
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            _invalid_token()
        jwk = _find_signing_jwk(normalized_url, kid, algorithm)
        try:
            claims = jwt.decode(
                token,
                key=jwk,
                algorithms=[algorithm],
                issuer=expected_issuer,
                audience="authenticated",
                leeway=_CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "role"]},
            )
        except jwt.PyJWTError:
            _invalid_token()

    subject = claims.get("sub")
    if claims.get("role") != "authenticated" or not isinstance(subject, str):
        _invalid_token()

    try:
        return str(UUID(subject))
    except ValueError:
        _invalid_token()


def _validated_supabase_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        parsed = None
        hostname = None
        port = None
    settings = get_settings()
    on_render = bool(os.getenv("RENDER_SERVICE_ID"))
    local_development_http = (
        not on_render and settings.app_env.strip().lower() == "development"
        and parsed is not None
        and parsed.scheme == "http"
        and hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if (
        parsed is None
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65_535
        or (parsed.scheme != "https" and not local_development_http)
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication requires a valid HTTPS project URL.",
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _load_jwks(supabase_url: str, *, refresh: bool = False) -> list[dict[str, object]]:
    now = time.monotonic()
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(supabase_url)
        if not refresh and cached is not None and now - cached[0] < _JWKS_TTL_SECONDS:
            return cached[1]

    request = URLRequest(
        f"{supabase_url}/auth/v1/.well-known/jwks.json",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with _JWKS_OPENER.open(request, timeout=5) as response:
            body = response.read(_JWKS_MAX_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise HTTPException(
            status_code=503,
            detail="Supabase signing keys are temporarily unavailable.",
        ) from None
    if len(body) > _JWKS_MAX_BYTES:
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an oversized signing-key set.",
        )
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid signing-key set.",
        ) from None
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if (
        not isinstance(keys, list)
        or len(keys) > _JWKS_MAX_KEYS
        or any(not isinstance(item, dict) for item in keys)
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid signing-key set.",
        )
    normalized_keys = keys
    with _JWKS_LOCK:
        _JWKS_CACHE[supabase_url] = (time.monotonic(), normalized_keys)
    return normalized_keys


def _find_signing_jwk(supabase_url: str, kid: str, algorithm: str):
    keys = _load_jwks(supabase_url)
    matching = [item for item in keys if item.get("kid") == kid]
    if not matching:
        # A newly rotated key may not be in our still-fresh process cache.
        matching = [item for item in _load_jwks(supabase_url, refresh=True) if item.get("kid") == kid]
    if len(matching) != 1:
        _invalid_token()
    key = matching[0]
    key_ops = key.get("key_ops")
    if (
        key.get("use") not in {None, "sig"}
        or key.get("alg") not in {None, algorithm}
        or (key_ops is not None and key_ops != ["verify"])
    ):
        _invalid_token()
    try:
        parsed = jwt.PyJWK.from_dict(key, algorithm=algorithm)
    except (jwt.PyJWTError, TypeError, ValueError):
        _invalid_token()
    return parsed.key


def _invalid_token() -> None:
    raise HTTPException(
        status_code=401,
        detail="The sign-in token is invalid or expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class SlidingWindowRateLimiter:
    """Small, process-local sliding-window limiter keyed by authenticated user id."""

    def __init__(self, *, window_seconds: int = 60, max_principals: int = 10_000) -> None:
        self._window_seconds = window_seconds
        self._max_principals = max_principals
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self, principal: str, *, limit: int, resource: str = "Market-data"
    ) -> None:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            requests = self._requests.get(principal)
            if requests is not None:
                while requests and requests[0] <= cutoff:
                    requests.popleft()

            if requests is None or not requests:
                self._requests.pop(principal, None)
                if len(self._requests) >= self._max_principals:
                    for key, bucket in tuple(self._requests.items()):
                        while bucket and bucket[0] <= cutoff:
                            bucket.popleft()
                        if not bucket:
                            del self._requests[key]
                if len(self._requests) >= self._max_principals:
                    raise HTTPException(
                        status_code=429,
                        detail=f"{resource} request capacity is temporarily full. Try again shortly.",
                        headers={"Retry-After": str(self._window_seconds)},
                    )
                requests = deque()
                self._requests[principal] = requests

            if len(requests) >= limit:
                retry_after = max(
                    1,
                    math.ceil(self._window_seconds - (now - requests[0])),
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"{resource} request limit reached. Try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            requests.append(now)


market_data_rate_limiter = SlidingWindowRateLimiter()
