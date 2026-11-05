"""Independent Security Audit Revalidation & Integration Readiness Test Suite.

Covers:
1. Admin IP exemption vs. Customer IP allowlist enforcement (IPv4, IPv6, CIDR, IPv4-mapped IPv6)
2. Anti-spoofing proxy trust, right-to-left X-Forwarded-For hop selection, duplicate headers, and malformed IPs
3. Prevention of privilege escalation via JWT claims, user_metadata, role/profile tampering, or Admin Portal login
4. JWKS caching, refresh throttling cooldown, unknown kid rejection, RS256/ES256/HS256 verification, and expired/tampered tokens
5. Concurrent rate limiting under multi-threaded load, session token rotation (/api/v1/auth/refresh), and password change session revocation
6. Supabase SQL migration & RLS policy static verification
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
import pytest

from app.auth.security import (
    JWKSCache,
    PERMANENT_SUPER_ADMIN_ID,
    _b64url_encode,
    extract_client_ip,
    is_client_ip_allowed,
    normalize_ip_string,
    verify_jwt_with_jwks_or_secret,
)
from app.auth.store import AuthStore, set_auth_store
from app.config import Settings
from app.main import app


def _int_to_b64url(val: int, length: int | None = None) -> str:
    byte_len = length or max(1, (val.bit_length() + 7) // 8)
    return _b64url_encode(val.to_bytes(byte_len, "big"))


@pytest.fixture()
def audit_env():
    """Isolated test environment with fast PBKDF2 hashing for security revalidation tests."""
    admin_pw = "SuperAdmin#2026!Audit"
    settings = Settings(
        app_env="test",
        auth_secret_key="audit-revalidation-hmac-secret-key-2026",
        supabase_jwt_secret="supabase-hs256-jwt-secret-key-2026",
        super_admin_id=PERMANENT_SUPER_ADMIN_ID,
        super_admin_username="superadmin",
        super_admin_email="admin@allsafe.ai",
        super_admin_initial_password=admin_pw,
        auth_login_rate_limit_per_minute=12,
        auth_max_failed_attempts=4,
        auth_lockout_seconds=300,
        admin_global_ip_access=True,
        trust_proxy_headers=True,
        trusted_proxy_hops=1,
    )
    store = AuthStore(settings=settings, fast_hash=True)
    set_auth_store(app, store)
    client = TestClient(app)
    yield client, store, admin_pw
    set_auth_store(app, None)


def test_ip_normalization_ipv4_ipv6_mapped_and_malformed_rejection():
    # Valid IPv4, IPv4+port, IPv6, bracketed IPv6+port, IPv6 zone ID, and IPv4-mapped IPv6
    assert normalize_ip_string("203.0.113.44", strict=True) == "203.0.113.44"
    assert normalize_ip_string("203.0.113.44:54321", strict=True) == "203.0.113.44"
    assert normalize_ip_string("2001:db8:85a3::8a2e:370:7334", strict=True) == "2001:db8:85a3::8a2e:370:7334"
    assert normalize_ip_string("[2001:db8::1]:8443", strict=True) == "2001:db8::1"
    assert normalize_ip_string("fe80::1%eth0", strict=True) == "fe80::1"
    assert normalize_ip_string("::ffff:203.0.113.44", strict=True) == "203.0.113.44"
    assert normalize_ip_string("[::ffff:203.0.113.44]:443", strict=True) == "203.0.113.44"

    # Malformed strings MUST return "" in strict mode
    for malformed in (
        "",
        "   ",
        "unknown",
        "not-an-ip",
        "999.999.999.999",
        "203.0.113.44:notaport",
        "[2001:db8::1",
        "[2001:db8::1]:badport",
        "'; DROP TABLE app_users; --",
    ):
        assert normalize_ip_string(malformed, strict=True) == "", f"Expected '' for {malformed!r}"
        assert is_client_ip_allowed(malformed, "203.0.113.0/24", role="user") is False


def test_anti_spoofing_proxy_trust_duplicate_headers_and_right_to_left_hop_extraction(audit_env):
    client, store, admin_pw = audit_env

    # Provision a customer restricted to 203.0.113.0/24
    sa_login = client.post("/api/v1/auth/admin/login", json={"email": "superadmin", "password": admin_pw})
    assert sa_login.status_code == 200
    sa_token = sa_login.json()["access_token"]

    cust_pw = "CustomerPass!2026#Ip"
    create_res = client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={
            "email": "ipcustomer@allsafe.ai",
            "username": "ip_customer",
            "password": cust_pw,
            "role": "user",
            "status": "active",
            "allowed_ip": "203.0.113.0/24",
        },
    )
    assert create_res.status_code == 201

    # 1. Attacker from 198.51.100.99 prepends spoofed allowed IP "203.0.113.44" while proxy appends "198.51.100.99"
    spoof_chain_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ipcustomer@allsafe.ai", "password": cust_pw},
        headers={"X-Forwarded-For": "203.0.113.44, 198.51.100.99"},
    )
    assert spoof_chain_res.status_code == 403
    assert "198.51.100.99" in spoof_chain_res.json()["detail"]

    # 2. Attacker sends duplicate X-Forwarded-For headers: first is spoofed 203.0.113.44, second is proxy-appended 198.51.100.99
    dup_hdr_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ipcustomer@allsafe.ai", "password": cust_pw},
        headers=[
            ("X-Forwarded-For", "203.0.113.44"),
            ("X-Forwarded-For", "198.51.100.99"),
        ],
    )
    assert dup_hdr_res.status_code == 403
    assert "198.51.100.99" in dup_hdr_res.json()["detail"]

    # 3. Legitimate customer at 203.0.113.44 routed through internal trusted load balancer 10.0.1.15 succeeds
    trusted_lb_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ipcustomer@allsafe.ai", "password": cust_pw},
        headers={"X-Forwarded-For": "203.0.113.44, 10.0.1.15"},
    )
    assert trusted_lb_res.status_code == 200
    assert trusted_lb_res.json()["user"]["last_login_ip"] == "203.0.113.44"

    # 4. When trust_proxy_headers=False, spoofed X-Forwarded-For headers are completely ignored
    store.settings.trust_proxy_headers = False
    try:
        no_proxy_trust_res = client.post(
            "/api/v1/auth/login",
            json={"email": "ipcustomer@allsafe.ai", "password": cust_pw},
            headers={"X-Forwarded-For": "203.0.113.44"},
        )
        # Peer is 127.0.0.1 (not in 203.0.113.0/24), so login is rejected with 403
        assert no_proxy_trust_res.status_code == 403
    finally:
        store.settings.trust_proxy_headers = True


def test_admin_portal_separation_and_privilege_escalation_prevention(audit_env):
    client, store, admin_pw = audit_env

    sa_login = client.post("/api/v1/auth/admin/login", json={"email": "superadmin", "password": admin_pw})
    assert sa_login.status_code == 200
    sa_headers = {"Authorization": f"Bearer {sa_login.json()['access_token']}"}

    cust_pw = "CustomerOnly!2026#1"
    cust = client.post(
        "/api/v1/admin/users",
        headers=sa_headers,
        json={
            "email": "customer.portal@allsafe.ai",
            "username": "cust_portal",
            "password": cust_pw,
            "role": "user",
            "status": "active",
            "allowed_ip": "203.0.113.50",
        },
    ).json()

    # 1. Customer CANNOT sign in via /api/v1/auth/admin/login (even from their allowed IP)
    admin_portal_attempt = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "customer.portal@allsafe.ai", "password": cust_pw},
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert admin_portal_attempt.status_code == 403
    assert "Admin Portal" in admin_portal_attempt.json()["detail"]

    # 2. Customer CAN sign in via /api/v1/auth/login from their allowed IP
    cust_login = client.post(
        "/api/v1/auth/login",
        json={"email": "customer.portal@allsafe.ai", "password": cust_pw, "portal": "customer"},
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert cust_login.status_code == 200

    # 3. Forged Supabase JWT with user_metadata.role='admin' and user_metadata.is_super_admin=True
    #    cannot escalate customer privileges or bypass customer IP allowlist!
    now_ts = int(time.time())
    header_b64 = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_b64 = _b64url_encode(
        json.dumps(
            {
                "sub": cust["id"],
                "email": cust["email"],
                "role": "authenticated",
                "user_metadata": {
                    "role": "admin",
                    "is_super_admin": True,
                    "allowed_ip": "*",
                },
                "iat": now_ts,
                "exp": now_ts + 3600,
            }
        ).encode()
    )
    import hashlib
    import hmac

    sig = hmac.new(
        store.settings.supabase_jwt_secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    supabase_jwt = f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"

    # Attempting to use this JWT from unauthorized IP 198.51.100.88 is BLOCKED (403) because server uses StoredUser
    roam_attempt = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {supabase_jwt}",
            "X-Forwarded-For": "198.51.100.88",
        },
    )
    assert roam_attempt.status_code == 403

    # From authorized IP 203.0.113.50, /api/v1/auth/me returns role='user', is_super_admin=False
    me_ok = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {supabase_jwt}",
            "X-Forwarded-For": "203.0.113.50",
        },
    )
    assert me_ok.status_code == 200
    assert me_ok.json()["role"] == "user"
    assert me_ok.json()["is_super_admin"] is False

    # And accessing /api/v1/admin/users with that JWT is strictly BLOCKED (403)
    admin_attempt = client.get(
        "/api/v1/admin/users",
        headers={
            "Authorization": f"Bearer {supabase_jwt}",
            "X-Forwarded-For": "203.0.113.50",
        },
    )
    assert admin_attempt.status_code == 403


def test_jwks_caching_refresh_throttling_unknown_kid_rs256_es256_and_expiry():
    # Generate RSA-2048 keypair for RS256 and P-256 keypair for ES256
    rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pub = rsa_priv.public_key().public_numbers()

    ec_priv = ec.generate_private_key(ec.SECP256R1())
    ec_pub = ec_priv.public_key().public_numbers()

    jwks_doc = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "rsa-key-2026-01",
                "use": "sig",
                "alg": "RS256",
                "n": _int_to_b64url(rsa_pub.n),
                "e": _int_to_b64url(rsa_pub.e),
            },
            {
                "kty": "EC",
                "kid": "ec-key-2026-01",
                "use": "sig",
                "crv": "P-256",
                "alg": "ES256",
                "x": _int_to_b64url(ec_pub.x, 32),
                "y": _int_to_b64url(ec_pub.y, 32),
            },
        ]
    }

    fetch_calls = 0

    def mock_fetcher():
        nonlocal fetch_calls
        fetch_calls += 1
        return jwks_doc

    cache = JWKSCache(
        jwks_fetcher=mock_fetcher,
        cache_ttl_seconds=3600.0,
        refresh_cooldown_seconds=30.0,
    )

    now_ts = 1_762_300_000

    # Sign an RS256 JWT
    rs_hdr = _b64url_encode(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "rsa-key-2026-01"}).encode())
    rs_pay = _b64url_encode(
        json.dumps(
            {
                "sub": "user-rs256",
                "exp": now_ts + 600,
                "user_metadata": {"role": "admin", "is_super_admin": True},
            }
        ).encode()
    )
    rs_sig = rsa_priv.sign(f"{rs_hdr}.{rs_pay}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    rs_jwt = f"{rs_hdr}.{rs_pay}.{_b64url_encode(rs_sig)}"

    # First verification triggers 1 JWKS fetch; subsequent verifications hit cache
    claims1 = verify_jwt_with_jwks_or_secret(rs_jwt, jwks_cache=cache, now_epoch=now_ts)
    assert claims1 is not None
    assert claims1["sub"] == "user-rs256"
    # Verify client-mutable user_metadata.role & is_super_admin were stripped
    assert "role" not in claims1["user_metadata"]
    assert "is_super_admin" not in claims1["user_metadata"]
    assert fetch_calls == 1

    claims2 = verify_jwt_with_jwks_or_secret(rs_jwt, jwks_cache=cache, now_epoch=now_ts + 5)
    assert claims2 is not None
    assert fetch_calls == 1

    # Sign an ES256 JWT
    es_hdr = _b64url_encode(json.dumps({"alg": "ES256", "typ": "JWT", "kid": "ec-key-2026-01"}).encode())
    es_pay = _b64url_encode(json.dumps({"sub": "user-es256", "exp": now_ts + 600}).encode())
    der_sig = ec_priv.sign(f"{es_hdr}.{es_pay}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r_int, s_int = decode_dss_signature(der_sig)
    raw_es_sig = r_int.to_bytes(32, "big") + s_int.to_bytes(32, "big")
    es_jwt = f"{es_hdr}.{es_pay}.{_b64url_encode(raw_es_sig)}"

    es_claims = verify_jwt_with_jwks_or_secret(es_jwt, jwks_cache=cache, now_epoch=now_ts + 10)
    assert es_claims is not None
    assert es_claims["sub"] == "user-es256"
    assert fetch_calls == 1

    # Unknown kid within 30s cooldown is throttled (does NOT trigger another fetch) and returns None
    unk_hdr = _b64url_encode(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "unknown-kid-999"}).encode())
    unk_jwt = f"{unk_hdr}.{rs_pay}.{_b64url_encode(rs_sig)}"
    assert verify_jwt_with_jwks_or_secret(unk_jwt, jwks_cache=cache, now_epoch=now_ts + 15) is None
    assert fetch_calls == 1
    assert cache.throttled_refresh_count == 1

    # Unknown kid after 30s cooldown triggers exactly 1 throttled refresh, still fails closed
    assert verify_jwt_with_jwks_or_secret(unk_jwt, jwks_cache=cache, now_epoch=now_ts + 45) is None
    assert fetch_calls == 2

    # Expired token is rejected
    assert verify_jwt_with_jwks_or_secret(rs_jwt, jwks_cache=cache, now_epoch=now_ts + 601) is None

    # Tampered signature is rejected
    tampered_jwt = f"{rs_hdr}.{rs_pay}.{_b64url_encode(b'0' * 256)}"
    assert verify_jwt_with_jwks_or_secret(tampered_jwt, jwks_cache=cache, now_epoch=now_ts + 50) is None

    # alg='none' is strictly rejected
    none_hdr = _b64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    assert verify_jwt_with_jwks_or_secret(f"{none_hdr}.{rs_pay}.", jwks_cache=cache, now_epoch=now_ts) is None


def test_concurrent_rate_limiting_session_refresh_and_password_rotation_revocation(audit_env):
    client, store, admin_pw = audit_env

    # 1. Test concurrent login rate-limiting from a single IP (limit = 12/min)
    def attempt_bad_login(idx: int) -> int:
        res = client.post(
            "/api/v1/auth/login",
            json={"email": f"nonexistent_{idx}@allsafe.ai", "password": "BadPassword!123"},
            headers={"X-Forwarded-For": "198.51.100.222"},
        )
        return res.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(attempt_bad_login, range(18)))

    assert statuses.count(401) == 12
    assert statuses.count(429) == 6

    # 2. Test session token refresh (/api/v1/auth/refresh) and old-token revocation
    login_res = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "superadmin", "password": admin_pw},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert login_res.status_code == 200
    old_token = login_res.json()["access_token"]

    refresh_res = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {old_token}", "X-Forwarded-For": "203.0.113.10"},
    )
    assert refresh_res.status_code == 200
    new_token = refresh_res.json()["access_token"]
    assert new_token != old_token

    # Old token is now revoked (401)
    old_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_me.status_code == 401

    # New token is active (200)
    new_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert new_me.status_code == 200

    # 3. Password change rotates PBKDF2 hash and revokes active sessions
    rotated_pw = "SuperAdmin#2026!Rotated9"
    pw_res = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {new_token}"},
        json={"current_password": admin_pw, "new_password": rotated_pw},
    )
    assert pw_res.status_code == 200

    # Pre-rotation session token is immediately invalidated
    after_pw_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert after_pw_me.status_code == 401


def test_supabase_migrations_rls_and_super_admin_trigger_invariants():
    repo_root = Path(__file__).resolve().parents[3]
    migrations_dir = repo_root / "supabase" / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    assert len(sql_files) >= 3

    auth_sql = (migrations_dir / "20261101000001_auth_users_super_admin_and_audit.sql").read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in auth_sql
    assert "FORCE ROW LEVEL SECURITY" in auth_sql
    assert "REVOKE ALL ON public.app_users FROM anon, PUBLIC;" in auth_sql
    assert "protect_permanent_super_admin()" in auth_sql
    assert "00000000-0000-4000-a000-000000000001" in auth_sql
    assert "is_admin_ip_independent" in auth_sql
