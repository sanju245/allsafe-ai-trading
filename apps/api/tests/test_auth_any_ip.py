"""Authentication must be independent of the client IP address (security layer).

These are MOCKED unit tests: the Supabase profile lookup is replaced with a stub and
JWTs are signed with a test-only secret. They exercise the real ``app.security`` code
(token verification, status/role checks, rate limiting). They do not talk to Supabase.
Sign-in password checking happens in Supabase Auth (browser -> Supabase) and is not
covered here.
"""

import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.security as security
from tests.test_security import SUPABASE_URL, _hs256_token, _request, _settings

ADMIN_EMAIL = "sanjay@gmail.com"


def _reset_limiters():
    security.api_rate_limiter.reset()
    security.failed_auth_throttle.reset()


def _install(monkeypatch, *, role="admin", status="active", allowed_ip="192.0.2.10",
             email=ADMIN_EMAIL, profile_missing=False, **settings_changes):
    """Mock settings and the Supabase profile lookup; return the profile dict."""
    _reset_limiters()
    monkeypatch.setattr(security, "get_settings", lambda: _settings(**settings_changes))
    state = {"role": role, "status": status, "allowed_ip": allowed_ip, "email": email}
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda user_id, settings=None: None if profile_missing else {"id": user_id, **state},
    )
    return state


def _cf(ip):
    return [(b"cf-connecting-ip", ip.encode())]


# --- Admin / user can authenticate from any IP --------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "198.51.100.7",  # IP A: home Wi-Fi
        "203.0.113.200",  # IP B: a different network
        "2001:db8:abcd::1",  # IPv6 mobile data
        "100.64.12.34",  # carrier-grade NAT range
    ],
)
def test_admin_authenticates_from_any_ip_in_production(monkeypatch, ip):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, allowed_ip="192.0.2.10")  # stored IP differs from every caller
    user_id = str(uuid4())
    token = f"Bearer {_hs256_token(user_id=user_id)}"

    account = security.require_admin_account(_request(_cf(ip)), token)

    assert account.id == user_id
    assert account.role == "admin"
    assert account.client_ip is not None  # recorded for display/throttling only


def test_admin_authenticates_when_no_allowed_ip_is_stored(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, allowed_ip=None)
    token = f"Bearer {_hs256_token()}"
    assert security.require_admin_account(_request(_cf("198.51.100.8")), token).role == "admin"


@pytest.mark.parametrize("allowed_ip", ["192.0.2.0/24", "not-an-ip", "", None])
def test_invalid_or_missing_stored_ip_no_longer_blocks_access(monkeypatch, allowed_ip):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, allowed_ip=allowed_ip)
    token = f"Bearer {_hs256_token()}"
    account = security.require_active_account(_request(_cf("198.51.100.9")), token)
    assert account.status == "active"
    assert account.allowed_ip is None  # normalised, informational only


def test_unknown_client_ip_does_not_block_authentication(monkeypatch):
    # Production with no Cloudflare header: previously a 503 for every authenticated call.
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch)
    token = f"Bearer {_hs256_token()}"
    account = security.require_active_account(_request(), token)
    assert account.client_ip is None


def test_forged_forwarded_header_does_not_change_identity(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, role="user", email="customer@example.com")
    token = f"Bearer {_hs256_token()}"
    request = _request([(b"x-forwarded-for", b"198.51.100.1"), (b"cf-connecting-ip", b"203.0.113.9")])
    account = security.require_active_account(request, token)
    assert account.client_ip == "203.0.113.9"  # only the trusted header is used
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(request, token)
    assert error.value.status_code == 403


def test_active_user_is_allowed_from_any_ip(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, role="user", email="customer@example.com", allowed_ip="192.0.2.50")
    token = f"Bearer {_hs256_token()}"
    assert security.require_active_account(_request(_cf("198.51.100.77")), token).role == "user"


# --- Account state is still enforced -------------------------------------------------


def test_paused_user_is_rejected(monkeypatch):
    _install(monkeypatch, role="user", status="paused")
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "account_paused"


def test_paused_admin_is_rejected(monkeypatch):
    _install(monkeypatch, role="admin", status="paused")
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403


@pytest.mark.parametrize("status", ["inactive", "disabled", "", None])
def test_inactive_account_is_rejected(monkeypatch, status):
    _install(monkeypatch, role="user", status=status)
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "account_inactive"


def test_account_without_a_profile_is_rejected(monkeypatch):
    _install(monkeypatch, profile_missing=True)
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "account_unavailable"


def test_pausing_an_account_revokes_an_unexpired_token_immediately(monkeypatch):
    state = _install(monkeypatch, role="admin")
    token = f"Bearer {_hs256_token()}"
    assert security.require_admin_account(_request(), token).role == "admin"

    state["status"] = "paused"  # administrator pauses the account; the JWT is still valid
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), token)
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "account_paused"


def test_demoting_an_admin_takes_effect_on_the_next_request(monkeypatch):
    state = _install(monkeypatch, role="admin")
    token = f"Bearer {_hs256_token()}"
    security.require_admin_account(_request(), token)
    state["role"] = "user"
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), token)
    assert error.value.status_code == 403


def test_non_admin_cannot_use_admin_dependency(monkeypatch):
    _install(monkeypatch, role="user", email="customer@example.com")
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403


# --- JWT validity: invalid / expired / tampered -> 401 -------------------------------


def _expect_401(monkeypatch, authorization, request=None):
    with pytest.raises(HTTPException) as error:
        security.require_active_account(request or _request(), authorization)
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_missing_or_malformed_authorization_is_401(monkeypatch):
    _install(monkeypatch)
    for value in (None, "", "Bearer", "Bearer not.a.jwt", "Basic abc", "Bearer a.b"):
        _expect_401(monkeypatch, value)


def test_expired_token_is_401(monkeypatch):
    _install(monkeypatch)
    _expect_401(monkeypatch, f"Bearer {_hs256_token(exp=time.time() - 60)}")


def test_tampered_signature_is_401(monkeypatch):
    _install(monkeypatch)
    token = _hs256_token()
    head, payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    _expect_401(monkeypatch, f"Bearer {head}.{payload}.{flipped}")


def test_token_for_another_project_or_audience_is_401(monkeypatch):
    _install(monkeypatch)
    _expect_401(monkeypatch, f"Bearer {_hs256_token(iss='https://attacker.invalid/auth/v1')}")
    _expect_401(monkeypatch, f"Bearer {_hs256_token(aud='anon')}")
    _expect_401(monkeypatch, f"Bearer {_hs256_token(nbf=time.time() + 3600)}")


# --- Role escalation is rejected -----------------------------------------------------


def test_admin_role_in_token_claims_is_ignored(monkeypatch):
    _install(monkeypatch, role="user", email="customer@example.com")
    token = _hs256_token(
        user_metadata={"role": "admin"},
        app_metadata={"role": "admin", "roles": ["admin"]},
    )
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), f"Bearer {token}")
    assert error.value.status_code == 403


def test_token_claiming_admin_as_the_jwt_role_is_rejected(monkeypatch):
    _install(monkeypatch, role="admin")
    # The Supabase JWT "role" claim must be exactly "authenticated".
    _expect_401(monkeypatch, f"Bearer {_hs256_token(role='admin')}")
    _expect_401(monkeypatch, f"Bearer {_hs256_token(role='service_role')}")


def test_owner_email_alone_does_not_grant_admin(monkeypatch):
    # A profile that merely has the owner's email but the "user" role is not an admin.
    _install(monkeypatch, role="user", email=ADMIN_EMAIL)
    token = _hs256_token(email=ADMIN_EMAIL)
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), f"Bearer {token}")
    assert error.value.status_code == 403


def test_unknown_role_value_is_rejected(monkeypatch):
    _install(monkeypatch, role="superuser")
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(), f"Bearer {_hs256_token()}")
    assert error.value.status_code == 403


# --- Rate limiting and brute-force protection ----------------------------------------


def test_per_account_rate_limit_returns_429_with_retry_after(monkeypatch):
    _install(monkeypatch, auth_rate_limit_per_minute=3)
    token = f"Bearer {_hs256_token(user_id=str(uuid4()))}"
    for _ in range(3):
        security.require_active_account(_request(), token)
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(), token)
    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_account_not_global(monkeypatch):
    _install(monkeypatch, auth_rate_limit_per_minute=2)
    noisy = f"Bearer {_hs256_token(user_id=str(uuid4()))}"
    owner = f"Bearer {_hs256_token(user_id=str(uuid4()))}"
    security.require_active_account(_request(), noisy)
    security.require_active_account(_request(), noisy)
    with pytest.raises(HTTPException):
        security.require_active_account(_request(), noisy)
    # A different account is unaffected by the noisy one.
    assert security.require_active_account(_request(), owner).status == "active"


def test_default_rate_limit_allows_normal_dashboard_polling(monkeypatch):
    _install(monkeypatch)
    token = f"Bearer {_hs256_token()}"
    for _ in range(100):  # well under the default of 120 per minute
        security.require_active_account(_request(), token)


def test_repeated_failed_authentication_is_throttled_with_429(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, auth_failure_limit=3)
    attacker = _request(_cf("203.0.113.66"))
    for _ in range(3):
        _expect_401(monkeypatch, "Bearer invalid.token.value", attacker)
    with pytest.raises(HTTPException) as error:
        security.require_active_account(attacker, "Bearer invalid.token.value")
    assert error.value.status_code == 429
    assert "Retry-After" in error.value.headers


def test_failed_attempts_never_block_a_valid_token_or_other_clients(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, auth_failure_limit=2)
    shared_ip = _cf("203.0.113.66")
    for _ in range(2):
        _expect_401(monkeypatch, "Bearer bad.bad.bad", _request(shared_ip))
    with pytest.raises(HTTPException) as blocked:
        security.require_active_account(_request(shared_ip), "Bearer bad.bad.bad")
    assert blocked.value.status_code == 429

    # Same (now throttled) IP, but a genuine token: still authenticated.
    good = f"Bearer {_hs256_token()}"
    assert security.require_active_account(_request(shared_ip), good).role == "admin"
    # A different IP is not throttled.
    _expect_401(monkeypatch, "Bearer bad.bad.bad", _request(_cf("198.51.100.1")))


def test_failed_auth_is_not_counted_without_a_trusted_client_ip(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, auth_failure_limit=1)
    # No Cloudflare header -> no trusted IP -> everyone would share one bucket, so skip it.
    for _ in range(5):
        _expect_401(monkeypatch, "Bearer bad.bad.bad", _request())


# --- Errors reveal nothing sensitive --------------------------------------------------


def test_error_responses_do_not_expose_ip_details_or_secrets(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    _install(monkeypatch, role="user", status="paused", allowed_ip="192.0.2.10")
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(_cf("198.51.100.1")), f"Bearer {_hs256_token()}")
    text = str(error.value.detail)
    assert "192.0.2.10" not in text and "198.51.100.1" not in text
    assert "ip_not_allowed" not in text and "ip_not_configured" not in text
    assert SUPABASE_URL not in text
