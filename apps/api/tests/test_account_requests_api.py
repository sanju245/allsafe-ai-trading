"""Customer application lifecycle: no Auth user before approval, and decision mail."""

import base64
import json
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from io import BytesIO
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.email_notifications as notifications
import app.routers.account_requests as routes
from app.config import Settings
from app.email_notifications import EmailDeliveryError
from app.main import app
from app.supabase_admin import SupabaseAdminAPIError

client = TestClient(app)
ADMIN_ID = "00000000-0000-4000-8000-000000000002"


def test_gmail_https_delivery(monkeypatch):
    monkeypatch.setattr(notifications, "get_settings", lambda: Settings(
        gmail_client_id="client-id",
        gmail_client_secret=SecretStr("client-secret"),
        gmail_refresh_token=SecretStr("refresh-token"),
        gmail_from_email="sanjay200123@gmail.com",
    ))
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return BytesIO(json.dumps({"access_token": "access-token"} if len(requests) == 1 else {"id": "message-id"}).encode())

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)
    notifications.send_email("asha@example.com", "Account approved", "Hello Asha")

    assert len(requests) == 2
    assert requests[0].full_url == "https://oauth2.googleapis.com/token"
    assert b"grant_type=refresh_token" in requests[0].data
    assert requests[1].full_url == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert requests[1].get_header("Authorization") == "Bearer access-token"
    raw = json.loads(requests[1].data)["raw"]
    sent = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert sent["From"] == "sanjay200123@gmail.com"
    assert sent["To"] == "asha@example.com"
    assert "Hello Asha" in sent.get_payload(decode=True).decode()


def test_password_confirmation_uses_the_account_email_and_a_plain_notice(monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, "send_email", lambda *args: sent.append(args))
    notifications.send_password_changed("customer@example.test")
    assert len(sent) == 1
    recipient, subject, body = sent[0]
    assert recipient == "customer@example.test"
    assert subject == "Your AllSafe password has changed"
    assert "AllSafe AI Trading account has been changed" in body
    assert "contact the AllSafe administrator" in body
    assert "://" not in body


def test_gmail_api_failure_is_private(monkeypatch):
    monkeypatch.setattr(notifications, "get_settings", lambda: Settings(
        gmail_client_id="client-id",
        gmail_client_secret=SecretStr("client-secret"),
        gmail_refresh_token=SecretStr("refresh-token"),
    ))
    monkeypatch.setattr(notifications, "urlopen", lambda request, timeout: (_ for _ in ()).throw(
        HTTPError(request.full_url, 401, "Invalid token", {}, None)
    ))
    with pytest.raises(EmailDeliveryError) as exc:
        notifications.send_email("asha@example.com", "Account approved", "Hello Asha")
    assert str(exc.value) == ""


def test_admin_request_notification_includes_application_details(monkeypatch):
    settings = Settings(
        gmail_client_id="client-id",
        gmail_client_secret=SecretStr("client-secret"),
        gmail_refresh_token=SecretStr("refresh-token"),
        gmail_from_email="admin@example.com",
    )
    sent = []
    monkeypatch.setattr(notifications, "get_settings", lambda: settings)
    monkeypatch.setattr(notifications, "send_email", lambda *args: sent.append(args))

    notifications.send_admin_request_notification(
        name="Asha Kumar",
        email="asha@example.com",
        date_of_birth="1995-04-20",
        phone_number="+91 9876543210",
        whatsapp_number="+91 9876543210",
    )

    assert len(sent) == 1
    recipient, subject, body = sent[0]
    assert recipient == "admin@example.com"
    assert subject == "New AllSafe account request"
    assert "asha@example.com" in body
    assert "1995-04-20" in body
    assert "+91 9876543210" in body


@pytest.fixture
def store(monkeypatch):
    rows = {}
    calls = []
    monkeypatch.setattr(routes, "ensure_email_ready", lambda: None)
    monkeypatch.setattr(routes, "setup_redirect_url", lambda: "https://example.com/set-password")
    monkeypatch.setattr(routes, "request_client_ip", lambda request: "203.0.113.5")
    monkeypatch.setattr(routes._request_rate_limiter, "check", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "send_request_received", lambda email, name: calls.append(("received", email)))
    monkeypatch.setattr(
        routes,
        "send_admin_request_notification",
        lambda **values: calls.append(("admin_request", values["email"])),
    )
    monkeypatch.setattr(routes, "send_approved", lambda email, name, link: calls.append(("approved", email, link)))
    monkeypatch.setattr(routes, "send_declined", lambda email, name: calls.append(("declined", email)))

    def insert(values):
        if any(row["email"] == values["email"] and row["status"] in {"pending", "processing"} for row in rows.values()):
            raise SupabaseAdminAPIError(409)
        row = {
            **values, "id": str(uuid4()), "status": "pending", "notification_status": "pending",
            "auth_user_id": None, "decided_by": None, "created_at": datetime.now(timezone.utc).isoformat(),
            "receipt_sent_at": None, "decided_at": None, "notification_sent_at": None,
        }
        rows[row["id"]] = row
        return row.copy()

    def update(request_id, changes, *, expected_status=None, expected=None):
        row = rows.get(request_id)
        if row is None or expected_status is not None and row["status"] != expected_status:
            return None
        if any(row.get(key) != value for key, value in (expected or {}).items()):
            return None
        row.update(changes)
        return row.copy()

    monkeypatch.setattr(routes, "insert_account_request", insert)
    monkeypatch.setattr(routes, "get_account_request", lambda request_id: rows.get(request_id))
    monkeypatch.setattr(routes, "get_profile_by_email", lambda email: None)
    monkeypatch.setattr(routes, "get_open_account_request", lambda email: next(
        (row.copy() for row in rows.values() if row["email"] == email and row["status"] in {"pending", "processing"}), None,
    ))
    def listed(*, offset, limit, review_only):
        ordered = list(reversed(list(rows.values())))
        if review_only:
            ordered = [row for row in ordered if row["status"] in {"pending", "processing"} or row["notification_status"] != "sent"]
        return ordered[offset:offset + limit]
    monkeypatch.setattr(routes, "list_account_requests", listed)
    monkeypatch.setattr(routes, "update_account_request", update)
    monkeypatch.setattr(routes, "delete_account_request", lambda request_id, **_: bool(rows.pop(request_id, None)))
    return rows, calls


def application(**changes):
    return {
        "full_name": "Asha Kumar", "date_of_birth": "1995-04-20",
        "email": "asha@example.com", "phone_number": "+91 9876543210",
        "whatsapp_number": "+91 9876543210",
        **changes,
    }


def test_public_request_sends_receipt_without_creating_account(store, monkeypatch):
    rows, calls = store
    monkeypatch.setattr(routes, "generate_account_link", lambda *args, **kwargs: pytest.fail("Auth user created before approval"))
    response = client.post("/api/v1/account-requests", json=application())
    assert response.status_code == 202
    assert len(rows) == 1
    assert next(iter(rows.values()))["status"] == "pending"
    assert calls == [("received", "asha@example.com"), ("admin_request", "asha@example.com")]


def test_request_needs_no_customer_ip_and_duplicate_is_generic(store):
    rows, calls = store
    first = client.post("/api/v1/account-requests", json=application())
    duplicate = client.post("/api/v1/account-requests", json=application())
    assert first.status_code == duplicate.status_code == 202
    assert len(rows) == 1
    assert next(iter(rows.values()))["request_ip"] == "203.0.113.5"
    assert calls == [("received", "asha@example.com"), ("admin_request", "asha@example.com")]


def test_failed_receipt_can_retry_the_same_pending_request(store, monkeypatch):
    rows, calls = store
    monkeypatch.setattr(routes, "send_request_received", lambda *args: (_ for _ in ()).throw(EmailDeliveryError()))
    response = client.post("/api/v1/account-requests", json=application())
    assert response.status_code == 503
    assert len(rows) == 1
    assert next(iter(rows.values()))["receipt_started_at"] is None
    monkeypatch.setattr(routes, "send_request_received", lambda *args: calls.append(("received", args[0])))
    assert client.post("/api/v1/account-requests", json=application()).status_code == 202
    assert len(rows) == 1
    assert next(iter(rows.values()))["receipt_sent_at"]
    assert calls[0] == ("received", "asha@example.com")


def test_failed_admin_notification_keeps_saved_request_and_receipt(store, monkeypatch, caplog):
    rows, calls = store
    monkeypatch.setattr(
        routes,
        "send_admin_request_notification",
        lambda **kwargs: (_ for _ in ()).throw(EmailDeliveryError()),
    )

    response = client.post("/api/v1/account-requests", json=application())

    assert response.status_code == 202
    assert len(rows) == 1
    assert next(iter(rows.values()))["status"] == "pending"
    assert calls == [("received", "asha@example.com")]
    assert "administrator email notification failed" in caplog.text


@pytest.mark.usefixtures("admin_account_override")
def test_approval_creates_user_without_ip_binding_and_sends_setup_link(store, monkeypatch):
    rows, calls = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    user_id = str(uuid4())
    monkeypatch.setattr(routes, "generate_account_link", lambda email, **kwargs: {
        "user": {"id": user_id}, "action_link": "https://auth.example/verify?token=secret"
    })
    monkeypatch.setattr(routes, "get_profile", lambda account_id: {"id": account_id, "role": "user", "status": "active", "email": "asha@example.com"})
    response = client.post(f"/api/v1/admin/account-requests/{request_id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["auth_user_id"] == user_id
    assert not any(call[0] == "profile" for call in calls)
    assert ("approved", "asha@example.com", "https://auth.example/verify?token=secret") in calls
    assert rows[request_id]["notification_status"] == "sent"
    assert client.post(f"/api/v1/admin/account-requests/{request_id}/approve").status_code == 409


@pytest.mark.usefixtures("admin_account_override")
def test_approval_explains_existing_account_and_leaves_request_pending(store, monkeypatch):
    rows, _ = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    existing_user_id = str(uuid4())
    monkeypatch.setattr(routes, "get_profile_by_email", lambda email: {
        "id": existing_user_id, "email": "asha@example.com", "role": "user", "status": "active",
    })
    monkeypatch.setattr(routes, "generate_account_link", lambda *args, **kwargs: pytest.fail("Duplicate account invite was attempted"))

    response = client.post(f"/api/v1/admin/account-requests/{request_id}/approve")

    assert response.status_code == 409
    assert "already belongs to an AllSafe account" in response.json()["detail"]
    assert rows[request_id]["status"] == "pending"


@pytest.mark.usefixtures("admin_account_override")
def test_approval_database_lookup_failure_does_not_claim_request(store, monkeypatch):
    rows, _ = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    monkeypatch.setattr(routes, "get_profile_by_email", lambda email: (_ for _ in ()).throw(SupabaseAdminAPIError(503)))

    response = client.post(f"/api/v1/admin/account-requests/{request_id}/approve")

    assert response.status_code == 502
    assert rows[request_id]["status"] == "pending"


@pytest.mark.usefixtures("admin_account_override")
def test_decline_never_creates_user_and_sends_email(store, monkeypatch):
    rows, calls = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    monkeypatch.setattr(routes, "generate_account_link", lambda *args, **kwargs: pytest.fail("Decline created an Auth user"))
    response = client.post(f"/api/v1/admin/account-requests/{request_id}/decline")
    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    assert response.json()["auth_user_id"] is None
    assert ("declined", "asha@example.com") in calls


@pytest.mark.usefixtures("admin_account_override")
def test_failed_decision_email_can_be_retried(store, monkeypatch):
    rows, calls = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    monkeypatch.setattr(routes, "send_declined", lambda *args: (_ for _ in ()).throw(EmailDeliveryError()))
    declined = client.post(f"/api/v1/admin/account-requests/{request_id}/decline")
    assert declined.status_code == 200
    assert declined.json()["notification_status"] == "failed"
    monkeypatch.setattr(routes, "send_declined", lambda email, name: calls.append(("declined", email)))
    retried = client.post(f"/api/v1/admin/account-requests/{request_id}/retry-email")
    assert retried.status_code == 200
    assert retried.json()["notification_status"] == "sent"
    assert calls[-1] == ("declined", "asha@example.com")


@pytest.mark.usefixtures("admin_account_override")
def test_failed_approval_email_keeps_approved_account_and_can_retry(store, monkeypatch):
    rows, calls = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    user_id = str(uuid4())
    link_types = []
    def link(email, *, link_type, redirect_to, approval_attempt=None):
        link_types.append(link_type)
        return {"user": {"id": user_id}, "action_link": "https://auth.example/verify?token=secret"}
    monkeypatch.setattr(routes, "generate_account_link", link)
    monkeypatch.setattr(routes, "get_profile", lambda account_id: {"id": account_id, "role": "user", "status": "active", "email": "asha@example.com"})
    monkeypatch.setattr(routes, "send_approved", lambda *args: (_ for _ in ()).throw(EmailDeliveryError()))
    approved = client.post(f"/api/v1/admin/account-requests/{request_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["notification_status"] == "failed"
    monkeypatch.setattr(routes, "send_approved", lambda email, name, action_link: calls.append(("approved", email, action_link)))
    retried = client.post(f"/api/v1/admin/account-requests/{request_id}/retry-email")
    assert retried.status_code == 200
    assert retried.json()["notification_status"] == "sent"
    assert link_types == ["invite", "recovery"]


@pytest.mark.usefixtures("admin_account_override")
def test_interrupted_approval_resumes_the_same_invited_customer(store, monkeypatch):
    rows, _ = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    path = f"/api/v1/admin/account-requests/{request_id}/approve"
    user_id = str(uuid4())
    profile = {"id": user_id, "email": "asha@example.com", "role": "user", "status": "active"}
    invocations = []
    def link(email, *, link_type, redirect_to, approval_attempt=None):
        invocations.append((link_type, approval_attempt))
        return {"user": profile, "action_link": "https://auth.example/mock"}
    monkeypatch.setattr(routes, "generate_account_link", link)
    monkeypatch.setattr(routes, "get_profile", lambda _: profile)
    update = routes.update_account_request
    def outage(row_id, changes, **kwargs):
        if changes.get("status") == "approved" or changes.get("processing_started_at", True) is None:
            raise SupabaseAdminAPIError(503)
        return update(row_id, changes, **kwargs)
    monkeypatch.setattr(routes, "update_account_request", outage)
    assert client.post(path).status_code == 502
    assert rows[request_id]["status"] == "processing"
    assert client.post(path).status_code == 409

    rows[request_id]["processing_started_at"] = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    monkeypatch.setattr(routes, "update_account_request", update)
    monkeypatch.setattr(routes, "get_profile_by_email", lambda _: profile)
    monkeypatch.setattr(routes, "get_auth_user", lambda _: {
        **profile, "user_metadata": {"allsafe_approval_attempt": invocations[0][1]},
    })
    assert client.post(path).status_code == 200
    assert rows[request_id]["auth_user_id"] == user_id
    assert [entry[0] for entry in invocations] == ["invite", "recovery"]


@pytest.mark.usefixtures("admin_account_override")
def test_pending_decision_acknowledgement_can_be_retried(store, monkeypatch):
    rows, calls = store
    client.post("/api/v1/account-requests", json=application())
    request_id = next(iter(rows))
    path = f"/api/v1/admin/account-requests/{request_id}"
    update = routes.update_account_request
    def lose_ack(row_id, changes, **kwargs):
        if changes.get("notification_status") == "sent":
            raise SupabaseAdminAPIError(503)
        return update(row_id, changes, **kwargs)
    monkeypatch.setattr(routes, "update_account_request", lose_ack)
    assert client.post(path + "/decline").status_code == 502
    assert rows[request_id]["notification_status"] == "pending"
    assert client.post(path + "/retry-email").status_code == 409

    rows[request_id]["notification_started_at"] = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    monkeypatch.setattr(routes, "update_account_request", update)
    assert client.post(path + "/retry-email").status_code == 200
    assert rows[request_id]["notification_status"] == "sent"
    assert [call[0] for call in calls].count("declined") == 2


@pytest.mark.usefixtures("admin_account_override")
def test_queue_pages_and_admin_can_remove_an_application(store):
    rows, _ = store
    for index in range(3):
        assert client.post("/api/v1/account-requests", json=application(email=f"fixture-{index}@example.test")).status_code == 202
    first = client.get("/api/v1/admin/account-requests?limit=2").json()
    second = client.get("/api/v1/admin/account-requests?limit=2&offset=2").json()
    assert first["has_more"] is True
    assert second["has_more"] is False
    assert len(second["requests"]) == 1
    request_id = second["requests"][0]["id"]
    assert client.delete(f"/api/v1/admin/account-requests/{request_id}").status_code == 204
    assert request_id not in rows
