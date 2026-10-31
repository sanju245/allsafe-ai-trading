"""Shared API test fixtures for authenticated product routes."""

import pytest

from app.main import app
from app.security import AccountPrincipal, require_active_account, require_admin_account


@pytest.fixture
def active_account_override():
    """Model an active, IP-approved customer without depending on Supabase."""
    principal = AccountPrincipal(
        id="00000000-0000-4000-8000-000000000001",
        email="customer@example.com",
        role="user",
        status="active",
        allowed_ip="192.0.2.10",
        client_ip="192.0.2.10",
    )
    missing = object()
    previous = app.dependency_overrides.get(require_active_account, missing)
    app.dependency_overrides[require_active_account] = lambda: principal
    try:
        yield principal
    finally:
        if previous is missing:
            app.dependency_overrides.pop(require_active_account, None)
        else:
            app.dependency_overrides[require_active_account] = previous


@pytest.fixture
def admin_account_override():
    """Model a currently authorized administrator for admin-route tests."""
    principal = AccountPrincipal(
        id="00000000-0000-4000-8000-000000000002",
        email="admin@example.com",
        role="admin",
        status="active",
        allowed_ip="192.0.2.20",
        client_ip="192.0.2.20",
    )
    missing = object()
    previous = app.dependency_overrides.get(require_admin_account, missing)
    app.dependency_overrides[require_admin_account] = lambda: principal
    try:
        yield principal
    finally:
        if previous is missing:
            app.dependency_overrides.pop(require_admin_account, None)
        else:
            app.dependency_overrides[require_admin_account] = previous
