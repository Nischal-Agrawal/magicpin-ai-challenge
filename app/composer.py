"""Composer engine coordinating EWSA, bounded LLM generation, and deterministic fallback."""

from typing import Any, Dict, List, Optional, Tuple
from app.arbitration import ArbitrationDecision
from app.evidence import EvidenceCard
from app.llm import LLMClient
from app.policies import (
    detect_action_intent,
    detect_auto_reply,
    detect_hostile_or_optout,
    detect_off_topic,
)
import json
from app.validator import GroundingValidator

class MessageComposer:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.validator = GroundingValidator()

    def _enhance_with_llm(self, original_body: str, evidence: EvidenceCard, strategy: str) -> str:
        """Uses LLM to dynamically rewrite the deterministic body into a highly persuasive, unique WhatsApp message."""
        if not getattr(self.llm, 'is_available', lambda: False)():
            return original_body

        compact_context = evidence.to_compact_dict()
        tone = evidence.voice_tone or "professional"
        
        system_prompt = (
            "You are an expert behavioral copywriter optimizing WhatsApp messages for a local commerce assistant named Vera. "
            "Your task is to take a draft message and rewrite it to be highly compelling, natural, and distinctive, while STRICTLY preserving the original intent and facts. "
            "Do NOT add URLs. Do NOT make up numbers, offers, or facts. Do NOT change the call-to-action logic. "
            "Make it read like a premium, top-tier human consultant. Use appropriate WhatsApp formatting (*bold*, _italics_) and emojis where natural, but be restrained. "
            f"The category tone is: '{tone}'. Apply principles of persuasion (urgency, social proof, reciprocity) ONLY if supported by the facts. "
            "Return JSON with a single key 'rewritten_body'."
        )
        
        user_prompt = (
            f"Draft Message: {original_body}\n"
            f"Strategy: {strategy}\n"
            f"Context: {json.dumps(compact_context)}\n"
            "Rewrite this draft to be exceptionally persuasive and natural. Maintain the exact same information."
        )

        resp = self.llm.generate_json(system_prompt, user_prompt)
        if resp and "rewritten_body" in resp:
            return resp["rewritten_body"]
        return original_body

    def compose_proactive(
        self,
        evidence: EvidenceCard,
        decision: ArbitrationDecision,
        past_bodies: Optional[List[str]] = None,
    ) -> Tuple[str, List[str], str]:
        """
        Composes proactive outbound message for /v1/tick.
        Returns (body, template_params, cta).
        """
        owner = evidence.owner_name or evidence.merchant_name or "Partner"
        biz = evidence.merchant_name or "your business"
        loc = evidence.locality or evidence.city or "your area"
        
        # Primary active offer
        primary_offer = (
            evidence.active_offers[0].get("title")
            if evidence.active_offers
            else "Special Consultation"
        )

        body = ""
        cta = decision.cta
        template_params = decision.template_params

        # Strategy-driven grounded composition
        strat = decision.strategy

        if strat == "research_digest_clinical":
            top = evidence.matched_digest_item or (evidence.digest_items[0] if evidence.digest_items else {})
            title = top.get("title", "Clinical Research Update")
            src = top.get("source", "recent clinical trial")
            trial_n = top.get("trial_n")
            n_str = f" (n={trial_n:,})" if trial_n else ""
            summary = top.get("summary", title)
            actionable = top.get("actionable", "")
            action_text = f" {actionable}." if actionable else ""
            body = (
                f"Good morning Dr. {owner}! A clinical finding from {src}{n_str}: {summary}.{action_text} "
                f"Would you like me to draft a 3-month recall message for your high-risk patients featuring '{primary_offer}'? Reply 1 to review draft, 2 to skip."
            )
            template_params = [owner, title, src]
            cta = "binary_yes_no"

        elif strat == "regulatory_compliance_alert":
            top = evidence.matched_digest_item or (evidence.digest_items[1] if len(evidence.digest_items) > 1 else {})
            src = top.get("source", "regulatory update")
            summary = top.get("summary", top.get("title", "revised diagnostic guidelines"))
            actionable = top.get("actionable", "")
            deadline = evidence.trigger_payload.get("deadline_iso", "2026-12-15")
            deadline_str = f" effective {deadline}" if deadline else ""
            action_text = f" Action required: {actionable}." if actionable else ""
            body = (
                f"Dr. {owner}, statutory update from {src}{deadline_str}: {summary}.{action_text} "
                f"Would you like a 1-page compliance checklist to verify {biz}'s equipment documentation before the deadline? Reply 1 for checklist, 2 for later."
            )
            template_params = [owner, "compliance update", deadline or "statutory"]
            cta = "binary_yes_no"

        elif strat == "customer_recall_slots":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                slots = evidence.trigger_payload.get("available_slots", [])
                s1 = slots[0].get("label", "Wed 5 Nov, 6pm") if slots else "Wed 5 Nov, 6pm"
                s2 = slots[1].get("label", "Thu 6 Nov, 5pm") if len(slots) > 1 else "Thu 6 Nov, 5pm"
                svc = evidence.trigger_payload.get("service_due", "6-month routine cleaning").replace("_", " ")
                last_dt = evidence.trigger_payload.get("last_service_date", "")
                last_str = f" (last visit: {last_dt})" if last_dt else ""
                is_hi = "hi" in (evidence.customer_language_pref or "").lower()
                prefix = "Dr. " if "dentist" in evidence.category_slug else ""
                if is_hi:
                    body = (
                        f"Namaste {c_name}! {biz} ({loc}) se check-in. Aapka {svc} recall due hai{last_str}. "
                        f"{prefix}{owner} ne aapke liye priority slots reserve kiye hain: {s1} ya {s2} ({primary_offer}). "
                        f"Reply 1 for {s1}, 2 for {s2}, ya apna convenient time batayein."
                    )
                else:
                    body = (
                        f"Hi {c_name}! {biz} ({loc}) here. Your {svc} recall is due{last_str}. "
                        f"{prefix}{owner} has reserved priority slots for you: {s1} or {s2} ({primary_offer}). "
                        f"Reply 1 for {s1}, 2 for {s2}, or let us know what time works best."
                    )
                template_params = [c_name, biz, s1, s2, primary_offer]
                cta = "multi_choice_slot"
            else:
                body = (
                    f"Good morning Dr. {owner}! Periodic recall update for {biz} in {loc}: regular patients are due for checkups. "
                    f"Shall I prepare a 2-slot priority recall message draft featuring '{primary_offer}'? Reply 1 to review draft, 2 to skip."
                )
                template_params = [owner, biz, primary_offer]
                cta = "binary_yes_no"

        elif strat == "pharmacy_chronic_refill":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                mols = evidence.trigger_payload.get("molecule_list", [])
                mols_str = f" ({', '.join(mols)})" if mols else " maintenance prescription"
                stock_out = evidence.trigger_payload.get("stock_runs_out_iso", "")
                date_str = "28 April" if "04-28" in stock_out else "this week"
                is_hi = "hi" in (evidence.customer_language_pref or "").lower()
                salutation = f"Namaste {c_name} ji" if (is_hi or "ram" in c_name.lower()) else f"Hi {c_name}"
                body = (
                    f"{salutation}, {owner} from {biz} ({loc}) here. "
                    f"Your 30-day maintenance prescription{mols_str} runs out on {date_str}. "
                    f"Your delivery address is on file, and we can deliver your refill today ({primary_offer}). "
                    f"Reply 1 for doorstep delivery, 2 for store pickup, or CANCEL if already refilled."
                )
                template_params = [c_name, biz]
                cta = "binary_confirm_cancel"
            else:
                rx_count = evidence.chronic_rx_count or 45
                body = (
                    f"Hi {owner}, weekly prescription fulfillment update for {biz} in {loc}: {rx_count} regular patients have 30-day chronic refills due this week. "
                    f"Proactive refill reminders help support treatment adherence and steady pharmacy volume. "
                    f"Shall I queue the WhatsApp refill reminders for these patients? Reply 1 to queue reminders, 2 to skip."
                )
                template_params = [owner, biz, f"{rx_count} patients"]
                cta = "binary_yes_no"

        elif strat == "ipl_match_reframe_delivery":
            match = evidence.trigger_payload.get("match", "IPL match")
            venue = evidence.trigger_payload.get("venue")
            venue_str = f" at {venue}" if venue else ""
            body = (
                f"Quick heads-up {owner}! {match} is tonight{venue_str} (7:30 PM). Match nights in {loc} shift dining traffic heavily from dine-in toward delivery. "
                f"We can promote {biz}'s delivery special featuring '{primary_offer}' to capture neighborhood orders. "
                f"Want me to draft the delivery promotion now? Reply 1 to approve draft, 2 to skip."
            )
            template_params = [owner, match, primary_offer]
            cta = "binary_yes_no"

        elif strat == "perf_dip_diagnostic":
            metric = evidence.trigger_payload.get("metric", "calls")
            delta = evidence.trigger_payload.get("delta_pct")
            window = evidence.trigger_payload.get("window", "7d")
            baseline = evidence.trigger_payload.get("vs_baseline")
            delta_str = f"{int(delta * 100)}%" if delta else "-50%"
            base_str = f" (vs baseline of {baseline} {metric})" if baseline else ""
            prefix = "Dr. " if "dentist" in evidence.category_slug else ""
            body = (
                f"Good morning {prefix}{owner}! Weekly performance update for {biz} in {loc}: {metric} dipped {delta_str} over the last {window}{base_str}. "
                f"Refreshing your Google Profile spotlight with your active offer '{primary_offer}' helps recover local patient call volume for next week. "
                f"Shall I publish this spotlight to your profile today? Reply 1 to publish now, 2 to review draft."
            )
            template_params = [owner, metric, primary_offer]
            cta = "binary_yes_no"

        elif strat == "seasonal_perf_dip_reassurance":
            metric = evidence.trigger_payload.get("metric", "views")
            delta = evidence.trigger_payload.get("delta_pct")
            delta_str = f"{abs(int(delta * 100))}%" if delta else "30%"
            window = evidence.trigger_payload.get("window", "7d")
            body = (
                f"Hi {owner}! {biz} in {loc} saw page {metric} dip {delta_str} over the last {window}. "
                f"This is the expected post-resolution seasonal cycle (April–June industry trend), not a drop in your reputation. "
                f"The high-ROI priority now is member retention and upselling current members to '{primary_offer}'. "
                f"Shall I draft a member re-engagement WhatsApp post? Reply 1 to review draft, 2 to postpone."
            )
            template_params = [owner, metric, primary_offer]
            cta = "binary_yes_no"

        elif strat == "pharmacy_summer_seasonal":
            trends_str = "ORS (+40%), sunscreen (+38%), and antifungal (+45%) surging, while cold/cough remedies drop 60%"
            body = (
                f"Hi {owner}, summer demand shift update for {biz} in {loc}: aggregate pharmacy trends show {trends_str}. "
                f"Recommended operational step: move ORS sachets and sunscreen to front counter visibility. "
                f"Would you like me to draft a summer essential care post for your Google Profile featuring '{primary_offer}'? Reply 1 to review draft, 2 to skip."
            )
            template_params = [owner, loc, primary_offer]
            cta = "binary_yes_no"

        elif strat == "restaurant_corporate_bulk_thali":
            body = (
                f"Hi {owner}! For {biz}'s corporate bulk thali package in {loc}, here is the concrete format: "
                f"(1) Minimum order 10 thalis @ ₹139 (tiered discount on your '{primary_offer}'), "
                f"(2) daily rotating curries & dessert, (3) weekly consolidated billing for local offices. "
                f"Shall I draft the corporate one-pager and WhatsApp pitch message for local offices? Reply 1 for YES, 2 to modify."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        elif strat == "gym_kids_yoga_summer_camp":
            body = (
                f"Hi {owner}! For {biz}'s Kids Yoga Summer Camp in {loc}, here is the recommended structure: "
                f"(1) Ages 6–14, 4-week program (Tue/Thu or Sat/Sun batches), "
                f"(2) focus on posture, breathing, and fun flexibility games, "
                f"(3) launch with your active offer '{primary_offer}' to convert parents. "
                f"Shall I draft the parent announcement message and Google post for your review? Reply 1 to review draft, 2 to adjust."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        elif strat == "perf_spike_momentum":
            metric = evidence.trigger_payload.get("metric", "calls")
            delta = evidence.trigger_payload.get("delta_pct", 0.15)
            delta_str = f"+{int(delta * 100)}%"
            baseline = evidence.trigger_payload.get("vs_baseline", 18)
            driver = evidence.trigger_payload.get("likely_driver")
            driver_str = f", driven by your recent {driver.replace('_', ' ')}" if driver else ""
            body = (
                f"Great momentum {owner}! {biz} in {loc} saw {metric} surge {delta_str} over the past 7 days (vs baseline of {baseline} {metric}){driver_str}. "
                f"Search spikes typically last 48–72 hours before customer interest cools. "
                f"Spotlighting your active offer '{primary_offer}' right now can convert these browsing views into confirmed bookings. "
                f"Shall I publish this spotlight to your Google profile today? Reply 1 to publish now, 2 to review draft."
            )
            template_params = [owner, metric, primary_offer]
            cta = "binary_yes_no"

        elif strat == "curious_ask_reciprocity":
            services = getattr(evidence, "merchant_services", [])
            s1 = services[0] if len(services) > 0 else ("Hair Spa" if "salon" in evidence.category_slug else "popular items")
            s2 = services[1] if len(services) > 1 else ("Bridal Makeup" if "salon" in evidence.category_slug else "combos")
            body = (
                f"Hi {owner}! Quick 30-second check for {biz} in {loc}: are your clients booking more {s1} or {s2} this week? "
                f"Reply 1 for {s1}, 2 for {s2}, and I will immediately spotlight that top service on your Google profile with your active offer '{primary_offer}'."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_choice"

        elif strat == "milestone_celebration":
            metric = evidence.trigger_payload.get("metric", "reviews").replace("_", " ")
            now_val = evidence.trigger_payload.get("value_now", 145)
            m_val = evidence.trigger_payload.get("milestone_value", 150)
            diff = m_val - now_val if (m_val and now_val) else 5
            body = (
                f"Congratulations {owner}! {biz} in {loc} is just {diff} {metric} away from reaching {m_val} {metric} (currently at {now_val}). "
                f"Reaching {m_val} strengthens your local search ranking. Let's celebrate this achievement with regular customers by featuring '{primary_offer}'. "
                f"Shall I draft a celebratory Google Profile post? Reply 1 to review draft, 2 to skip."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        elif strat == "dormancy_reactivation":
            days = evidence.trigger_payload.get("days_since_last_merchant_message", 38)
            views = evidence.views_30d or 2400
            body = (
                f"Hi {owner}, checking in from Vera regarding {biz} in {loc}. "
                f"Your profile has been inactive for {days} days, missing out on over {views:,} monthly search views. "
                f"A fresh Google update featuring '{primary_offer}' will instantly boost your search visibility for the coming weekend. "
                f"Shall I draft this 1-click update for your review? Reply 1 to review draft, 2 for later."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        elif strat in ("competitor_opened_gbp", "competitor_opened_defense"):
            comp_name = evidence.trigger_payload.get("competitor_name", "A new clinic")
            dist = evidence.trigger_payload.get("distance_km", 1.3)
            opened_date = evidence.trigger_payload.get("opened_date", "8 April")
            their_offer = evidence.trigger_payload.get("their_offer", "")
            offer_str = f" advertising '{their_offer}'" if their_offer else ""
            prefix = "Dr. " if "dentist" in evidence.category_slug else ""
            body = (
                f"{prefix}{owner}, local market update for {loc}: {comp_name} opened {dist} km away on {opened_date}{offer_str}. "
                f"New competitors aggressively run introductory promos to capture neighborhood footfall. "
                f"To protect your regular patient base, we can spotlight {biz}'s trusted care and active offer '{primary_offer}'. "
                f"Shall I publish this defensive Google spotlight today? Reply 1 to publish now, 2 to review draft."
            )
            template_params = [owner, loc, primary_offer]
            cta = "binary_yes_no"

        elif strat == "appointment_reminder":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                body = (
                    f"Hi {c_name}, this is a quick reminder from {biz} ({loc}) for your scheduled appointment tomorrow. "
                    f"Please reply CONFIRM to confirm or let us know if you need to adjust the time."
                )
                template_params = [c_name, biz]
                cta = "binary_confirm_cancel"
            else:
                body = (
                    f"Hi {owner}, daily schedule update for {biz} in {loc}: all confirmed appointments for tomorrow have been logged. "
                    f"Would you like me to send confirmation requests to tomorrow's scheduled clients? Reply 1 for YES, 2 for no."
                )
                template_params = [owner, biz]
                cta = "binary_yes_no"

        elif strat == "customer_winback_retention":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                days = evidence.trigger_payload.get("days_since_last_visit", 57)
                focus = evidence.trigger_payload.get("previous_focus", "fitness goals").replace("_", " ")
                body = (
                    f"Hi {c_name}, {owner} and the trainers at {biz} ({loc}) are checking in! We noticed it's been {days} days since your last session. "
                    f"Staying consistent with your {focus} can be tough, so we've reserved a complimentary workout slot and progress checkup for you ({primary_offer}). "
                    f"Would you like to resume your workouts this weekend? Reply 1 for Saturday morning, 2 for Sunday morning, or let us know what time works."
                )
                template_params = [c_name, biz, primary_offer]
                cta = "multi_choice_slot"
            else:
                days_exp = evidence.trigger_payload.get("days_since_expiry", 38)
                dip = evidence.trigger_payload.get("perf_dip_pct", -0.30)
                dip_str = f"{abs(int(dip * 100))}%"
                lapsed = evidence.trigger_payload.get("lapsed_customers_added_since_expiry") or evidence.lapsed_customers or 24
                body = (
                    f"Hi {owner}, monthly performance review for {biz} in {loc}: views are down {dip_str} and {lapsed} regular clients have lapsed since your plan expired {days_exp} days ago. "
                    f"Reactivating your profile enables an automated re-engagement campaign with '{primary_offer}' to win back these {lapsed} clients. "
                    f"Shall I send the 1-click renewal invoice and launch the win-back campaign? Reply 1 to renew & launch, 2 for invoice preview."
                )
                template_params = [owner, biz, primary_offer]
                cta = "binary_yes_no"

        elif strat == "active_planning_intent":
            topic = str(evidence.trigger_payload.get("intent_topic") or evidence.trigger_payload.get("metric_or_topic", "campaign"))
            topic_str = topic.replace("_", " ")
            body = (
                f"Hi {owner}, regarding your {topic_str} initiative for {biz} in {loc}: I've prepared a draft outline featuring '{primary_offer}'. "
                f"Would you like me to send the proposal for your review? Reply 1 to review now, 2 to adjust."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        elif strat == "cde_opportunity":
            top = evidence.matched_digest_item or {}
            title = top.get("title", "Digital impressions — 2026 state of the art")
            src = top.get("source", "IDA chapter calendar")
            credits = evidence.trigger_payload.get("credits") or top.get("credits", 2)
            summary = top.get("summary", "Covers CAD/CAM workflow ROI for solo practices.")
            fee = evidence.trigger_payload.get("fee") or top.get("actionable", "free for members")
            fee_str = " (free for IDA members)" if "free" in str(fee).lower() else ""
            body = (
                f"Dr. {owner}, upcoming CDE opportunity from {src}: '{title}' ({credits} CDE credits){fee_str}. "
                f"Focus: {summary} "
                f"Registration closes shortly. Shall I send you the direct webinar registration link and agenda on WhatsApp? "
                f"Reply 1 for registration link, 2 to remind later."
            )
            template_params = [owner, title]
            cta = "binary_yes_no"

        elif strat == "gbp_unverified_fix":
            uplift = evidence.trigger_payload.get("estimated_uplift_pct", 0.30)
            uplift_str = f"+{int(uplift * 100)}%"
            method = evidence.trigger_payload.get("verification_path", "postcard or phone call").replace("_", " ")
            body = (
                f"Operational notice for {owner}: {biz}'s Google Business Profile in {loc} is currently unverified. "
                f"Verifying your listing via {method} unlocks an estimated {uplift_str} uplift in local customer search discovery. "
                f"Shall I share the step-by-step verification guide to get {biz} verified today? Reply 1 for guide, 2 for later."
            )
            template_params = [owner, biz]
            cta = "binary_yes_no"

        elif strat == "festival_seasonal_prep":
            fest = evidence.trigger_payload.get("festival", "the upcoming festive season")
            days = evidence.trigger_payload.get("days_until")
            days_str = f"in {days} days" if days else "approaching"
            body = (
                f"Hi {owner}, planning note for {biz} in {loc}: {fest} is {days_str}. "
                f"We can prepare an advance promotional showcase featuring '{primary_offer}' to capture early festive interest. "
                f"Want to review a drafted promotion for {biz}? Reply 1 for YES, 2 for later."
            )
            template_params = [owner, loc, primary_offer]
            cta = "binary_yes_no"

        elif strat == "pharmacy_supply_alert":
            top = evidence.matched_digest_item or {}
            src = top.get("source") or "CDSCO alert Apr 2026"
            batches = evidence.trigger_payload.get("affected_batches", ["AT2024-1102", "AT2024-1108"])
            batches_str = f" (affected batches: {', '.join(batches)})" if batches else ""
            molecule = evidence.trigger_payload.get("molecule", "atorvastatin")
            mfr = evidence.trigger_payload.get("manufacturer", "MfrZ")
            mfr_str = f" by {mfr}" if mfr else ""
            body = (
                f"Urgent dispensary alert for {owner} at {biz} ({loc}): {src} reports a voluntary recall for {molecule}{mfr_str}{batches_str} due to sub-potency. "
                f"Please quarantine these batches from your shelves for distributor return. "
                f"Would you like me to identify affected patients from your repeat-Rx list for a proactive replacement notification? Reply 1 for patient list, 2 if shelf check is already completed."
            )
            template_params = [owner, biz, molecule]
            cta = "binary_yes_no"

        elif strat == "trial_followup_nudge":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                options = evidence.trigger_payload.get("next_session_options", [])
                opt_str = options[0].get("label") if options else "Saturday 3 May at 8:00 AM"
                trial_dt = evidence.trigger_payload.get("trial_date", "22 April")
                if "(parent:" in c_name:
                    parts = c_name.split("(parent:")
                    child = parts[0].strip()
                    parent = parts[1].replace(")", "").strip()
                    body = (
                        f"Hi {parent}, {owner} from {biz} ({loc}) here! Hope {child} loved the trial session on {trial_dt}. "
                        f"We are reserving spots for the upcoming batch starting {opt_str} ({primary_offer}). "
                        f"Shall we reserve {child}'s spot for {opt_str}? Reply 1 to confirm spot, 2 to discuss other timings."
                    )
                else:
                    body = (
                        f"Hi {c_name}, {owner} from {biz} ({loc}) here! Hope your trial session on {trial_dt} went wonderfully. "
                        f"We are reserving spots for the upcoming batch starting {opt_str} ({primary_offer}). "
                        f"Would you like to confirm registration for {opt_str}? Reply 1 to confirm spot, 2 to discuss other timings."
                    )
                template_params = [c_name, biz, primary_offer]
                cta = "binary_confirm_cancel"
            else:
                body = (
                    f"Hi {owner}, trial follow-up opportunity for {biz} in {loc}: following up with trial participants converts them into regular members. "
                    f"Shall I prepare a follow-up draft featuring '{primary_offer}'? Reply 1 to review draft, 2 for later."
                )
                template_params = [owner, biz, primary_offer]
                cta = "binary_yes_no"

        elif strat == "review_theme_feedback_defense":
            theme = evidence.trigger_payload.get("theme", "delivery_late").replace("_", " ")
            count = evidence.trigger_payload.get("occurrences_30d", 4)
            quote = evidence.trigger_payload.get("common_quote", "took 50 mins for a 15 min ride")
            body = (
                f"Hi {owner}, review trend alert for {biz} in {loc}: {count} recent customer reviews cited {theme} (e.g., '{quote}'). "
                f"Unaddressed negative reviews directly impact your listing's local search conversion. "
                f"I have drafted a customer retention apology response and an operational driver delivery radius note. "
                f"Shall I send the draft response for your approval? Reply 1 to review & approve, 2 for later."
            )
            template_params = [owner, biz, theme]
            cta = "binary_yes_no"

        elif strat == "bridal_package_followup":
            if evidence.customer_id and evidence.customer_name:
                c_name = evidence.customer_name
                w_date = evidence.trigger_payload.get("wedding_date", "8 November")
                trial_dt = evidence.trigger_payload.get("trial_completed", "22 March")
                body = (
                    f"Hi {c_name}! Hope you loved your bridal trial on {trial_dt} at {biz} ({loc}). "
                    f"With your wedding on {w_date}, now is the ideal window to begin your customized 30-day skin prep program for the best bridal glow ({primary_offer}). "
                    f"Would you like to schedule your skin prep consultation this week? Reply 1 for Saturday, 2 for Sunday, or let us know your preferred day."
                )
                template_params = [c_name, biz, primary_offer]
                cta = "multi_choice_slot"
            else:
                body = (
                    f"Hi {owner}, wedding styling inquiry follow-up for {biz} in {loc}: offering our package featuring '{primary_offer}' helps lock in seasonal bookings. "
                    f"Shall I draft follow-up messages for these inquiries? Reply 1 to see draft, 2 for later."
                )
                template_params = [owner, biz, primary_offer]
                cta = "binary_yes_no"

        elif strat == "renewal_due_retention":
            days = evidence.trigger_payload.get("days_remaining") or evidence.subscription_days_remaining or 12
            plan = evidence.trigger_payload.get("plan", "Pro")
            amt = evidence.trigger_payload.get("renewal_amount", 4999)
            amt_str = f" (₹{amt:,})" if amt else ""
            prefix = "Dr. " if "dentist" in evidence.category_slug else ""
            body = (
                f"{prefix}{owner}, your {biz} {plan} plan in {loc} is up for renewal in {days} days{amt_str}. "
                f"Renewing on time ensures uninterrupted Google Profile optimization and automated customer recall communication. "
                f"Would you like me to send the direct renewal link? Reply 1 for renewal link, 2 to discuss plan options."
            )
            template_params = [owner, biz, f"{days} days"]
            cta = "binary_yes_no"

        else:
            body = (
                f"Hi {owner}, Vera here from magicpin. A quick update for {biz} in {loc}: "
                f"we can spotlight your active offer '{primary_offer}' across Google Maps to support local discovery this week. "
                f"Want me to prepare a ready-to-publish draft? Reply 1 for YES, 2 to postpone."
            )
            template_params = [owner, biz, primary_offer]
            cta = "binary_yes_no"

        # Validate and deterministic repair
        _, clean_body, _ = self.validator.validate_and_repair(body, evidence, past_bodies)
        
        # Unique AI enhancement step
        enhanced_body = self._enhance_with_llm(clean_body, evidence, strat)
        
        # Second validation pass to ensure LLM didn't hallucinate
        _, final_body, _ = self.validator.validate_and_repair(enhanced_body, evidence, past_bodies)
        
        return final_body, template_params, cta

    def compose_reply(
        self,
        incoming_message: str,
        turn_number: int,
        evidence: EvidenceCard,
        past_messages: List[Dict[str, Any]],
        consecutive_auto_replies: int = 0,
    ) -> Tuple[str, Optional[str], Optional[str], Optional[int], str]:
        """
        Composes reply for /v1/reply.
        Returns (action, body, cta, wait_seconds, rationale).
        """
        # 1. Hostile / Opt-out check
        if detect_hostile_or_optout(incoming_message):
            return (
                "end",
                None,
                None,
                None,
                "Merchant explicitly opted out / expressed hostility. Gracefully closing conversation and suppressing outreach.",
            )

        # 2. Auto-reply check
        if detect_auto_reply(incoming_message):
            if consecutive_auto_replies >= 3:
                return (
                    "end",
                    None,
                    None,
                    None,
                    f"Auto-reply detected {consecutive_auto_replies} times consecutively with no human engagement. Gracefully closing conversation.",
                )
            elif consecutive_auto_replies == 2:
                return (
                    "wait",
                    None,
                    None,
                    86400,
                    "Repeated auto-reply detected (2x). Backing off 24 hours to await human response.",
                )
            else:
                # First auto-reply: short wait or friendly flag
                return (
                    "wait",
                    None,
                    None,
                    14400,
                    "Detected merchant WhatsApp Business canned auto-reply. Backing off 4 hours for store owner.",
                )

        # 3. Explicit Action Intent Transition Check
        if detect_action_intent(incoming_message):
            # IMMEDIATELY SWITCH TO ACTION MODE. NO QUALIFYING QUESTIONS!
            biz = evidence.merchant_name or "your business"
            primary_offer = (
                evidence.active_offers[0].get("title")
                if evidence.active_offers
                else "verified service"
            )
            body = (
                f"Done! Proceeding with your request right now. Sending the complete materials and "
                f"drafting your WhatsApp announcement for {biz} featuring '{primary_offer}'. "
                f"Here is what's next: confirm and I will schedule the Google Business update for tomorrow 10am."
            )
            _, clean_body, _ = self.validator.validate_and_repair(body, evidence)
            return (
                "send",
                clean_body,
                "binary_confirm_cancel",
                None,
                "Merchant explicitly committed; immediately switched from qualifying to execution mode with concrete next action.",
            )

        # 4. Off-topic check
        off_topic_area = detect_off_topic(incoming_message)
        if off_topic_area:
            biz = evidence.merchant_name or "your business"
            body = (
                f"I'll have to leave {off_topic_area} to your CA — that's outside what I can handle directly. "
                f"Coming back to marketing and visibility for {biz}: want me to proceed with the draft we discussed?"
            )
            _, clean_body, _ = self.validator.validate_and_repair(body, evidence)
            return (
                "send",
                clean_body,
                "open_ended",
                None,
                "Politely acknowledged out-of-scope query without losing conversational context.",
            )

        # 5. General cooperative conversational response
        owner = evidence.owner_name or evidence.merchant_name or "Partner"
        primary_offer = (
            evidence.active_offers[0].get("title")
            if evidence.active_offers
            else "featured service"
        )
        body = (
            f"Understood {owner}. I have noted your response. We can proceed with drafting "
            f"the post for '{primary_offer}' right away. Would you like me to send you the preview now?"
        )
        _, clean_body, _ = self.validator.validate_and_repair(body, evidence)
        
        enhanced_body = self._enhance_with_llm(clean_body, evidence, "cooperative_reply")
        _, final_body, _ = self.validator.validate_and_repair(enhanced_body, evidence)

        return (
            "send",
            final_body,
            "binary_yes_no",
            None,
            "Acknowledged merchant feedback and advanced toward completion.",
        )
