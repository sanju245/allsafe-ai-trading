"""Admin customer-account lifecycle route tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.routers.admin as admin_router
import app.security as security
from app.main import app
from tests.test_security import _hs256_token, _settings


pytestmark = pytest.mark.usefixtures("admin_account_override")
client = TestClient(app)


def _profile(*, user_id, email="customer@example.com", status="active", role="user"):
    return {
        "id": str(user_id),
        "email": email,
        "role": role,
        "status": status,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    }


def test_admin_sees_a_paused_customer_sign_in_history_without_internal_fields(monkeypatch):
    user_id = uuid4()
    calls = []
    monkeypatch.setattr(admin_router, "get_profile", lambda account_id: _profile(user_id=account_id, status="paused"))
    monkeypatch.setattr(admin_router, "list_customer_sign_ins", lambda account_id: calls.append(account_id) or [
        {"signed_in_at": "2026-11-25T03:45:00Z", "ip_address": "2001:db8::12", "session_id": "not-public"},
        {"signed_in_at": "2026-11-24T03:45:00Z", "ip_address": "192.0.2.15"},
        {"signed_in_at": "2026-11-23T03:45:00Z", "ip_address": None},
    ])
    response = client.get(f"/api/v1/admin/users/{user_id}/sign-ins")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == [str(user_id)]
    assert response.json()["sign_ins"] == [
        {"signed_in_at": "2026-11-25T03:45:00Z", "ip_address": "2001:db8::12"},
        {"signed_in_at": "2026-11-24T03:45:00Z", "ip_address": "192.0.2.15"},
        {"signed_in_at": "2026-11-23T03:45:00Z", "ip_address": None},
    ]


@pytest.mark.parametrize(("role", "expected"), [(None, 404), ("admin", 409)])
def test_sign_in_history_is_only_for_existing_customers(monkeypatch, role, expected):
    user_id = uuid4()
    monkeypatch.setattr(admin_router, "get_profile", lambda _: _profile(user_id=user_id, role=role) if role else None)
    monkeypatch.setattr(admin_router, "list_customer_sign_ins", lambda _: pytest.fail("History lookup ran"))
    assert client.get(f"/api/v1/admin/users/{user_id}/sign-ins").status_code == expected


@pytest.mark.parametrize(("role", "status", "expected"), [
    (None, None, 401), ("user", "active", 403), ("admin", "paused", 403),
])
def test_sign_in_history_requires_a_current_active_admin(monkeypatch, role, status, expected):
    monkeypatch.delitem(app.dependency_overrides, security.require_admin_account)
    monkeypatch.setattr(security, "get_settings", _settings)
    monkeypatch.setattr(security, "get_profile", lambda user_id, **_: _profile(user_id=user_id, role=role, status=status))
    monkeypatch.setattr(admin_router, "list_customer_sign_ins", lambda _: pytest.fail("History lookup ran"))
    headers = {"Authorization": f"Bearer {_hs256_token()}"} if role else {}
    response = client.get(f"/api/v1/admin/users/{uuid4()}/sign-ins", headers=headers)
    assert response.status_code == expected


def test_admin_creates_email_login_without_ip_requirement(monkeypatch):
    user_id = uuid4()
    captured = {}
    monkeypatch.setattr(admin_router, "require_safe_password", lambda password: None)
    monkeypatch.setattr(
        admin_router,
        "create_auth_user",
        lambda email, password: captured.update(email=email, password=password) or {"id": str(user_id)},
    )
    monkeypatch.setattr(
        admin_router,
        "get_profile",
        lambda account_id: _profile(user_id=account_id, email=captured["email"]),
    )

    response = client.post(
        "/api/v1/admin/users",
        json={
            "email": "  CUSTOMER@Example.COM ",
            "password": "initial-password-123",
        },
    )

    assert response.status_code == 201
    assert captured == {"email": "customer@example.com", "password": "initial-password-123"}
    assert response.json()["email"] == "customer@example.com"
    assert response.json()["role"] == "user"
    assert "allowed_ip" not in response.json()


def test_admin_creation_rejects_removed_ip_field_and_short_password(monkeypatch):
    called = False

    def unexpected_create(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(admin_router, "create_auth_user", unexpected_create)
    legacy_ip_field = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "long-enough-password", "allowed_ip": "203.0.113.0/24"},
    )
    bad_password = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "short"},
    )

    assert legacy_ip_field.status_code == 422
    assert bad_password.status_code == 422
    assert "short" not in bad_password.text
    assert called is False


def test_account_validation_errors_do_not_echo_submitted_password():
    response = client.post(
        "/api/v1/admin/users",
        json={"email": "customer@example.com", "password": "secret"},
    )

    assert response.status_code == 422
    assert "secret" not in response.text


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


def test_admin_update_rejects_legacy_ip_allowlist_field():
    response = client.patch(f"/api/v1/admin/users/{uuid4()}", json={"allowed_ip": "203.0.113.5"})

    assert response.status_code == 422


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
