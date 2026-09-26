"""Policy rules for intent transitions, auto-reply, hostility, and off-topic messages."""

import re
from typing import Optional, Tuple

# Action Commitment Phrases
ACTION_INTENT_PATTERNS = [
    r"\b(ok\s+)?(let'?s\s+do\s+it)\b",
    r"\bgo\s+ahead\b",
    r"\bdo\s+it\b",
    r"\bi\s+want\s+to\s+join\b",
    r"\bsend\s+it\b",
    r"\bproceed\b",
    r"\bwhat'?s\s+next\b",
    r"\bconfirm\b",
    r"\byes\s+(please\s+)?(send|draft|schedule|do)\b",
    r"\byes\s+please\b",
    r"\bsure\s+(send|do|let'?s)\b",
]

# Auto-Reply Phrasing
AUTO_REPLY_PATTERNS = [
    r"thank\s+you\s+for\s+contacting",
    r"our\s+team\s+will\s+respond\s+shortly",
    r"we\s+have\s+received\s+your\s+message",
    r"automated\s+response",
    r"business\s+hours",
    r"will\s+get\s+back\s+to\s+you",
    r"thanks\s+for\s+reaching\s+out",
    r"auto-?reply",
]

# Hostile / Opt-out Phrasing
HOSTILE_PATTERNS = [
    r"\bstop\b",
    r"\bdo\s*n'?t\s+message\b",
    r"\bnot\s+interested\b",
    r"\bremove\s+me\b",
    r"\buseless\s+spam\b",
    r"\bstop\s+sending\b",
    r"\bwhy\s+are\s+you\s+bothering\b",
    r"\bunsubscribe\b",
    r"\bspam\b",
]

# Off-topic / Curveball Phrasing
OFF_TOPIC_PATTERNS = [
    r"\bgst\b",
    r"\btax\b",
    r"\bincome\s+tax\b",
    r"\baccounting\b",
    r"\bloan\b",
]

def detect_action_intent(text: str) -> bool:
    """Returns True if message represents explicit merchant commitment/action intent."""
    lower = text.lower()
    for pat in ACTION_INTENT_PATTERNS:
        if re.search(pat, lower):
            return True
    return False

def detect_auto_reply(text: str) -> bool:
    """Returns True if message matches canned WhatsApp business auto-reply."""
    lower = text.lower()
    for pat in AUTO_REPLY_PATTERNS:
        if re.search(pat, lower):
            return True
    return False

def detect_hostile_or_optout(text: str) -> bool:
    """Returns True if message is opt-out or hostile."""
    lower = text.lower()
    for pat in HOSTILE_PATTERNS:
        if re.search(pat, lower):
            return True
    return False

def detect_off_topic(text: str) -> Optional[str]:
    """Returns the off-topic topic if detected, else None."""
    lower = text.lower()
    for pat in OFF_TOPIC_PATTERNS:
        if re.search(pat, lower):
            return "financial/tax administration"
    return None
