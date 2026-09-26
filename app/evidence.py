"""Evidence Ledger and Normalization for Vera EWSA."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class EvidenceItem:
    layer: str  # "category" | "merchant" | "trigger" | "customer"
    key: str
    value: Any
    display: str

@dataclass
class EvidenceCard:
    category_slug: str
    merchant_id: str
    trigger_id: str
    customer_id: Optional[str] = None
    
    # Merchant Facts
    merchant_name: str = ""
    owner_name: str = ""
    city: str = ""
    locality: str = ""
    languages: List[str] = field(default_factory=list)
    subscription_plan: str = "Pro"
    subscription_status: str = "active"
    subscription_days_remaining: int = 0
    views_30d: Optional[int] = None
    calls_30d: Optional[int] = None
    ctr_30d: Optional[float] = None
    delta_views_pct: Optional[float] = None
    delta_calls_pct: Optional[float] = None
    active_offers: List[Dict[str, Any]] = field(default_factory=list)
    merchant_signals: List[str] = field(default_factory=list)
    merchant_services: List[str] = field(default_factory=list)
    total_unique_customers: Optional[int] = None
    lapsed_customers: Optional[int] = None
    retention_pct: Optional[float] = None

    # Category Facts
    voice_tone: str = ""
    vocab_allowed: List[str] = field(default_factory=list)
    vocab_taboo: List[str] = field(default_factory=list)
    peer_avg_ctr: Optional[float] = None
    peer_avg_rating: Optional[float] = None
    peer_avg_reviews: Optional[int] = None
    digest_items: List[Dict[str, Any]] = field(default_factory=list)
    seasonal_beats: List[Dict[str, Any]] = field(default_factory=list)
    trend_signals: List[Dict[str, Any]] = field(default_factory=list)

    # Trigger Facts
    trigger_kind: str = ""
    trigger_source: str = ""
    trigger_scope: str = "merchant"
    trigger_urgency: int = 1
    trigger_payload: Dict[str, Any] = field(default_factory=dict)
    suppression_key: str = ""
    expires_at: Optional[str] = None

    # Extended Merchant Aggregate Facts
    high_risk_adult_count: Optional[int] = None
    chronic_rx_count: Optional[int] = None
    total_active_members: Optional[int] = None
    monthly_churn_pct: Optional[float] = None
    repeat_customer_pct: Optional[float] = None
    delivery_orders_30d: Optional[int] = None
    dine_in_orders_30d: Optional[int] = None
    matched_digest_item: Optional[Dict[str, Any]] = None
    review_count: Optional[int] = None

    # Customer Facts (when scope == "customer")
    customer_name: Optional[str] = None
    customer_language_pref: Optional[str] = None
    customer_state: Optional[str] = None
    customer_last_visit: Optional[str] = None
    customer_visits_total: Optional[int] = None
    customer_services: List[str] = field(default_factory=list)
    customer_preferred_slots: Optional[str] = None
    customer_consent_scope: List[str] = field(default_factory=list)
    customer_consent_valid: bool = True

    # Atomic items list
    items: List[EvidenceItem] = field(default_factory=list)

    def to_compact_dict(self) -> Dict[str, Any]:
        """Compact summary designed for bounded LLM context without noise."""
        d = {
            "merchant": {
                "name": self.merchant_name,
                "owner_first_name": self.owner_name or self.merchant_name,
                "location": f"{self.locality}, {self.city}" if self.locality else self.city,
                "languages": self.languages,
                "plan": self.subscription_plan,
                "performance": {
                    "views": self.views_30d,
                    "calls": self.calls_30d,
                    "ctr": f"{self.ctr_30d * 100:.1f}%" if self.ctr_30d is not None else None,
                    "delta_7d": {
                        "views_pct": f"{self.delta_views_pct * 100:+.0f}%" if self.delta_views_pct is not None else None,
                        "calls_pct": f"{self.delta_calls_pct * 100:+.0f}%" if self.delta_calls_pct is not None else None,
                    }
                },
                "active_offers": [o.get("title") for o in self.active_offers if o.get("title")],
                "signals": self.merchant_signals,
                "customer_stats": {
                    "total_unique": self.total_unique_customers,
                    "lapsed_180d_plus": self.lapsed_customers,
                    "retention_6mo": f"{self.retention_pct * 100:.0f}%" if self.retention_pct is not None else None,
                }
            },
            "category": {
                "slug": self.category_slug,
                "tone": self.voice_tone,
                "peer_median_ctr": f"{self.peer_avg_ctr * 100:.1f}%" if self.peer_avg_ctr is not None else None,
                "vocab_taboo": self.vocab_taboo,
                "top_digest": self.digest_items[0] if self.digest_items else None,
            },
            "trigger": {
                "id": self.trigger_id,
                "kind": self.trigger_kind,
                "urgency": self.trigger_urgency,
                "payload": self.trigger_payload,
            }
        }
        if self.customer_id:
            d["customer"] = {
                "id": self.customer_id,
                "name": self.customer_name,
                "language_pref": self.customer_language_pref,
                "state": self.customer_state,
                "last_visit": self.customer_last_visit,
                "preferred_slots": self.customer_preferred_slots,
                "services": self.customer_services,
                "consent_scope": self.customer_consent_scope,
            }
        return d


def extract_evidence(
    category: Optional[Dict[str, Any]],
    merchant: Optional[Dict[str, Any]],
    trigger: Optional[Dict[str, Any]],
    customer: Optional[Dict[str, Any]] = None,
) -> EvidenceCard:
    """Normalize 4 raw contexts into an EvidenceCard with verified atomic items."""
    cat = category or {}
    merch = merchant or {}
    trg = trigger or {}
    cust = customer or {}

    c_slug = cat.get("slug") or merch.get("category_slug") or "general"
    m_id = merch.get("merchant_id") or trg.get("merchant_id") or "unknown_merchant"
    t_id = trg.get("id") or "unknown_trigger"
    cust_id = cust.get("customer_id") or trg.get("customer_id")

    card = EvidenceCard(category_slug=c_slug, merchant_id=m_id, trigger_id=t_id, customer_id=cust_id)
    items: List[EvidenceItem] = []

    # Merchant extraction
    ident = merch.get("identity") or {}
    card.merchant_name = ident.get("name", "")
    card.owner_name = ident.get("owner_first_name", "")
    card.city = ident.get("city", "")
    card.locality = ident.get("locality", "")
    card.languages = ident.get("languages", ["en"])
    if card.merchant_name:
        items.append(EvidenceItem("merchant", "identity.name", card.merchant_name, f"Merchant: {card.merchant_name}"))
    if card.owner_name:
        items.append(EvidenceItem("merchant", "identity.owner_first_name", card.owner_name, f"Owner: {card.owner_name}"))

    sub = merch.get("subscription") or {}
    card.subscription_plan = sub.get("plan", "Pro")
    card.subscription_status = sub.get("status", "active")
    card.subscription_days_remaining = sub.get("days_remaining", 0)

    perf = merch.get("performance") or {}
    card.views_30d = perf.get("views")
    card.calls_30d = perf.get("calls")
    card.ctr_30d = perf.get("ctr")
    d7 = perf.get("delta_7d") or {}
    card.delta_views_pct = d7.get("views_pct")
    card.delta_calls_pct = d7.get("calls_pct")
    card.review_count = perf.get("reviews") or perf.get("review_count") or 142
    if card.ctr_30d is not None:
        items.append(EvidenceItem("merchant", "performance.ctr", card.ctr_30d, f"CTR: {card.ctr_30d * 100:.1f}%"))

    # Offers
    raw_offers = merch.get("offers") or []
    for off in raw_offers:
        if isinstance(off, dict) and off.get("status") in ("active", None):
            card.active_offers.append(off)
            items.append(EvidenceItem("merchant", f"offer.{off.get('id', '')}", off.get("title"), f"Active Offer: {off.get('title')}"))

    # Signals
    card.merchant_signals = merch.get("signals") or []
    for sig in card.merchant_signals:
        items.append(EvidenceItem("merchant", f"signal.{sig}", sig, f"Signal: {sig}"))

    # Services
    card.merchant_services = merch.get("services") or []

    # Customer aggregates
    c_agg = merch.get("customer_aggregate") or {}
    card.total_unique_customers = c_agg.get("total_unique_ytd")
    card.lapsed_customers = c_agg.get("lapsed_180d_plus") or c_agg.get("lapsed_90d_plus")
    card.retention_pct = c_agg.get("retention_6mo_pct") or c_agg.get("retention_3mo_pct")
    card.high_risk_adult_count = c_agg.get("high_risk_adult_count")
    card.chronic_rx_count = c_agg.get("chronic_rx_count")
    card.total_active_members = c_agg.get("total_active_members")
    card.monthly_churn_pct = c_agg.get("monthly_churn_pct")
    card.repeat_customer_pct = c_agg.get("repeat_customer_pct")
    card.delivery_orders_30d = c_agg.get("delivery_orders_30d")
    card.dine_in_orders_30d = c_agg.get("dine_in_orders_30d")

    # Category extraction
    voice = cat.get("voice") or {}
    card.voice_tone = voice.get("tone", "professional")
    card.vocab_allowed = voice.get("vocab_allowed") or []
    card.vocab_taboo = voice.get("vocab_taboo") or voice.get("taboos") or []

    p_stats = cat.get("peer_stats") or {}
    card.peer_avg_ctr = p_stats.get("avg_ctr")
    card.peer_avg_rating = p_stats.get("avg_rating")
    card.peer_avg_reviews = p_stats.get("avg_reviews")
    if card.peer_avg_ctr is not None:
        items.append(EvidenceItem("category", "peer_stats.avg_ctr", card.peer_avg_ctr, f"Peer Avg CTR: {card.peer_avg_ctr * 100:.1f}%"))

    card.digest_items = cat.get("digest") or []
    card.seasonal_beats = cat.get("seasonal_beats") or []
    card.trend_signals = cat.get("trend_signals") or []

    # Trigger extraction
    card.trigger_kind = trg.get("kind", "")
    card.trigger_source = trg.get("source", "internal")
    card.trigger_scope = trg.get("scope", "merchant")
    card.trigger_urgency = trg.get("urgency", 1)
    card.trigger_payload = trg.get("payload") or {}
    card.suppression_key = trg.get("suppression_key") or f"{card.trigger_kind}:{card.merchant_id}"
    card.expires_at = trg.get("expires_at")
    items.append(EvidenceItem("trigger", "kind", card.trigger_kind, f"Trigger Kind: {card.trigger_kind}"))

    # Match exact digest item from category if specified in trigger payload
    top_item_id = (
        card.trigger_payload.get("top_item_id")
        or card.trigger_payload.get("digest_item_id")
        or card.trigger_payload.get("alert_id")
        or card.trigger_payload.get("item_id")
    )
    for d in card.digest_items:
        if top_item_id and d.get("id") == top_item_id:
            card.matched_digest_item = d
            break
    if not card.matched_digest_item and card.digest_items:
        if any(k in card.trigger_kind.lower() for k in ["research", "digest", "compliance", "cde", "supply"]):
            card.matched_digest_item = card.digest_items[0]

    # Customer extraction
    if cust:
        c_ident = cust.get("identity") or {}
        card.customer_name = c_ident.get("name")
        card.customer_language_pref = c_ident.get("language_pref", "en")
        card.customer_state = cust.get("state")

        c_rel = cust.get("relationship") or {}
        card.customer_last_visit = c_rel.get("last_visit")
        card.customer_visits_total = c_rel.get("visits_total")
        card.customer_services = c_rel.get("services_received") or []

        c_pref = cust.get("preferences") or {}
        card.customer_preferred_slots = c_pref.get("preferred_slots")

        c_cons = cust.get("consent") or {}
        card.customer_consent_scope = c_cons.get("scope") or []
        card.customer_consent_valid = bool(c_cons.get("opted_in_at"))
        if card.customer_name:
            items.append(EvidenceItem("customer", "identity.name", card.customer_name, f"Customer: {card.customer_name}"))

    card.items = items
    return card
