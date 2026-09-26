"""Pydantic models for Vera API endpoints."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# --- Health & Metadata ---

class HealthzResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: Dict[str, int]

class MetadataResponse(BaseModel):
    team_name: str
    team_members: List[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str

# --- Context Ingestion ---

class ContextPushRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None

class ContextPushSuccessResponse(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str

class ContextPushConflictResponse(BaseModel):
    accepted: bool = False
    reason: str = "stale_version"
    current_version: int

class ContextPushErrorResponse(BaseModel):
    accepted: bool = False
    reason: str
    details: Optional[str] = None

# --- Tick Endpoint ---

class TickRequest(BaseModel):
    now: str
    available_triggers: List[str] = Field(default_factory=list)

class ActionItem(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: List[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str

class TickResponse(BaseModel):
    actions: List[ActionItem] = Field(default_factory=list)

# --- Reply Endpoint ---

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

class ReplyResponse(BaseModel):
    action: Literal["send", "wait", "end"]
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str

# --- Teardown Endpoint ---

class TeardownResponse(BaseModel):
    status: str = "wiped"
    contexts_cleared: int
