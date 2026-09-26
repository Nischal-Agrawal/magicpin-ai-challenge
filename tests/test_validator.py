"""Tests for deterministic GroundingValidator."""

from app.evidence import EvidenceCard
from app.validator import GroundingValidator

def test_url_removal():
    evidence = EvidenceCard(category_slug="dentists", merchant_id="m_001", trigger_id="trg_1")
    body = "Check our website at https://example.com/promo or www.dentist.in for details!"
    valid, cleaned, repairs = GroundingValidator.validate_and_repair(body, evidence)
    assert valid is True
    assert "https://" not in cleaned
    assert "www." not in cleaned
    assert len(repairs) > 0

def test_taboo_word_replacement():
    evidence = EvidenceCard(
        category_slug="dentists",
        merchant_id="m_001",
        trigger_id="trg_1",
        vocab_taboo=["guaranteed", "cure"],
    )
    body = "We offer a guaranteed cure for toothache."
    valid, cleaned, repairs = GroundingValidator.validate_and_repair(body, evidence)
    assert valid is True
    assert "guaranteed" not in cleaned.lower()
    assert "cure" not in cleaned.lower()
    assert "effective" in cleaned.lower()
    assert len(repairs) >= 2

def test_anti_repetition():
    evidence = EvidenceCard(category_slug="salons", merchant_id="m_002", trigger_id="trg_2")
    body = "Hi Karim, want to schedule your post today?"
    past = ["Hi Karim, want to schedule your post today?"]
    valid, cleaned, repairs = GroundingValidator.validate_and_repair(body, evidence, past_bodies=past)
    assert valid is True
    assert cleaned != past[0]
    assert len(repairs) > 0
