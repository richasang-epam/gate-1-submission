"""FNOLOrchestrator — agent loop using Claude API tool_use.

Each claim is a single synchronous invocation. The orchestrator calls tools in
order, handles escalation polling, and exits when the claim reaches COMPLETE or
ERROR state.
"""
import json
import logging
import time
from typing import Any

import anthropic

from fnol_agent.config import config
import fnol_agent.tools as tools

logger = logging.getLogger(__name__)

ORCHESTRATOR_MODEL = "claude-sonnet-4-6"
HUMAN_REVIEW_POLL_INTERVAL_S = 60
HUMAN_REVIEW_SLA_LIMIT_S = 90 * 60

SYSTEM_PROMPT = """You are FNOLOrchestrator, an AI agent that processes First Notice of Loss (FNOL) insurance claims end-to-end within a 2-hour SLA.

## MANDATORY TOOL CALL SEQUENCE — HAPPY PATH
1. ingest_claim → creates CRM record, returns claim_id and reference_number
2. send_acknowledgment (template_id="receipt_acknowledgment") — MUST fire immediately after ingest, BEFORE extraction
3. update_claim_state → EXTRACTING
4. parse_claim_document → extract structured data from raw text
5. update_claim_state → EXTRACTED (or ESCALATED — see Escalation Rules)
6. update_claim_state → VALIDATING
7. lookup_policy → validate policy and coverage
8. update_claim_state → VALIDATED (or ESCALATED)
9. classify_severity → determine HIGH/MEDIUM/LOW
10. update_claim_state → TRIAGED (or ESCALATED)
11. update_claim_state → ROUTING
12. get_adjuster_assignment → route to adjuster (pass coverage_type from policy result)
13. update_claim_state → ROUTED
14. send_acknowledgment (template_id="routing_complete")
15. update_claim_state → COMPLETE

## ESCALATION TRIGGERS — call escalate_to_human if ANY of these occur
- extraction_confidence < 0.80 → reason_code="low_extraction_confidence"
- Any required field in missing_fields → reason_code="missing_required_field:{field_name}"
- policy_status = "not_found" → reason_code="policy_not_found"
- policy_status = "lapsed" or "grace_period" → reason_code="policy_status_requires_review"
- policy_status = "unavailable" (system down) → reason_code="policy_system_unavailable"
- loss_type_covered = null (ambiguous) → reason_code="coverage_ambiguous"
- severity = "HIGH" → reason_code="high_severity"
- triage confidence < 0.85 → reason_code="low_triage_confidence"
- get_adjuster_assignment returns assigned=false → reason_code="no_available_adjuster"

## ESCALATION SEQUENCE (when ANY trigger fires)
1. update_claim_state → ESCALATED (include escalation_reason in metadata)
2. escalate_to_human (priority="urgent" if severity=HIGH or SLA < 45 min remaining; else "standard")
3. send_acknowledgment (template_id="escalation_notice")
4. poll_human_review repeatedly (every 60 seconds) until status="completed" or 90 minutes elapsed
5. On status="completed", read human_decision.action:
   - "approve_routing" → apply any field updates, re-run get_adjuster_assignment, send routing_complete ACK, update_claim_state COMPLETE
   - "close_claim" → update_claim_state COMPLETE
   - "reject" → update_claim_state ERROR
6. If 90 minutes elapse with no decision → escalate_to_human reason_code="human_review_sla_breach", update_claim_state ERROR

## SAFETY RULE
NEVER route a HIGH-severity claim through the automated path. Always escalate HIGH severity to human review before routing.

## SLA MONITORING
Check received_at vs current time at each step. If < 45 minutes remaining in the 2-hour SLA, use priority="urgent" on all escalations.

## ERROR HANDLING
If any tool returns an error after retries, call update_claim_state with new_state="ERROR" and include error details in metadata.

## SEND ACKNOWLEDGMENT — REQUIRED TEMPLATE DATA
- receipt_acknowledgment: {"reference_number": ..., "claimant_name": ..., "received_at": ...}
- routing_complete: {"reference_number": ..., "adjuster_name": ..., "adjuster_contact": ..., "next_contact_window": "within 4 business hours"}
- escalation_notice: {"reference_number": ..., "estimated_resolution_time": "within 90 minutes"}

When processing is complete, output a brief one-paragraph summary of the claim outcome."""

TOOL_DEFINITIONS = [
    {
        "name": "ingest_claim",
        "description": "Creates CRM record, assigns reference number. Call first. Immediately after, call send_acknowledgment with template_id='receipt_acknowledgment'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "raw_content": {"type": "string", "description": "Original unstructured claim text"},
                "source": {
                    "type": "string",
                    "enum": ["email", "phone_transcript", "web_form"],
                },
            },
            "required": ["raw_content", "source"],
        },
    },
    {
        "name": "parse_claim_document",
        "description": "Calls claude-haiku-4-5-20251001 to extract structured data. Returns extraction_confidence (0-1) and missing_fields. Escalate if confidence < 0.80.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "raw_content": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["claim_id", "raw_content", "source"],
        },
    },
    {
        "name": "lookup_policy",
        "description": "Calls SOAP policy admin: GetPolicyDetails + ValidateCoverage. Escalate if policy_status is not_found/lapsed/grace_period/unavailable or loss_type_covered is null.",
        "input_schema": {
            "type": "object",
            "properties": {
                "policy_number": {"type": "string"},
                "loss_type": {"type": "string"},
                "estimated_amount": {"type": ["number", "null"]},
            },
            "required": ["policy_number", "loss_type"],
        },
    },
    {
        "name": "classify_severity",
        "description": "Deterministic severity rules. Returns severity (HIGH/MEDIUM/LOW) and confidence. Escalate if severity=HIGH or confidence < 0.85.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loss_type": {"type": "string"},
                "estimated_loss_amount": {"type": ["number", "null"]},
                "third_party_involved": {"type": ["boolean", "null"]},
                "policy_status": {"type": "string"},
                "coverage_limit": {"type": "number"},
            },
            "required": ["loss_type"],
        },
    },
    {
        "name": "get_adjuster_assignment",
        "description": "Routes claim to adjuster: lowest queue depth, tie-break by longest idle. Returns assigned=false if no eligible adjuster (escalate). Pass coverage_type from the policy coverage_types list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "coverage_type": {"type": "string"},
            },
            "required": ["claim_id", "severity", "coverage_type"],
        },
    },
    {
        "name": "send_acknowledgment",
        "description": "Sends templated acknowledgment to claimant. Called twice on automated path (receipt_acknowledgment at intake; routing_complete after adjuster assigned) and once on escalation path (escalation_notice).",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "claimant_contact": {
                    "type": "object",
                    "properties": {
                        "email": {"type": ["string", "null"]},
                        "phone": {"type": ["string", "null"]},
                    },
                },
                "template_id": {
                    "type": "string",
                    "enum": ["receipt_acknowledgment", "routing_complete", "escalation_notice"],
                },
                "template_data": {"type": "object"},
            },
            "required": ["claim_id", "claimant_contact", "template_id", "template_data"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Creates human review task in CRM. Returns task_id for polling. Include raw text, extracted fields, policy summary, and escalation reason in dossier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "reason_code": {"type": "string"},
                "dossier": {"type": "object"},
                "priority": {"type": "string", "enum": ["urgent", "standard"]},
            },
            "required": ["claim_id", "reason_code", "dossier", "priority"],
        },
    },
    {
        "name": "poll_human_review",
        "description": "Checks review task status. Returns status ('pending'|'completed') and human_decision when completed. Call every 60 seconds; stop after 90 minutes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "update_claim_state",
        "description": "Writes state transition to CRM audit log. Call after every major state change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "new_state": {
                    "type": "string",
                    "enum": [
                        "RECEIVED", "EXTRACTING", "EXTRACTED", "VALIDATING", "VALIDATED",
                        "TRIAGED", "ROUTING", "ROUTED", "ACKNOWLEDGED", "ESCALATED",
                        "HUMAN_REVIEWED", "COMPLETE", "ERROR",
                    ],
                },
                "metadata": {"type": "object"},
            },
            "required": ["claim_id", "new_state", "metadata"],
        },
    },
]

TOOL_REGISTRY: dict[str, Any] = {
    "ingest_claim": tools.ingest_claim,
    "parse_claim_document": tools.parse_claim_document,
    "lookup_policy": tools.lookup_policy,
    "classify_severity": tools.classify_severity,
    "get_adjuster_assignment": tools.get_adjuster_assignment,
    "send_acknowledgment": tools.send_acknowledgment,
    "escalate_to_human": tools.escalate_to_human,
    "poll_human_review": tools.poll_human_review,
    "update_claim_state": tools.update_claim_state,
}


def run_claim(raw_content: str, source: str) -> dict:
    """Process one FNOL claim end-to-end. Returns final outcome dict."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    messages = [
        {
            "role": "user",
            "content": (
                f"Process this FNOL claim.\n\n"
                f"Source: {source}\n\n"
                f"Claim text:\n{raw_content}"
            ),
        }
    ]

    poll_start: dict[str, float] = {}  # task_id → timestamp of first poll

    while True:
        response = client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            summary = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return {"status": "complete", "summary": summary}

        if response.stop_reason != "tool_use":
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            return {"status": "error", "reason": f"stop_reason={response.stop_reason}"}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            logger.info("Tool call: %s %s", tool_name, json.dumps(tool_input)[:120])

            # Throttle polling to 60-second intervals to avoid tight loops
            if tool_name == "poll_human_review":
                task_id = tool_input.get("task_id", "")
                now = time.time()
                if task_id not in poll_start:
                    poll_start[task_id] = now
                elif now - poll_start[task_id] > HUMAN_REVIEW_SLA_LIMIT_S:
                    result = {
                        "task_id": task_id,
                        "status": "sla_breached",
                        "human_decision": None,
                    }
                    tool_results.append(_tool_result(block.id, result))
                    continue
                else:
                    elapsed = now - poll_start.get(f"{task_id}_last", now - HUMAN_REVIEW_POLL_INTERVAL_S)
                    if elapsed < HUMAN_REVIEW_POLL_INTERVAL_S:
                        wait = HUMAN_REVIEW_POLL_INTERVAL_S - elapsed
                        logger.info("Waiting %.0fs before next poll for %s", wait, task_id)
                        time.sleep(wait)
                poll_start[f"{task_id}_last"] = time.time()

            try:
                fn = TOOL_REGISTRY.get(tool_name)
                if fn is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    result = fn(**tool_input)
                    if hasattr(result, "model_dump"):
                        result = result.model_dump()
            except Exception as exc:
                logger.exception("Tool %s raised: %s", tool_name, exc)
                result = {"error": str(exc), "tool": tool_name}

            logger.info("Tool result: %s → %s", tool_name, json.dumps(result)[:120])
            tool_results.append(_tool_result(block.id, result))

        messages.append({"role": "user", "content": tool_results})


def _tool_result(tool_use_id: str, result: dict) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, default=str),
    }
