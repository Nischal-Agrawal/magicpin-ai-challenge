"""Unit and integration tests for Vera HTTP API."""

import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.storage import Storage

@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test.db")
    app = create_app(db_path=db_file)
    return TestClient(app)

def test_healthz(client):
    resp = client.get("/v1/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "contexts_loaded" in data
    assert isinstance(data["contexts_loaded"], dict)

def test_metadata(client):
    resp = client.get("/v1/metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert "team_name" in data
    assert "team_members" in data
    assert "model" in data
    assert "approach" in data
    assert "contact_email" in data
    assert "version" in data
    assert "submitted_at" in data

def test_context_push_lifecycle(client):
    # Push version 1
    resp = client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists", "voice": {"tone": "peer_clinical"}},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True
    assert "ack_id" in resp.json()

    # Re-push version 1 (stale / duplicate -> 409)
    resp2 = client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": {"slug": "dentists"},
        },
    )
    assert resp2.status_code == 409
    assert resp2.json()["accepted"] is False
    assert resp2.json()["reason"] == "stale_version"
    assert resp2.json()["current_version"] == 1

    # Push version 2 (upgrade -> 200)
    resp3 = client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 2,
            "payload": {"slug": "dentists", "updated": True},
        },
    )
    assert resp3.status_code == 200
    assert resp3.json()["accepted"] is True

    # Invalid scope -> 400
    resp4 = client.post(
        "/v1/context",
        json={
            "scope": "invalid_scope",
            "context_id": "test",
            "version": 1,
            "payload": {},
        },
    )
    assert resp4.status_code == 400
    assert resp4.json()["accepted"] is False
    assert resp4.json()["reason"] == "invalid_scope"

def test_tick_and_reply_flow(client):
    # Setup category, merchant, trigger
    client.post(
        "/v1/context",
        json={
            "scope": "category",
            "context_id": "dentists",
            "version": 10,
            "payload": {
                "slug": "dentists",
                "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed"]},
                "digest": [{"title": "Fluoride 3-mo recall", "source": "JIDA"}],
            },
        },
    )
    client.post(
        "/v1/context",
        json={
            "scope": "merchant",
            "context_id": "m_test_dentist",
            "version": 10,
            "payload": {
                "merchant_id": "m_test_dentist",
                "category_slug": "dentists",
                "identity": {"name": "Dr Test Clinic", "owner_first_name": "TestDoc", "city": "Delhi"},
                "performance": {"views": 1000, "ctr": 0.025},
                "offers": [{"id": "off_1", "title": "Dental Cleaning @ ₹299", "status": "active"}],
            },
        },
    )
    client.post(
        "/v1/context",
        json={
            "scope": "trigger",
            "context_id": "trg_test_1",
            "version": 10,
            "payload": {
                "id": "trg_test_1",
                "kind": "research_digest",
                "merchant_id": "m_test_dentist",
                "urgency": 3,
                "suppression_key": "test_digest_supp_key_1",
            },
        },
    )

    # Tick with trigger
    tick_resp = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:30:00Z", "available_triggers": ["trg_test_1"]},
    )
    assert tick_resp.status_code == 200
    actions = tick_resp.json()["actions"]
    assert len(actions) == 1
    action = actions[0]
    assert action["merchant_id"] == "m_test_dentist"
    assert action["send_as"] == "vera"
    assert "TestDoc" in action["body"]
    assert "JIDA" in action["body"]
    conv_id = action["conversation_id"]

    # Reply engaged
    reply_resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_test_dentist",
            "from_role": "merchant",
            "message": "Yes, please send me the abstract and draft the post.",
            "received_at": "2026-04-26T10:35:00Z",
            "turn_number": 2,
        },
    )
    assert reply_resp.status_code == 200
    r_data = reply_resp.json()
    assert r_data["action"] == "send"
    assert len(r_data["body"]) > 0
    assert "rationale" in r_data

def test_teardown(client):
    resp = client.post("/v1/teardown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "wiped"
    # verify healthz shows 0 contexts
    h_resp = client.get("/v1/healthz")
    counts = h_resp.json()["contexts_loaded"]
    assert all(v == 0 for v in counts.values())
