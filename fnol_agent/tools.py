"""All nine tool implementations for FNOLOrchestrator.

Client instances are module-level singletons initialised from config. Tests and
the demo override them via configure_clients() before calling any tool.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic

from fnol_agent.config import config
from fnol_agent.integrations.policy_client import PolicySystemUnavailable

logger = logging.getLogger(__name__)

# Required fields for extraction confidence formula (spec §3.4)
REQUIRED_FIELDS = [
    "claimant_name",
    "policy_number",
    "incident_date",
    "incident_description",
    "loss_type",
    "third_party_involved",
]

EXTRACTION_CONFIDENCE_THRESHOLD = 0.80
TRIAGE_CONFIDENCE_THRESHOLD = 0.85

_clients: dict = {"crm": None, "policy": None, "dms": None}


def configure_clients(crm=None, policy=None, dms=None) -> None:
    """Override client instances — used in tests and demo mode."""
    if crm is not None:
        _clients["crm"] = crm
    if policy is not None:
        _clients["policy"] = policy
    if dms is not None:
        _clients["dms"] = dms


def _crm():
    if _clients["crm"] is None:
        if config.MOCK_MODE:
            from fnol_agent.integrations.mock_clients import MockCRMClient
            _clients["crm"] = MockCRMClient()
        else:
            from fnol_agent.integrations.crm_client import CRMClient
            _clients["crm"] = CRMClient(
                config.CRM_BASE_URL, config.CRM_CLIENT_ID, config.CRM_CLIENT_SECRET
            )
    return _clients["crm"]


def _policy():
    if _clients["policy"] is None:
        if config.MOCK_MODE:
            from fnol_agent.integrations.mock_clients import MockPolicyClient
            _clients["policy"] = MockPolicyClient()
        else:
            from fnol_agent.integrations.policy_client import PolicyClient
            _clients["policy"] = PolicyClient(config.SOAP_WSDL_URL)
    return _clients["policy"]


def _dms():
    if _clients["dms"] is None:
        if config.MOCK_MODE:
            from fnol_agent.integrations.mock_clients import MockDMSClient
            _clients["dms"] = MockDMSClient()
        else:
            from fnol_agent.integrations.dms_client import DMSClient
            _clients["dms"] = DMSClient(config.DMS_BASE_URL, config.DMS_API_KEY)
    return _clients["dms"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_reference_number(claim_id: str) -> str:
    return f"FNOL-{claim_id[:8].upper()}"


# ── Tool 1 ────────────────────────────────────────────────────────────────────

def ingest_claim(raw_content: str, source: str) -> dict:
    """Creates CRM record, assigns reference number, returns initial ClaimRecord."""
    claim_id = str(uuid.uuid4())
    received_at = _now()
    reference_number = _make_reference_number(claim_id)

    try:
        _crm().create_claim(
            source=source,
            raw_content=raw_content,
            received_at=received_at,
            reference_number=reference_number,
        )
    except Exception as exc:
        logger.error("CRM create_claim failed: %s", exc)
        # Persist to fallback queue — claim must not be dropped (D5.A6)
        _persist_fallback(claim_id, "create_claim", {
            "source": source, "raw_content": raw_content,
            "received_at": received_at, "reference_number": reference_number,
        })

    return {
        "claim_id": claim_id,
        "reference_number": reference_number,
        "received_at": received_at,
        "source": source,
        "state": "RECEIVED",
    }


# ── Tool 2 ────────────────────────────────────────────────────────────────────

def parse_claim_document(claim_id: str, raw_content: str, source: str) -> dict:
    """Calls claude-haiku-4-5-20251001 to extract structured data.

    Confidence = (required fields present and not in missing_fields) / 6.
    """
    system_prompt = (
        "You are a claims extraction assistant for an insurance company.\n"
        "Your task is to extract structured data from the FNOL (first notice of loss) text provided.\n"
        "Return ONLY a valid JSON object matching the schema below. Do not infer or assume facts not\n"
        "explicitly stated in the text. If a required field cannot be determined, set it to null and\n"
        "add the field name to missing_fields. Do not fabricate policy numbers, dates, or amounts."
    )
    user_prompt = (
        f"Extract FNOL claim data from the following {source} submission.\n\n"
        f"---\n{raw_content}\n---\n\n"
        "Return JSON with exactly these fields:\n"
        "{\n"
        '  "claimant_name": string | null,\n'
        '  "claimant_contact": {"email": string | null, "phone": string | null},\n'
        '  "policy_number": string | null,\n'
        '  "incident_date": "YYYY-MM-DD" | null,\n'
        '  "incident_description": string (max 500 chars, normalised prose) | null,\n'
        '  "loss_type": "property_damage" | "bodily_injury" | "liability" | "theft" | "other" | null,\n'
        '  "estimated_loss_amount": number (USD) | null,\n'
        '  "third_party_involved": true | false | null,\n'
        '  "missing_fields": [list of required field names that could not be determined]\n'
        "}"
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_json = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]
        raw_json = raw_json.strip()

    try:
        llm_output = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.error("Extraction returned invalid JSON: %s", exc)
        return {
            "claimant_name": None,
            "claimant_contact": {"email": None, "phone": None},
            "policy_number": None,
            "incident_date": None,
            "incident_description": None,
            "loss_type": None,
            "estimated_loss_amount": None,
            "third_party_involved": None,
            "extraction_confidence": 0.0,
            "missing_fields": REQUIRED_FIELDS,
        }

    confidence = _calculate_extraction_confidence(llm_output)
    llm_output["extraction_confidence"] = confidence
    if "missing_fields" not in llm_output:
        llm_output["missing_fields"] = []

    # Upload raw + parsed to DMS for audit trail
    try:
        _dms().upload_claim(claim_id, raw_content, llm_output, [])
    except Exception as exc:
        logger.warning("DMS upload failed (non-blocking): %s", exc)

    return llm_output


def _calculate_extraction_confidence(llm_output: dict) -> float:
    """Spec §3.4 formula: (required fields present and not in missing_fields) / 6."""
    missing = set(llm_output.get("missing_fields", []))
    extracted_count = sum(
        1
        for f in REQUIRED_FIELDS
        if llm_output.get(f) is not None and f not in missing
    )
    return extracted_count / len(REQUIRED_FIELDS)


# ── Tool 3 ────────────────────────────────────────────────────────────────────

def lookup_policy(
    policy_number: str, loss_type: str, estimated_amount: Optional[float] = None
) -> dict:
    """Calls SOAP GetPolicyDetails + ValidateCoverage. Returns PolicyResult dict."""
    try:
        details = _policy().get_policy_details(policy_number)
        coverage = _policy().validate_coverage(policy_number, loss_type, estimated_amount)
        return {**details, **coverage}
    except PolicySystemUnavailable as exc:
        logger.error("Policy system unavailable: %s", exc)
        return {
            "policy_number": policy_number,
            "policy_status": "unavailable",
            "coverage_types": [],
            "coverage_limit": 0.0,
            "deductible": 0.0,
            "loss_type_covered": None,
            "coverage_notes": str(exc),
            "_system_unavailable": True,
        }


# ── Tool 4 ────────────────────────────────────────────────────────────────────

def classify_severity(
    loss_type: str,
    estimated_loss_amount: Optional[float] = None,
    third_party_involved: Optional[bool] = None,
    policy_status: str = "active",
    coverage_limit: float = 0.0,
) -> dict:
    """Deterministic severity classification. No LLM. First-match rule set (spec §3.4)."""
    loss_type = (loss_type or "").lower()
    amt = estimated_loss_amount
    third_party = bool(third_party_involved)

    # Rule 1
    if loss_type == "bodily_injury":
        return _triage("HIGH", "bodily_injury loss type", 1.0)

    # Rule 2
    if third_party and amt is not None and amt > 0:
        return _triage("HIGH", "third party involved with stated loss amount", 1.0)

    # Rule 3
    if loss_type == "liability":
        return _triage("HIGH", "liability loss type", 1.0)

    # Rule 4
    if amt is not None and amt > 50_000:
        return _triage("HIGH", f"estimated loss ${amt:,.0f} exceeds $50,000 threshold (A1)", 1.0)

    # Rule 5
    if amt is not None and 5_000 <= amt <= 50_000:
        return _triage("MEDIUM", f"estimated loss ${amt:,.0f} in $5,000–$50,000 range", 0.95)

    # Rule 6
    if amt is not None and amt < 5_000 and loss_type == "property_damage":
        return _triage("LOW", f"property_damage under $5,000 (est. ${amt:,.0f})", 1.0)

    # Rule 7: conservative default — amount unknown or loss type doesn't match clear rules
    return _triage(
        "MEDIUM",
        "conservative default: loss amount unknown or not clearly categorised",
        0.75,
    )


def _triage(severity: str, reason: str, confidence: float) -> dict:
    return {
        "severity": severity,
        "severity_reason": reason,
        "confidence": confidence,
        "requires_human_review": severity == "HIGH" or confidence < TRIAGE_CONFIDENCE_THRESHOLD,
    }


# ── Tool 5 ────────────────────────────────────────────────────────────────────

def get_adjuster_assignment(
    claim_id: str, severity: str, coverage_type: str
) -> dict:
    """Routes claim to adjuster with lowest queue depth. Tie-breaks by longest idle time."""
    adjusters = _crm().get_adjusters(specialisation=coverage_type)

    eligible = [a for a in adjusters if a.get("is_available", False)]
    if not eligible:
        return {"assigned": False, "reason": "no_available_adjuster"}

    eligible.sort(
        key=lambda a: (
            a.get("current_queue_depth", 999),
            # Ascending last_assigned_at — longest idle time wins ties
            a.get("last_assigned_at", ""),
        )
    )
    best = eligible[0]

    assignment = _crm().assign_adjuster(
        claim_id=claim_id,
        adjuster_id=best["id"],
        routing_reason=f"severity={severity} coverage={coverage_type} queue_depth={best.get('current_queue_depth')}",
    )

    return {
        "assigned": True,
        "assigned_adjuster_id": best["id"],
        "adjuster_name": assignment.get("adjuster_name", best.get("name")),
        "adjuster_specialisation": coverage_type,
        "routing_algorithm_version": "1.0",
        "routed_at": assignment.get("assigned_at", _now()),
        "adjuster_contact": best.get("contact_email", ""),
    }


# ── Tool 6 ────────────────────────────────────────────────────────────────────

def send_acknowledgment(
    claim_id: str,
    claimant_contact: dict,
    template_id: str,
    template_data: dict,
) -> dict:
    """Sends acknowledgment via CRM. Channel priority: email > sms > portal."""
    channel = _pick_channel(claimant_contact)
    recipient = {
        "email": claimant_contact.get("email"),
        "phone": claimant_contact.get("phone"),
    }

    try:
        result = _crm().send_communication(
            claim_id=claim_id,
            channel=channel,
            template_id=template_id,
            recipient=recipient,
            template_data=template_data,
        )
        if result.get("delivery_status") == "failed":
            # Retry on alternate channel
            alternate = _pick_channel(claimant_contact, exclude=channel)
            if alternate:
                result = _crm().send_communication(
                    claim_id=claim_id,
                    channel=alternate,
                    template_id=template_id,
                    recipient=recipient,
                    template_data=template_data,
                )
                channel = alternate
    except Exception as exc:
        logger.error("send_acknowledgment failed (non-blocking): %s", exc)
        return {"sent": False, "error": str(exc), "template_id": template_id}

    return {
        "sent": True,
        "sent_at": result.get("sent_at", _now()),
        "channel": channel,
        "template_id": template_id,
        "reference_number": template_data.get("reference_number", ""),
        "delivery_status": result.get("delivery_status", "unknown"),
    }


def _pick_channel(contact: dict, exclude: Optional[str] = None) -> str:
    if contact.get("email") and exclude != "email":
        return "email"
    if contact.get("phone") and exclude != "sms":
        return "sms"
    return "portal"


# ── Tool 7 ────────────────────────────────────────────────────────────────────

def escalate_to_human(
    claim_id: str, reason_code: str, dossier: dict, priority: str
) -> dict:
    """Creates CRM review task. Returns {task_id}."""
    result = _crm().create_review_task(
        claim_id=claim_id,
        priority=priority,
        reason=reason_code,
        dossier=dossier,
    )
    return {
        "task_id": result["task_id"],
        "queue_position": result.get("queue_position"),
        "assigned_reviewer_id": result.get("assigned_reviewer_id"),
        "escalated_at": _now(),
    }


# ── Tool 8 ────────────────────────────────────────────────────────────────────

def poll_human_review(task_id: str) -> dict:
    """Polls CRM review task status. Called every 60s by orchestrator until completed."""
    result = _crm().get_review_task(task_id)
    return {
        "task_id": task_id,
        "status": result.get("status", "pending"),
        "human_decision": result.get("human_decision"),
        "polled_at": _now(),
    }


# ── Tool 9 ────────────────────────────────────────────────────────────────────

def update_claim_state(claim_id: str, new_state: str, metadata: dict) -> dict:
    """Writes state transition to CRM audit log."""
    try:
        result = _crm().update_claim(claim_id=claim_id, state=new_state, metadata=metadata)
        return {"claim_id": claim_id, "state": new_state, "updated_at": result.get("updated_at", _now())}
    except Exception as exc:
        logger.error("update_claim_state failed for %s → %s: %s", claim_id, new_state, exc)
        return {"claim_id": claim_id, "state": new_state, "updated_at": _now(), "warning": str(exc)}


# ── Fallback queue ─────────────────────────────────────────────────────────────

def _persist_fallback(claim_id: str, operation: str, payload: dict) -> None:
    """Persist to Redis fallback queue when CRM is unavailable (D5.A6)."""
    try:
        import redis
        url = config.REDIS_URL or "redis://localhost:6379/0"
        r = redis.from_url(url)
        r.rpush("fnol:crm_fallback", json.dumps({
            "claim_id": claim_id, "operation": operation, "payload": payload,
        }))
        logger.info("Claim %s persisted to fallback queue", claim_id)
    except Exception as exc:
        logger.error("Fallback queue unavailable — claim %s may be lost: %s", claim_id, exc)
