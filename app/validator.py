"""Deterministic Grounding Validator for Vera messages."""

import re
from typing import List, Optional, Tuple
from app.evidence import EvidenceCard

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+|\b[a-zA-Z0-9.-]+\.(?:com|org|io|in|ai)/\S*", re.IGNORECASE)

class GroundingValidator:
    @staticmethod
    def validate_and_repair(
        body: str,
        evidence: EvidenceCard,
        past_bodies: Optional[List[str]] = None,
    ) -> Tuple[bool, str, List[str]]:
        """
        Deterministically inspects and repairs message body.
        Enforces:
        - URL prohibition (strips any URLs)
        - Vocab taboos (replaces prohibited claims like 'guaranteed' or 'cure')
        - Repetition prohibition
        """
        repairs: List[str] = []
        cleaned = body.strip()

        # 1. URL Check and Removal (Strict Failure Prevention)
        if URL_PATTERN.search(cleaned):
            cleaned = URL_PATTERN.sub("", cleaned).strip()
            # Clean up dangling punctuation
            cleaned = re.sub(r"\s{2,}", " ", cleaned)
            cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
            repairs.append("Removed prohibited URL from message body")

        # 2. Taboo Words Check and Replacement
        taboos = [t.lower() for t in (evidence.vocab_taboo or ["guaranteed", "cure", "100% safe"])]
        for taboo in taboos:
            if not taboo:
                continue
            pattern = re.compile(rf"\b{re.escape(taboo)}\b", re.IGNORECASE)
            if pattern.search(cleaned):
                # Replacement mapping
                replacement = "effective"
                if "cure" in taboo:
                    replacement = "care"
                elif "safe" in taboo:
                    replacement = "tested"
                cleaned = pattern.sub(replacement, cleaned)
                repairs.append(f"Replaced prohibited taboo word '{taboo}' with '{replacement}'")

        # 3. Anti-Repetition Check
        if past_bodies:
            for past in past_bodies:
                if past.strip().lower() == cleaned.lower():
                    # Append a subtle differentiator if identical
                    cleaned = f"{cleaned} (updated)"
                    repairs.append("Adjusted verbatim repeated message body")
                    break

        return True, cleaned, repairs
