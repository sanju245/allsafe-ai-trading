from uuid import uuid4

from fastapi.testclient import TestClient

import app.routers.admin as admin_routes
import app.routers.auth as auth_routes
from app.main import app
import app.security as security
from app.security import AccountPrincipal

client = TestClient(app)


def test_successful_customer_login_records_only_server_observed_ip(active_account_override, monkeypatch):
    captured = []
    monkeypatch.setattr(auth_routes, "request_client_ip", lambda request: "203.0.113.24")
    monkeypatch.setattr(
        auth_routes,
        "insert_customer_login_ip_event",
        lambda user_id, ip: captured.append((user_id, ip)),
    )

    response = client.post(
        "/api/v1/auth/login-events",
        headers={"X-Forwarded-For": "198.51.100.77"},
        json={"client_ip": "192.0.2.55"},
    )

    assert response.status_code == 204
    assert captured == [(active_account_override.id, "203.0.113.24")]


def test_customer_cannot_read_admin_login_ip_history(monkeypatch):
    customer = AccountPrincipal(
        id="00000000-0000-4000-8000-000000000001",
        email="customer@example.com", role="user", status="active",
    )
    monkeypatch.setattr(security, "require_active_account", lambda authorization=None: customer)
    response = client.get("/api/v1/admin/login-ip-audit")
    assert response.status_code == 403


def test_admin_login_ip_history_joins_customer_email_and_daily_flags(admin_account_override, monkeypatch):
    user_id = str(uuid4())
    monkeypatch.setattr(admin_routes, "list_customer_profiles", lambda: [{
        "id": user_id, "email": "customer@example.com", "role": "user", "status": "active",
        "created_at": "2026-01-01T00:00:00+00:00",
    }])
    monkeypatch.setattr(admin_routes, "list_customer_login_ip_events", lambda **kwargs: [{
        "user_id": user_id, "client_ip": "203.0.113.4", "logged_at": "2026-11-19T10:00:00+00:00",
    }])
    monkeypatch.setattr(admin_routes, "list_customer_login_ip_daily_summaries", lambda: [{
        "user_id": user_id, "login_date": "2026-11-19", "login_count": 2,
        "distinct_ip_count": 2, "ip_addresses": ["203.0.113.4", "198.51.100.9"],
    }])

    response = client.get("/api/v1/admin/login-ip-audit?limit=25&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["events"][0]["email"] == "customer@example.com"
    assert body["events"][0]["client_ip"] == "203.0.113.4"
    assert body["multiple_ip_days"][0]["distinct_ip_count"] == 2
    assert body["multiple_ip_days"][0]["ip_addresses"] == ["203.0.113.4", "198.51.100.9"]


def test_admin_audit_limit_is_bounded(admin_account_override):
    response = client.get("/api/v1/admin/login-ip-audit?limit=501")
    assert response.status_code == 422
