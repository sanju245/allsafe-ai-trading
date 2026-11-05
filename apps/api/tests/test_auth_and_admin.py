"""End-to-end authentication, authorization, Super Admin, global IP access, and Admin Panel API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.auth.security import (
    PERMANENT_SUPER_ADMIN_ID,
    hash_password,
    is_client_ip_allowed,
    validate_and_normalize_allowed_ip,
    validate_password_strength,
    verify_password,
)
from app.auth.store import AuthStore, set_auth_store
from app.config import Settings
from app.main import app


@pytest.fixture()
def admin_test_env():
    """Configure an isolated AuthStore with fast PBKDF2 iterations for unit tests."""
    test_pw = "AdminSecure#2026!Xy"
    settings = Settings(
        app_env="test",
        auth_secret_key="test-hmac-secret-key-for-allsafe-suite-only",
        super_admin_id=PERMANENT_SUPER_ADMIN_ID,
        super_admin_username="superadmin",
        super_admin_email="admin@allsafe.ai",
        super_admin_initial_password=test_pw,
        auth_login_rate_limit_per_minute=20,
        auth_max_failed_attempts=4,
        auth_lockout_seconds=300,
        admin_global_ip_access=True,
    )
    store = AuthStore(settings=settings, fast_hash=True)
    set_auth_store(app, store)
    client = TestClient(app)
    yield client, store, test_pw
    set_auth_store(app, None)


def test_pbkdf2_password_hashing_and_strength_validation():
    raw = "StrongPass!2026#AllSafe"
    validate_password_strength(raw)
    encoded = hash_password(raw, iterations=20_000)
    assert encoded.startswith("pbkdf2_sha256$20000$")
    assert raw not in encoded
    assert verify_password(raw, encoded) is True
    assert verify_password("WrongPass!2026#AllSafe", encoded) is False

    with pytest.raises(ValueError, match="at least 10 characters"):
        validate_password_strength("Short1!")
    with pytest.raises(ValueError, match="uppercase"):
        validate_password_strength("alllowercase123!")
    with pytest.raises(ValueError, match="special character"):
        validate_password_strength("NoSpecialChar123")


def test_super_admin_global_ip_login_from_any_network(admin_test_env):
    client, store, test_pw = admin_test_env

    # Verify Super Admin can log in using username OR email from multiple global public IPs (IPv4 & IPv6)
    global_ips = [
        "203.0.113.5",
        "198.51.100.42",
        "8.8.8.8",
        "2001:db8:85a3::8a2e:370:7334",
        "127.0.0.1",
    ]
    for idx, ip in enumerate(global_ips):
        identifier = "superadmin" if idx % 2 == 0 else "admin@allsafe.ai"
        res = client.post(
            "/api/v1/auth/login",
            json={"email": identifier, "password": test_pw},
            headers={"X-Forwarded-For": ip, "User-Agent": f"AllSafe-QA-Device-{idx}"},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["user"]["id"] == PERMANENT_SUPER_ADMIN_ID
        assert data["user"]["username"] == "superadmin"
        assert data["user"]["role"] == "admin"
        assert data["user"]["is_super_admin"] is True
        assert data["user"]["allowed_ip"] == "*"
        assert "*" in data["user"]["permissions"]

        # Verify /api/v1/auth/me works from a different global IP (roaming network/device)
        roaming_ip = "192.0.2.188"
        me_res = client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {data['access_token']}",
                "X-Forwarded-For": roaming_ip,
            },
        )
        assert me_res.status_code == 200
        assert me_res.json()["id"] == PERMANENT_SUPER_ADMIN_ID


def test_super_admin_protection_against_deletion_demotion_and_ip_lockout(admin_test_env):
    client, _, test_pw = admin_test_env
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin", "password": test_pw},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Cannot delete permanent Super Admin
    del_res = client.delete(f"/api/v1/admin/users/{PERMANENT_SUPER_ADMIN_ID}", headers=headers)
    assert del_res.status_code == 403
    assert "Super Admin" in del_res.json()["detail"]

    # 2. Cannot demote permanent Super Admin role
    demote_res = client.patch(
        f"/api/v1/admin/users/{PERMANENT_SUPER_ADMIN_ID}",
        headers=headers,
        json={"role": "user"},
    )
    assert demote_res.status_code == 403

    # 3. Cannot pause permanent Super Admin account
    pause_res = client.patch(
        f"/api/v1/admin/users/{PERMANENT_SUPER_ADMIN_ID}",
        headers=headers,
        json={"status": "paused"},
    )
    assert pause_res.status_code == 403

    # 4. Cannot lock permanent Super Admin to a fixed IP
    ip_res = client.patch(
        f"/api/v1/admin/users/{PERMANENT_SUPER_ADMIN_ID}",
        headers=headers,
        json={"allowed_ip": "203.0.113.10"},
    )
    assert ip_res.status_code == 403


def test_ordinary_user_cannot_access_admin_endpoints_and_ip_policy_enforced(admin_test_env):
    client, _, test_pw = admin_test_env
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin", "password": test_pw},
    )
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates a customer account restricted to 203.0.113.0/24
    user_pw = "TraderPass!2026#Ok"
    create_res = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "trader@allsafe.ai",
            "username": "trader_one",
            "password": user_pw,
            "role": "user",
            "status": "active",
            "allowed_ip": "203.0.113.0/24",
        },
    )
    assert create_res.status_code == 201, create_res.text
    created_user = create_res.json()
    assert created_user["role"] == "user"
    assert created_user["allowed_ip"] == "203.0.113.0/24"

    # Customer login from unauthorized IP (198.51.100.25) is denied (403)
    bad_ip_login = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@allsafe.ai", "password": user_pw},
        headers={"X-Forwarded-For": "198.51.100.25"},
    )
    assert bad_ip_login.status_code == 403

    # Customer login from authorized CIDR IP (203.0.113.44) succeeds
    ok_login = client.post(
        "/api/v1/auth/login",
        json={"email": "trader@allsafe.ai", "password": user_pw},
        headers={"X-Forwarded-For": "203.0.113.44"},
    )
    assert ok_login.status_code == 200
    user_token = ok_login.json()["access_token"]
    user_headers = {
        "Authorization": f"Bearer {user_token}",
        "X-Forwarded-For": "203.0.113.44",
    }

    # Ordinary user is strictly blocked (403) from all Admin Control Center endpoints
    for path in (
        "/api/v1/admin/stats",
        "/api/v1/admin/users",
        "/api/v1/admin/roles",
        "/api/v1/admin/content",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/settings",
        "/api/v1/admin/health",
    ):
        res = client.get(path, headers=user_headers)
        assert res.status_code == 403, f"Expected 403 on {path}, got {res.status_code}"


def test_brute_force_lockout_and_admin_unlock_workflow(admin_test_env):
    client, _, test_pw = admin_test_env
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin", "password": test_pw},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # Create a user account
    user_pw = "ValidPass!2026#99"
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "locktest@allsafe.ai",
            "password": user_pw,
            "role": "user",
            "status": "active",
            "allowed_ip": "*",
        },
    ).json()

    # 4 failed password attempts trigger brute-force lockout
    for _ in range(4):
        fail_res = client.post(
            "/api/v1/auth/login",
            json={"email": "locktest@allsafe.ai", "password": "WrongPassword!123"},
            headers={"X-Forwarded-For": "198.51.100.77"},
        )
        assert fail_res.status_code == 401

    # 5th attempt (even with right password) returns 429 Too Many Requests while locked out
    locked_res = client.post(
        "/api/v1/auth/login",
        json={"email": "locktest@allsafe.ai", "password": user_pw},
        headers={"X-Forwarded-For": "198.51.100.77"},
    )
    assert locked_res.status_code == 429
    assert "Retry-After" in locked_res.headers

    # Admin unlocks the user via POST /api/v1/admin/users/{id}/unlock
    unlock_res = client.post(
        f"/api/v1/admin/users/{created['id']}/unlock",
        headers=admin_headers,
    )
    assert unlock_res.status_code == 200
    assert unlock_res.json()["status"] == "active"

    # User can now sign in normally
    recovered_res = client.post(
        "/api/v1/auth/login",
        json={"email": "locktest@allsafe.ai", "password": user_pw},
        headers={"X-Forwarded-For": "198.51.100.77"},
    )
    assert recovered_res.status_code == 200


def test_admin_panel_full_crud_stats_roles_content_settings_audit_and_health(admin_test_env):
    client, _, test_pw = admin_test_env
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin", "password": test_pw},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Security headers check
    stats_res = client.get("/api/v1/admin/stats", headers=headers)
    assert stats_res.status_code == 200
    assert stats_res.headers["X-Content-Type-Options"] == "nosniff"
    assert stats_res.headers["X-Frame-Options"] == "DENY"
    stats = stats_res.json()
    assert stats["super_admin_id"] == PERMANENT_SUPER_ADMIN_ID
    assert stats["read_only_mode"] is True
    assert stats["execution_disabled"] is True

    # 2. User CRUD (create, search, PATCH, PUT, revoke-sessions, delete)
    u_res = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "ops@allsafe.ai",
            "username": "ops_lead",
            "password": "OpsPassword!2026#",
            "role": "operator",
            "status": "active",
            "allowed_ip": "*",
        },
    )
    assert u_res.status_code == 201
    uid = u_res.json()["id"]

    # Search filter
    search_res = client.get("/api/v1/admin/users?search=ops@allsafe.ai", headers=headers)
    assert search_res.status_code == 200
    assert len(search_res.json()) == 1

    # Update via PUT (verifying PR #6 PUT support)
    put_res = client.put(
        f"/api/v1/admin/users/{uid}",
        headers=headers,
        json={"status": "paused", "allowed_ip": "198.51.100.10"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "paused"
    assert put_res.json()["allowed_ip"] == "198.51.100.10"

    # Delete customer
    del_res = client.delete(f"/api/v1/admin/users/{uid}", headers=headers)
    assert del_res.status_code == 200

    # 3. Roles & Permissions
    roles_res = client.get("/api/v1/admin/roles", headers=headers)
    assert roles_res.status_code == 200
    assert any(r["role"] == "super_admin" for r in roles_res.json())

    # 4. Content & Application Config
    content_patch = client.patch(
        "/api/v1/admin/content",
        headers=headers,
        json={"default_capital_inr": 350000, "default_risk_pct": 1.25},
    )
    assert content_patch.status_code == 200
    assert content_patch.json()["default_capital_inr"] == 350000
    assert content_patch.json()["read_only_safety_lock"] is True

    # 5. System & Security Settings
    settings_patch = client.patch(
        "/api/v1/admin/settings",
        headers=headers,
        json={"session_ttl_seconds": 14400, "admin_global_ip_access": True},
    )
    assert settings_patch.status_code == 200
    assert settings_patch.json()["session_ttl_seconds"] == 14400
    assert settings_patch.json()["read_only_trading_invariant"] is True

    # 6. Audit logs & System health
    audit_res = client.get("/api/v1/admin/audit-logs?limit=25", headers=headers)
    assert audit_res.status_code == 200
    assert len(audit_res.json()) >= 5

    health_res = client.get("/api/v1/admin/health", headers=headers)
    assert health_res.status_code == 200
    assert health_res.json()["super_admin_provisioned"] is True

    # 7. Logout revokes session
    logout_res = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert after_logout.status_code == 401


def test_admin_ip_independence_across_wifi_mobile_hotspot_ipv6_and_legacy_ip_records(admin_test_env):
    client, store, test_pw = admin_test_env
    sa_login = client.post(
        "/api/v1/auth/login",
        json={"email": "superadmin", "password": test_pw},
    )
    sa_token = sa_login.json()["access_token"]
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    # Create a secondary admin account that initially had a specific office Wi-Fi IP recorded
    admin2_pw = "SecondAdmin!2026#IpFree"
    create_res = client.post(
        "/api/v1/admin/users",
        headers=sa_headers,
        json={
            "email": "sanjay.admin@allsafe.ai",
            "username": "sanjay_admin",
            "password": admin2_pw,
            "role": "admin",
            "status": "active",
            "allowed_ip": "203.0.113.10",
        },
    )
    assert create_res.status_code == 201

    # Verify this admin can log in and roam across completely different networks:
    # 1. Home Wi-Fi IPv4
    # 2. Mobile hotspot CGNAT IPv4 with port suffix
    # 3. Mobile carrier IPv6 with brackets and port
    # 4. IPv4-mapped IPv6 proxy address
    networks = [
        ("49.37.120.15", "49.37.120.15"),
        ("100.64.22.91:54321", "100.64.22.91"),
        ("[2409:40e0:102b::88a1]:44320", "2409:40e0:102b::88a1"),
        ("::ffff:198.51.100.88", "198.51.100.88"),
    ]
    token = None
    for raw_header_ip, expected_norm_ip in networks:
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": "sanjay.admin@allsafe.ai", "password": admin2_pw},
            headers={"X-Forwarded-For": raw_header_ip},
        )
        assert login_res.status_code == 200, f"Admin login failed from {raw_header_ip}: {login_res.text}"
        token = login_res.json()["access_token"]
        assert login_res.json()["user"]["last_login_ip"] == expected_norm_ip

    # Roam mid-session with the same token onto a brand new mobile hotspot IP
    roam_res = client.get(
        "/api/v1/admin/stats",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Forwarded-For": "157.48.99.201",
        },
    )
    assert roam_res.status_code == 200


def test_vercel_preview_cors_and_production_cross_site_cookie_attributes():
    prod_pw = "ProdSuperAdmin!2026#Key"
    prod_settings = Settings(
        app_env="production",
        auth_secret_key="prod-test-hmac-secret-key-for-allsafe-suite",
        super_admin_id=PERMANENT_SUPER_ADMIN_ID,
        super_admin_username="superadmin",
        super_admin_email="admin@allsafe.ai",
        super_admin_initial_password=prod_pw,
        admin_global_ip_access=True,
    )
    store = AuthStore(settings=prod_settings, fast_hash=True)
    set_auth_store(app, store)
    client = TestClient(app)
    try:
        # 1. Verify CORS preflight from Vercel preview deployment origin succeeds
        preview_origin = "https://allsafe-ai-trading-git-fix-auth-cors-admin-i-e5bd51-sanjay-68f9.vercel.app"
        preflight = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": preview_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type,X-CSRF-Token",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers.get("access-control-allow-origin") == preview_origin

        # 2. Verify production login sets SameSite=none; Secure cookies for cross-domain Vercel <-> Render
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": "superadmin", "password": prod_pw},
            headers={"Origin": "https://allsafe-ai-trading.vercel.app"},
        )
        assert login_res.status_code == 200
        set_cookie_hdr = " ".join(login_res.headers.get_list("set-cookie") if hasattr(login_res.headers, "get_list") else [login_res.headers.get("set-cookie", "")]).lower()
        assert "samesite=none" in set_cookie_hdr
        assert "secure" in set_cookie_hdr
    finally:
        set_auth_store(app, None)
