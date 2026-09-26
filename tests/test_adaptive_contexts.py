"""Tests verifying adaptive handling of completely novel, unseen contexts and IDs."""

import pytest
from app.storage import Storage
from app.context_store import ContextStore
from app.evidence import extract_evidence
from app.arbitration import arbitrate
from app.composer import MessageComposer

def test_unseen_ids_and_version_progression(tmp_path):
    db_file = str(tmp_path / "test_adaptive.db")
    storage = Storage(db_file)
    context_store = ContextStore(storage)

    # 1. Push novel category with version 1
    ok1, _, _ = context_store.push(
        scope="category",
        context_id="veterinary_clinics",
        version=1,
        payload={
            "slug": "veterinary_clinics",
            "display_name": "Veterinary Clinics",
            "voice": {"tone": "caring_clinical", "vocab_allowed": ["vaccination", "checkup"], "vocab_taboo": ["miracle"]},
            "offer_catalog": [{"id": "vet_001", "title": "Pet Wellness Exam @ ₹499", "status": "active"}]
        }
    )
    assert ok1 is True

    # 2. Push novel merchant with version 1
    ok2, _, _ = context_store.push(
        scope="merchant",
        context_id="m_novel_petcare_kolkata",
        version=1,
        payload={
            "merchant_id": "m_novel_petcare_kolkata",
            "category_slug": "veterinary_clinics",
            "identity": {
                "name": "Kolkata Paws Clinic",
                "owner_first_name": "Debashis",
                "locality": "Salt Lake",
                "city": "Kolkata",
                "languages": ["en", "bn"]
            },
            "offers": [{"id": "vet_001", "title": "Pet Wellness Exam @ ₹499", "status": "active"}],
            "performance": {"views": 1500, "calls": 25, "ctr": 0.04}
        }
    )
    assert ok2 is True

    # 3. Upgrade merchant to version 2 (adaptive version progression)
    ok3, _, _ = context_store.push(
        scope="merchant",
        context_id="m_novel_petcare_kolkata",
        version=2,
        payload={
            "merchant_id": "m_novel_petcare_kolkata",
            "category_slug": "veterinary_clinics",
            "identity": {
                "name": "Kolkata Paws Clinic",
                "owner_first_name": "Debashis",
                "locality": "Salt Lake",
                "city": "Kolkata",
                "languages": ["en", "bn"]
            },
            "offers": [{"id": "vet_002", "title": "Annual Pet Vaccination @ ₹899", "status": "active"}],
            "performance": {"views": 2100, "calls": 40, "ctr": 0.05}
        }
    )
    assert ok3 is True

    # 4. Reject stale version 1
    ok_stale, _, _ = context_store.push(
        scope="merchant",
        context_id="m_novel_petcare_kolkata",
        version=1,
        payload={}
    )
    assert ok_stale is False

    # 5. Process completely unseen trigger kind
    novel_trigger = {
        "id": "trg_novel_annual_deworming_campaign",
        "scope": "merchant",
        "kind": "deworming_seasonal_drive",
        "merchant_id": "m_novel_petcare_kolkata",
        "customer_id": None,
        "payload": {
            "campaign_topic": "deworming_drive",
            "target_period": "pre_monsoon"
        },
        "urgency": 2,
        "suppression_key": "vet:deworming:2026",
        "expires_at": "2026-07-01T00:00:00Z"
    }

    cat = context_store.get("category", "veterinary_clinics")
    merch = context_store.get("merchant", "m_novel_petcare_kolkata")
    evidence = extract_evidence(cat, merch, novel_trigger, None)

    assert evidence.merchant_name == "Kolkata Paws Clinic"
    assert evidence.owner_name == "Debashis"
    assert evidence.locality == "Salt Lake"
    assert len(evidence.active_offers) == 1
    assert evidence.active_offers[0]["title"] == "Annual Pet Vaccination @ ₹899"

    # 6. Arbitrate and compose
    decision = arbitrate(evidence, storage, now_iso="2026-05-01T10:00:00Z")
    assert decision.action_type in ("ACT", "REFRAME")

    composer = MessageComposer()
    body, params, cta = composer.compose_proactive(evidence, decision)
    assert "Debashis" in body
    assert "Kolkata Paws Clinic" in body
    assert "Salt Lake" in body
    assert "Annual Pet Vaccination @ ₹899" in body
    assert cta in ("binary_yes_no", "multi_choice_slot", "binary_confirm_cancel")

def test_unseen_customer_consent_and_scoping(tmp_path):
    db_file = str(tmp_path / "test_cust.db")
    storage = Storage(db_file)
    context_store = ContextStore(storage)

    # Push customer without consent
    context_store.push(
        scope="customer",
        context_id="c_unseen_999",
        version=1,
        payload={
            "customer_id": "c_unseen_999",
            "identity": {"name": "Rohan Gupta", "preferred_language": "en"},
            "consent": {"marketing": False, "channels": []}
        }
    )
    cust = context_store.get("customer", "c_unseen_999")
    trigger = {
        "id": "trg_recall_unseen",
        "scope": "customer",
        "kind": "recall_due",
        "merchant_id": "m_test",
        "customer_id": "c_unseen_999",
        "payload": {},
        "expires_at": "2026-06-01T00:00:00Z"
    }
    evidence = extract_evidence(None, None, trigger, cust)
    decision = arbitrate(evidence, storage)
    # Must SUPPRESS due to lack of consent
    assert decision.action_type == "SUPPRESS"
    assert "consent" in decision.strategy.lower() or "consent" in decision.rationale.lower()
