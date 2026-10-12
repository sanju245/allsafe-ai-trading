"""HTTP-level tests for the market-data endpoints and the preserved /health endpoint.

These need FastAPI and httpx (see requirements-dev.txt). If either is not installed the
whole module is SKIPPED, not passed.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
PREFIX = "/api/v1/market-data"


def body(**overrides):
    payload = {
        "instrument": "BANKNIFTY",
        "timeframe": "5m",
        "source": {"name": "SAMPLE-FIXTURE-NOT-MARKET-DATA", "kind": "sample"},
        "candles": [
            {"timestamp": "2026-01-05T09:15:00+05:30", "open": 1000, "high": 1002, "low": 998, "close": 1001, "volume": 5},
            {"timestamp": "2026-01-05T09:20:00+05:30", "open": 1001, "high": 1003, "low": 999, "close": 1002, "volume": 6},
        ],
        "as_of": "2026-02-02T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_health_endpoint_is_preserved():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "allsafe-ai-trading-api"
    assert set(data) == {"status", "service", "version", "environment", "time_utc"}


def test_instruments_endpoint():
    response = client.get(f"{PREFIX}/instruments")
    assert response.status_code == 200
    data = response.json()
    assert {i["id"] for i in data} == {"NIFTY50", "BANKNIFTY"}
    assert {i["name"] for i in data} == {"NIFTY 50", "BANK NIFTY"}


def test_timeframes_endpoint():
    response = client.get(f"{PREFIX}/timeframes")
    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == ["1m", "3m", "5m", "15m", "1h", "1d"]


def test_validate_good_series():
    response = client.post(f"{PREFIX}/validate", json=body())
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["error_count"] == 0


def test_validate_reports_bad_data_with_200_not_an_error_status():
    payload = body()
    payload["candles"][0]["high"] = 990
    response = client.post(f"{PREFIX}/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert "INVALID_OHLC" in data["issue_counts"]


def test_validate_flags_sample_data_and_never_calls_it_live():
    data = client.post(f"{PREFIX}/validate", json=body()).json()
    assert data["source"]["kind"] == "sample"
    assert "SAMPLE_DATA" in data["issue_counts"]


@pytest.mark.parametrize(
    "overrides",
    [{"timeframe": "2m"}, {"instrument": "SENSEX"}, {"as_of": "2026-02-02T00:00:00"}, {"nope": 1}],
    ids=["timeframe", "instrument", "naive-as-of", "extra-field"],
)
def test_malformed_validate_requests_get_422(overrides):
    assert client.post(f"{PREFIX}/validate", json=body(**overrides)).status_code == 422


def test_validate_requires_post():
    assert client.get(f"{PREFIX}/validate").status_code == 405


def test_openapi_lists_the_new_endpoints():
    paths = client.get("/openapi.json").json()["paths"]
    for path in (f"{PREFIX}/instruments", f"{PREFIX}/timeframes", f"{PREFIX}/validate", "/health"):
        assert path in paths
