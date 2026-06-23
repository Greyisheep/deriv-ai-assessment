"""Thin coverage of the FastAPI layer (forced to mock mode, no key needed)."""

import os

os.environ["LLM_MODE"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_extract_returns_results_and_summary():
    r = client.post(
        "/extract",
        json={"quotes": [{
            "id": "API-T1",
            "text": "Supplier: Acme. Currency USD. 10 units of Bolt at $2 each. SKU B-1. Lead time 1 week. Shipping included.",
        }]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["currency"] == "USD"
    assert body["results"][0]["items"][0]["lead_time_days"] == 7
    assert body["review_summary"][0]["needs_review"] is False


def test_run_bad_path_returns_400():
    assert client.post("/run", json={"input_path": "does-not-exist.json"}).status_code == 400
