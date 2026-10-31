"""JWT, account-state, and trusted-proxy IP enforcement tests."""

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request

import app.security as security


SUPABASE_URL = "https://test-project.supabase.co"
JWT_SECRET = "test-only-supabase-signing-secret"


def _segment(value):
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _hs256_token(*, user_id=None, **claim_overrides):
    user_id = user_id or str(uuid4())
    claims = {
        "aud": "authenticated",
        "exp": time.time() + 300,
        "iat": time.time(),
        "iss": f"{SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "sub": user_id,
    }
    claims.update(claim_overrides)
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment(claims)
    signing_input = f"{header}.{payload}"
    signature = hmac.new(JWT_SECRET.encode(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def _request(headers=(), client=("10.0.0.2", 1234)):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": list(headers),
        "client": client,
        "server": ("test", 443),
    })


def _settings(**changes):
    values = {
        "app_env": "production",
        "supabase_url": SUPABASE_URL,
        "supabase_jwt_secret": SecretStr(JWT_SECRET),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_hs256_token_checks_issuer_audience_and_required_auth_role(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    user_id = str(uuid4())
    assert security.verify_supabase_access_token(
        f"Bearer {_hs256_token(user_id=user_id)}",
        supabase_url=SUPABASE_URL,
        jwt_secret=SecretStr(JWT_SECRET),
    ) == user_id

    bad_issuer = _hs256_token(iss="https://attacker.invalid/auth/v1")
    with pytest.raises(HTTPException) as error:
        security.verify_supabase_access_token(
            f"Bearer {bad_issuer}",
            supabase_url=SUPABASE_URL,
            jwt_secret=SecretStr(JWT_SECRET),
        )
    assert error.value.status_code == 401


def test_es256_token_uses_matching_public_jwk_without_shared_secret(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings(supabase_jwt_secret=None))
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-es256-key", "use": "sig", "alg": "ES256", "key_ops": ["verify"]})
    monkeypatch.setattr(security, "_load_jwks", lambda url, refresh=False: [public_jwk])
    user_id = str(uuid4())
    claims = {
        "aud": "authenticated",
        "exp": time.time() + 300,
        "iat": time.time(),
        "iss": f"{SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "sub": user_id,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "test-es256-key"})

    assert security.verify_supabase_access_token(
        f"Bearer {token}",
        supabase_url=SUPABASE_URL,
        jwt_secret=None,
    ) == user_id


def test_rs256_token_uses_matching_public_jwk_without_shared_secret(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings(supabase_jwt_secret=None))
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-rs256-key", "use": "sig", "alg": "RS256", "key_ops": ["verify"]})
    monkeypatch.setattr(security, "_load_jwks", lambda url, refresh=False: [public_jwk])
    user_id = str(uuid4())
    claims = {
        "aud": "authenticated",
        "exp": time.time() + 300,
        "iat": time.time(),
        "iss": f"{SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "sub": user_id,
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-rs256-key"})

    assert security.verify_supabase_access_token(
        f"Bearer {token}",
        supabase_url=SUPABASE_URL,
        jwt_secret=None,
    ) == user_id


def test_unsupported_algorithm_and_missing_bearer_fail_closed(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    token = f"{_segment({'alg': 'none'})}.{_segment({})}."
    with pytest.raises(HTTPException) as unsupported:
        security.verify_supabase_access_token(
            f"Bearer {token}", supabase_url=SUPABASE_URL, jwt_secret=SecretStr(JWT_SECRET)
        )
    assert unsupported.value.status_code == 401

    with pytest.raises(HTTPException) as missing:
        security.verify_supabase_access_token(
            None, supabase_url=SUPABASE_URL, jwt_secret=SecretStr(JWT_SECRET)
        )
    assert missing.value.status_code == 401


def test_production_ip_uses_only_the_trusted_cloudflare_header(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    request = _request([
        (b"cf-connecting-ip", b"198.51.100.24"),
        (b"x-forwarded-for", b"203.0.113.77"),
    ])
    assert security.request_client_ip(request) == "198.51.100.24"

    forged_only = _request([(b"x-forwarded-for", b"203.0.113.77")])
    with pytest.raises(HTTPException) as error:
        security.request_client_ip(forged_only)
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("status", "allowed_ip", "expected_status", "expected_code"),
    [
        ("active", "192.0.2.10", None, None),
        ("paused", "192.0.2.10", 403, "account_paused"),
        ("active", "192.0.2.11", 403, "ip_not_allowed"),
        ("active", None, 403, "ip_not_configured"),
        ("active", "192.0.2.0/24", 403, "ip_configuration_invalid"),
    ],
)
def test_account_access_requires_active_status_and_exact_host_ip(
    monkeypatch, status, allowed_ip, expected_status, expected_code
):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    monkeypatch.setattr(security, "request_client_ip", lambda request: "192.0.2.10")
    user_id = str(uuid4())
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda user_id, settings=None: {
            "id": user_id,
            "email": "customer@example.com",
            "role": "user",
            "status": status,
            "allowed_ip": allowed_ip,
        },
    )
    authorization = f"Bearer {_hs256_token(user_id=user_id)}"

    if expected_status is not None:
        with pytest.raises(HTTPException) as error:
            security.require_active_account(_request(), authorization)
        assert error.value.status_code == expected_status
        assert error.value.detail["code"] == expected_code
    else:
        account = security.require_active_account(_request(), authorization)
        assert account.id == user_id
        assert account.allowed_ip == "192.0.2.10"


@pytest.mark.parametrize(
    ("allowed_ip", "expected_status"),
    [
        ("2001:0db8:0:0:0:0:0:1/128", None),
        ("2001:db8::2/128", 403),
    ],
)
def test_ipv6_allowlist_matches_only_the_canonical_exact_host(
    monkeypatch, allowed_ip, expected_status
):
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    user_id = str(uuid4())
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda account_id, settings=None: {
            "id": account_id,
            "email": "customer@example.com",
            "role": "user",
            "status": "active",
            "allowed_ip": allowed_ip,
        },
    )
    request = _request([
        (b"cf-connecting-ip", b"2001:0db8:0:0:0:0:0:1"),
    ])
    authorization = f"Bearer {_hs256_token(user_id=user_id)}"

    assert security.request_client_ip(request) == "2001:db8::1"
    if expected_status is None:
        account = security.require_active_account(request, authorization)
        assert account.allowed_ip == "2001:db8::1"
    else:
        with pytest.raises(HTTPException) as error:
            security.require_active_account(request, authorization)
        assert error.value.status_code == expected_status
        assert error.value.detail["code"] == "ip_not_allowed"


def test_non_admin_cannot_use_admin_dependency(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: _settings())
    monkeypatch.setattr(security, "request_client_ip", lambda request: "192.0.2.10")
    user_id = str(uuid4())
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda user_id, settings=None: {
            "id": user_id,
            "email": "customer@example.com",
            "role": "user",
            "status": "active",
            "allowed_ip": "192.0.2.10",
        },
    )

    with pytest.raises(HTTPException) as error:
        security.require_admin_account(_request(), f"Bearer {_hs256_token(user_id=user_id)}")
    assert error.value.status_code == 403
