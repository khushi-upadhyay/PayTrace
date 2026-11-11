"""
PayTrace LangGraph Investigation Workflow
Stateful, agentic investigation of payment failures using LangGraph + LangChain.

Architecture:
  gather_initial_evidence → analyze_evidence → select_investigation_tools
  → execute_tools → verify_hypothesis (loop up to MAX_CYCLES) → generate_report

Safety guarantees:
- Never retries capture, initiates refunds, or modifies payment state.
- Gracefully degrades when LangGraph/LangChain are not installed.
- Falls back to deterministic investigator on any graph/LLM failure.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session

from app.agents.investigation_tools import (
    TOOL_DESCRIPTIONS,
    analyze_failure_patterns,
    compare_successful_payments,
    find_similar_failures,
    get_incident_overview,
    get_payment_facts,
    get_paypal_order,
    inspect_payment_timeline,
    inspect_webhook_events,
)
from app.core.config import settings
from app.schemas.ai import AIInvestigationResponse

logger = logging.getLogger(__name__)

MAX_INVESTIGATION_CYCLES = 3

# ─── LangGraph availability guard ────────────────────────────────────────────
try:
    from langgraph.graph import StateGraph, END  # type: ignore
    LANGGRAPH_AVAILABLE = True
    logger.info("LangGraph is available — agentic investigation enabled.")
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning(
        "LangGraph not installed — investigation will use direct pipeline (no graph loops)."
    )


# ─── Graph State ─────────────────────────────────────────────────────────────
class InvestigationState(TypedDict, total=False):
    investigation_id: str
    payment_id: str
    question: str
    db: Any  # SQLAlchemy Session (not serializable; kept in memory only)

    # Evidence
    initial_evidence: Dict[str, Any]
    tool_results: Dict[str, Any]  # tool_name -> result

    # Analysis
    hypotheses: List[Dict[str, Any]]  # [{root_cause, confidence, missing_evidence, next_action}]
    selected_tools: List[str]

    # Cycle control
    cycle: int
    investigation_complete: bool
    stop_reason: str

    # Final report
    report: Optional[AIInvestigationResponse]
    tools_used: List[str]
    nodes_executed: List[str]


# ─── Node A: gather_initial_evidence ─────────────────────────────────────────
def node_gather_initial_evidence(state: InvestigationState) -> InvestigationState:
    """Collect all local database evidence using existing evidence gatherer."""
    t0 = time.monotonic()
    payment_id = state["payment_id"]
    db: Session = state["db"]

    logger.info(
        "investigation_id=%s node=gather_initial_evidence payment_id=%s",
        state.get("investigation_id"),
        payment_id,
    )

    facts = get_payment_facts(db, payment_id)
    similar = find_similar_failures(db, payment_id)
    comparison = compare_successful_payments(db, payment_id)
    webhooks = inspect_webhook_events(db, payment_id)
    timeline = inspect_payment_timeline(db, payment_id)

    initial_evidence = {
        "payment_facts": facts,
        "similar_failures": similar,
        "comparison_with_successful": comparison,
        "webhook_events": webhooks,
        "timeline": timeline,
    }

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "investigation_id=%s node=gather_initial_evidence elapsed_ms=%d "
        "event_count=%d webhook_count=%d similar_count=%d",
        state.get("investigation_id"),
        elapsed_ms,
        facts.get("event_count", 0),
        webhooks.get("total_webhook_events", 0),
        similar.get("similar_count", 0),
    )

    nodes = list(state.get("nodes_executed", []))
    nodes.append("gather_initial_evidence")
    return {
        **state,
        "initial_evidence": initial_evidence,
        "tool_results": {},
        "tools_used": [],
        "cycle": 0,
        "investigation_complete": False,
        "nodes_executed": nodes,
    }


# ─── Node B: analyze_evidence ─────────────────────────────────────────────────
def node_analyze_evidence(state: InvestigationState) -> InvestigationState:
    """
    Use LLM to analyze evidence and generate hypotheses.
    Falls back to deterministic analysis if LLM unavailable.
    """
    t0 = time.monotonic()
    investigation_id = state.get("investigation_id")
    cycle = state.get("cycle", 0)
    logger.info(
        "investigation_id=%s node=analyze_evidence cycle=%d",
        investigation_id,
        cycle,
    )

    evidence = state.get("initial_evidence", {})
    tool_results = state.get("tool_results", {})
    all_evidence = {**evidence, "additional_tool_results": tool_results}

    hypotheses = _analyze_with_llm(all_evidence, state.get("question", ""))
    if hypotheses is None:
        hypotheses = _deterministic_hypotheses(evidence)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "investigation_id=%s node=analyze_evidence cycle=%d hypotheses=%d elapsed_ms=%d",
        investigation_id,
        cycle,
        len(hypotheses),
        elapsed_ms,
    )

    nodes = list(state.get("nodes_executed", []))
    nodes.append(f"analyze_evidence_cycle_{cycle}")
    return {**state, "hypotheses": hypotheses, "nodes_executed": nodes}


def _analyze_with_llm(
    all_evidence: Dict[str, Any], question: str
) -> Optional[List[Dict[str, Any]]]:
    """Call LLM synchronously (httpx sync) to analyze evidence and return hypotheses."""
    if not settings.is_ai_configured:
        return None

    import httpx

    prompt = f"""You are PayTrace AI Payment Investigator analyzing evidence to form hypotheses.

EVIDENCE:
{json.dumps(all_evidence, indent=2, default=str)}

QUESTION: {question}

SAFETY RULES (mandatory):
- Never recommend retrying a capture without confirmed reconciliation first.
- Never assume a timeout means failure. The capture may have succeeded at PayPal.
- Never assume a missing webhook means the payment failed.
- Distinguish VERIFIED FACTS from INFERENCES.

Analyze the evidence and return a JSON array of hypotheses (1 to 3 items):
[
  {{
    "root_cause": "concise root cause string",
    "confidence": 0.0 to 1.0,
    "supporting_evidence": ["list of specific evidence items that support this"],
    "contradicting_evidence": ["list of evidence that contradicts this"],
    "missing_evidence": ["what additional evidence would confirm or deny this"],
    "next_investigation_action": "one of: get_paypal_order | inspect_webhook_events | find_similar_failures | compare_successful_payments | inspect_payment_timeline | analyze_failure_patterns | none",
    "severity": "LOW | MEDIUM | HIGH | CRITICAL"
  }}
]

Return ONLY the JSON array. No markdown. No explanation."""

    try:
        headers = {
            "Authorization": f"Bearer {settings.effective_ai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.effective_ai_model,
            "messages": [
                {"role": "system", "content": "You are PayTrace AI Investigator. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        # Wrap array in object for providers requiring json_object
        body["messages"][0]["content"] += " Wrap the hypotheses array as {\"hypotheses\": [...]}."

        with httpx.Client(timeout=25.0) as client:
            resp = client.post(settings.effective_ai_endpoint, headers=headers, json=body)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            parsed = json.loads(cleaned)

            # Handle both {hypotheses: [...]} and [...] formats
            if isinstance(parsed, dict):
                hyps = parsed.get("hypotheses", [])
            elif isinstance(parsed, list):
                hyps = parsed
            else:
                return None

            # Validate and sanitize
            valid = []
            for h in hyps[:3]:  # max 3 hypotheses
                if isinstance(h, dict) and "root_cause" in h:
                    valid.append({
                        "root_cause": str(h.get("root_cause", ""))[:512],
                        "confidence": float(h.get("confidence", 0.7)),
                        "supporting_evidence": h.get("supporting_evidence", []),
                        "contradicting_evidence": h.get("contradicting_evidence", []),
                        "missing_evidence": h.get("missing_evidence", []),
                        "next_investigation_action": h.get("next_investigation_action", "none"),
                        "severity": h.get("severity", "MEDIUM"),
                    })
            return valid if valid else None

    except Exception as exc:
        logger.warning("LLM hypothesis analysis failed: %s", exc)
        return None


def _deterministic_hypotheses(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate hypotheses using deterministic rules when LLM is unavailable."""
    facts = evidence.get("payment_facts", {})
    status = facts.get("status", "UNKNOWN")
    failure_code = facts.get("failure_code")
    timed_out = facts.get("timed_out", False)
    denied = facts.get("denied", False)
    webhooks = evidence.get("webhook_events", {})
    similar = evidence.get("similar_failures", {})

    if timed_out or status == "CAPTURE_UNCERTAIN":
        return [{
            "root_cause": "Merchant backend timed out awaiting PayPal capture response",
            "confidence": 0.9,
            "supporting_evidence": ["CAPTURE_UNCERTAIN status", "TIMEOUT event in timeline"],
            "contradicting_evidence": [],
            "missing_evidence": ["PayPal order live state", "Webhook confirmation"],
            "next_investigation_action": "get_paypal_order",
            "severity": "HIGH",
        }]
    if denied or failure_code in ("CAPTURE_DENIED", "INSTRUMENT_DECLINED"):
        return [{
            "root_cause": "Payment instrument declined by issuing bank or PayPal",
            "confidence": 0.88,
            "supporting_evidence": [f"failure_code={failure_code}", f"status={status}"],
            "contradicting_evidence": [],
            "missing_evidence": ["Similar failure pattern" if similar.get("similar_count", 0) < 2 else ""],
            "next_investigation_action": "find_similar_failures" if similar.get("similar_count", 0) < 2 else "none",
            "severity": "MEDIUM",
        }]
    if status == "PENDING":
        return [{
            "root_cause": "Capture pending PayPal risk review or settlement",
            "confidence": 0.85,
            "supporting_evidence": [f"status={status}"],
            "contradicting_evidence": [],
            "missing_evidence": ["Webhook confirmation of resolution"],
            "next_investigation_action": "inspect_webhook_events",
            "severity": "MEDIUM",
        }]
    if status == "CAPTURED" and webhooks.get("total_webhook_events", 0) == 0:
        return [{
            "root_cause": "Capture is recorded locally, but no linked webhook record is available",
            "confidence": 0.82,
            "supporting_evidence": ["CAPTURED status", "zero webhook events"],
            "contradicting_evidence": [],
            "missing_evidence": ["Webhook delivery logs"],
            "next_investigation_action": "analyze_failure_patterns",
            "severity": "LOW",
        }]
    if status == "CAPTURED":
        return [{
            "root_cause": "Payment lifecycle completed normally with full API and webhook verification",
            "confidence": 0.99,
            "supporting_evidence": ["Status is CAPTURED", f"Verified webhook events: {webhooks.get('total_webhook_events', 0)}"],
            "contradicting_evidence": [],
            "missing_evidence": [],
            "next_investigation_action": "none",
            "severity": "LOW",
        }]
    webhooks_count = webhooks.get("total_webhook_events", 0)
    if (status in ("CREATED", "INITIATED") and webhooks_count > 0) or (status == "APPROVED" and facts.get("paypal_capture_id")):
        return [{
            "root_cause": "Payment state mismatch detected: asynchronous webhooks diverge from local payment status",
            "confidence": 0.88,
            "supporting_evidence": [f"Internal payment status is {status}", f"Webhook events exist ({webhooks_count})"],
            "contradicting_evidence": [],
            "missing_evidence": ["Reconciliation with PayPal order API"],
            "next_investigation_action": "get_paypal_order",
            "severity": "HIGH",
        }]
    return [{
        "root_cause": "Insufficient evidence to determine root cause",
        "confidence": 0.4,
        "supporting_evidence": [f"status={status}"],
        "contradicting_evidence": [],
        "missing_evidence": ["More payment lifecycle events", "PayPal order state"],
        "next_investigation_action": "inspect_payment_timeline",
        "severity": "MEDIUM",
    }]


# ─── Node C: select_investigation_tools ──────────────────────────────────────
def node_select_investigation_tools(state: InvestigationState) -> InvestigationState:
    """
    Determine which tools are needed to verify or refute the current hypotheses.
    Selection is driven by LLM-generated next_investigation_action fields.
    """
    investigation_id = state.get("investigation_id")
    cycle = state.get("cycle", 0)
    hypotheses = state.get("hypotheses", [])
    already_used = set(state.get("tools_used", []))

    # Collect tool recommendations from all hypotheses
    requested = set()
    for h in hypotheses:
        action = h.get("next_investigation_action", "none")
        if action and action != "none":
            requested.add(action)

    # Filter out already-used tools to avoid redundant calls
    selected = [t for t in requested if t not in already_used and t in TOOL_DESCRIPTIONS]

    # An uncertain capture always requires provider reconciliation before report generation.
    facts = state.get("initial_evidence", {}).get("payment_facts", {})
    if facts.get("status") == "CAPTURE_UNCERTAIN" and "get_paypal_order" not in already_used:
        selected = list(dict.fromkeys([*selected, "get_paypal_order"]))
    question = state.get("question", "").lower()
    needs_provider_reconciliation = any(
        word in question for word in ("retry", "capture", "paypal", "provider", "order", "reconcile")
    )
    if (
        needs_provider_reconciliation
        and facts.get("paypal_order_id")
        and "get_paypal_order" not in already_used
    ):
        selected = list(dict.fromkeys([*selected, "get_paypal_order"]))

    # Safety: never select tools that modify state (none exist in our toolset, but explicit check)
    ALLOWED_TOOLS = set(TOOL_DESCRIPTIONS.keys())
    selected = [t for t in selected if t in ALLOWED_TOOLS]

    logger.info(
        "investigation_id=%s node=select_tools cycle=%d requested=%s selected=%s already_used=%s",
        investigation_id,
        cycle,
        list(requested),
        selected,
        list(already_used),
    )

    nodes = list(state.get("nodes_executed", []))
    nodes.append(f"select_tools_cycle_{cycle}")
    return {**state, "selected_tools": selected, "nodes_executed": nodes}


# ─── Node D: execute_tools ───────────────────────────────────────────────────
def node_execute_tools(state: InvestigationState) -> InvestigationState:
    """
    Execute the selected investigation tools.
    Results are stored in tool_results keyed by tool name.
    SAFETY: All tools are read-only. No tool can modify payment state.
    """
    import asyncio

    investigation_id = state.get("investigation_id")
    payment_id = state["payment_id"]
    db: Session = state["db"]
    selected = state.get("selected_tools", [])
    cycle = state.get("cycle", 0)

    logger.info(
        "investigation_id=%s node=execute_tools cycle=%d tools=%s",
        investigation_id,
        cycle,
        selected,
    )

    tool_results = dict(state.get("tool_results", {}))
    tools_used = list(state.get("tools_used", []))
    facts = state.get("initial_evidence", {}).get("payment_facts", {})

    for tool_name in selected:
        t0 = time.monotonic()
        try:
            result = _execute_single_tool(tool_name, payment_id, db, facts)
            tool_results[tool_name] = result
            tools_used.append(tool_name)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "investigation_id=%s tool=%s elapsed_ms=%d cycle=%d",
                investigation_id,
                tool_name,
                elapsed_ms,
                cycle,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "investigation_id=%s tool=%s error=%s elapsed_ms=%d",
                investigation_id,
                tool_name,
                exc,
                elapsed_ms,
            )
            tool_results[tool_name] = {"error": str(exc), "tool": tool_name}

    nodes = list(state.get("nodes_executed", []))
    nodes.append(f"execute_tools_cycle_{cycle}")
    return {
        **state,
        "tool_results": tool_results,
        "tools_used": tools_used,
        "nodes_executed": nodes,
    }


def _execute_single_tool(
    tool_name: str, payment_id: str, db: Session, facts: Dict[str, Any]
) -> Dict[str, Any]:
    """Dispatch to the correct tool function."""
    import asyncio

    if tool_name == "get_payment_facts":
        return get_payment_facts(db, payment_id)
    elif tool_name == "get_paypal_order":
        order_id = facts.get("paypal_order_id", "")
        if not order_id:
            return {"skipped": True, "reason": "No PayPal order ID available"}
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, get_paypal_order(order_id, facts.get("paypal_capture_id"), facts.get("source_mode")))
                    return future.result(timeout=45)
            else:
                return asyncio.run(get_paypal_order(order_id, facts.get("paypal_capture_id"), facts.get("source_mode")))
        except Exception as exc:
            return {"skipped": True, "reason": f"async execution failed: {exc}"}
    elif tool_name == "inspect_webhook_events":
        return inspect_webhook_events(db, payment_id)
    elif tool_name == "find_similar_failures":
        return find_similar_failures(db, payment_id)
    elif tool_name == "compare_successful_payments":
        return compare_successful_payments(db, payment_id)
    elif tool_name == "inspect_payment_timeline":
        return inspect_payment_timeline(db, payment_id)
    elif tool_name == "analyze_failure_patterns":
        return analyze_failure_patterns(db, payment_id)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ─── Node E: verify_hypothesis ────────────────────────────────────────────────
def node_verify_hypothesis(state: InvestigationState) -> InvestigationState:
    """
    Analyze tool results against existing hypotheses.
    Determines whether to continue investigating or move to report generation.
    Enforces MAX_INVESTIGATION_CYCLES to prevent infinite loops.
    """
    t0 = time.monotonic()
    investigation_id = state.get("investigation_id")
    cycle = state.get("cycle", 0) + 1
    hypotheses = state.get("hypotheses", [])
    tool_results = state.get("tool_results", {})

    logger.info(
        "investigation_id=%s node=verify_hypothesis cycle=%d tools_available=%d",
        investigation_id,
        cycle,
        len(tool_results),
    )

    # Check cycle limit
    if cycle >= MAX_INVESTIGATION_CYCLES:
        logger.info(
            "investigation_id=%s verify: max cycles (%d) reached — stopping.",
            investigation_id,
            MAX_INVESTIGATION_CYCLES,
        )
        nodes = list(state.get("nodes_executed", []))
        nodes.append(f"verify_hypothesis_cycle_{cycle}")
        return {
            **state,
            "cycle": cycle,
            "investigation_complete": True,
            "stop_reason": f"max_cycles_reached ({MAX_INVESTIGATION_CYCLES})",
            "nodes_executed": nodes,
        }

    # Check if hypotheses are already high-confidence
    top = max(hypotheses, key=lambda h: h.get("confidence", 0), default={})
    top_confidence = top.get("confidence", 0)
    top_action = top.get("next_investigation_action", "none")

    # Sufficient evidence check
    if top_confidence >= 0.88 and not tool_results:
        # High confidence without needing tools — proceed to report
        complete = True
        stop_reason = "sufficient_confidence_without_additional_tools"
    elif tool_results and top_action == "none":
        # Tools executed and no more recommended — proceed to report
        complete = True
        stop_reason = "tools_exhausted_no_further_action"
    elif top_confidence >= 0.92 and tool_results:
        # Very high confidence after tool results
        complete = True
        stop_reason = "high_confidence_post_tool_verification"
    else:
        complete = False
        stop_reason = "needs_more_evidence"

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "investigation_id=%s verify_hypothesis cycle=%d complete=%s "
        "stop_reason=%s top_confidence=%.2f elapsed_ms=%d",
        investigation_id,
        cycle,
        complete,
        stop_reason,
        top_confidence,
        elapsed_ms,
    )

    nodes = list(state.get("nodes_executed", []))
    nodes.append(f"verify_hypothesis_cycle_{cycle}")
    return {
        **state,
        "cycle": cycle,
        "investigation_complete": complete,
        "stop_reason": stop_reason,
        "nodes_executed": nodes,
    }


# ─── Node F: generate_investigation_report ───────────────────────────────────
def node_generate_report(state: InvestigationState) -> InvestigationState:
    """
    Generate structured investigation report.
    Uses LLM for narrative synthesis, falls back to deterministic report.
    SAFETY: Never includes fabricated facts. All claims grounded in state evidence.
    """
    t0 = time.monotonic()
    investigation_id = state.get("investigation_id")
    payment_id = state["payment_id"]
    hypotheses = state.get("hypotheses", [])
    initial_evidence = state.get("initial_evidence", {})
    tool_results = state.get("tool_results", {})
    tools_used = state.get("tools_used", [])
    cycle = state.get("cycle", 0)
    stop_reason = state.get("stop_reason", "unknown")

    logger.info(
        "investigation_id=%s node=generate_report cycle=%d stop_reason=%s tools_used=%s",
        investigation_id,
        cycle,
        stop_reason,
        tools_used,
    )

    all_evidence = {
        **initial_evidence,
        "additional_tool_results": tool_results,
        "investigation_metadata": {
            "cycles_completed": cycle,
            "stop_reason": stop_reason,
            "tools_used": tools_used,
        },
    }

    # Try LLM report generation
    report = _generate_report_with_llm(
        payment_id=payment_id,
        question=state.get("question", ""),
        hypotheses=hypotheses,
        all_evidence=all_evidence,
        tools_used=tools_used,
        investigation_id=investigation_id or "",
    )

    if report is None:
        report = _generate_deterministic_report(
            payment_id=payment_id,
            hypotheses=hypotheses,
            initial_evidence=initial_evidence,
            tool_results=tool_results,
            tools_used=tools_used,
        )

    # Surface the provider retrieval provenance in the API result itself. The
    # local payment's source_mode alone does not prove that reconciliation GETs
    # succeeded during this particular investigation.
    provider_result = tool_results.get("get_paypal_order")
    if isinstance(provider_result, dict):
        retrieval = provider_result.get("retrieval_status", "UNKNOWN")
        source = provider_result.get("source", "UNKNOWN")
        if retrieval == "LIVE_RESPONSE":
            captures = provider_result.get("captures", [])
            capture_states = ", ".join(
                str(item.get("status", "UNKNOWN")) for item in captures if isinstance(item, dict)
            ) or "none returned"
            provenance = f"Provider evidence: {source}; retrieval_status=LIVE_RESPONSE; order status={provider_result.get('status', 'UNKNOWN')}; capture states={capture_states}."
        else:
            provenance = f"Provider evidence: {source}; retrieval_status={retrieval}; {provider_result.get('reason', 'No live provider response was available for this investigation.')}"
        report.facts = [fact for fact in report.facts if not str(fact).startswith("Provider evidence:")]
        report.facts.append(provenance)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "investigation_id=%s node=generate_report confidence=%.2f "
        "severity=%s model=%s elapsed_ms=%d",
        investigation_id,
        report.confidence,
        report.severity,
        report.model_name,
        elapsed_ms,
    )

    nodes = list(state.get("nodes_executed", []))
    nodes.append("generate_report")
    report.workflow_nodes = nodes
    report.tool_calls = list(tools_used)
    report.execution_mode = "langgraph" if LANGGRAPH_AVAILABLE else "direct_pipeline"
    report.langsmith_tracing_enabled = settings.is_langsmith_tracing_enabled
    return {**state, "report": report, "nodes_executed": nodes}


def _generate_report_with_llm(
    payment_id: str,
    question: str,
    hypotheses: List[Dict[str, Any]],
    all_evidence: Dict[str, Any],
    tools_used: List[str],
    investigation_id: str,
) -> Optional[AIInvestigationResponse]:
    """Generate structured report via LLM call."""
    if not settings.is_ai_configured:
        return None

    import httpx

    prompt = f"""You are PayTrace AI Investigator generating a final investigation report.

USER'S INVESTIGATION QUESTION (answer this directly):
{question}

HYPOTHESES FORMED:
{json.dumps(hypotheses, indent=2, default=str)}

ALL EVIDENCE (initial + tool results):
{json.dumps(all_evidence, indent=2, default=str)}

TOOLS USED: {tools_used}

SAFETY RULES (non-negotiable):
- Only state verified facts. Never fabricate payment events, captures, or webhooks.
- Respect the evidence source label. DEMO_RESPONSE is simulated and must never be described as PayPal Sandbox evidence.
- A PayPal provider fact is live only when the tool result says retrieval_status=LIVE_RESPONSE.
- If evidence is insufficient, set insufficient_evidence=true and confidence<0.5.
- Never recommend retrying a capture without reconciliation confirmation.
- Never recommend autonomous refunds — always require human approval.
- Do not claim a systemic outage without 5+ similar failures as evidence.
- Make the summary and recommendation specific to the user's question. Compare the corresponding retrieved evidence when asked, and say when evidence does not answer it.

Return ONLY valid JSON (no markdown) matching this schema:
{{
  "root_cause": "string (max 300 chars)",
  "root_cause_category": "TIMEOUT | INSTRUMENT_DECLINE | WEBHOOK_FAILURE | STATE_MISMATCH | PENDING_REVIEW | SUCCESSFUL | INSUFFICIENT_EVIDENCE | OTHER",
  "confidence": 0.0-1.0,
  "severity": "LOW | MEDIUM | HIGH | CRITICAL",
  "facts": ["verified fact 1", "verified fact 2"],
  "inferences": ["inference 1"],
  "contradicting_evidence": ["contradiction if any"],
  "customer_impact": "string",
  "business_impact": "string",
  "recommendation": "string (safe, human-approved actions only)",
  "is_incident_likely": true|false,
  "insufficient_evidence": true|false,
  "investigation_summary": "2-3 sentence narrative"
}}"""

    try:
        headers = {
            "Authorization": f"Bearer {settings.effective_ai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.effective_ai_model,
            "messages": [
                {"role": "system", "content": "You are PayTrace AI Investigator. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(settings.effective_ai_endpoint, headers=headers, json=body)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            parsed = json.loads(cleaned)

            return AIInvestigationResponse(
                payment_id=payment_id,
                root_cause=str(parsed.get("root_cause", ""))[:512],
                confidence=float(parsed.get("confidence", 0.7)),
                severity=str(parsed.get("severity", "MEDIUM")),
                facts=list(parsed.get("facts", [])),
                inferences=list(parsed.get("inferences", [])),
                customer_impact=str(parsed.get("customer_impact", "")),
                business_impact=str(parsed.get("business_impact", "")),
                recommendation=str(parsed.get("recommendation", "")),
                is_incident_likely=bool(parsed.get("is_incident_likely", False)),
                insufficient_evidence=bool(parsed.get("insufficient_evidence", False)),
                model_name=f"langgraph/{settings.effective_ai_model}",
                comparison_notes=parsed.get("investigation_summary"),
            )

    except Exception as exc:
        logger.warning("LLM report generation failed: %s", exc)
        return None


def _generate_deterministic_report(
    payment_id: str,
    hypotheses: List[Dict[str, Any]],
    initial_evidence: Dict[str, Any],
    tool_results: Dict[str, Any],
    tools_used: List[str],
) -> AIInvestigationResponse:
    """Build a report from the best hypothesis + evidence without LLM."""
    facts_data = initial_evidence.get("payment_facts", {})
    webhooks = initial_evidence.get("webhook_events", {})
    similar = initial_evidence.get("similar_failures", {})

    # Pick best hypothesis
    top = max(hypotheses, key=lambda h: h.get("confidence", 0), default={})
    root_cause = top.get("root_cause", "Insufficient evidence to determine root cause")
    confidence = float(top.get("confidence", 0.4))
    severity = top.get("severity", "MEDIUM")

    # Build facts from evidence
    facts = list(top.get("supporting_evidence", []))
    status = facts_data.get("status", "UNKNOWN")
    amount = facts_data.get("amount", 0.0)
    currency = facts_data.get("currency", "USD")
    order_id = facts_data.get("paypal_order_id", "UNKNOWN")

    if order_id and order_id != "UNKNOWN":
        facts.append(f"PayPal order ID: {order_id}")
    facts.append(f"Payment status: {status}")
    if facts_data.get("paypal_capture_id"):
        facts.append(f"Locally recorded PayPal capture ID: {facts_data['paypal_capture_id']}")
    facts.append(f"Event count: {facts_data.get('event_count', 0)}")
    facts.append(f"Webhook events: {webhooks.get('total_webhook_events', 0)}")
    if webhooks.get("total_webhook_events", 0) == 0:
        facts.append("No linked webhook records were found; this does not prove PayPal failed to send a webhook.")
    for event in facts_data.get("events_summary", [])[:20]:
        facts.append(
            f"Merchant lifecycle event {event.get('event_type')}: source={event.get('source')}, status={event.get('status')}, latency_ms={event.get('latency_ms')}, simulated={event.get('is_simulated')}."
        )
    for webhook in webhooks.get("verified_events", [])[:20]:
        facts.append(
            f"Webhook {webhook.get('event_type')}: signature_verified={webhook.get('signature_verified')}, processing_status={webhook.get('processing_status')}, received_at={webhook.get('received_at')}."
        )
    for webhook in webhooks.get("unverified_events", [])[:20]:
        facts.append(
            f"Webhook {webhook.get('event_type')}: signature_verified=false, processing_status={webhook.get('processing_status')}, received_at={webhook.get('received_at')}."
        )
    if similar.get("similar_count", 0) > 0:
        facts.append(f"Similar failures found: {similar.get('similar_count')}")

    # PayPal reconciliation result if fetched
    paypal_result = tool_results.get("get_paypal_order", {})
    live_provider_capture_confirmed = (
        paypal_result.get("retrieval_status") == "LIVE_RESPONSE"
        and paypal_result.get("status") == "COMPLETED"
        and any(
            capture.get("status") == "COMPLETED"
            and capture.get("retrieval_status") in ("LIVE_RESPONSE", "FROM_LIVE_ORDER_RESPONSE")
            for capture in paypal_result.get("captures", [])
        )
    )
    demo_capture_confirmed = (
        paypal_result.get("retrieval_status") == "DEMO_RESPONSE"
        and paypal_result.get("status") == "COMPLETED"
        and any(capture.get("status") == "COMPLETED" for capture in paypal_result.get("captures", []))
    )
    if "get_paypal_order" in tool_results:
        pp = paypal_result
        if pp.get("retrieval_status") == "LIVE_RESPONSE" and pp.get("status"):
            facts.append(f"PayPal live order status: {pp['status']}")
            captures = pp.get("captures", [])
            if captures:
                for capture in captures:
                    facts.append(f"PayPal capture {capture.get('capture_id') or 'ID unavailable'} status: {capture.get('status') or 'unknown'}.")
                if live_provider_capture_confirmed:
                    facts.append("Live PayPal order and capture responses confirm that the payment was captured.")
            else:
                facts.append("No capture details were returned by the live order lookup; provider capture state remains unconfirmed.")
        elif pp.get("retrieval_status") == "UNAVAILABLE":
            facts.append("Live PayPal reconciliation was unavailable; provider capture state remains unconfirmed.")
        elif pp.get("retrieval_status") == "DEMO_RESPONSE":
            facts.append(f"Simulated demo provider order status: {pp.get('status') or 'unknown'} (not PayPal Sandbox evidence).")
            for capture in pp.get("captures", []):
                facts.append(f"Simulated demo capture {capture.get('capture_id') or 'ID unavailable'} status: {capture.get('status') or 'unknown'} (not PayPal evidence).")

    inferences = list(top.get("inferences", []))
    missing = top.get("missing_evidence", [])
    insufficient = confidence < 0.5 or "Insufficient" in root_cause

    is_timeout = (
        "timed out" in root_cause.lower()
        or "timeout" in root_cause.lower()
        or "uncertain" in root_cause.lower()
        or status in ("CAPTURE_UNCERTAIN", "TIMEOUT_BEFORE_RESPONSE")
        or facts_data.get("timed_out", False)
    )
    is_declined = (
        "declined" in root_cause.lower()
        or "denied" in root_cause.lower()
        or status in ("DENIED", "CAPTURE_FAILED")
        or facts_data.get("denied", False)
    )
    is_captured = (status == "CAPTURED" or live_provider_capture_confirmed) and "delayed" not in root_cause.lower()
    is_mismatch = "mismatch" in root_cause.lower() or "diverge" in root_cause.lower()

    if not inferences:
        if is_timeout:
            inferences = [
                "PayPal may have successfully processed the capture on their ledger despite the local HTTP timeout.",
                "A blind capture retry risks duplicate charges on the customer's payment instrument.",
            ]
        elif is_declined:
            inferences = [
                "Buyer instrument has insufficient balance, expiration, or fraud flag from issuing bank.",
                "Retry with identical payment instrument will consistently fail.",
            ]
        elif is_mismatch:
            inferences = [
                "Local transaction record fell out of sync with provider ledger due to dropped state machine transition or race condition.",
            ]
        elif status == "PENDING":
            inferences = [
                "Funds have not yet settled; transaction may require risk review or clearing delay.",
                "Do not release goods or services until webhook confirms PAYMENT.CAPTURE.COMPLETED.",
            ]
        elif status == "CAPTURED" and webhooks.get("total_webhook_events", 0) == 0:
            inferences = [
                "Downstream systems that rely exclusively on asynchronous webhooks may not have fulfilled the order yet.",
            ]
        elif status == "CAPTURED":
            inferences = [
                "Payment is fully settled in PayPal Sandbox with confirmed API and webhook verification.",
            ]
        else:
            inferences = [
                "Evidence in database is insufficient or events are incomplete to draw definitive conclusions.",
            ]

    if live_provider_capture_confirmed and status != "CAPTURED":
        recommendation = "PayPal confirms a completed capture while PayTrace remains uncertain. Reconcile the local payment record from this provider evidence; do not issue another capture."
    elif demo_capture_confirmed:
        recommendation = "SIMULATED DEMO ONLY: the in-memory provider reports a completed capture. This is not PayPal Sandbox evidence. In a real transaction, reconcile the live PayPal order and capture before retrying."
    elif is_timeout:
        recommendation = "DO NOT RETRY CAPTURE. Reconcile order state with PayPal or verify incoming webhooks before taking further action to prevent duplicate charges."
    elif is_declined:
        recommendation = "Prompt customer to select an alternative payment method. Do not automatically re-attempt with current instrument."
    elif is_mismatch:
        recommendation = "Run provider reconciliation via GET /paypal/orders/{order_id} to re-align internal payment state with PayPal."
    elif is_captured:
        recommendation = "No action required. Transaction is healthy and fully settled."
    else:
        recommendation = "Review evidence and take appropriate action under human supervision."

    return AIInvestigationResponse(
        payment_id=payment_id,
        root_cause=root_cause,
        confidence=confidence,
        severity=severity,
        facts=facts,
        inferences=inferences,
        customer_impact=f"Customer checkout status: {status}",
        business_impact=f"Transaction value: ${amount:.2f} {currency}",
        recommendation=recommendation,
        is_incident_likely=similar.get("pattern_detected", False),
        insufficient_evidence=insufficient,
        model_name="langgraph/deterministic-pipeline-v1",
        comparison_notes=f"Missing evidence: {'; '.join(missing)}" if missing else None,
    )


# ─── Graph Router: should_continue_or_report ─────────────────────────────────
def should_continue_or_report(state: InvestigationState) -> str:
    """LangGraph conditional edge: route to execute_tools or generate_report."""
    if state.get("investigation_complete", False):
        return "generate_report"
    selected = state.get("selected_tools", [])
    if selected:
        return "execute_tools"
    return "generate_report"


def after_execute_tools(state: InvestigationState) -> str:
    """After executing tools, go back to analyze evidence."""
    return "analyze_evidence"


# ─── Build the LangGraph ──────────────────────────────────────────────────────
def build_investigation_graph():
    """Construct and compile the LangGraph investigation workflow."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(InvestigationState)

    graph.add_node("gather_initial_evidence", node_gather_initial_evidence)
    graph.add_node("analyze_evidence", node_analyze_evidence)
    graph.add_node("select_investigation_tools", node_select_investigation_tools)
    graph.add_node("execute_tools", node_execute_tools)
    graph.add_node("verify_hypothesis", node_verify_hypothesis)
    graph.add_node("generate_report", node_generate_report)

    graph.set_entry_point("gather_initial_evidence")

    graph.add_edge("gather_initial_evidence", "analyze_evidence")
    graph.add_edge("analyze_evidence", "select_investigation_tools")
    graph.add_conditional_edges(
        "select_investigation_tools",
        should_continue_or_report,
        {
            "execute_tools": "execute_tools",
            "generate_report": "generate_report",
        },
    )
    graph.add_edge("execute_tools", "verify_hypothesis")
    graph.add_conditional_edges(
        "verify_hypothesis",
        lambda s: "generate_report" if s.get("investigation_complete") else "analyze_evidence",
        {
            "generate_report": "generate_report",
            "analyze_evidence": "analyze_evidence",
        },
    )
    graph.add_edge("generate_report", END)

    return graph.compile()


# ─── Direct pipeline (when LangGraph not available) ───────────────────────────
def run_direct_pipeline(
    db: Session,
    payment_id: str,
    question: str,
    investigation_id: str,
) -> AIInvestigationResponse:
    """
    Executes the same node sequence without LangGraph when the library is unavailable.
    Provides identical behavior (minus graph-level state management).
    """
    state: InvestigationState = {
        "investigation_id": investigation_id,
        "payment_id": payment_id,
        "question": question,
        "db": db,
        "initial_evidence": {},
        "tool_results": {},
        "hypotheses": [],
        "selected_tools": [],
        "cycle": 0,
        "investigation_complete": False,
        "stop_reason": "",
        "report": None,
        "tools_used": [],
        "nodes_executed": [],
    }

    state = node_gather_initial_evidence(state)
    state = node_analyze_evidence(state)

    for _ in range(MAX_INVESTIGATION_CYCLES):
        state = node_select_investigation_tools(state)
        selected = state.get("selected_tools", [])
        if not selected:
            state = {**state, "investigation_complete": True, "stop_reason": "no_tools_selected"}
            break
        state = node_execute_tools(state)
        state = node_verify_hypothesis(state)
        if state.get("investigation_complete"):
            break
        # Re-analyze with new tool results
        state = node_analyze_evidence(state)

    state = node_generate_report(state)
    report = state.get("report")
    if report is None:
        raise ValueError("Report generation returned None")
    report.execution_mode = "direct_pipeline"
    report.langsmith_tracing_enabled = settings.is_langsmith_tracing_enabled
    return report


# ─── Compiled graph (module-level singleton) ──────────────────────────────────
_compiled_graph = None


def get_investigation_graph():
    """Returns the compiled graph (lazy initialization)."""
    global _compiled_graph
    if _compiled_graph is None and LANGGRAPH_AVAILABLE:
        try:
            _compiled_graph = build_investigation_graph()
            logger.info("LangGraph investigation graph compiled successfully.")
        except Exception as exc:
            logger.error("Failed to compile LangGraph investigation graph: %s", exc)
    return _compiled_graph


# ─── Main entry point ─────────────────────────────────────────────────────────
def run_investigation_graph(
    db: Session,
    payment_id: str,
    question: str,
) -> AIInvestigationResponse:
    """
    Run the LangGraph investigation workflow (or direct pipeline if LangGraph unavailable).
    
    Returns a structured AIInvestigationResponse.
    Raises an exception if both graph and pipeline fail (caller should use deterministic fallback).
    """
    investigation_id = str(uuid.uuid4())
    t0 = time.monotonic()

    logger.info(
        "investigation_id=%s starting LangGraph investigation payment_id=%s langgraph=%s",
        investigation_id,
        payment_id,
        LANGGRAPH_AVAILABLE,
    )

    try:
        if LANGGRAPH_AVAILABLE:
            graph = get_investigation_graph()
            if graph is not None:
                initial_state: InvestigationState = {
                    "investigation_id": investigation_id,
                    "payment_id": payment_id,
                    "question": question,
                    "db": db,
                    "initial_evidence": {},
                    "tool_results": {},
                    "hypotheses": [],
                    "selected_tools": [],
                    "cycle": 0,
                    "investigation_complete": False,
                    "stop_reason": "",
                    "report": None,
                    "tools_used": [],
                    "nodes_executed": [],
                }
                final_state = graph.invoke(initial_state, config={"run_name": "PayTrace payment investigation", "tags": ["paytrace", "payment-investigation"]})
                report = final_state.get("report")
                if report is None:
                    raise ValueError("Graph returned no report")
                report.execution_mode = "langgraph"
                report.langsmith_tracing_enabled = settings.is_langsmith_tracing_enabled

                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    "investigation_id=%s completed via LangGraph graph elapsed_ms=%d "
                    "nodes=%s tools=%s cycles=%d",
                    investigation_id,
                    elapsed_ms,
                    final_state.get("nodes_executed", []),
                    final_state.get("tools_used", []),
                    final_state.get("cycle", 0),
                )
                return report

        # LangGraph not available or graph failed — use direct pipeline
        report = run_direct_pipeline(db, payment_id, question, investigation_id)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "investigation_id=%s completed via direct pipeline elapsed_ms=%d",
            investigation_id,
            elapsed_ms,
        )
        return report

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "investigation_id=%s graph/pipeline failed elapsed_ms=%d error=%s",
            investigation_id,
            elapsed_ms,
            exc,
            exc_info=True,
        )
        raise


class IncidentCommandState(TypedDict, total=False):
    db: Any
    question: str
    window_minutes: int
    evidence: Dict[str, Any]
    hypotheses: List[Dict[str, Any]]
    report: Optional[AIInvestigationResponse]


def _incident_command_gather(state: IncidentCommandState) -> IncidentCommandState:
    return {**state, "evidence": get_incident_overview(state["db"], state.get("window_minutes", 15))}


def _incident_command_analyze(state: IncidentCommandState) -> IncidentCommandState:
    evidence = state.get("evidence", {})
    hypotheses = _analyze_with_llm(evidence, state.get("question", ""))
    if hypotheses is None:
        failures = evidence.get("failure_pattern_counts", [])
        dominant = max(failures, key=lambda row: row.get("count", 0), default=None)
        hypotheses = [{
            "root_cause": (f"Most frequent recorded failure pattern: {dominant['failure_code']}" if dominant else "No failed payment pattern was recorded in the selected window."),
            "confidence": 0.6 if dominant else 0.35,
            "severity": "HIGH" if dominant and dominant.get("count", 0) >= 5 else "MEDIUM" if dominant else "LOW",
            "supporting_evidence": [f"SQL aggregation counted {dominant['count']} records for {dominant['failure_code']}." ] if dominant else ["SQL aggregation returned no failed payment records."],
            "inferences": [],
            "missing_evidence": [],
            "next_investigation_action": "none",
        }]
    return {**state, "hypotheses": hypotheses}


def _incident_command_report(state: IncidentCommandState) -> IncidentCommandState:
    evidence = state.get("evidence", {})
    hypotheses = state.get("hypotheses", [])
    report = _generate_report_with_llm(
        payment_id="fleet-level",
        question=state.get("question", ""),
        hypotheses=hypotheses,
        all_evidence={"sql_incident_overview": evidence},
        tools_used=["get_incident_overview"],
        investigation_id=str(uuid.uuid4()),
    )
    if report is None:
        failures = evidence.get("failure_pattern_counts", [])
        dominant = max(failures, key=lambda row: row.get("count", 0), default=None)
        statuses = evidence.get("payment_status_counts", {})
        uncertain_count = statuses.get("CAPTURE_UNCERTAIN", 0)
        report = AIInvestigationResponse(
            root_cause=hypotheses[0].get("root_cause", "Insufficient evidence to identify a failure pattern"),
            confidence=hypotheses[0].get("confidence", 0.35),
            severity=hypotheses[0].get("severity", "LOW"),
            facts=[
                f"SQL counted {sum(statuses.values())} payments updated in the last {evidence.get('window_minutes')} minutes.",
                f"Failed-payment count changed by {evidence.get('failed_payment_count_change', 0)} versus the immediately preceding {evidence.get('window_minutes')}-minute window.",
                f"SQL counted {uncertain_count} payments in CAPTURE_UNCERTAIN status.",
                f"Most frequent failure pattern: {dominant['failure_code']} ({dominant['count']} records)." if dominant else "No failed payment pattern was recorded in this window.",
                f"Reconciliation candidates retrieved: {evidence.get('reconciliation_candidate_count', 0)}.",
                f"Merchant event and webhook aggregates were retrieved from SQL for the same window.",
            ],
            inferences=["Compare merchant event latency and PayPal API evidence before attributing failures to a provider."],
            customer_impact=f"{sum(statuses.values())} recent payments are represented in this investigation window.",
            business_impact=f"{evidence.get('reconciliation_candidate_count', 0)} payment(s) need provider reconciliation review.",
            recommendation="Reconcile each CAPTURE_UNCERTAIN order with PayPal order and capture details and verified webhooks before any capture retry.",
            is_incident_likely=bool(dominant and dominant.get("count", 0) >= 3),
            insufficient_evidence=not bool(statuses),
            model_name="langgraph/sql-evidence-fallback-v1",
        )
    else:
        # Keep incident counts, window comparisons, and reconciliation totals
        # bound to SQL results even when the model writes the narrative.
        statuses = evidence.get("payment_status_counts", {})
        failures = evidence.get("failure_pattern_counts", [])
        dominant = max(failures, key=lambda row: row.get("count", 0), default=None)
        report.facts = [
            f"SQL counted {sum(statuses.values())} payments updated in the last {evidence.get('window_minutes')} minutes.",
            f"Failed-payment count changed by {evidence.get('failed_payment_count_change', 0)} versus the immediately preceding {evidence.get('window_minutes')}-minute window.",
            f"SQL counted {statuses.get('CAPTURE_UNCERTAIN', 0)} CAPTURE_UNCERTAIN payments.",
            f"Most frequent failure pattern: {dominant['failure_code']} ({dominant['count']} records)." if dominant else "No failed payment pattern was recorded in this window.",
            f"Reconciliation candidates retrieved: {evidence.get('reconciliation_candidate_count', 0)}.",
            f"Merchant backend event aggregates retrieved: {len(evidence.get('merchant_backend_event_aggregates', []))}.",
            f"Webhook processing status aggregates retrieved: {len(evidence.get('webhook_processing_counts', {}))}.",
            *[
                f"Merchant event {row['source']}/{row['event_type']}: count={row['count']}, average recorded latency_ms={row['average_latency_ms']}."
                for row in evidence.get("merchant_backend_event_aggregates", [])[:10]
            ],
            *[
                f"Webhook processing status {status}: {count} record(s)."
                for status, count in evidence.get("webhook_processing_counts", {}).items()
            ],
            *[
                f"Reconciliation candidate payment {row['payment_id']}: status={row['status']}, order_id={row.get('paypal_order_id') or 'not recorded'}; reconcile before retry."
                for row in evidence.get("reconciliation_candidates", [])
            ],
        ]
        report.customer_impact = f"{sum(statuses.values())} recent payment records were included in this query window."
        report.business_impact = f"{evidence.get('reconciliation_candidate_count', 0)} payment(s) were retrieved for reconciliation review."
        report.comparison_notes = "Incident counts and latency aggregates are SQL results. Source correlation alone does not establish whether PayPal or the merchant backend caused the failures."
        report.severity = "HIGH" if dominant and dominant.get("count", 0) >= 5 else "MEDIUM" if dominant else "LOW"
        report.is_incident_likely = bool(dominant and dominant.get("count", 0) >= 3)
        report.insufficient_evidence = not bool(statuses)
        report.recommendation = "Compare merchant backend latency with live PayPal order/capture evidence and verified webhook history. Reconcile CAPTURE_UNCERTAIN orders before any capture retry."
    report.payment_id = None
    report.workflow_nodes = ["aggregate_sql_evidence", "analyze_patterns", "generate_grounded_report"]
    report.tool_calls = ["get_incident_overview"]
    report.execution_mode = "langgraph"
    report.langsmith_tracing_enabled = settings.is_langsmith_tracing_enabled
    return {**state, "report": report}


def run_incident_command_graph(db: Session, question: str, window_minutes: int = 15) -> AIInvestigationResponse:
    """Run a fleet-level SQL evidence investigation through a small LangGraph workflow."""
    if not LANGGRAPH_AVAILABLE:
        raise RuntimeError("LangGraph is unavailable")
    graph = StateGraph(IncidentCommandState)
    graph.add_node("aggregate_sql_evidence", _incident_command_gather)
    graph.add_node("analyze_patterns", _incident_command_analyze)
    graph.add_node("generate_grounded_report", _incident_command_report)
    graph.set_entry_point("aggregate_sql_evidence")
    graph.add_edge("aggregate_sql_evidence", "analyze_patterns")
    graph.add_edge("analyze_patterns", "generate_grounded_report")
    graph.add_edge("generate_grounded_report", END)
    final_state = graph.compile().invoke(
        {"db": db, "question": question, "window_minutes": window_minutes},
        config={"run_name": "PayTrace incident command", "tags": ["paytrace", "incident-command", "sql-evidence"]},
    )
    report = final_state.get("report")
    if report is None:
        raise ValueError("Incident command graph returned no report")
    report.execution_mode = "langgraph"
    report.langsmith_tracing_enabled = settings.is_langsmith_tracing_enabled
    return report

