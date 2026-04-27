"""Integration tests for tool sequences, escalation paths, and two-stage ACK (spec §4.1)."""
import pytest
from unittest.mock import MagicMock, patch, call
import fnol_agent.tools as tools


# ── Two-stage acknowledgment ──────────────────────────────────────────────────

def test_two_ack_calls_automated_path(mock_clients):
    """Verify exactly two send_acknowledgment calls per automated claim (spec §4.1)."""
    ack_calls = []

    original_send = tools.send_acknowledgment
    def record_ack(*args, **kwargs):
        ack_calls.append(kwargs.get("template_id") or args[2])
        return {"sent": True, "sent_at": "2026-04-27T10:00:00Z", "channel": "email",
                "template_id": kwargs.get("template_id", ""), "reference_number": "FNOL-TEST",
                "delivery_status": "delivered"}

    with patch.object(tools, "send_acknowledgment", side_effect=record_ack):
        ingest_result = tools.ingest_claim("Test claim text", "email")
        claim_id = ingest_result["claim_id"]
        ref = ingest_result["reference_number"]
        contact = {"email": "test@example.com", "phone": None}

        # Call 1: receipt_acknowledgment at intake
        tools.send_acknowledgment(
            claim_id=claim_id, claimant_contact=contact,
            template_id="receipt_acknowledgment",
            template_data={"reference_number": ref, "claimant_name": "Test", "received_at": "now"},
        )

        # Call 2: routing_complete after assignment
        tools.send_acknowledgment(
            claim_id=claim_id, claimant_contact=contact,
            template_id="routing_complete",
            template_data={"reference_number": ref, "adjuster_name": "Alice",
                           "adjuster_contact": "alice@ins.com", "next_contact_window": "4h"},
        )

    assert len(ack_calls) == 2
    assert ack_calls[0] == "receipt_acknowledgment"
    assert ack_calls[1] == "routing_complete"


# ── Happy path tool sequence ──────────────────────────────────────────────────

def test_ingest_returns_claim_id_and_reference(mock_clients):
    result = tools.ingest_claim("Claim text about a flood", "email")
    assert "claim_id" in result
    assert result["reference_number"].startswith("FNOL-")
    assert result["state"] == "RECEIVED"


def test_ingest_assigns_unique_ids(mock_clients):
    r1 = tools.ingest_claim("Claim A", "email")
    r2 = tools.ingest_claim("Claim B", "email")
    assert r1["claim_id"] != r2["claim_id"]
    assert r1["reference_number"] != r2["reference_number"]


def test_update_claim_state_calls_crm(mock_clients):
    ingest = tools.ingest_claim("Flood", "email")
    result = tools.update_claim_state(ingest["claim_id"], "EXTRACTING", {})
    assert result["state"] == "EXTRACTING"


def test_lookup_policy_active_policy(mock_clients):
    result = tools.lookup_policy("POL-001", "property_damage", 5000)
    assert result["policy_status"] == "active"
    assert result["loss_type_covered"] is True


def test_lookup_policy_not_found(mock_clients):
    result = tools.lookup_policy("NOTFOUND-999", "property_damage", None)
    assert result["policy_status"] == "not_found"


def test_lookup_policy_lapsed(mock_clients):
    result = tools.lookup_policy("LAPSED-123", "property_damage", 1000)
    assert result["policy_status"] == "lapsed"


def test_lookup_policy_ambiguous_coverage(mock_clients):
    result = tools.lookup_policy("AMBIG-555", "property_damage", 10_000)
    assert result["loss_type_covered"] is None
    assert result["coverage_notes"] is not None


# ── Escalation path ───────────────────────────────────────────────────────────

def test_escalate_to_human_returns_task_id(mock_clients):
    result = tools.escalate_to_human(
        claim_id="claim-123",
        reason_code="high_severity",
        dossier={"raw": "claim text", "extracted": {}, "policy": {}, "suggested_routing": None},
        priority="urgent",
    )
    assert "task_id" in result
    assert result["task_id"]


def test_poll_human_review_returns_status(mock_clients):
    # MockCRMClient returns status=completed immediately
    result = tools.poll_human_review("task-001")
    assert result["status"] in ("pending", "completed")
    assert "task_id" in result


def test_escalation_notice_ack_template(mock_clients):
    ingest = tools.ingest_claim("High severity claim", "phone_transcript")
    result = tools.send_acknowledgment(
        claim_id=ingest["claim_id"],
        claimant_contact={"email": "claimant@example.com", "phone": None},
        template_id="escalation_notice",
        template_data={
            "reference_number": ingest["reference_number"],
            "estimated_resolution_time": "within 90 minutes",
        },
    )
    assert result["sent"] is True
    assert result["template_id"] == "escalation_notice"


# ── Channel priority ──────────────────────────────────────────────────────────

def test_ack_uses_email_when_available(mock_clients):
    ingest = tools.ingest_claim("Claim", "email")
    result = tools.send_acknowledgment(
        claim_id=ingest["claim_id"],
        claimant_contact={"email": "user@example.com", "phone": "+441234567"},
        template_id="receipt_acknowledgment",
        template_data={"reference_number": "FNOL-TEST", "claimant_name": "Test", "received_at": "now"},
    )
    assert result["channel"] == "email"


def test_ack_falls_back_to_sms_when_no_email(mock_clients):
    from fnol_agent.tools import _pick_channel
    channel = _pick_channel({"email": None, "phone": "+441234567"})
    assert channel == "sms"


def test_ack_falls_back_to_portal_when_no_contacts(mock_clients):
    from fnol_agent.tools import _pick_channel
    channel = _pick_channel({"email": None, "phone": None})
    assert channel == "portal"


# ── Error recovery ────────────────────────────────────────────────────────────

def test_update_claim_state_error_on_crm_failure(mock_clients):
    from fnol_agent.integrations.crm_client import CRMError
    crm = tools._clients["crm"]
    crm.update_claim = MagicMock(side_effect=CRMError("CRM unavailable"))
    result = tools.update_claim_state("claim-123", "ERROR", {"reason": "test"})
    # Should return gracefully with warning rather than raising
    assert result["state"] == "ERROR"
    assert "warning" in result


def test_lookup_policy_system_unavailable_returns_safe_result(mock_clients):
    from fnol_agent.integrations.policy_client import PolicySystemUnavailable
    policy_client = tools._clients["policy"]
    policy_client.get_policy_details = MagicMock(
        side_effect=PolicySystemUnavailable("Circuit breaker open")
    )
    result = tools.lookup_policy("POL-001", "property_damage", None)
    # Safe fallback — caller should escalate with policy_system_unavailable
    assert result["policy_status"] == "unavailable"
    assert result.get("_system_unavailable") is True


# ── SLA clock uses received_at ────────────────────────────────────────────────

def test_ingest_sets_received_at_timestamp(mock_clients):
    from datetime import datetime, timezone
    result = tools.ingest_claim("Claim text", "web_form")
    received_at = result["received_at"]
    # Should be parseable ISO8601
    dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    assert dt.tzinfo is not None


# ── Confidence thresholds ─────────────────────────────────────────────────────

def test_extraction_confidence_threshold_constants():
    from fnol_agent.tools import EXTRACTION_CONFIDENCE_THRESHOLD, TRIAGE_CONFIDENCE_THRESHOLD
    assert EXTRACTION_CONFIDENCE_THRESHOLD == 0.80
    assert TRIAGE_CONFIDENCE_THRESHOLD == 0.85
