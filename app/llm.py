"""LLM Client provider with timeout handling and graceful fallback."""

import json
import logging
from typing import Any, Dict, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_sec

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_json(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """Invokes LLM with bounded timeout and expects JSON response."""
        if not self.is_available():
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://magicpin.com"
            headers["X-Title"] = "Vera Merchant AI"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                else:
                    logger.warning(f"LLM call failed with status {resp.status_code}: {resp.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"LLM call exception: {e}")
            return None
