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


def test_login_event_insert_uses_service_role_path_and_bounds_user_agent(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs["payload"])) or [{"id": "event-id"}],
    )

    event = supabase_admin.record_login_event(
        "00000000-0000-4000-8000-000000000001",
        "customer@example.com",
        "198.51.100.44",
        "A" * 600,
    )

    assert event == {"id": "event-id"}
    assert calls == [(
        "POST",
        "rest/v1/login_events",
        {
            "user_id": "00000000-0000-4000-8000-000000000001",
            "email": "customer@example.com",
            "client_ip": "198.51.100.44",
            "user_agent": "A" * 512,
        },
    )]


def test_login_event_reader_uses_paginated_descending_service_request(monkeypatch):
    calls = []
    monkeypatch.setattr(
        supabase_admin,
        "_request_json",
        lambda method, endpoint, **kwargs: calls.append((method, endpoint, kwargs["query"])) or [],
    )

    assert supabase_admin.list_login_events(limit=25, offset=100) == []
    assert calls == [(
        "GET",
        "rest/v1/login_events",
        {
            "select": "id,user_id,email,client_ip,user_agent,occurred_at",
            "order": "occurred_at.desc,id.desc",
            "limit": "25",
            "offset": "100",
        },
    )]
