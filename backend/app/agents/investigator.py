import uuid
import json
import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.models.ai_investigation import AIInvestigation
from app.db.models.payment import Payment
from app.agents.tools import evidence_gatherer
from app.schemas.ai import AIInvestigationResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

class AIInvestigator:
    """Investigates payment failures using structured cross-signal evidence and deterministic fallbacks."""

    @staticmethod
    async def investigate(
        db: Session,
        payment_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        question: str = "Investigate payment outcome and root cause",
    ) -> AIInvestigationResponse:
        if not payment_id:
            return AIInvestigationResponse(
                root_cause="No payment specified for investigation",
                confidence=0.0,
                severity="LOW",
                customer_impact="None",
                business_impact="None",
                recommendation="Provide a valid payment ID to investigate.",
                insufficient_evidence=True,
                model_name="deterministic-rule-engine-v1",
            )

        # 1. Gather deterministic facts from database
        facts_data = evidence_gatherer.get_payment_facts(db, payment_id)
        if "error" in facts_data:
            return AIInvestigationResponse(
                root_cause="Payment record not found",
                confidence=0.0,
                severity="LOW",
                customer_impact="Unknown",
                business_impact="None",
                recommendation="Verify the payment ID.",
                insufficient_evidence=True,
                model_name="deterministic-rule-engine-v1",
            )

        similar_failures = evidence_gatherer.find_similar_failures(db, payment_id)
        comparison = evidence_gatherer.compare_with_successful(db, payment_id)

        evidence_event_ids = [e["id"] for e in facts_data.get("events_summary", [])]

        # 2. Try LLM Provider if configured
        if settings.is_ai_configured:
            try:
                llm_response = await AIInvestigator._call_llm(facts_data, similar_failures, comparison, question)
                if llm_response:
                    llm_response.payment_id = payment_id
                    llm_response.evidence_event_ids = evidence_event_ids[:10]
                    # Save to DB
                    AIInvestigator._save_investigation(db, llm_response)
                    return llm_response
            except Exception as e:
                logger.warning(f"AI provider call failed, falling back to deterministic investigator: {e}")

        # 3. Deterministic Evidence-Based Fallback Investigator
        fallback_res = AIInvestigator._deterministic_investigate(facts_data, similar_failures, comparison, question)
        fallback_res.payment_id = payment_id
        fallback_res.evidence_event_ids = evidence_event_ids[:10]
        AIInvestigator._save_investigation(db, fallback_res)
        return fallback_res

    @staticmethod
    def _deterministic_investigate(
        facts: Dict[str, Any],
        similar: List[Dict[str, Any]],
        comparison: Optional[Dict[str, Any]],
        question: str,
    ) -> AIInvestigationResponse:
        status = facts.get("status")
        failure_code = facts.get("failure_code")
        failure_reason = facts.get("failure_reason")
        amount = facts.get("amount", 0.0)
        currency = facts.get("currency", "USD")
        order_id = facts.get("paypal_order_id", "UNKNOWN")
        timed_out = facts.get("timed_out", False)
        denied = facts.get("denied", False)
        order_approved = facts.get("order_approved", False)
        webhooks_count = facts.get("webhooks_count", 0)

        # SCENARIO 1: Timeout before capture response (CRITICAL UNCERTAIN STATE)
        if timed_out or status == "CAPTURE_UNCERTAIN" or failure_code == "TIMEOUT_BEFORE_RESPONSE":
            return AIInvestigationResponse(
                root_cause="Merchant backend timed out while awaiting PayPal capture response; final capture outcome is unconfirmed locally.",
                confidence=0.94,
                severity="HIGH",
                facts=[
                    f"PayPal order {order_id} was successfully created and approved by the buyer.",
                    "The merchant backend dispatched a capture request to PayPal.",
                    "Merchant HTTP client timed out (>5000ms) before receiving the HTTP capture response.",
                    f"No verified PAYMENT.CAPTURE.COMPLETED webhook was processed prior to timeout.",
                    "Payment marked CAPTURE_UNCERTAIN to prevent premature retry.",
                ],
                inferences=[
                    "PayPal may have successfully processed the capture on their ledger despite the local HTTP timeout.",
                    "A blind capture retry risks duplicate charges on the customer's payment instrument.",
                ],
                customer_impact="Customer observed a connection timeout spinner; funds may have been debited or reserved without local confirmation.",
                business_impact=f"Potential revenue at risk of ${amount:.2f} {currency}. High dispute risk if double-captured.",
                recommendation="DO NOT RETRY CAPTURE. Reconcile order state via GET /v2/checkout/orders/{order_id} or verify incoming webhooks before taking further action.",
                is_incident_likely=True,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
                comparison_notes=comparison.get("key_divergence") if comparison else None,
            )

        # SCENARIO 2: Capture Denied
        if denied or status in ("DENIED", "CAPTURE_FAILED") or failure_code in ("CAPTURE_DENIED", "INSTRUMENT_DECLINED"):
            return AIInvestigationResponse(
                root_cause=f"Payment capture was declined by PayPal or issuing bank ({failure_reason or 'INSTRUMENT_DECLINED'}).",
                confidence=0.91,
                severity="MEDIUM",
                facts=[
                    f"Order {order_id} was submitted for capture.",
                    f"PayPal returned decline code: {failure_code or 'INSTRUMENT_DECLINED'}.",
                    f"Decline reason: {failure_reason or 'Instrument declined by issuing bank'}.",
                ],
                inferences=[
                    "Buyer instrument has insufficient balance, expiration, or fraud flag from issuing bank.",
                    "Retry with identical payment instrument will consistently fail.",
                ],
                customer_impact="Customer received payment declined message during checkout.",
                business_impact=f"Potential lost revenue of ${amount:.2f} {currency}.",
                recommendation="Prompt customer to select an alternative payment method (different card or PayPal balance). Do not automatically re-attempt with current instrument.",
                is_incident_likely=len(similar) >= 2,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
                comparison_notes=comparison.get("key_divergence") if comparison else None,
            )

        # SCENARIO 3: Delayed Webhook
        if status == "CAPTURED" and webhooks_count == 0:
            return AIInvestigationResponse(
                root_cause="Payment was captured synchronously via API, but PayPal webhook delivery is delayed or missing.",
                confidence=0.85,
                severity="LOW",
                facts=[
                    f"Order {order_id} successfully captured.",
                    "Synchronous API response confirms CAPTURED state.",
                    "Zero verified webhook events recorded for this payment.",
                ],
                inferences=[
                    "Downstream systems that rely exclusively on asynchronous webhooks may not have fulfilled the order yet.",
                ],
                customer_impact="Customer checkout succeeded, but fulfillment confirmation may lag.",
                business_impact="Low revenue risk; operational reconciliation recommended.",
                recommendation="Trigger manual webhook re-sync or verify webhook endpoint reachability in PayPal developer settings.",
                is_incident_likely=False,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
            )

        # SCENARIO 4: Successful Payment
        if status == "CAPTURED":
            return AIInvestigationResponse(
                root_cause="Payment lifecycle completed normally with full API and webhook verification.",
                confidence=0.99,
                severity="LOW",
                facts=[
                    f"Order {order_id} created and approved.",
                    "Capture completed successfully within acceptable latency.",
                    f"Verified webhook events received: {webhooks_count}.",
                ],
                inferences=[
                    "Payment is fully settled in PayPal Sandbox.",
                ],
                customer_impact="Seamless checkout experience with immediate confirmation.",
                business_impact=f"Successfully captured revenue of ${amount:.2f} {currency}.",
                recommendation="No action required. Transaction is healthy.",
                is_incident_likely=False,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
            )

        # Generic / Insufficient Evidence Case
        return AIInvestigationResponse(
            root_cause="Insufficient evidence to definitively determine payment failure root cause.",
            confidence=0.40,
            severity="MEDIUM",
            facts=[
                f"Current recorded status: {status}.",
                f"Recorded events count: {facts.get('event_count', 0)}.",
            ],
            inferences=[
                "Evidence in database is insufficient or events are incomplete.",
            ],
            customer_impact="Customer checkout state may be unresolved.",
            business_impact=f"Potential transaction amount ${amount:.2f} {currency}.",
            recommendation="Inspect application logs and check PayPal dashboard directly.",
            is_incident_likely=False,
            insufficient_evidence=True,
            model_name="deterministic-rule-engine-v1",
        )

    @staticmethod
    async def _call_llm(
        facts: Dict[str, Any],
        similar: List[Dict[str, Any]],
        comparison: Optional[Dict[str, Any]],
        question: str,
    ) -> Optional[AIInvestigationResponse]:
        """Calls OpenAI or OpenAI-compatible provider with structured JSON output."""
        prompt = f"""
You are the PayTrace AI Payment Investigator. Analyze this PayPal payment evidence and return structured findings.
Strictly adhere to the facts provided. Never invent missing events. Separate FACT, INFERENCE, and RECOMMENDATION.
If evidence is missing or ambiguous (especially timeouts where backend did not receive capture response), emphasize the uncertainty and explicitly warn against blind retries to prevent duplicate charges.

EVIDENCE DATA:
{json.dumps(facts, indent=2)}

SIMILAR FAILURES:
{json.dumps(similar, indent=2)}

COMPARISON WITH SUCCESSFUL PAYMENT:
{json.dumps(comparison, indent=2) if comparison else "None available"}

QUESTION:
{question}

Return ONLY valid JSON matching this exact schema:
{{
  "root_cause": "string",
  "confidence": 0.0 to 1.0,
  "severity": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "facts": ["string"],
  "inferences": ["string"],
  "customer_impact": "string",
  "business_impact": "string",
  "recommendation": "string",
  "is_incident_likely": true | false,
  "insufficient_evidence": true | false
}}
"""
        headers = {
            "Authorization": f"Bearer {settings.AI_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": settings.AI_MODEL or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are PayTrace AI Investigator. Return only JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return AIInvestigationResponse(
                root_cause=parsed.get("root_cause", ""),
                confidence=float(parsed.get("confidence", 0.8)),
                severity=parsed.get("severity", "MEDIUM"),
                facts=parsed.get("facts", []),
                inferences=parsed.get("inferences", []),
                customer_impact=parsed.get("customer_impact", ""),
                business_impact=parsed.get("business_impact", ""),
                recommendation=parsed.get("recommendation", ""),
                is_incident_likely=bool(parsed.get("is_incident_likely", False)),
                insufficient_evidence=bool(parsed.get("insufficient_evidence", False)),
                model_name=settings.AI_MODEL,
            )

    @staticmethod
    def _save_investigation(db: Session, inv: AIInvestigationResponse) -> None:
        rec = AIInvestigation(
            id=str(uuid.uuid4()),
            payment_id=inv.payment_id,
            incident_id=inv.incident_id,
            question="Payment outcome and root cause investigation",
            root_cause=inv.root_cause,
            confidence=inv.confidence,
            severity=inv.severity,
            facts=inv.facts,
            inferences=inv.inferences,
            customer_impact=inv.customer_impact,
            business_impact=inv.business_impact,
            recommendation=inv.recommendation,
            evidence_event_ids=inv.evidence_event_ids,
            is_incident_likely=inv.is_incident_likely,
            insufficient_evidence=inv.insufficient_evidence,
            model_name=inv.model_name,
            created_at=datetime.utcnow(),
        )
        db.add(rec)
        db.commit()
        inv.id = rec.id
        inv.created_at = rec.created_at

    @staticmethod
    async def chat(
        db: Session,
        payment_id: Optional[str],
        incident_id: Optional[str],
        messages: List[Dict[str, str]],
        question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evidence-grounded follow-up chat with the AI Investigator."""
        facts_data = evidence_gatherer.get_payment_facts(db, payment_id) if payment_id else {}
        evidence_ids = [e["id"] for e in facts_data.get("events_summary", [])][:5]

        query = question or (messages[-1]["content"] if messages else "Explain the status")
        
        # Grounded response formulation
        status = facts_data.get("status", "UNKNOWN")
        timed_out = facts_data.get("timed_out", False)
        denied = facts_data.get("denied", False)

        if "duplicate" in query.lower() or "retry" in query.lower():
            if timed_out or status == "CAPTURE_UNCERTAIN":
                reply = (
                    "**Crucial Warning:** You should **NOT** retry capturing this payment yet. "
                    "Because the merchant backend timed out before receiving PayPal's HTTP response, "
                    "the capture may have succeeded on PayPal's end. Re-sending a capture call could charge the buyer a second time. "
                    "**Next Step:** Use order reconciliation (GET /v2/checkout/orders/{order_id}) or check webhook logs first."
                )
            else:
                reply = "Automatic retries are subject to safety checks. If the failure was a permanent denial (e.g. INSTRUMENT_DECLINED), retrying will fail again."
        elif "refund" in query.lower():
            reply = (
                "PayTrace policy mandates that all refund actions require explicit human operator approval. "
                "You can initiate a refund proposal from the payment actions panel, which routes into the Human Approval Inbox."
            )
        else:
            reply = (
                f"Based on the cross-signal evidence for payment `{payment_id}` (current status: `{status}`), "
                f"the investigation detected {facts_data.get('event_count', 0)} lifecycle events and "
                f"{facts_data.get('webhooks_count', 0)} verified webhooks. "
                f"Root cause summary: {facts_data.get('failure_reason') or 'Normal settlement or pending outcome.'}"
            )

        return {
            "response": reply,
            "grounded_facts": [
                f"Payment Status: {status}",
                f"Amount: {facts_data.get('amount', 0.0)} {facts_data.get('currency', 'USD')}",
                f"PayPal Order ID: {facts_data.get('paypal_order_id', 'N/A')}",
            ],
            "recommended_action": "Reconcile order state" if (timed_out or status == "CAPTURE_UNCERTAIN") else None,
            "evidence_event_ids": evidence_ids,
        }

ai_investigator = AIInvestigator()
