"""IP policy: Super Admin from any IP; customers restricted to their exact registered IP.

MOCKED unit tests of the real ``app.security`` code: the Supabase profile lookup is
stubbed and JWTs are signed with a test-only secret. Sign-in password checking happens
in Supabase Auth (browser -> Supabase) and is not covered here.
"""

import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.security as security
from tests.test_security import SUPABASE_URL, _hs256_token, _request, _settings

ADMIN_EMAIL = "sanjay@gmail.com"
CUSTOMER_EMAIL = "customer@example.com"
REGISTERED_IP = "192.0.2.10"  # the customer's registered address
OTHER_IP = "198.51.100.7"


def _cf(ip):
    return [(b"cf-connecting-ip", ip.encode())]


def _install(monkeypatch, *, role="user", status="active", allowed_ip=REGISTERED_IP,
             email=None, profile_missing=False, **settings_changes):
    """Production-like settings + a stubbed profile lookup; returns the mutable profile."""
    security.api_rate_limiter.reset()
    security.failed_auth_throttle.reset()
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings(**settings_changes))
    state = {
        "role": role,
        "status": status,
        "allowed_ip": allowed_ip,
        "email": email or (ADMIN_EMAIL if role == "admin" else CUSTOMER_EMAIL),
    }
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda user_id, settings=None: None if profile_missing else {"id": user_id, **state},
    )
    return state


def _auth(**claims):
    return f"Bearer {_hs256_token(**claims)}"


def _denied(monkeypatch, request, authorization, status_code, code=None):
    with pytest.raises(HTTPException) as error:
        security.require_active_account(request, authorization)
    assert error.value.status_code == status_code
    if code is not None:
        assert error.value.detail["code"] == code
    return error.value


# --- Super Admin: any IP ---------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    ["198.51.100.7", "203.0.113.200", "2001:db8:abcd::1", "100.64.12.34"],
)
def test_admin_succeeds_from_multiple_ips(monkeypatch, ip):
    _install(monkeypatch, role="admin", allowed_ip=REGISTERED_IP)  # stored IP matches none
    user_id = str(uuid4())
    account = security.require_admin_account(_request(_cf(ip)), _auth(user_id=user_id))
    assert account.id == user_id
    assert account.role == "admin"


@pytest.mark.parametrize("allowed_ip", [None, "", "not-an-ip", "192.0.2.0/24"])
def test_admin_ignores_missing_or_malformed_stored_ip(monkeypatch, allowed_ip):
    _install(monkeypatch, role="admin", allowed_ip=allowed_ip)
    account = security.require_admin_account(_request(_cf(OTHER_IP)), _auth())
    assert account.role == "admin"


def test_admin_succeeds_when_the_client_ip_cannot_be_determined(monkeypatch):
    _install(monkeypatch, role="admin")
    account = security.require_admin_account(_request(), _auth())  # no trusted header
    assert account.client_ip is None


# --- Customers: exact registered IP, fail closed ----------------------------------------


def test_customer_succeeds_from_their_registered_ip(monkeypatch):
    _install(monkeypatch, role="user")
    account = security.require_active_account(_request(_cf(REGISTERED_IP)), _auth())
    assert account.role == "user"
    assert account.client_ip == REGISTERED_IP


def test_customer_fails_from_a_different_ip(monkeypatch):
    _install(monkeypatch, role="user")
    _denied(monkeypatch, _request(_cf(OTHER_IP)), _auth(), 403, "ip_not_allowed")


@pytest.mark.parametrize(
    ("allowed_ip", "code"),
    [
        (None, "ip_not_configured"),
        ("", "ip_not_configured"),
        ("   ", "ip_not_configured"),
        ("not-an-ip", "ip_configuration_invalid"),
        ("192.0.2.0/24", "ip_configuration_invalid"),  # a range is not one exact host
        ("2001:db8::/64", "ip_configuration_invalid"),
    ],
)
def test_customer_with_missing_or_malformed_ip_is_denied(monkeypatch, allowed_ip, code):
    _install(monkeypatch, role="user", allowed_ip=allowed_ip)
    _denied(monkeypatch, _request(_cf(REGISTERED_IP)), _auth(), 403, code)


def test_customer_is_denied_when_the_client_ip_cannot_be_verified(monkeypatch):
    _install(monkeypatch, role="user")
    # Production with no Cloudflare header: fail closed (503), never allow.
    _denied(monkeypatch, _request(), _auth(), 503)


def test_customer_cannot_bypass_the_ip_check_with_forged_headers(monkeypatch):
    _install(monkeypatch, role="user")
    forged = _request([
        (b"x-forwarded-for", REGISTERED_IP.encode()),  # claims to be the registered IP
        (b"x-real-ip", REGISTERED_IP.encode()),
        (b"forwarded", f"for={REGISTERED_IP}".encode()),
        (b"cf-connecting-ip", OTHER_IP.encode()),  # the trusted header says otherwise
    ])
    _denied(monkeypatch, forged, _auth(), 403, "ip_not_allowed")

    only_forged = _request([(b"x-forwarded-for", REGISTERED_IP.encode())])
    _denied(monkeypatch, only_forged, _auth(), 503)  # no trusted header: still denied

    listed = _request([(b"cf-connecting-ip", f"{REGISTERED_IP}, {OTHER_IP}".encode())])
    _denied(monkeypatch, listed, _auth(), 503)  # a header list is never accepted


def test_forged_header_does_not_make_a_customer_an_admin_or_change_admin_identity(monkeypatch):
    _install(monkeypatch, role="user")
    request = _request(_cf(REGISTERED_IP) + [(b"x-forwarded-for", OTHER_IP.encode())])
    account = security.require_active_account(request, _auth())
    assert account.client_ip == REGISTERED_IP  # only the trusted header is used
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(request, _auth())
    assert error.value.status_code == 403


# --- Immediate effect of account changes ------------------------------------------------


def test_demoted_admin_becomes_subject_to_user_restrictions_immediately(monkeypatch):
    state = _install(monkeypatch, role="admin", allowed_ip=REGISTERED_IP)
    token = _auth()
    elsewhere = _request(_cf(OTHER_IP))
    assert security.require_admin_account(elsewhere, token).role == "admin"

    state["role"] = "user"  # demoted; the JWT is still valid
    _denied(monkeypatch, elsewhere, token, 403, "ip_not_allowed")  # now IP-restricted
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(_cf(REGISTERED_IP)), token)
    assert error.value.status_code == 403  # and no longer an administrator
    assert security.require_active_account(_request(_cf(REGISTERED_IP)), token).role == "user"


def test_promoting_a_customer_does_not_happen_from_the_client_side(monkeypatch):
    state = _install(monkeypatch, role="user")
    token = _auth(user_metadata={"role": "admin"}, app_metadata={"role": "admin"})
    request = _request(_cf(REGISTERED_IP))
    assert security.require_active_account(request, token).role == "user"
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(request, token)
    assert error.value.status_code == 403
    assert state["role"] == "user"


def test_pausing_an_account_revokes_an_unexpired_token_immediately(monkeypatch):
    state = _install(monkeypatch, role="admin")
    token = _auth()
    request = _request(_cf(OTHER_IP))
    assert security.require_admin_account(request, token).role == "admin"
    state["status"] = "paused"
    _denied(monkeypatch, request, token, 403, "account_paused")


@pytest.mark.parametrize("role", ["user", "admin"])
def test_paused_account_is_denied(monkeypatch, role):
    _install(monkeypatch, role=role, status="paused")
    _denied(monkeypatch, _request(_cf(REGISTERED_IP)), _auth(), 403, "account_paused")


@pytest.mark.parametrize("status", ["inactive", "disabled", "", None])
def test_inactive_account_is_denied(monkeypatch, status):
    _install(monkeypatch, role="admin", status=status)
    _denied(monkeypatch, _request(_cf(OTHER_IP)), _auth(), 403, "account_inactive")


def test_deleted_profile_is_denied(monkeypatch):
    _install(monkeypatch, profile_missing=True)
    _denied(monkeypatch, _request(_cf(REGISTERED_IP)), _auth(), 403, "account_unavailable")


def test_unknown_role_is_denied(monkeypatch):
    _install(monkeypatch, role="superuser")
    _denied(monkeypatch, _request(_cf(REGISTERED_IP)), _auth(), 403, "account_unavailable")


# --- JWT validity ----------------------------------------------------------------------


def _expect_401(request, authorization):
    with pytest.raises(HTTPException) as error:
        security.require_active_account(request, authorization)
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_missing_or_malformed_authorization_is_401(monkeypatch):
    _install(monkeypatch, role="admin")
    for value in (None, "", "Bearer", "Bearer not.a.jwt", "Basic abc", "Bearer a.b"):
        _expect_401(_request(), value)


def test_expired_token_is_401(monkeypatch):
    _install(monkeypatch, role="admin")
    _expect_401(_request(), _auth(exp=time.time() - 60))


def test_tampered_signature_is_401(monkeypatch):
    _install(monkeypatch, role="admin")
    head, payload, signature = _hs256_token().split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    _expect_401(_request(), f"Bearer {head}.{payload}.{flipped}")


def test_token_for_another_project_audience_or_time_is_401(monkeypatch):
    _install(monkeypatch, role="admin")
    _expect_401(_request(), _auth(iss="https://attacker.invalid/auth/v1"))
    _expect_401(_request(), _auth(aud="anon"))
    _expect_401(_request(), _auth(nbf=time.time() + 3600))


# --- Role escalation --------------------------------------------------------------------


def test_token_claiming_an_admin_jwt_role_is_rejected(monkeypatch):
    _install(monkeypatch, role="admin")
    _expect_401(_request(), _auth(role="admin"))
    _expect_401(_request(), _auth(role="service_role"))


def test_owner_email_alone_does_not_grant_admin(monkeypatch):
    _install(monkeypatch, role="user", email=ADMIN_EMAIL)
    request = _request(_cf(REGISTERED_IP))
    token = _auth(email=ADMIN_EMAIL)
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(request, token)
    assert error.value.status_code == 403
    # ...and the customer rules still apply to that profile.
    _denied(monkeypatch, _request(_cf(OTHER_IP)), token, 403, "ip_not_allowed")


def test_non_admin_cannot_use_admin_dependency(monkeypatch):
    _install(monkeypatch, role="user")
    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(_cf(REGISTERED_IP)), _auth())
    assert error.value.status_code == 403


# --- Rate limiting and brute-force protection ---------------------------------------------


def test_per_account_rate_limit_returns_429_with_retry_after(monkeypatch):
    _install(monkeypatch, role="admin", auth_rate_limit_per_minute=3)
    token = _auth(user_id=str(uuid4()))
    for _ in range(3):
        security.require_active_account(_request(), token)
    error = _denied(monkeypatch, _request(), token, 429)
    assert int(error.headers["Retry-After"]) >= 1


def test_rate_limiting_does_not_affect_unrelated_users(monkeypatch):
    _install(monkeypatch, role="user", auth_rate_limit_per_minute=2)
    noisy = _auth(user_id=str(uuid4()))
    other = _auth(user_id=str(uuid4()))
    request = _request(_cf(REGISTERED_IP))
    security.require_active_account(request, noisy)
    security.require_active_account(request, noisy)
    _denied(monkeypatch, request, noisy, 429)
    assert security.require_active_account(request, other).status == "active"


def test_default_rate_limit_allows_normal_dashboard_polling(monkeypatch):
    _install(monkeypatch, role="user")
    token = _auth()
    for _ in range(100):  # under the default of 120 per minute
        security.require_active_account(_request(_cf(REGISTERED_IP)), token)


def test_repeated_failed_authentication_is_throttled_with_429(monkeypatch):
    _install(monkeypatch, role="admin", auth_failure_limit=3)
    attacker = _request(_cf("203.0.113.66"))
    for _ in range(3):
        _expect_401(attacker, "Bearer invalid.token.value")
    error = _denied(monkeypatch, attacker, "Bearer invalid.token.value", 429)
    assert "Retry-After" in error.headers


def test_failed_attempts_never_block_a_valid_token_or_other_clients(monkeypatch):
    _install(monkeypatch, role="admin", auth_failure_limit=2)
    shared = _cf("203.0.113.66")
    for _ in range(2):
        _expect_401(_request(shared), "Bearer bad.bad.bad")
    _denied(monkeypatch, _request(shared), "Bearer bad.bad.bad", 429)
    assert security.require_active_account(_request(shared), _auth()).role == "admin"
    _expect_401(_request(_cf("198.51.100.1")), "Bearer bad.bad.bad")  # different IP: not throttled


def test_failed_auth_is_not_counted_without_a_trusted_client_ip(monkeypatch):
    _install(monkeypatch, role="admin", auth_failure_limit=1)
    for _ in range(5):  # no trusted IP -> would be one shared bucket, so it is skipped
        _expect_401(_request(), "Bearer bad.bad.bad")


# --- Errors reveal nothing sensitive ------------------------------------------------------


def test_error_responses_do_not_expose_secrets(monkeypatch):
    _install(monkeypatch, role="user", status="paused")
    error = _denied(monkeypatch, _request(_cf(OTHER_IP)), _auth(), 403)
    text = str(error.detail)
    assert SUPABASE_URL not in text and REGISTERED_IP not in text and OTHER_IP not in text
