from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "allsafe-ai-trading-api"
    assert body["version"]


def test_health_time_is_timezone_aware_iso():
    body = client.get("/health").json()
    parsed = datetime.fromisoformat(body["time_utc"])
    assert parsed.tzinfo is not None


def test_health_contains_no_market_data():
    body = client.get("/health").json()
    assert not any(key in body for key in ("price", "quote", "signal", "ltp"))
