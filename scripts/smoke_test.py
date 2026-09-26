"""Smoke test for Vera Bot HTTP endpoints."""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api import create_app

def run_smoke_test():
    print("Running smoke tests on Vera application...")
    app = create_app(db_path="smoke_test.db")
    client = TestClient(app)
    # Start with a clean slate
    client.post("/v1/teardown")

    # 1. Healthz
    r = client.get("/v1/healthz")
    assert r.status_code == 200, f"Healthz failed: {r.text}"
    print("[PASS] GET /v1/healthz")

    # 2. Metadata
    r = client.get("/v1/metadata")
    assert r.status_code == 200, f"Metadata failed: {r.text}"
    print("[PASS] GET /v1/metadata")

    # 3. Context Push
    r = client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists", "voice": {"tone": "peer_clinical"}},
        },
    )
    assert r.status_code == 200, f"Context push failed: {r.text}"
    print("[PASS] POST /v1/context (new version)")

    # 4. Context Conflict (stale)
    r = client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists"},
        },
    )
    assert r.status_code == 409, f"Expected 409 for duplicate version: {r.text}"
    print("[PASS] POST /v1/context (stale version 409 conflict)")

    # 5. Tick
    r = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:00:00Z", "available_triggers": []},
    )
    assert r.status_code == 200, f"Tick failed: {r.text}"
    assert "actions" in r.json()
    print("[PASS] POST /v1/tick (empty trigger list)")

    # 6. Reply - Hostile
    r = client.post(
        "/v1/reply",
        json={
            "conversation_id": "smoke_conv_1",
            "merchant_id": "m_smoke",
            "from_role": "merchant",
            "message": "Stop messaging me. Not interested.",
            "received_at": "2026-04-26T10:05:00Z",
            "turn_number": 2,
        },
    )
    assert r.status_code == 200, f"Reply failed: {r.text}"
    assert r.json()["action"] == "end"
    print("[PASS] POST /v1/reply (hostile opt-out)")

    # 7. Reply - Intent Switch
    r = client.post(
        "/v1/reply",
        json={
            "conversation_id": "smoke_conv_2",
            "merchant_id": "m_smoke",
            "from_role": "merchant",
            "message": "Ok let's do it. What's next?",
            "received_at": "2026-04-26T10:06:00Z",
            "turn_number": 2,
        },
    )
    assert r.status_code == 200, f"Reply failed: {r.text}"
    assert r.json()["action"] == "send"
    print("[PASS] POST /v1/reply (action intent switch)")

    # 8. Teardown
    r = client.post("/v1/teardown")
    assert r.status_code == 200, f"Teardown failed: {r.text}"
    print("[PASS] POST /v1/teardown")

    print("\nALL SMOKE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_smoke_test()
