"""Signed-in account route tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth as auth_router
from app.security import AccountPrincipal, require_active_account


client = TestClient(app)


def test_current_admin_profile_has_only_account_access_fields():
    principal = AccountPrincipal(
        id="00000000-0000-4000-8000-000000000002",
        email="admin@example.com",
        role="admin",
        status="active",
    )
    missing = object()
    previous = app.dependency_overrides.get(require_active_account, missing)
    app.dependency_overrides[require_active_account] = lambda: principal
    try:
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer test-token"}
        )
    finally:
        if previous is missing:
            app.dependency_overrides.pop(require_active_account, None)
        else:
            app.dependency_overrides[require_active_account] = previous

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert "allowed_ip" not in response.json()
    assert "client_ip" not in response.json()


def test_password_change_requires_a_verified_account(monkeypatch):
    from types import SimpleNamespace

    import app.security as security

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            app_env="test",
            supabase_url="https://test-project.supabase.co",
            supabase_jwt_secret=None,
        ),
    )
    response = client.put("/api/v1/auth/password", json={"current_password": "fixture-current", "password": "new-password-123"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.usefixtures("active_account_override")
def test_password_change_checks_minimum_password_length(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth_router,
        "update_auth_user_password",
        lambda user_id, password: calls.append((user_id, password)),
    )

    response = client.put(
        "/api/v1/auth/password",
        headers={"Authorization": "Bearer test-token"},
        json={"current_password": "fixture-current", "password": "short"},
    )

    assert response.status_code == 422
    assert '"input"' not in response.text
    assert '"short"' not in response.text
    assert calls == []


@pytest.mark.usefixtures("active_account_override")
def test_password_change_uses_the_current_verified_user(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_router, "check_current_password",
                        lambda email, password, **_: password == "fixture-current")
    monkeypatch.setattr(auth_router, "require_safe_password", lambda password: None)
    denied = client.put("/api/v1/auth/password", headers={"Authorization": "Bearer test-token"},
                        json={"current_password": "wrong", "password": "new-password-123"})
    assert denied.status_code == 422
    assert "current password is incorrect" in denied.text
    monkeypatch.setattr(
        auth_router,
        "update_auth_user_password",
        lambda user_id, password: calls.append((user_id, password)),
    )

    response = client.put(
        "/api/v1/auth/password",
        headers={"Authorization": "Bearer test-token"},
        json={"current_password": "fixture-current", "password": "new-password-123"},
    )

    assert response.status_code == 204
    assert calls == [("00000000-0000-4000-8000-000000000001", "new-password-123")]


def test_email_password_reset_uses_generic_public_response(monkeypatch):
    emails = []
    monkeypatch.setattr(auth_router, "ensure_email_ready", lambda: None)
    monkeypatch.setattr(auth_router, "request_client_ip", lambda _: "192.0.2.45")
    monkeypatch.setattr(auth_router, "get_profile_by_email", lambda email: (
        {"status": "active"} if email == "fixture@example.test" else None
    ))
    monkeypatch.setattr(auth_router, "generate_account_link", lambda *_, **__: {
        "action_link": "https://auth.example.test/reset",
    })
    monkeypatch.setattr(auth_router, "send_password_reset", lambda *args: emails.append(args))
    first = client.post("/api/v1/auth/password/recover", json={"email": "fixture@example.test"})
    second = client.post("/api/v1/auth/password/recover", json={"email": "missing@example.test"})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert emails == [("fixture@example.test", "https://auth.example.test/reset")]


def test_email_proof_rejects_compromised_password_before_consuming_link(monkeypatch):
    from fastapi import HTTPException
    def reject(password):
        raise HTTPException(status_code=422, detail="Choose another password.")
    monkeypatch.setattr(auth_router, "request_client_ip", lambda _: "192.0.2.46")
    monkeypatch.setattr(auth_router, "require_safe_password", reject)
    monkeypatch.setattr(auth_router, "verify_email_otp", lambda *_: pytest.fail("setup link was consumed"))
    result = client.post("/api/v1/auth/password/setup",
                         json={"token_hash": "fixture-proof", "type": "invite", "password": "fixture-password"})
    assert result.status_code == 422
