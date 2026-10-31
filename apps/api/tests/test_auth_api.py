"""Signed-in account route tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth as auth_router


client = TestClient(app)


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
    response = client.put("/api/v1/auth/password", json={"password": "new-password-123"})

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
        json={"password": "short"},
    )

    assert response.status_code == 422
    assert '"input"' not in response.text
    assert '"short"' not in response.text
    assert calls == []


@pytest.mark.usefixtures("active_account_override")
def test_password_change_uses_the_current_verified_user(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth_router,
        "update_auth_user_password",
        lambda user_id, password: calls.append((user_id, password)),
    )

    response = client.put(
        "/api/v1/auth/password",
        headers={"Authorization": "Bearer test-token"},
        json={"password": "new-password-123"},
    )

    assert response.status_code == 204
    assert calls == [("00000000-0000-4000-8000-000000000001", "new-password-123")]
