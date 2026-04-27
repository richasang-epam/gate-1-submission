"""Unit tests: severity classification — 50 input combinations (spec §4.1).

All tests are deterministic (100% pass target — no LLM involved).
"""
import pytest
from fnol_agent.tools import classify_severity


# ── Rule 1: bodily_injury → HIGH ──────────────────────────────────────────────

def test_bodily_injury_no_amount():
    r = classify_severity(loss_type="bodily_injury")
    assert r["severity"] == "HIGH"
    assert r["confidence"] == 1.0


def test_bodily_injury_with_low_amount():
    r = classify_severity(loss_type="bodily_injury", estimated_loss_amount=500)
    assert r["severity"] == "HIGH"


def test_bodily_injury_with_high_amount():
    r = classify_severity(loss_type="bodily_injury", estimated_loss_amount=100_000)
    assert r["severity"] == "HIGH"


def test_bodily_injury_with_third_party():
    r = classify_severity(loss_type="bodily_injury", third_party_involved=True, estimated_loss_amount=1_000)
    assert r["severity"] == "HIGH"


def test_bodily_injury_without_third_party():
    r = classify_severity(loss_type="bodily_injury", third_party_involved=False)
    assert r["severity"] == "HIGH"


def test_bodily_injury_null_third_party():
    r = classify_severity(loss_type="bodily_injury", third_party_involved=None)
    assert r["severity"] == "HIGH"


def test_bodily_injury_zero_amount():
    r = classify_severity(loss_type="bodily_injury", estimated_loss_amount=0)
    assert r["severity"] == "HIGH"


def test_bodily_injury_uppercase_normalised():
    # loss_type normalised to lowercase internally
    r = classify_severity(loss_type="BODILY_INJURY")
    assert r["severity"] == "HIGH"


# ── Rule 2: third_party + loss > 0 → HIGH ────────────────────────────────────

def test_third_party_property_damage_with_amount():
    r = classify_severity(loss_type="property_damage", third_party_involved=True, estimated_loss_amount=3_000)
    assert r["severity"] == "HIGH"


def test_third_party_theft_with_amount():
    r = classify_severity(loss_type="theft", third_party_involved=True, estimated_loss_amount=100)
    assert r["severity"] == "HIGH"


def test_third_party_with_zero_amount_not_high():
    # Rule 2 requires amount > 0; zero does not trigger it
    r = classify_severity(loss_type="property_damage", third_party_involved=True, estimated_loss_amount=0)
    # Falls through to rule 6 (property_damage, amount < 5000) → LOW
    assert r["severity"] == "LOW"


def test_third_party_true_null_amount_not_rule2():
    # No amount stated — rule 2 requires amount > 0
    r = classify_severity(loss_type="property_damage", third_party_involved=True, estimated_loss_amount=None)
    # Falls to conservative MEDIUM default
    assert r["severity"] == "MEDIUM"


def test_third_party_false_does_not_trigger_rule2():
    r = classify_severity(loss_type="property_damage", third_party_involved=False, estimated_loss_amount=3_000)
    assert r["severity"] == "LOW"  # < 5000 property_damage


def test_third_party_none_does_not_trigger_rule2():
    r = classify_severity(loss_type="property_damage", third_party_involved=None, estimated_loss_amount=3_000)
    assert r["severity"] == "LOW"


def test_third_party_other_loss_type_with_amount():
    r = classify_severity(loss_type="other", third_party_involved=True, estimated_loss_amount=1_000)
    assert r["severity"] == "HIGH"


# ── Rule 3: liability → HIGH ──────────────────────────────────────────────────

def test_liability_no_amount():
    r = classify_severity(loss_type="liability")
    assert r["severity"] == "HIGH"


def test_liability_with_low_amount():
    r = classify_severity(loss_type="liability", estimated_loss_amount=100)
    assert r["severity"] == "HIGH"


def test_liability_with_third_party_false():
    r = classify_severity(loss_type="liability", third_party_involved=False)
    assert r["severity"] == "HIGH"


def test_liability_uppercase():
    r = classify_severity(loss_type="LIABILITY")
    assert r["severity"] == "HIGH"


def test_liability_with_very_high_amount():
    r = classify_severity(loss_type="liability", estimated_loss_amount=500_000)
    assert r["severity"] == "HIGH"


# ── Rule 4: amount > $50,000 → HIGH ──────────────────────────────────────────

def test_amount_above_50k_property():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=50_001)
    assert r["severity"] == "HIGH"


def test_amount_exactly_50k_not_rule4():
    # Boundary: $50,000 is MEDIUM (rule 5 range is $5k–$50k inclusive)
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=50_000)
    assert r["severity"] == "MEDIUM"


def test_amount_100k_theft():
    r = classify_severity(loss_type="theft", estimated_loss_amount=100_000)
    assert r["severity"] == "HIGH"


def test_amount_250k_other():
    r = classify_severity(loss_type="other", estimated_loss_amount=250_000)
    assert r["severity"] == "HIGH"


def test_amount_50001_no_third_party():
    r = classify_severity(loss_type="property_damage", third_party_involved=False, estimated_loss_amount=50_001)
    assert r["severity"] == "HIGH"


# ── Rule 5: $5,000–$50,000 → MEDIUM ──────────────────────────────────────────

def test_amount_exactly_5k():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=5_000)
    assert r["severity"] == "MEDIUM"


def test_amount_midrange():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=25_000)
    assert r["severity"] == "MEDIUM"
    assert r["confidence"] == 0.95


def test_amount_just_below_50k():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=49_999)
    assert r["severity"] == "MEDIUM"


def test_amount_5k_theft():
    r = classify_severity(loss_type="theft", estimated_loss_amount=5_000)
    assert r["severity"] == "MEDIUM"


def test_amount_10k_other():
    r = classify_severity(loss_type="other", estimated_loss_amount=10_000)
    assert r["severity"] == "MEDIUM"


# ── Rule 6: < $5,000 + property_damage → LOW ─────────────────────────────────

def test_low_property_damage():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=1_000)
    assert r["severity"] == "LOW"
    assert r["confidence"] == 1.0


def test_property_damage_exactly_below_5k_boundary():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=4_999)
    assert r["severity"] == "LOW"


def test_property_damage_zero():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=0)
    assert r["severity"] == "LOW"


def test_property_damage_very_small():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=100)
    assert r["severity"] == "LOW"


def test_property_damage_no_third_party_no_amount_no_rule6():
    # No amount — can't confirm < 5000, falls to conservative MEDIUM
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=None)
    assert r["severity"] == "MEDIUM"


# ── Rule 7: Conservative MEDIUM default ──────────────────────────────────────

def test_other_loss_no_amount():
    r = classify_severity(loss_type="other", estimated_loss_amount=None)
    assert r["severity"] == "MEDIUM"
    assert r["confidence"] < 0.85  # should trigger escalation


def test_theft_no_amount():
    r = classify_severity(loss_type="theft", estimated_loss_amount=None)
    assert r["severity"] == "MEDIUM"
    assert r["confidence"] < 0.85


def test_unknown_loss_type_no_amount():
    r = classify_severity(loss_type="unknown", estimated_loss_amount=None)
    assert r["severity"] == "MEDIUM"


def test_empty_loss_type_no_amount():
    r = classify_severity(loss_type="", estimated_loss_amount=None)
    assert r["severity"] == "MEDIUM"


def test_theft_small_amount_not_property_damage():
    # theft < 5000 does NOT match rule 6 (property_damage only) — falls to MEDIUM rule 5
    r = classify_severity(loss_type="theft", estimated_loss_amount=2_000)
    # 2000 < 5000, but loss_type is theft not property_damage → falls to conservative MEDIUM
    # Actually it falls through all rules to conservative default since 2000 < 5000 and not property_damage
    assert r["severity"] == "MEDIUM"


def test_other_type_below_5k():
    r = classify_severity(loss_type="other", estimated_loss_amount=3_000)
    # Rule 6 is property_damage only — "other" < 5000 hits conservative MEDIUM
    assert r["severity"] == "MEDIUM"


# ── Priority ordering (first match wins) ──────────────────────────────────────

def test_bodily_injury_beats_high_amount():
    # bodily_injury (rule 1) fires before amount check (rule 4)
    r = classify_severity(loss_type="bodily_injury", estimated_loss_amount=200_000)
    assert r["severity"] == "HIGH"
    assert "bodily_injury" in r["severity_reason"]


def test_liability_beats_medium_amount():
    # liability (rule 3) fires before medium amount range (rule 5)
    r = classify_severity(loss_type="liability", estimated_loss_amount=10_000)
    assert r["severity"] == "HIGH"
    assert "liability" in r["severity_reason"]


def test_third_party_beats_low_property():
    # Rule 2 fires before rule 6 — property_damage with third party
    r = classify_severity(loss_type="property_damage", third_party_involved=True, estimated_loss_amount=500)
    # Rule 2: third_party=True AND amount>0 → HIGH
    assert r["severity"] == "HIGH"


def test_requires_human_review_true_for_high():
    r = classify_severity(loss_type="bodily_injury")
    assert r["requires_human_review"] is True


def test_requires_human_review_true_for_low_confidence():
    r = classify_severity(loss_type="theft", estimated_loss_amount=None)
    # confidence < 0.85 → requires_human_review = True
    assert r["requires_human_review"] is True


def test_requires_human_review_false_for_clean_low():
    r = classify_severity(loss_type="property_damage", estimated_loss_amount=500)
    assert r["severity"] == "LOW"
    assert r["requires_human_review"] is False
