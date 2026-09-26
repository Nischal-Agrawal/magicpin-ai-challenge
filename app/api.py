"""FastAPI Application exposing the Vera Bot API Contract."""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.arbitration import arbitrate
from app.composer import MessageComposer
from app.config import settings
from app.context_store import ContextStore
from app.conversation import ConversationManager
from app.evidence import extract_evidence
from app.models import (
    ActionItem,
    ContextPushRequest,
    HealthzResponse,
    MetadataResponse,
    ReplyRequest,
    ReplyResponse,
    TeardownResponse,
    TickRequest,
    TickResponse,
)
from app.policies import detect_auto_reply, detect_hostile_or_optout
from app.storage import Storage

START_TIME = time.time()

def create_app(db_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="Vera Merchant AI", version=settings.version)
    target_db = db_path or settings.db_path
    storage = Storage(target_db)
    context_store = ContextStore(storage)
    composer = MessageComposer()
    conversation_manager = ConversationManager(storage)

    @app.get("/v1/healthz", response_model=HealthzResponse)
    async def healthz():
        uptime = int(time.time() - START_TIME)
        counts = context_store.counts()
        return HealthzResponse(status="ok", uptime_seconds=uptime, contexts_loaded=counts)

    @app.get("/v1/metadata", response_model=MetadataResponse)
    async def metadata():
        return MetadataResponse(
            team_name=settings.team_name,
            team_members=settings.team_members,
            model=settings.model_name,
            approach=settings.approach_desc,
            contact_email=settings.contact_email,
            version=settings.version,
            submitted_at=settings.submitted_at,
        )

    @app.post("/v1/context")
    async def push_context(body: ContextPushRequest):
        if body.scope not in ("category", "merchant", "customer", "trigger"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"accepted": False, "reason": "invalid_scope", "details": f"Unknown scope '{body.scope}'"},
            )

        accepted, reason_or_ack, cur_ver = context_store.push(
            scope=body.scope,
            context_id=body.context_id,
            version=body.version,
            payload=body.payload,
            delivered_at=body.delivered_at,
        )

        if not accepted:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"accepted": False, "reason": "stale_version", "current_version": cur_ver},
            )

        return {
            "accepted": True,
            "ack_id": reason_or_ack,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/v1/tick", response_model=TickResponse)
    async def tick(body: TickRequest):
        actions: List[ActionItem] = []
        # Cap actions at 20 per official constraint
        triggers_to_process = body.available_triggers[:20]

        for trg_id in triggers_to_process:
            trg = context_store.get("trigger", trg_id)
            if not trg:
                continue

            merch_id = trg.get("merchant_id")
            if not merch_id:
                continue

            merchant = context_store.get("merchant", merch_id)
            if not merchant:
                continue

            cat_slug = merchant.get("category_slug") or trg.get("payload", {}).get("category")
            category = context_store.get("category", cat_slug) if cat_slug else None

            cust_id = trg.get("customer_id")
            customer = context_store.get("customer", cust_id) if cust_id else None

            # Build EvidenceCard
            evidence = extract_evidence(category, merchant, trg, customer)

            # Arbitration
            decision = arbitrate(evidence, storage, now_iso=body.now)
            if decision.action_type in ("SUPPRESS", "WAIT"):
                continue

            # Generate fresh, unique conversation_id for tick initiation
            conv_id = f"conv_{merch_id}_{trg_id}_{uuid.uuid4().hex[:6]}"
            conversation_manager.get_or_create(conv_id, merch_id, cust_id, trg_id)

            body_text, template_params, cta = composer.compose_proactive(evidence, decision)
            send_as = "merchant_on_behalf" if (cust_id or trg.get("scope") == "customer") else "vera"

            # Record outbound message
            conversation_manager.record_turn(
                conversation_id=conv_id,
                from_role=send_as,
                message=body_text,
                action="send",
                rationale=decision.rationale,
                cta=cta,
                timestamp=body.now,
            )

            # Mark suppression key active
            supp_key = trg.get("suppression_key") or f"{evidence.trigger_kind}:{merch_id}"
            storage.add_suppression(supp_key, trg.get("scope", "merchant"), merch_id, trg.get("expires_at"))

            actions.append(
                ActionItem(
                    conversation_id=conv_id,
                    merchant_id=merch_id,
                    customer_id=cust_id,
                    send_as=send_as,
                    trigger_id=trg_id,
                    template_name=decision.template_name,
                    template_params=template_params,
                    body=body_text,
                    cta=cta,
                    suppression_key=supp_key,
                    rationale=decision.rationale,
                )
            )

        return TickResponse(actions=actions)

    @app.post("/v1/reply", response_model=ReplyResponse)
    async def reply(body: ReplyRequest):
        conv = conversation_manager.get_or_create(body.conversation_id, body.merchant_id, body.customer_id)
        merch_id = body.merchant_id or conv.get("merchant_id")
        cust_id = body.customer_id or conv.get("customer_id")
        trg_id = conv.get("trigger_id")

        is_auto = detect_auto_reply(body.message)
        is_hostile = detect_hostile_or_optout(body.message)

        conv_auto_cnt, m_auto_cnt = conversation_manager.handle_reply_state(
            body.conversation_id, merch_id, body.from_role, body.message, is_auto, is_hostile
        )
        max_auto = max(conv_auto_cnt, m_auto_cnt)

        # Contexts for composition
        merchant = context_store.get("merchant", merch_id) if merch_id else None
        cat_slug = merchant.get("category_slug") if merchant else None
        category = context_store.get("category", cat_slug) if cat_slug else None
        customer = context_store.get("customer", cust_id) if cust_id else None
        trigger = context_store.get("trigger", trg_id) if trg_id else None

        evidence = extract_evidence(category, merchant, trigger, customer)
        past_msgs = storage.get_conversation_messages(body.conversation_id)

        # Record inbound message
        conversation_manager.record_turn(
            conversation_id=body.conversation_id,
            from_role=body.from_role,
            message=body.message,
            timestamp=body.received_at,
        )

        action, reply_body, cta, wait_sec, rationale = composer.compose_reply(
            incoming_message=body.message,
            turn_number=body.turn_number,
            evidence=evidence,
            past_messages=past_msgs,
            consecutive_auto_replies=max_auto,
        )

        # Record outbound response
        if reply_body or action != "send":
            conversation_manager.record_turn(
                conversation_id=body.conversation_id,
                from_role="vera",
                message=reply_body or f"[{action}]",
                action=action,
                rationale=rationale,
                cta=cta,
                timestamp=body.received_at,
            )

        return ReplyResponse(
            action=action,
            body=reply_body,
            cta=cta,
            wait_seconds=wait_sec,
            rationale=rationale,
        )

    @app.post("/v1/teardown", response_model=TeardownResponse)
    async def teardown():
        cleared = context_store.clear()
        return TeardownResponse(status="wiped", contexts_cleared=cleared)

    return app

app = create_app()
