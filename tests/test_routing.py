"""Unit tests: routing algorithm (spec §3.4, §4.1)."""
import pytest
from unittest.mock import MagicMock
import fnol_agent.tools as tools


def _make_adjuster(adj_id, name, spec, queue_depth, last_assigned, available=True):
    return {
        "id": adj_id,
        "name": name,
        "specialisation": spec,
        "current_queue_depth": queue_depth,
        "last_assigned_at": last_assigned,
        "is_available": available,
        "contact_email": f"{adj_id}@example.com",
    }


@pytest.fixture
def mock_crm(mock_clients):
    return tools._clients["crm"]


def test_single_eligible_adjuster_assigned(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 2, "2026-04-27T08:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a1", "adjuster_name": "Alice", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is True
    assert result["assigned_adjuster_id"] == "adj-1"


def test_no_available_adjuster_returns_not_assigned(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[])
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is False
    assert result["reason"] == "no_available_adjuster"


def test_all_adjusters_unavailable(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 0, "2026-04-27T08:00:00Z", available=False),
        _make_adjuster("adj-2", "Bob", "property_damage", 1, "2026-04-27T09:00:00Z", available=False),
    ])
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is False


def test_selects_lowest_queue_depth(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 5, "2026-04-27T08:00:00Z"),
        _make_adjuster("adj-2", "Bob", "property_damage", 2, "2026-04-27T09:00:00Z"),
        _make_adjuster("adj-3", "Carol", "property_damage", 8, "2026-04-27T07:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a2", "adjuster_name": "Bob", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is True
    call_args = mock_crm.assign_adjuster.call_args[1]
    assert call_args["adjuster_id"] == "adj-2"


def test_tiebreak_by_longest_idle_time(mock_crm):
    # adj-1 and adj-2 both have queue_depth=3; adj-1 was assigned earlier (longer idle)
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 3, "2026-04-27T07:00:00Z"),
        _make_adjuster("adj-2", "Bob", "property_damage", 3, "2026-04-27T09:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a1", "adjuster_name": "Alice", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is True
    # adj-1 has older last_assigned_at (longer idle) — selected on tiebreak
    call_args = mock_crm.assign_adjuster.call_args[1]
    assert call_args["adjuster_id"] == "adj-1"


def test_tiebreak_three_way(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 4, "2026-04-27T09:00:00Z"),
        _make_adjuster("adj-2", "Bob", "property_damage", 4, "2026-04-27T06:00:00Z"),
        _make_adjuster("adj-3", "Carol", "property_damage", 4, "2026-04-27T08:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a2", "adjuster_name": "Bob", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is True
    call_args = mock_crm.assign_adjuster.call_args[1]
    assert call_args["adjuster_id"] == "adj-2"  # oldest last_assigned


def test_specialisation_filter_passed_to_crm(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "bodily_injury", 0, "2026-04-27T08:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "ax", "adjuster_name": "Alice", "assigned_at": "2026-04-27T10:00:00Z"
    })
    tools.get_adjuster_assignment("claim-1", "LOW", "bodily_injury")
    mock_crm.get_adjusters.assert_called_once_with(specialisation="bodily_injury")


def test_unavailable_adjuster_filtered_out(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 0, "2026-04-27T08:00:00Z", available=False),
        _make_adjuster("adj-2", "Bob", "property_damage", 10, "2026-04-27T08:00:00Z", available=True),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a2", "adjuster_name": "Bob", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["assigned"] is True
    call_args = mock_crm.assign_adjuster.call_args[1]
    assert call_args["adjuster_id"] == "adj-2"


def test_routing_algorithm_version_logged(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "property_damage", 1, "2026-04-27T08:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a1", "adjuster_name": "Alice", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "LOW", "property_damage")
    assert result["routing_algorithm_version"] == "1.0"


def test_zero_queue_depth_adjuster_preferred(mock_crm):
    mock_crm.get_adjusters = MagicMock(return_value=[
        _make_adjuster("adj-1", "Alice", "theft", 0, "2026-04-27T08:00:00Z"),
        _make_adjuster("adj-2", "Bob", "theft", 1, "2026-04-27T07:00:00Z"),
    ])
    mock_crm.assign_adjuster = MagicMock(return_value={
        "assignment_id": "a1", "adjuster_name": "Alice", "assigned_at": "2026-04-27T10:00:00Z"
    })
    result = tools.get_adjuster_assignment("claim-1", "MEDIUM", "theft")
    assert result["assigned"] is True
    call_args = mock_crm.assign_adjuster.call_args[1]
    assert call_args["adjuster_id"] == "adj-1"
