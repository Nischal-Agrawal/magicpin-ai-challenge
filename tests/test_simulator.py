"""Integration tests mirroring the official judge_simulator scenarios."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.api import create_app

@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test.db")
    app = create_app(db_path=db_file)
    return TestClient(app)

def test_simulator_warmup_flow(client):
    # 1. Healthz check
    h_resp = client.get("/v1/healthz")
    assert h_resp.status_code == 200
    assert h_resp.json()["status"] == "ok"

    # 2. Metadata check
    m_resp = client.get("/v1/metadata")
    assert m_resp.status_code == 200

    # 3. Load dataset categories
    cat_path = Path(__file__).resolve().parent.parent / "dataset" / "categories"
    for cat_file in cat_path.glob("*.json"):
        with open(cat_file, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
            resp = client.post(
                "/v1/context",
                json={
                    "scope": "category",
                    "context_id": cat_data["slug"],
                    "version": 1,
                    "payload": cat_data,
                },
            )
            assert resp.status_code in (200, 409)

    # 4. Push 1 merchant, 1 customer, 1 trigger
    merch_file = Path(__file__).resolve().parent.parent / "dataset" / "merchants_seed.json"
    with open(merch_file, "r", encoding="utf-8") as f:
        merchants = json.load(f)["merchants"]
        m0 = merchants[0]
        client.post(
            "/v1/context",
            json={
                "scope": "merchant",
                "context_id": m0["merchant_id"],
                "version": 1,
                "payload": m0,
            },
        )

    trg_file = Path(__file__).resolve().parent.parent / "dataset" / "triggers_seed.json"
    with open(trg_file, "r", encoding="utf-8") as f:
        triggers = json.load(f)["triggers"]
        t0 = triggers[0]
        client.post(
            "/v1/context",
            json={
                "scope": "trigger",
                "context_id": t0["id"],
                "version": 1,
                "payload": t0,
            },
        )

    # 5. Call Tick
    tick_resp = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:35:00Z", "available_triggers": [t0["id"]]},
    )
    assert tick_resp.status_code == 200
    data = tick_resp.json()
    assert "actions" in data
    assert len(data["actions"]) <= 20

def test_simulator_intent_scenario(client):
    mid = "m_test_doc"
    conv_id = "conv_intent_sim"
    resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": mid,
            "customer_id": None,
            "from_role": "merchant",
            "message": "Ok lets do it. Whats next?",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    action = data.get("action")
    body = data.get("body", "").lower()
    assert action == "send"
    actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
    qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
    assert any(w in body for w in actioning)
    assert not any(w in body for w in qualifying)

def test_simulator_hostile_scenario(client):
    mid = "m_test_doc"
    conv_id = "conv_hostile_sim"
    resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": mid,
            "customer_id": None,
            "from_role": "merchant",
            "message": "Stop messaging me. This is useless spam.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("action") == "end"
