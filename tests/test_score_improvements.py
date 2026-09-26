"""Tests for EWSA arbitration and grounding improvements on tricky trigger families."""

import pytest
from app.evidence import extract_evidence
from app.arbitration import arbitrate
from app.composer import MessageComposer
from app.storage import Storage

def test_cde_webinar_digest_item_matching(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    composer = MessageComposer()

    category = {
        "slug": "dentists",
        "voice": {"tone": "clinical_peer"},
        "digest": [
            {"id": "d_fluoride", "title": "Fluoride Trial", "source": "JIDA"},
            {"id": "d_ida_webinar", "title": "Digital Impressions 2026", "source": "IDA Delhi", "credits": 2, "summary": "CAD/CAM workflow ROI for solo practices.", "actionable": "Free for members"}
        ]
    }
    merchant = {
        "merchant_id": "m_test_dentist",
        "identity": {"name": "Test Dental", "owner_first_name": "Meera", "locality": "Defence Colony"},
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹499"}]
    }
    trigger = {
        "id": "trg_cde",
        "kind": "cde_opportunity",
        "payload": {"digest_item_id": "d_ida_webinar", "credits": 2, "fee": "free_for_members"}
    }

    card = extract_evidence(category, merchant, trigger)
    assert card.matched_digest_item is not None
    assert card.matched_digest_item["id"] == "d_ida_webinar"

    decision = arbitrate(card, storage)
    assert decision.action_type == "ACT"
    assert decision.strategy == "cde_opportunity"

    body, _, cta = composer.compose_proactive(card, decision)
    assert "Digital Impressions 2026" in body
    assert "Dr. Meera" in body
    assert "IDA Delhi" in body
    assert "CAD/CAM" in body
    assert cta == "binary_yes_no"


def test_festival_restraint_suppression_when_distant(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))

    category = {"slug": "salons"}
    merchant = {
        "merchant_id": "m_test_salon",
        "identity": {"name": "Test Salon", "owner_first_name": "Priya"}
    }
    trigger = {
        "id": "trg_diwali_distant",
        "kind": "festival_upcoming",
        "payload": {"festival": "Diwali", "days_until": 188}
    }

    card = extract_evidence(category, merchant, trigger)
    decision = arbitrate(card, storage)
    assert decision.action_type == "WAIT"
    assert "188 days away" in decision.rationale


def test_seasonal_gym_dip_reassurance_vs_unplanned(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    composer = MessageComposer()

    category = {"slug": "gyms"}
    merchant = {
        "merchant_id": "m_gym",
        "identity": {"name": "Powerhouse Gym", "owner_first_name": "Rajesh", "locality": "Koramangala"},
        "offers": [{"id": "g1", "title": "Personal Training 3 Sessions @ ₹999"}]
    }
    trigger = {
        "id": "trg_gym_dip",
        "kind": "seasonal_perf_dip",
        "payload": {"metric": "views", "delta_pct": -0.30, "window": "7d", "is_expected_seasonal": True}
    }

    card = extract_evidence(category, merchant, trigger)
    decision = arbitrate(card, storage)
    assert decision.action_type == "REFRAME"
    assert decision.strategy == "seasonal_perf_dip_reassurance"

    body, _, cta = composer.compose_proactive(card, decision)
    assert "expected post-resolution seasonal cycle" in body
    assert "not a drop in your reputation" in body
    assert "Personal Training 3 Sessions @ ₹999" in body


def test_customer_scoped_recall_with_language_and_slots(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    composer = MessageComposer()

    category = {"slug": "dentists"}
    merchant = {
        "merchant_id": "m_dentist",
        "identity": {"name": "Dr. Meera Dental", "owner_first_name": "Meera", "locality": "Defence Colony"},
        "offers": [{"id": "d1", "title": "Dental Cleaning @ ₹499"}]
    }
    customer = {
        "customer_id": "c_priya",
        "identity": {"name": "Priya", "language_pref": "hi-en mix"},
        "relationship": {"last_visit": "2026-05-12"},
        "consent": {"opted_in_at": "2025-11-04", "scope": ["recall_reminders"]}
    }
    trigger = {
        "id": "trg_recall",
        "kind": "recall_due",
        "customer_id": "c_priya",
        "payload": {
            "service_due": "6_month_cleaning",
            "last_service_date": "2026-05-12",
            "available_slots": [{"label": "Wed 5 Nov, 6pm"}, {"label": "Thu 6 Nov, 5pm"}]
        }
    }

    card = extract_evidence(category, merchant, trigger, customer)
    decision = arbitrate(card, storage)
    assert decision.action_type == "ACT"
    assert decision.strategy == "customer_recall_slots"

    body, _, cta = composer.compose_proactive(card, decision)
    assert "Priya" in body
    assert "Namaste" in body
    assert "Wed 5 Nov, 6pm" in body
    assert "Thu 6 Nov, 5pm" in body
    assert "Dental Cleaning @ ₹499" in body
    assert cta == "multi_choice_slot"
