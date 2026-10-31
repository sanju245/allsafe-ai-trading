"""Admin customer-account lifecycle route tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.admin as admin_router
from app.main import app


pytestmark = pytest.mark.usefixtures("admin_account_override")
client = TestClient(app)


def _profile(*, user_id, email="customer@example.com", status="active", allowed_ip="203.0.113.5", role="user"):
    return {
        "id": str(user_id),
        "email": email,
        "role": role,
        "status": status,
        "allowed_ip": allowed_ip,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    }


def test_admin_creates_email_login_bound_to_one_exact_ip(monkeypatch):
    user_id = uuid4()
    captured = {}
    monkeypatch.setattr(
        admin_router,
        "create_auth_user",
        lambda email, password: captured.update(email=email, password=password) or {"id": str(user_id)},
    )
    monkeypatch.setattr(
        admin_router,
        "update_profile",
        lambda account_id, changes: _profile(
            user_id=account_id,
            email=captured["email"],
            allowed_ip=changes["allowed_ip"],
        ),
    )

    response = client.post(
        "/api/v1/admin/users",
        json={
            "email": "  CUSTOMER@Example.COM ",
            "password": "initial-password-123",
            "allowed_ip": "2001:0db8:0:0:0:0:0:10",
        },
    )

    assert response.status_code == 201
    assert captured == {"email": "customer@example.com", "password": "initial-password-123"}
    assert response.json()["email"] == "customer@example.com"
    assert response.json()["role"] == "user"
    assert response.json()["allowed_ip"] == "2001:db8::10"


def test_admin_cannot_create_cidr_allowlist_or_short_password(monkeypatch):
    called = False

    def unexpected_create(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(admin_router, "create_auth_user", unexpected_create)
    bad_ip = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "long-enough-password", "allowed_ip": "203.0.113.0/24"},
    )
    bad_password = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "short", "allowed_ip": "203.0.113.5"},
    )

    assert bad_ip.status_code == 422
    assert bad_password.status_code == 422
    assert "short" not in bad_password.text
    assert called is False


def test_account_validation_errors_do_not_echo_submitted_password():
    response = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "secret-only-in-request"},
    )

    assert response.status_code == 422
    assert "secret-only-in-request" not in response.text


def test_admin_can_pause_and_resume_customer(monkeypatch):
    user_id = uuid4()
    current = _profile(user_id=user_id)
    calls = []
    monkeypatch.setattr(admin_router, "_customer_profile", lambda account_id: current)
    monkeypatch.setattr(
        admin_router,
        "update_profile",
        lambda account_id, changes: {**current, **changes},
    )
    monkeypatch.setattr(
        admin_router,
        "set_auth_user_ban",
        lambda account_id, *, paused: calls.append((account_id, paused)),
    )

    paused = client.patch(f"/api/v1/admin/users/{user_id}", json={"status": "paused"})
    current.update(paused.json())
    resumed = client.patch(f"/api/v1/admin/users/{user_id}", json={"status": "active"})

    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert calls == [(str(user_id), True), (str(user_id), False)]


def test_admin_cannot_edit_or_delete_another_admin(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        admin_router,
        "get_profile",
        lambda account_id: _profile(user_id=account_id, role="admin"),
    )
    deleted = []
    monkeypatch.setattr(admin_router, "delete_auth_user", lambda account_id: deleted.append(account_id))

    update = client.patch(f"/api/v1/admin/users/{user_id}", json={"status": "paused"})
    delete = client.delete(f"/api/v1/admin/users/{user_id}")

    assert update.status_code == 409
    assert delete.status_code == 409
    assert deleted == []


def test_admin_can_delete_customer_account(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        admin_router,
        "_customer_profile",
        lambda account_id: _profile(user_id=account_id),
    )
    deleted = []
    monkeypatch.setattr(admin_router, "delete_auth_user", lambda account_id: deleted.append(account_id))

    response = client.delete(f"/api/v1/admin/users/{user_id}")

    assert response.status_code == 204
    assert deleted == [str(user_id)]
