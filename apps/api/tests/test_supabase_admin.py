"""Tests for server-only Supabase URL and admin credential handling."""

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.config import Settings
import app.supabase_admin as supabase_admin
from app.supabase_admin import _credentials


def test_supabase_admin_uses_https_and_server_only_credential(monkeypatch):
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    settings = Settings(
        _env_file=None,
        app_env="production",
        supabase_url="https://example.supabase.co/",
        supabase_service_role_key=SecretStr("test-only-value"),
    )

    url, service_key = _credentials(settings)

    assert url == "https://example.supabase.co"
    assert service_key == "test-only-value"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.supabase.co",
        "https://example.supabase.co/unexpected-path",
        "https://user:password@example.supabase.co",
    ],
)
def test_production_rejects_non_https_or_malformed_project_urls(monkeypatch, url):
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    settings = Settings(
        _env_file=None,
        app_env="production",
        supabase_url=url,
        supabase_service_role_key=SecretStr("test-only-value"),
    )

    with pytest.raises(HTTPException) as error:
        _credentials(settings)
    assert error.value.status_code == 503


def test_loopback_http_is_allowed_only_for_local_development(monkeypatch):
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    settings = Settings(
        _env_file=None,
        app_env="development",
        supabase_url="http://127.0.0.1:54321",
        supabase_service_role_key=SecretStr("test-only-value"),
    )
    assert _credentials(settings)[0] == "http://127.0.0.1:54321"

    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-test")
    with pytest.raises(HTTPException) as error:
        _credentials(settings)
    assert error.value.status_code == 503


def test_password_admin_call_targets_only_the_authenticated_user(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs["payload"])),
    )

    supabase_admin.update_auth_user_password(
        "00000000-0000-4000-8000-000000000001",
        "test-only-password",
    )

    assert calls == [(
        "PUT",
        "auth/v1/admin/users/00000000-0000-4000-8000-000000000001",
        {"password": "test-only-password"},
    )]


def test_profile_lookup_by_email_normalizes_email(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs["query"])) or [],
    )

    assert supabase_admin.get_profile_by_email("  SANJAY200123@GMAIL.COM  ") is None
    assert calls == [(
        "GET",
        "rest/v1/profiles",
        {"select": supabase_admin.PROFILE_COLUMNS, "email": "eq.sanjay200123@gmail.com", "limit": "1"},
    )]


def test_account_link_can_tag_the_request_for_safe_retry_reconciliation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs["payload"])) or {
            "action_link": "https://auth.example/invite", "user": {"id": "user-id"},
        },
    )

    supabase_admin.generate_account_link(
        "customer@example.com",
        link_type="invite",
        redirect_to="https://site.example/set-password",
        data={"allsafe_account_request_id": "request-id"},
    )

    assert calls == [(
        "POST",
        "auth/v1/admin/generate_link",
        {
            "type": "invite",
            "email": "customer@example.com",
            "redirect_to": "https://site.example/set-password",
            "data": {"allsafe_account_request_id": "request-id"},
        },
    )]


def test_login_ip_event_insert_uses_service_role_rest_table(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs)) or [{
            "user_id": "user-id", "client_ip": "203.0.113.4", "logged_at": "2026-11-19T10:00:00Z",
        }],
    )

    result = supabase_admin.insert_customer_login_ip_event("user-id", "203.0.113.4")

    assert result["client_ip"] == "203.0.113.4"
    assert calls[0][0:2] == ("POST", "rest/v1/customer_login_ip_events")
    assert calls[0][2]["payload"] == {"user_id": "user-id", "client_ip": "203.0.113.4"}
