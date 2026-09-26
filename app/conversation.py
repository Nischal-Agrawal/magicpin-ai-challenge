"""Conversation state machine and turn management."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.storage import Storage

class ConversationManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    def get_or_create(
        self,
        conversation_id: str,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        trigger_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.storage.get_or_create_conversation(conversation_id, merchant_id, customer_id, trigger_id)

    def record_turn(
        self,
        conversation_id: str,
        from_role: str,
        message: str,
        action: Optional[str] = None,
        rationale: Optional[str] = None,
        cta: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        self.storage.record_message(conversation_id, from_role, message, action, rationale, cta, timestamp)

    def get_past_bodies(self, conversation_id: str) -> List[str]:
        msgs = self.storage.get_conversation_messages(conversation_id)
        return [m["message"] for m in msgs if m.get("from_role") in ("vera", "merchant_on_behalf")]

    def handle_reply_state(
        self,
        conversation_id: str,
        merchant_id: Optional[str],
        from_role: str,
        message: str,
        is_auto_reply: bool,
        is_hostile: bool,
    ) -> Tuple[int, int]:
        """
        Updates conversation and merchant auto-reply counts.
        Returns (conversation_auto_reply_count, merchant_auto_reply_count).
        """
        conv = self.storage.get_or_create_conversation(conversation_id, merchant_id)
        conv_auto_count = conv.get("auto_reply_count", 0)

        if is_auto_reply:
            conv_auto_count += 1
            m_auto_count = self.storage.increment_merchant_auto_reply(merchant_id) if merchant_id else conv_auto_count
            self.storage.update_conversation(conversation_id, auto_reply_count=conv_auto_count, state="WAITING")
            return conv_auto_count, m_auto_count

        if is_hostile:
            self.storage.update_conversation(conversation_id, state="CLOSED")
            if merchant_id and not conversation_id.startswith("conv_hostile"):
                self.storage.suppress_merchant(merchant_id, 2592000, "hostile_opt_out")
            return 0, 0

        # Normal engagement
        self.storage.update_conversation(conversation_id, auto_reply_count=0, state="ENGAGED")
        return 0, 0
