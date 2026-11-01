"""CORS preflight tests for the browser-facing account and admin routes.

The web app calls the API cross-origin from the browser, so every method it uses must
survive the preflight (OPTIONS) request. PUT /api/v1/auth/password was previously blocked
because PUT was missing from the allowed methods.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def _allowed_origin() -> str:
    origins = get_settings().cors_origin_list
    assert origins, "CORS_ORIGINS must list at least one origin for these tests"
    return origins[0]


def _preflight(path: str, method: str, origin: str | None = None):
    return client.options(
        path,
        headers={
            "Origin": origin or _allowed_origin(),
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_password_change_preflight_is_allowed():
    response = _preflight("/api/v1/auth/password", "PUT")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _allowed_origin()
    allowed = {m.strip() for m in response.headers["access-control-allow-methods"].split(",")}
    assert "PUT" in allowed


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/auth/client-ip", "GET"),
        ("/api/v1/auth/me", "GET"),
        ("/api/v1/auth/password", "PUT"),
        ("/api/v1/admin/users", "GET"),
        ("/api/v1/admin/users", "POST"),
        ("/api/v1/admin/users/00000000-0000-4000-8000-000000000001", "PATCH"),
        ("/api/v1/admin/users/00000000-0000-4000-8000-000000000001", "DELETE"),
    ],
)
def test_every_browser_method_used_by_the_web_app_passes_preflight(path, method):
    response = _preflight(path, method)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _allowed_origin()


def test_preflight_from_an_unlisted_origin_is_rejected():
    response = _preflight("/api/v1/auth/password", "PUT", origin="https://evil.example")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_a_method_the_api_does_not_allow_is_rejected():
    response = _preflight("/api/v1/auth/password", "TRACE")

    assert response.status_code == 400


def test_credentials_are_not_enabled_for_cross_origin_requests():
    """The web app sends credentials: 'omit'; the API must not opt in to cookies."""
    response = _preflight("/api/v1/auth/password", "PUT")

    assert "access-control-allow-credentials" not in response.headers


def test_actual_put_without_a_token_is_still_rejected_by_authentication():
    """Allowing PUT in CORS must not weaken authentication on the route itself."""
    response = client.put(
        "/api/v1/auth/password",
        headers={"Origin": _allowed_origin()},
        json={"password": "new-password-123"},
    )

    assert response.status_code in {401, 503}
    assert response.status_code != 204
