"""Route-level checks of the IP policy: admin any IP, customers exact IP (FastAPI TestClient).

MOCKED: Supabase profile/Auth Admin calls are stubbed; JWTs use a test-only secret.
"""

import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.admin as admin_router
import app.security as security
from app.config import get_settings
from app.main import app
from tests.test_security import _hs256_token, _settings

client = TestClient(app)


def _mock_account(monkeypatch, *, role="admin", status="active", allowed_ip="192.0.2.10", **settings):
    security.api_rate_limiter.reset()
    security.failed_auth_throttle.reset()
    security.ip_mismatch_throttle.reset()
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    monkeypatch.setattr(security, "get_settings", lambda: _settings(**settings))
    monkeypatch.setattr(
        security,
        "get_profile",
        lambda user_id, settings=None: {
            "id": user_id,
            "email": "sanjay@gmail.com" if role == "admin" else "customer@example.com",
            "role": role,
            "status": status,
            "allowed_ip": allowed_ip,
        },
    )
    return {"Authorization": f"Bearer {_hs256_token()}"}


@pytest.mark.parametrize("ip", ["198.51.100.7", "203.0.113.200", "2001:db8:abcd::1"])
def test_me_succeeds_for_admin_from_any_network(monkeypatch, ip):
    headers = _mock_account(monkeypatch, allowed_ip="192.0.2.10")
    response = client.get("/api/v1/auth/me", headers={**headers, "CF-Connecting-IP": ip})

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["status"] == "active"
    assert response.headers["cache-control"] == "no-store"


def test_me_succeeds_without_any_stored_ip_or_client_ip(monkeypatch):
    headers = _mock_account(monkeypatch, allowed_ip=None)
    response = client.get("/api/v1/auth/me", headers=headers)  # no CF header at all
    assert response.status_code == 200
    assert response.json()["allowed_ip"] is None
    assert response.json()["client_ip"] is None


def test_admin_endpoints_reject_non_admin_with_403(monkeypatch):
    headers = {**_mock_account(monkeypatch, role="user"), "CF-Connecting-IP": "192.0.2.10"}
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    assert client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"email": "x@example.com", "password": "long-enough-password"},
    ).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{uuid4()}", headers=headers, json={"status": "paused"}).status_code == 403
    assert client.delete(f"/api/v1/admin/users/{uuid4()}", headers=headers).status_code == 403


def test_customer_me_succeeds_only_from_the_registered_ip(monkeypatch):
    headers = _mock_account(monkeypatch, role="user", allowed_ip="192.0.2.10")
    ok = client.get("/api/v1/auth/me", headers={**headers, "CF-Connecting-IP": "192.0.2.10"})
    assert ok.status_code == 200
    assert ok.json()["role"] == "user"
    assert ok.json()["client_ip"] == "192.0.2.10"

    denied = client.get("/api/v1/auth/me", headers={**headers, "CF-Connecting-IP": "198.51.100.7"})
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ip_not_allowed"


def test_customer_cannot_bypass_with_x_forwarded_for(monkeypatch):
    headers = _mock_account(monkeypatch, role="user", allowed_ip="192.0.2.10")
    forged = {**headers, "CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "192.0.2.10"}
    assert client.get("/api/v1/auth/me", headers=forged).status_code == 403
    only_forged = {**headers, "X-Forwarded-For": "192.0.2.10"}
    assert client.get("/api/v1/auth/me", headers=only_forged).status_code == 503


@pytest.mark.parametrize("stored", [None, "", "192.0.2.0/24", "garbage"])
def test_customer_with_missing_or_malformed_ip_is_denied(monkeypatch, stored):
    headers = _mock_account(monkeypatch, role="user", allowed_ip=stored)
    response = client.get("/api/v1/auth/me", headers={**headers, "CF-Connecting-IP": "192.0.2.10"})
    assert response.status_code == 403


def test_admin_endpoints_require_a_valid_token(monkeypatch):
    _mock_account(monkeypatch)
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.get("/api/v1/admin/users", headers={"Authorization": "Bearer bad.token.here"}).status_code == 401


def test_paused_account_is_rejected_by_the_api(monkeypatch):
    headers = _mock_account(monkeypatch, status="paused")
    response = client.get("/api/v1/auth/me", headers={**headers, "CF-Connecting-IP": "198.51.100.7"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "account_paused"


def test_rate_limit_returns_429_on_the_api(monkeypatch):
    headers = _mock_account(monkeypatch, auth_rate_limit_per_minute=2)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    limited = client.get("/api/v1/auth/me", headers=headers)
    assert limited.status_code == 429
    assert "retry-after" in limited.headers


@pytest.mark.usefixtures("admin_account_override")
def test_clients_cannot_set_a_role_when_creating_or_updating_accounts(monkeypatch):
    called = []
    monkeypatch.setattr(admin_router, "create_auth_user", lambda *a, **k: called.append("create"))
    monkeypatch.setattr(admin_router, "update_profile", lambda *a, **k: called.append("update"))

    create = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "long-enough-password", "role": "admin"},
    )
    patch = client.patch(f"/api/v1/admin/users/{uuid4()}", json={"role": "admin"})

    assert create.status_code == 422
    assert patch.status_code == 422
    assert called == []


# --- Trading safety invariants -------------------------------------------------------

_FORBIDDEN_PATH_WORDS = re.compile(r"order|execut|trade|broker|position|buy|sell", re.IGNORECASE)


def test_no_trading_execution_route_exists():
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert paths, "the API must expose routes"
    assert [p for p in paths if _FORBIDDEN_PATH_WORDS.search(p)] == []


def test_mutating_routes_are_limited_to_account_management_and_pure_validation():
    allowed_prefixes = ("/api/v1/admin", "/api/v1/auth", "/api/v1/market-data/validate")
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if methods & {"POST", "PUT", "PATCH", "DELETE"}:
            assert route.path.startswith(allowed_prefixes), route.path


def test_api_source_contains_no_broker_order_calls():
    root = Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"place_order|create_order|modify_order|cancel_order|submit_order", re.IGNORECASE)
    offenders = [str(p) for p in root.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


# --- CORS ----------------------------------------------------------------------------


def test_cors_uses_an_explicit_origin_allowlist():
    origins = get_settings().cors_origin_list
    assert origins and "*" not in origins


def test_cors_does_not_allow_an_unlisted_origin():
    response = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in response.headers
