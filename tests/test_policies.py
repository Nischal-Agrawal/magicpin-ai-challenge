"""Tests for conversation policies, auto-reply, intent transition, and hostility."""

import pytest
from fastapi.testclient import TestClient
from app.api import create_app

@pytest.fixture
def client(tmp_path):
    db_file = str(tmp_path / "test.db")
    app = create_app(db_path=db_file)
    return TestClient(app)

def test_auto_reply_hell_progression(client):
    conv_id = "conv_test_autoreply_progression"
    mid = "m_test_auto"
    canned = "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."

    ended = False
    for turn in range(1, 5):
        resp = client.post(
            "/v1/reply",
            json={
                "conversation_id": conv_id,
                "merchant_id": mid,
                "from_role": "merchant",
                "message": canned,
                "received_at": "2026-04-26T10:00:00Z",
                "turn_number": turn,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        action = data.get("action")
        if action == "end":
            ended = True
            break
        elif action == "wait":
            assert data.get("wait_seconds") in (14400, 86400)

    assert ended is True, "Bot should end after repeated canned auto-replies"

def test_intent_transition_mode_switch(client):
    conv_id = "conv_test_intent_switch"
    mid = "m_test_intent"
    commitment = "Ok let's do it. What's next?"

    resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": mid,
            "from_role": "merchant",
            "message": commitment,
            "received_at": "2026-04-26T10:00:00Z",
            "turn_number": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    body = data.get("body", "").lower()

    qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
    actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]

    assert any(w in body for w in actioning), f"Expected actioning words in response: {body}"
    assert not any(w in body for w in qualifying), f"Should NOT ask qualifying questions after intent transition: {body}"

def test_hostile_opt_out_exit(client):
    conv_id = "conv_test_hostile"
    mid = "m_test_hostile"
    hostile = "Stop messaging me. This is useless spam."

    resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": mid,
            "from_role": "merchant",
            "message": hostile,
            "received_at": "2026-04-26T10:00:00Z",
            "turn_number": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "end", "Should immediately end conversation on hostility/opt-out"
    assert "opt" in data.get("rationale", "").lower() or "hostil" in data.get("rationale", "").lower()

def test_off_topic_curveball(client):
    conv_id = "conv_test_offtopic"
    mid = "m_test_offtopic"
    off_topic = "Btw can you also help me with my GST filing this month?"

    resp = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": mid,
            "from_role": "merchant",
            "message": off_topic,
            "received_at": "2026-04-26T10:00:00Z",
            "turn_number": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    body = data.get("body", "")
    assert "ca" in body.lower() or "outside" in body.lower() or "tax" in body.lower()
