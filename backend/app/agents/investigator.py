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
from app.core.time import utc_now

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
        if incident_id:
            incident_facts = evidence_gatherer.get_incident_facts(db, incident_id)
            if incident_facts.get("error"):
                return AIInvestigationResponse(root_cause="Incident record not found", confidence=0.0, severity="LOW", customer_impact="Unknown", business_impact="Unknown", recommendation="Verify the incident ID.", insufficient_evidence=True, incident_id=incident_id)
            incident = incident_facts["incident"]
            payments = incident_facts["affected_payments"]
            evidence_ids = incident_facts["evidence_event_ids"]
            fact_lines = [
                f"Incident {incident['id']} is {incident['status']} with {incident['severity']} severity.",
                f"Detection rule: {incident['rule'] or 'not recorded'}.",
                f"The incident record lists {incident['affected_payment_count']} affected payments; {len(payments)} rule-matched payment records were retrieved (maximum 50).",
                f"Revenue at risk recorded on the incident: {incident['revenue_at_risk']} {incident['currency']}.",
            ]
            if incident["root_cause"]:
                fact_lines.append(f"Stored incident root-cause field: {incident['root_cause']}.")
            else:
                fact_lines.append("The incident has no stored root-cause assessment.")
            for payment in payments:
                fact_lines.append(f"Payment {payment.get('payment_id')}: status {payment.get('status')}, order {payment.get('paypal_order_id') or 'not recorded'}, failure code {payment.get('failure_code') or 'not recorded'}, stored events {payment.get('event_count', 0)}, linked webhooks {payment.get('webhooks_count', 0)}, browser events {payment.get('session_events_count', 0)}.")
                for signal in payment.get("session_signals_summary", []):
                    detail = signal.get("details", {})
                    if signal.get("category") in ("network", "console"):
                        fact_lines.append(f"Linked {signal.get('category')} record {signal.get('id')}: {signal.get('occurred_at')}, {detail.get('method', '')} {detail.get('url', detail.get('message', signal.get('event_type')))}, status {detail.get('status', 'not recorded')}, severity {signal.get('severity') or 'not recorded'}.")
            prompt_facts = {"incident": incident, "affected_payments": payments}
            if settings.is_ai_configured:
                try:
                    result = await AIInvestigator._call_llm(prompt_facts, [], None, question)
                    if result:
                        result.incident_id = incident_id
                        result.severity = incident["severity"]
                        result.evidence_event_ids = evidence_ids[:20]
                        AIInvestigator._save_investigation(db, result)
                        return result
                except Exception as exc:
                    logger.warning("Incident AI provider call failed; using stored incident evidence: %s", exc)
            response = AIInvestigationResponse(
                incident_id=incident_id,
                root_cause=incident["root_cause"] or "No root cause is stored for this incident; the retrieved records do not establish one.",
                confidence=float(incident["confidence"] or 0.0), severity=incident["severity"],
                facts=fact_lines, inferences=[],
                customer_impact=f"The incident record reports {incident['affected_payment_count']} affected payments.",
                business_impact=f"Recorded revenue at risk: {incident['revenue_at_risk']} {incident['currency']}.",
                recommendation="Review the linked payment lifecycle and browser evidence; the stored records do not independently establish a cause or provider state.",
                evidence_event_ids=evidence_ids[:20], is_incident_likely=True,
                insufficient_evidence=not bool(incident["root_cause"] or evidence_ids),
            )
            AIInvestigator._save_investigation(db, response)
            return response

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

        # 2. Try LLM Provider if configured (supports OpenAI, Grok, Groq)
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
                logger.warning(f"AI provider call failed ({settings.effective_ai_provider}), falling back to deterministic investigator: {e}")

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
                root_cause="Stored timeout or uncertain-state evidence indicates an unresolved capture outcome; available records do not confirm the provider's final result.",
                confidence=0.55,
                severity="HIGH",
                facts=[
                    f"The stored payment status is {status}.",
                    *[f"Recorded event: {event['event_type']} at {event['occurred_at']} (source: {event['source']}, status: {event['status']})." for event in facts.get("events_summary", []) if "TIMEOUT" in event["event_type"].upper() or "UNCERTAIN" in event["event_type"].upper()],
                    f"No linked webhook records were found for this payment." if webhooks_count == 0 else f"{webhooks_count} linked webhook record(s) were found.",
                    "The available records do not confirm the final provider capture outcome.",
                ],
                inferences=[
                    "A provider capture may or may not have completed; the local records cannot establish this.",
                    "A blind capture retry could create a duplicate charge if the provider already captured the order.",
                ],
                customer_impact="The local record does not confirm the final checkout outcome; customer-visible impact is not available in the payment record.",
                business_impact=f"${amount:.2f} {currency} is in an uncertain local state.",
                recommendation="Do not blindly retry capture. Reconcile the provider order and review any linked webhook records before acting.",
                is_incident_likely=True,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
                comparison_notes=comparison.get("key_divergence") if comparison else None,
            )

        # SCENARIO 2: Capture Denied
        if denied or status in ("DENIED", "CAPTURE_FAILED") or failure_code in ("CAPTURE_DENIED", "INSTRUMENT_DECLINED"):
            return AIInvestigationResponse(
                root_cause=f"The stored payment status is {status}; the available records do not establish the underlying provider decline cause.",
                confidence=0.55,
                severity="MEDIUM",
                facts=[
                    f"Order {order_id} was submitted for capture.",
                    f"Stored failure code: {failure_code}." if failure_code else "No failure code is stored for this payment.",
                    f"Stored failure reason: {failure_reason}." if failure_reason else "No failure reason is stored for this payment.",
                ],
                inferences=[
                    "The stored records do not identify why the provider declined the payment.",
                ],
                customer_impact="The payment record is declined; customer-visible messaging is not available in the stored evidence.",
                business_impact=f"Potential lost revenue of ${amount:.2f} {currency}.",
                recommendation="Prompt customer to select an alternative payment method (different card or PayPal balance). Do not automatically re-attempt with current instrument.",
                is_incident_likely=len(similar) >= 2,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
                comparison_notes=comparison.get("key_divergence") if comparison else None,
            )

        # SCENARIO 3: Capture Remains Pending
        if status == "PENDING" or failure_code == "CAPTURE_PENDING":
            return AIInvestigationResponse(
                root_cause=f"The stored payment status is {status}; the available record does not establish the reason or expected completion time.",
                confidence=0.55,
                severity="MEDIUM",
                facts=[
                    f"The stored payment status is {status}.",
                    *([f"Stored capture ID: {facts['paypal_capture_id']}."] if facts.get("paypal_capture_id") else []),
                    f"Stored failure reason: {failure_reason}." if failure_reason else "No pending reason is stored.",
                ],
                inferences=[
                    "The available records do not establish settlement timing or why the payment remains pending.",
                ],
                customer_impact="Customer payment is held in pending status.",
                business_impact=f"Pending transaction value: ${amount:.2f} {currency}.",
                recommendation="Check the provider order status before taking fulfillment or retry actions.",
                is_incident_likely=False,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
                comparison_notes=comparison.get("key_divergence") if comparison else None,
            )

        # SCENARIO 4: Delayed or Missing Webhook
        if status == "CAPTURED" and webhooks_count == 0:
            return AIInvestigationResponse(
                root_cause="The payment is marked captured locally; no linked webhook records were found.",
                confidence=0.55,
                severity="LOW",
                facts=[
                    f"The stored payment status is {status}.",
                    "No linked webhook records were found for this payment. This does not prove that PayPal never sent a webhook.",
                ],
                inferences=[
                    "The available records do not establish whether webhook delivery was delayed or whether a downstream system is affected.",
                ],
                customer_impact="The payment record is captured; customer-visible fulfillment status is not available here.",
                business_impact=f"The local payment record lists {amount:.2f} {currency} as captured.",
                recommendation="If webhook confirmation is required, check PayPal event delivery history and compare it with stored webhook records.",
                is_incident_likely=False,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
            )

        # SCENARIO 5: Payment State Mismatch
        if (status in ("CREATED", "INITIATED") and webhooks_count > 0) or (status == "APPROVED" and facts.get("paypal_capture_id")):
            return AIInvestigationResponse(
                root_cause="The stored payment status and linked webhook or capture identifiers warrant review; provider state has not been independently checked.",
                confidence=0.88,
                severity="HIGH",
                facts=[
                    f"Internal payment status is {status}.",
                    f"Webhook events exist ({webhooks_count}) or external capture ID is present ({facts.get('paypal_capture_id')}).",
                ],
                inferences=[
                    "The difference may indicate a state transition that needs reconciliation, but the available records do not establish the provider's current state.",
                ],
                customer_impact="Customer-visible state is not available in the stored payment evidence.",
                business_impact=f"Potential reconciliation dispute on ${amount:.2f} {currency}.",
                recommendation="Run provider reconciliation via GET /paypal/orders/{order_id} to re-align internal payment state with PayPal.",
                is_incident_likely=True,
                insufficient_evidence=False,
                model_name="deterministic-rule-engine-v1",
            )

        # SCENARIO 6: Successful Payment
        if status == "CAPTURED":
            has_capture_event = any("CAPTURE" in event["event_type"].upper() and event["status"].upper() in ("SUCCESS", "COMPLETED", "CAPTURED") for event in facts.get("events_summary", []))
            return AIInvestigationResponse(
                root_cause="Payment is marked captured in the stored PayTrace record.",
                confidence=0.7 if has_capture_event else 0.55,
                severity="LOW",
                facts=[
                    f"The stored payment status is {status}.",
                    *[f"Recorded event: {event['event_type']} at {event['occurred_at']} (source: {event['source']}, status: {event['status']})." for event in facts.get("events_summary", [])],
                    f"Linked webhook records found: {webhooks_count}.",
                ],
                inferences=[
                    "PayTrace's stored status does not independently confirm the current PayPal ledger state.",
                ],
                customer_impact="Customer-visible checkout experience is not included in this payment evidence.",
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
            inferences=["The available evidence is insufficient to identify a root cause."],
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
        """Calls OpenAI, Grok (xAI), or Groq with structured JSON output."""
        prompt = f"""
You are the PayTrace AI Investigator. Analyze the supplied persisted payment or incident evidence and return structured findings.
Strictly adhere to the facts provided. Never invent missing events. Separate FACT, INFERENCE, and RECOMMENDATION. A missing webhook record means only that no linked record was found; it does not prove PayPal failed to send one. A local payment status is not an independent live provider check. Never claim a browser-visible outcome unless it is in evidence. For every statement about an API call, event, webhook, or timeline, cite a corresponding evidence record in facts or say it is unknown. Do not present a hypothesis as a confirmed root cause.
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
        model_name = settings.effective_ai_model
        api_key = settings.effective_ai_api_key
        endpoint = settings.effective_ai_endpoint

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are PayTrace AI Investigator. Use only supplied persisted evidence. Clearly separate observed facts, inferences, and unknowns. Never invent API responses, webhooks, customer behavior, or causes. Return only JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(endpoint, headers=headers, json=body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())
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
                model_name=model_name,
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
            created_at=utc_now(),
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
        incident_facts = evidence_gatherer.get_incident_facts(db, incident_id) if incident_id else {}
        if incident_id and not incident_facts.get("error"):
            facts_data = {"incident": incident_facts["incident"], "affected_payments": incident_facts["affected_payments"]}
        evidence_ids = [e["id"] for e in facts_data.get("events_summary", [])][:5]
        if incident_id and incident_facts and not incident_facts.get("error"):
            evidence_ids = incident_facts["evidence_event_ids"][:20]

        query = question or (messages[-1]["content"] if messages else "Explain the status")
        conversation = [message for message in messages[-12:] if message.get("role") in ("user", "assistant")]
        if settings.is_ai_configured and facts_data and not facts_data.get("error"):
            try:
                answer = await AIInvestigator._call_chat_llm(facts_data, conversation, query)
                if answer:
                    return {"response": answer, "grounded_facts": AIInvestigator._grounded_fact_labels(facts_data), "recommended_action": None, "evidence_event_ids": evidence_ids}
            except Exception as exc:
                logger.warning("AI chat provider call failed; using evidence-only response: %s", exc)

        if incident_id:
            incident = incident_facts.get("incident", {}) if incident_facts else {}
            related = incident_facts.get("affected_payments", []) if incident_facts else []
            if incident_facts.get("error"):
                reply = "I couldn't retrieve the incident record. Check the incident ID and try again."
            elif "network" in query.lower() or "console" in query.lower() or "session" in query.lower():
                signals = [signal for payment in related for signal in payment.get("session_signals_summary", []) if signal.get("category") in ("network", "console")]
                reply = f"Retrieved {len(signals)} linked network/console records across {len(related)} rule-matched payments. These records show correlation only and do not establish causation."
            elif "payment" in query.lower() or "affected" in query.lower():
                reply = f"The incident rule matched {len(related)} payment records (up to 50 retrieved). " + "; ".join(f"{p.get('payment_id')}: {p.get('status')}, {p.get('failure_code') or 'no failure code recorded'}" for p in related[:10])
            else:
                reply = f"Stored incident {incident.get('id')} is {incident.get('status')} ({incident.get('severity')}), triggered by {incident.get('rule') or 'an unrecorded rule'}. Stored root cause: {incident.get('root_cause') or 'not available'}. {len(related)} rule-matched payments were retrieved."
            return {"response": reply, "grounded_facts": [f"Incident status: {incident.get('status', 'unknown')}", f"Detection rule: {incident.get('rule') or 'not recorded'}", f"Rule-matched payments retrieved: {len(related)}"], "recommended_action": None, "evidence_event_ids": evidence_ids}

        status = facts_data.get("status", "UNKNOWN")
        timed_out = facts_data.get("timed_out", False)
        denied = facts_data.get("denied", False)

        normalized_query = query.lower()
        if not facts_data or facts_data.get("error"):
            reply = "I couldn't retrieve a matching payment record, so I can't assess its lifecycle. Check the payment ID and try again."
        elif "webhook" in normalized_query:
            if facts_data.get("webhooks_count", 0):
                events = facts_data.get("webhooks_summary", [])
                reply = "Linked webhook records found: " + "; ".join(f"{item['event_type']} (signature verified: {item['verified']})" for item in events) + "."
            else:
                reply = "No webhook events were found for this payment in the available records. This does not prove that PayPal never sent a webhook."
        elif "session" in normalized_query or "network" in normalized_query or "console" in normalized_query:
            if facts_data.get("has_session_recording"):
                signals = facts_data.get("session_signals_summary", [])
                network = [event for event in signals if event.get("category") == "network"]
                console = [event for event in signals if event.get("category") == "console"]
                samples = []
                for event in signals:
                    details = event.get("details", {})
                    label = details.get("url") or details.get("message") or event.get("event_type")
                    if details.get("status") is not None:
                        label = f"{label} (HTTP {details['status']})"
                    status_code = details.get("status")
                    if event.get("severity") in ("error", "warn") or isinstance(status_code, (int, float)) and status_code >= 400:
                        samples.append(f"{event['occurred_at']} {event['category']}: {label}")
                reply = f"The linked browser session has {facts_data.get('session_events_count', 0)} stored events, including {len(network)} network and {len(console)} console samples in the retrieved evidence. "
                reply += "Recorded warning/error samples: " + "; ".join(samples[:5]) + "." if samples else "No warning/error network or console samples were present in the retrieved recent evidence."
                reply += " This correlation alone does not establish that a browser event caused the payment outcome."
            else:
                reply = "No linked browser session recording was found in the available payment records."
        elif "timeline" in normalized_query or "lifecycle" in normalized_query:
            events = facts_data.get("events_summary", [])
            reply = "Recorded lifecycle: " + ("; ".join(f"{event['occurred_at']} — {event['event_type']} ({event['source']}, {event['status']})" for event in events) if events else "no payment events are stored for this payment") + "."
        elif "duplicate" in normalized_query or "retry" in normalized_query:
            if timed_out or status == "CAPTURE_UNCERTAIN":
                reply = (
                    "The stored payment is in an uncertain state. The available records do not confirm the provider's final capture result, so do not blindly retry. Reconcile the provider order and review linked webhook records first."
                )
            else:
                reply = f"The stored status is {status}. I found no evidence here that a retry is safe or necessary; review the payment detail and provider state before retrying."
        elif "refund" in normalized_query:
            reply = (
                "PayTrace policy mandates that all refund actions require explicit human operator approval. "
                "You can initiate a refund proposal from the payment actions panel, which routes into the Human Approval Inbox."
            )
        elif settings.is_ai_configured:
            try:
                system_prompt = (
                    "You are PayTrace AI Investigator chatting with an authorized payments operator. "
                    "Answer strictly grounded in the following payment evidence facts. "
                    "Never invent facts or transactions. "
                    f"EVIDENCE: {json.dumps(facts_data)}"
                )
                chat_msgs = [{"role": "system", "content": system_prompt}]
                for m in messages[-4:]:
                    chat_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
                if question and not any(m.get("content") == question for m in messages):
                    chat_msgs.append({"role": "user", "content": question})

                headers = {
                    "Authorization": f"Bearer {settings.effective_ai_api_key}",
                    "Content-Type": "application/json"
                }
                body = {
                    "model": settings.effective_ai_model,
                    "messages": chat_msgs,
                    "temperature": 0.2
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(settings.effective_ai_endpoint, headers=headers, json=body)
                    if resp.status_code == 200:
                        reply = resp.json()["choices"][0]["message"]["content"]
                    else:
                        raise ValueError(f"HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"AI chat call failed ({settings.effective_ai_provider}), falling back to grounded rule engine: {e}")
                reply = (
                    f"Based on the cross-signal evidence for payment `{payment_id}` (current status: `{status}`), "
                    f"the investigation detected {facts_data.get('event_count', 0)} lifecycle events and "
                    f"{facts_data.get('webhooks_count', 0)} verified webhooks. "
                    f"Root cause summary: {facts_data.get('failure_reason') or 'Normal settlement or pending outcome.'}"
                )
        else:
            events = facts_data.get("events_summary", [])
            reply = f"The stored status is {status}. "
            if facts_data.get("failure_reason"):
                reply += f"Stored failure reason: {facts_data['failure_reason']}. "
            else:
                reply += "No failure reason is stored. "
            reply += f"I found {facts_data.get('event_count', 0)} payment lifecycle event(s) and {facts_data.get('webhooks_count', 0)} linked webhook record(s)."

        return {
            "response": reply,
            "grounded_facts": [
                f"Payment Status: {status}",
                f"Amount: {facts_data.get('amount', 0.0)} {facts_data.get('currency', 'USD')}",
                *( [f"PayPal Order ID: {facts_data['paypal_order_id']}"] if facts_data.get("paypal_order_id") else [] ),
            ],
            "recommended_action": "Reconcile provider order state before any capture retry" if (timed_out or status == "CAPTURE_UNCERTAIN") else None,
            "evidence_event_ids": evidence_ids,
        }

    @staticmethod
    def _grounded_fact_labels(facts: Dict[str, Any]) -> List[str]:
        incident = facts.get("incident")
        if incident:
            related = incident.get("related_payments", [])
            return [
                f"Incident status: {incident.get('status', 'unknown')}",
                f"Incident severity: {incident.get('severity', 'unknown')}",
                f"Detection rule: {incident.get('rule', 'unknown')}",
                f"Affected payments loaded: {len(related)}",
                f"Supporting evidence records: {len(facts.get('evidence_event_ids', []))}",
            ]
        labels = [f"Stored payment status: {facts.get('status', 'unknown')}", f"Payment events stored: {facts.get('event_count', 0)}", f"Linked webhook records stored: {facts.get('webhooks_count', 0)}"]
        if facts.get("paypal_order_id"):
            labels.append(f"PayPal order ID: {facts['paypal_order_id']}")
        return labels

    @staticmethod
    async def _call_chat_llm(facts: Dict[str, Any], messages: List[Dict[str, str]], question: str) -> Optional[str]:
        prompt = {
            "question": question,
            "evidence": facts,
            "conversation": messages,
        }
        headers = {"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": settings.AI_MODEL or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are PayTrace's payment investigation assistant. Answer the latest question directly, using only the supplied persisted evidence and prior conversation for context. Do not invent facts. Say when evidence is missing. A missing webhook record does not prove PayPal did not send one. Distinguish facts from hypotheses. Do not claim a live provider lookup."},
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

ai_investigator = AIInvestigator()
