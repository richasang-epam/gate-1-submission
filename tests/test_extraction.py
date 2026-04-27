"""Unit tests: extraction confidence formula and parse_claim_document (spec §3.4, §4.1)."""
import pytest
from unittest.mock import patch, MagicMock
from fnol_agent.tools import _calculate_extraction_confidence, REQUIRED_FIELDS


# ── Confidence formula ────────────────────────────────────────────────────────

def test_all_required_fields_present():
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": "POL-123",
        "incident_date": "2026-04-20",
        "incident_description": "Vehicle collision at junction",
        "loss_type": "property_damage",
        "third_party_involved": False,
        "missing_fields": [],
    }
    assert _calculate_extraction_confidence(output) == 1.0


def test_five_of_six_required_fields():
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": None,          # missing
        "incident_date": "2026-04-20",
        "incident_description": "Vehicle collision",
        "loss_type": "property_damage",
        "third_party_involved": False,
        "missing_fields": ["policy_number"],
    }
    confidence = _calculate_extraction_confidence(output)
    assert abs(confidence - 5 / 6) < 1e-9


def test_four_of_six_required_fields():
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": None,
        "incident_date": None,
        "incident_description": "Vehicle collision",
        "loss_type": "property_damage",
        "third_party_involved": False,
        "missing_fields": ["policy_number", "incident_date"],
    }
    confidence = _calculate_extraction_confidence(output)
    assert abs(confidence - 4 / 6) < 1e-9


def test_zero_required_fields():
    output = {f: None for f in REQUIRED_FIELDS}
    output["missing_fields"] = REQUIRED_FIELDS
    output["claimant_contact"] = {"email": None, "phone": None}
    assert _calculate_extraction_confidence(output) == 0.0


def test_optional_fields_do_not_affect_confidence():
    # estimated_loss_amount and claimant_contact are optional — not in REQUIRED_FIELDS
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": "POL-123",
        "incident_date": "2026-04-20",
        "incident_description": "Flood damage",
        "loss_type": "property_damage",
        "third_party_involved": True,
        "estimated_loss_amount": None,   # optional, absent
        "claimant_contact": {"email": None, "phone": None},  # optional, absent
        "missing_fields": [],
    }
    assert _calculate_extraction_confidence(output) == 1.0


def test_field_present_but_in_missing_fields_not_counted():
    # LLM might return a value but also mark it uncertain — missing_fields is authoritative
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": "POL-UNCERTAIN",  # present in JSON...
        "incident_date": "2026-04-20",
        "incident_description": "Burst pipe",
        "loss_type": "property_damage",
        "third_party_involved": False,
        "missing_fields": ["policy_number"],  # ...but LLM flagged it uncertain
    }
    confidence = _calculate_extraction_confidence(output)
    assert abs(confidence - 5 / 6) < 1e-9


def test_threshold_boundary_five_fields_passes():
    # 5/6 = 0.833 >= 0.80 → should not trigger escalation
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": "POL-123",
        "incident_date": "2026-04-20",
        "incident_description": "Flood",
        "loss_type": "property_damage",
        "third_party_involved": None,   # missing
        "missing_fields": ["third_party_involved"],
    }
    confidence = _calculate_extraction_confidence(output)
    assert confidence >= 0.80


def test_threshold_boundary_four_fields_fails():
    # 4/6 = 0.667 < 0.80 → should trigger escalation
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": None,
        "incident_date": None,
        "incident_description": "Flood",
        "loss_type": "property_damage",
        "third_party_involved": False,
        "missing_fields": ["policy_number", "incident_date"],
    }
    confidence = _calculate_extraction_confidence(output)
    assert confidence < 0.80


def test_missing_fields_list_absent_defaults_empty():
    # If LLM omits missing_fields entirely, treat as empty list
    output = {
        "claimant_name": "Jane Smith",
        "policy_number": "POL-123",
        "incident_date": "2026-04-20",
        "incident_description": "Theft",
        "loss_type": "theft",
        "third_party_involved": False,
        # no "missing_fields" key
    }
    assert _calculate_extraction_confidence(output) == 1.0


# ── parse_claim_document ──────────────────────────────────────────────────────

def test_parse_claim_document_happy_path(mock_clients):
    """Haiku returns well-formed JSON — confidence and missing_fields set."""
    fake_llm_output = {
        "claimant_name": "Jane Smith",
        "claimant_contact": {"email": "jane@example.com", "phone": None},
        "policy_number": "POL-2024-1234",
        "incident_date": "2026-04-20",
        "incident_description": "Vehicle struck a parked car at junction",
        "loss_type": "property_damage",
        "estimated_loss_amount": 3500.0,
        "third_party_involved": True,
        "missing_fields": [],
    }

    import json
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(fake_llm_output))]

    with patch("fnol_agent.tools.anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = mock_message
        result = tools.parse_claim_document(
            claim_id="claim-001",
            raw_content="Jane Smith POL-2024-1234 hit parked car April 20 $3500",
            source="email",
        )

    assert result["extraction_confidence"] == 1.0
    assert result["policy_number"] == "POL-2024-1234"
    assert result["loss_type"] == "property_damage"


def test_parse_claim_document_invalid_json_returns_zero_confidence(mock_clients):
    """If Haiku returns malformed JSON, confidence = 0 and all required fields missing."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json {{")]

    with patch("fnol_agent.tools.anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = mock_message
        result = tools.parse_claim_document("claim-001", "some text", "email")

    assert result["extraction_confidence"] == 0.0
    assert set(result["missing_fields"]) == set(REQUIRED_FIELDS)


def test_parse_claim_document_strips_markdown_fences(mock_clients):
    import json
    fake_output = {
        "claimant_name": "Bob", "policy_number": "POL-001", "incident_date": "2026-04-20",
        "incident_description": "Theft", "loss_type": "theft", "third_party_involved": False,
        "claimant_contact": {"email": None, "phone": None}, "estimated_loss_amount": None,
        "missing_fields": [],
    }
    wrapped = f"```json\n{json.dumps(fake_output)}\n```"
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=wrapped)]

    with patch("fnol_agent.tools.anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = mock_message
        result = tools.parse_claim_document("claim-001", "theft report", "web_form")

    assert result["policy_number"] == "POL-001"
    assert result["extraction_confidence"] == 1.0


import fnol_agent.tools as tools
