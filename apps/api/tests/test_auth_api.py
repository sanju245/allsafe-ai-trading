"""Signed-in account route tests."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import security
from app.main import app
from app.routers import auth as auth_router
from app.security import AccountPrincipal, require_sign_in_account
from tests.test_security import _hs256_token, _settings


client = TestClient(app)


@pytest.mark.parametrize(("method", "session_id", "capture"), [
    ("password", "00000000-0000-4000-8000-000000000100", True),
    ("password", "invalid-session-id", False),
    ("recovery", "00000000-0000-4000-8000-000000000100", False),
])
def test_portal_profile_lookup_uses_the_signed_password_session(monkeypatch, method, session_id, capture):
    user_id = str(uuid4())
    profile = {"id": user_id, "email": "customer@example.test", "role": "user", "status": "active"}
    captures = []
    monkeypatch.setattr(security, "get_settings", _settings)
    monkeypatch.setattr(security, "get_profile", lambda *args, **kwargs: profile)
    monkeypatch.setattr(
        security, "get_profile_for_sign_in",
        lambda customer, session, ip, **kwargs: captures.append((customer, session, ip)) or profile,
    )
    token = _hs256_token(user_id=user_id, session_id=session_id, amr=[{"method": method}])
    response = client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {token}",
        "CF-Connecting-IP": "2001:db8:0:0::12",
        "X-Forwarded-For": "192.0.2.22",
    })

    assert response.status_code == 200
    assert response.json() == profile
    assert captures == ([(user_id, session_id, "2001:db8::12")] if capture else [])


def test_current_admin_profile_has_only_account_access_fields():
    principal = AccountPrincipal(
        id="00000000-0000-4000-8000-000000000002",
        email="admin@example.com",
        role="admin",
        status="active",
    )
    missing = object()
    previous = app.dependency_overrides.get(require_sign_in_account, missing)
    app.dependency_overrides[require_sign_in_account] = lambda: principal
    try:
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer test-token"}
        )
    finally:
        if previous is missing:
            app.dependency_overrides.pop(require_sign_in_account, None)
        else:
            app.dependency_overrides[require_sign_in_account] = previous

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert "allowed_ip" not in response.json()
    assert "client_ip" not in response.json()


def test_pause_reason_is_visible_after_verified_login_and_market_access_stays_locked(monkeypatch):
    customer_id = str(uuid4())
    reason = "Please contact the administrator.\nWe need to review account activity."
    calls = []

    def profile(user_id, **_):
        calls.append(user_id)
        return {"id": user_id, "email": "customer@example.test", "role": "user",
                "status": "paused" if user_id == customer_id else "active", "pause_reason": reason if user_id == customer_id else None}

    monkeypatch.setattr(security, "get_settings", _settings)
    monkeypatch.setattr(security, "get_profile", profile)
    monkeypatch.setattr(security, "get_profile_for_sign_in", lambda customer, *_args, **_opts: profile(customer))
    token = _hs256_token(user_id=customer_id, session_id=str(uuid4()), amr=[{"method": "password"}])
    headers = {"Authorization": f"Bearer {token}"}
    signed_in = client.get("/api/v1/auth/me", headers=headers)
    assert signed_in.status_code == 403
    assert signed_in.json()["detail"]["pause_reason"] == reason
    assert signed_in.headers["cache-control"] == "private, no-store"
    for path in ["/api/v1/live/quote?symbol=NIFTY50", "/api/v1/auth/warnings"]:
        denied = client.get(path, headers=headers)
        assert denied.status_code == 403 and reason not in denied.text
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_hs256_token()}"}).json()["status"] == "active"
    assert calls.count(customer_id) == 3


@pytest.mark.usefixtures("active_account_override")
def test_warnings_read_only_for_current_customer_and_can_page(monkeypatch, active_account_override):
    calls = []
    warnings = [{"id": str(uuid4()), "message": "Example notice", "sent_at": "2026-11-25T09:30:00Z"} for _ in range(21)]
    monkeypatch.setattr(auth_router, "list_customer_warnings", lambda *args: calls.append(args) or warnings)
    response = client.get("/api/v1/auth/warnings", params={"customer_id": str(uuid4())})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"warnings": warnings[:20], "next_before": warnings[19]["id"]}
    assert calls == [(active_account_override.id, None)]
    assert client.get("/api/v1/auth/warnings", params={"before": warnings[19]["id"]}).status_code == 200
    assert calls[-1] == (active_account_override.id, warnings[19]["id"])


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
