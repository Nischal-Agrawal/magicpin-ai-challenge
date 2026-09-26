"""Configuration management for Vera Bot."""

import os
from datetime import datetime
from pydantic import BaseModel, Field

class Settings(BaseModel):
    port: int = Field(default_factory=lambda: int(os.environ.get("PORT", "8080")))
    host: str = Field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    bot_url: str = Field(default_factory=lambda: os.environ.get("BOT_URL", "http://localhost:8080"))
    db_path: str = Field(default_factory=lambda: os.environ.get("DATABASE_PATH", "vera.db"))
    
    # Metadata
    team_name: str = Field(default_factory=lambda: os.environ.get("TEAM_NAME", "Team Antigravity"))
    team_members: list[str] = Field(
        default_factory=lambda: [
            m.strip() for m in os.environ.get("TEAM_MEMBERS", "Lead Engineer, AI Architect").split(",")
        ]
    )
    model_name: str = Field(default_factory=lambda: os.environ.get("MODEL_NAME", "claude-3-haiku"))
    approach_desc: str = Field(
        default_factory=lambda: os.environ.get(
            "APPROACH_DESC",
            "Hybrid EWSA Architecture: Deterministic Grounding Validator + Dynamic Persuasive LLM Enhancer"
        )
    )
    contact_email: str = Field(default_factory=lambda: os.environ.get("CONTACT_EMAIL", "team@example.com"))
    version: str = Field(default_factory=lambda: os.environ.get("BOT_VERSION", "1.0.0"))
    submitted_at: str = Field(default_factory=lambda: os.environ.get("SUBMITTED_AT", "2026-04-26T08:00:00Z"))

    # LLM Settings
    openrouter_api_key: str = Field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    openai_api_key: str = Field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    llm_api_key: str = Field(
        default_factory=lambda: os.environ.get("LLM_API_KEY") 
        or os.environ.get("OPENROUTER_API_KEY") 
        or os.environ.get("OPENAI_API_KEY") 
        or ""
    )
    llm_base_url: str = Field(
        default_factory=lambda: os.environ.get(
            "LLM_BASE_URL",
            "https://openrouter.ai/api/v1" if (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_BASE_URL")) else "https://api.openai.com/v1"
        )
    )
    llm_model: str = Field(
        default_factory=lambda: os.environ.get(
            "LLM_MODEL",
            "openai/gpt-4o-mini" if os.environ.get("OPENROUTER_API_KEY") else "gpt-4o-mini"
        )
    )
    llm_timeout_sec: float = Field(default_factory=lambda: float(os.environ.get("LLM_TIMEOUT_SEC", "15.0")))

settings = Settings()
