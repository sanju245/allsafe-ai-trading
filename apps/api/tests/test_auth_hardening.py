"""Hardening added after the independent security audit (MOCKED unit tests).

Covers: IPv4-mapped address normalisation, a single trusted proxy header, throttling of
repeated wrong-IP attempts, the shared bucket for unknown clients, and rate-limiting of
signing-key (JWKS) refreshes. Real ``app.security`` code; Supabase and the network are stubbed.
"""

import base64
import json
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.security as security
from tests.test_security import SUPABASE_URL, _hs256_token, _request, _settings

REGISTERED_IP = "192.0.2.10"
OTHER_IP = "198.51.100.7"


def _cf(ip):
    return [(b"cf-connecting-ip", ip.encode())]


def _install(monkeypatch, *, role="user", allowed_ip=REGISTERED_IP, **settings_changes):
    security.api_rate_limiter.reset()
    security.failed_auth_throttle.reset()
    security.ip_mismatch_throttle.reset()
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings(**settings_changes))
    state = {
        "role": role,
        "status": "active",
        "allowed_ip": allowed_ip,
        "email": "customer@example.com" if role == "user" else "sanjay@gmail.com",
    }
    monkeypatch.setattr(
        security, "get_profile", lambda user_id, settings=None: {"id": user_id, **state}
    )
    return state


def _auth(**claims):
    return f"Bearer {_hs256_token(**claims)}"


# --- IPv4-mapped IPv6 addresses ----------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("::ffff:192.0.2.10", "192.0.2.10"),
        ("::FFFF:C000:020A", "192.0.2.10"),
        ("192.0.2.10", "192.0.2.10"),
        ("2001:0db8:0:0:0:0:0:1", "2001:db8::1"),
    ],
)
def test_client_ip_is_canonicalised(monkeypatch, header, expected):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    assert security.request_client_ip(_request(_cf(header))) == expected


def test_customer_matches_across_ipv4_and_ipv4_mapped_forms(monkeypatch):
    _install(monkeypatch, allowed_ip="::ffff:192.0.2.10/128")
    account = security.require_active_account(_request(_cf("192.0.2.10")), _auth())
    assert account.allowed_ip == "192.0.2.10"
    _install(monkeypatch, allowed_ip="192.0.2.10")
    assert security.require_active_account(_request(_cf("::ffff:192.0.2.10")), _auth()).role == "user"


def test_mapped_form_does_not_widen_access(monkeypatch):
    _install(monkeypatch, allowed_ip="192.0.2.10")
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(_cf("::ffff:192.0.2.11")), _auth())
    assert error.value.status_code == 403
    _install(monkeypatch, allowed_ip="::ffff:192.0.2.0/120")  # a range stays invalid
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(_cf("::ffff:192.0.2.10")), _auth())
    assert error.value.detail["code"] == "ip_configuration_invalid"


# --- Exactly one trusted proxy header ------------------------------------------------------


def test_duplicate_or_listed_proxy_headers_are_unverifiable(monkeypatch):
    _install(monkeypatch)
    duplicate = _request([
        (b"cf-connecting-ip", REGISTERED_IP.encode()),
        (b"cf-connecting-ip", OTHER_IP.encode()),
    ])
    with pytest.raises(HTTPException) as error:
        security.require_active_account(duplicate, _auth())
    assert error.value.status_code == 503  # fail closed for customers
    listed = _request(_cf(f"{REGISTERED_IP}, {OTHER_IP}"))
    with pytest.raises(HTTPException) as error:
        security.require_active_account(listed, _auth())
    assert error.value.status_code == 503


def test_proxy_header_is_ignored_outside_production(monkeypatch):
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setattr(security, "get_settings", lambda: _settings(app_env="development"))
    request = _request(_cf("203.0.113.9"), client=("127.0.0.1", 5555))
    assert security.request_client_ip(request) == "127.0.0.1"  # the socket peer, not the header


def test_render_environment_forces_production_trust_rules(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings(app_env="development"))
    request = _request(_cf("203.0.113.9"), client=("127.0.0.1", 5555))
    assert security.request_client_ip(request) == "203.0.113.9"
    with pytest.raises(HTTPException):
        security.request_client_ip(_request(client=("127.0.0.1", 5555)))  # no header: refuse


# --- Wrong-IP attempts are throttled (guessing an address) ----------------------------------


def test_repeated_wrong_ip_attempts_become_429_but_the_registered_ip_still_works(monkeypatch):
    _install(monkeypatch, auth_ip_mismatch_limit=3)
    user_id = str(uuid4())
    token = _auth(user_id=user_id)
    for n in range(3):
        with pytest.raises(HTTPException) as error:
            security.require_active_account(_request(_cf(f"203.0.113.{n + 1}")), token)
        assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(_cf("203.0.113.99")), token)
    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) >= 1
    # The legitimate address is never blocked by the wrong-IP counter.
    assert security.require_active_account(_request(_cf(REGISTERED_IP)), token).role == "user"


def test_wrong_ip_counter_is_per_account_and_never_applies_to_admins(monkeypatch):
    _install(monkeypatch, auth_ip_mismatch_limit=1)
    first, second = _auth(user_id=str(uuid4())), _auth(user_id=str(uuid4()))
    with pytest.raises(HTTPException):
        security.require_active_account(_request(_cf(OTHER_IP)), first)
    with pytest.raises(HTTPException) as error:
        security.require_active_account(_request(_cf(OTHER_IP)), second)
    assert error.value.status_code == 403  # a different account has its own counter

    _install(monkeypatch, role="admin", auth_ip_mismatch_limit=1)
    admin = _auth()
    for _ in range(5):
        assert security.require_active_account(_request(_cf(OTHER_IP)), admin).role == "admin"


# --- Signing-key (JWKS) refresh cannot be forced on every request ---------------------------


class _Body:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _limit=None):
        return self._data


class _CountingOpener:
    def __init__(self):
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        return _Body(json.dumps({"keys": []}).encode())


def _segment(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


def _unknown_kid_token(n):
    header = _segment({"alg": "ES256", "kid": f"random-{n}"})
    claims = _segment({"sub": str(uuid4())})
    return f"Bearer {header}.{claims}.AAAA"


def _reset_jwks(monkeypatch):
    opener = _CountingOpener()
    monkeypatch.setattr(security, "_JWKS_OPENER", opener)
    security._JWKS_CACHE.clear()
    security._JWKS_LAST_ATTEMPT.clear()
    monkeypatch.setattr(security, "get_settings", lambda: _settings(supabase_jwt_secret=None))
    return opener


def test_unknown_key_ids_do_not_trigger_a_signing_key_fetch_per_request(monkeypatch):
    opener = _reset_jwks(monkeypatch)
    security.failed_auth_throttle.reset()
    for n in range(25):
        with pytest.raises(HTTPException) as error:
            security.verify_supabase_access_token(
                _unknown_kid_token(n), supabase_url=SUPABASE_URL, jwt_secret=None
            )
        assert error.value.status_code == 401
    assert opener.calls == 1  # one initial load; forced refreshes are rate limited


def test_a_forced_refresh_is_allowed_again_after_the_minimum_interval(monkeypatch):
    opener = _reset_jwks(monkeypatch)
    with pytest.raises(HTTPException):
        security.verify_supabase_access_token(
            _unknown_kid_token(0), supabase_url=SUPABASE_URL, jwt_secret=None
        )
    assert opener.calls == 1
    security._JWKS_LAST_ATTEMPT[SUPABASE_URL] -= security._JWKS_MIN_REFRESH_SECONDS + 1
    with pytest.raises(HTTPException):
        security.verify_supabase_access_token(
            _unknown_kid_token(1), supabase_url=SUPABASE_URL, jwt_secret=None
        )
    assert opener.calls == 2  # a legitimate key rotation can still be picked up
