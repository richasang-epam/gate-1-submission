"""Mock clients for demo and development. No real HTTP calls made."""
import uuid
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockCRMClient:
    """Returns plausible canned responses for all CRM operations."""

    def create_claim(self, source: str, raw_content: str, received_at: str, reference_number: str) -> dict:
        return {"id": str(uuid.uuid4()), "reference_number": reference_number, "created_at": _now()}

    def update_claim(self, claim_id: str, state: str, metadata: dict) -> dict:
        return {"id": claim_id, "state": state, "updated_at": _now()}

    def get_adjusters(self, specialisation: str) -> list:
        return [
            {
                "id": "adj-001",
                "name": "Alice Moreau",
                "specialisation": specialisation,
                "current_queue_depth": 3,
                "last_assigned_at": "2026-04-27T08:00:00Z",
                "is_available": True,
            },
            {
                "id": "adj-002",
                "name": "Ben Tran",
                "specialisation": specialisation,
                "current_queue_depth": 5,
                "last_assigned_at": "2026-04-27T09:00:00Z",
                "is_available": True,
            },
        ]

    def assign_adjuster(self, claim_id: str, adjuster_id: str, routing_reason: str) -> dict:
        return {
            "assignment_id": str(uuid.uuid4()),
            "adjuster_name": "Alice Moreau",
            "assigned_at": _now(),
        }

    def send_communication(
        self,
        claim_id: str,
        channel: str,
        template_id: str,
        recipient: dict,
        template_data: dict,
    ) -> dict:
        return {
            "message_id": str(uuid.uuid4()),
            "sent_at": _now(),
            "delivery_status": "delivered",
        }

    def create_review_task(self, claim_id: str, priority: str, reason: str, dossier: dict) -> dict:
        return {
            "task_id": str(uuid.uuid4()),
            "queue_position": 1,
            "assigned_reviewer_id": "reviewer-001",
        }

    def get_review_task(self, task_id: str) -> dict:
        # Simulate immediate human approval for demo
        return {
            "task_id": task_id,
            "status": "completed",
            "human_decision": {
                "action": "approve_routing",
                "updates": {},
                "notes": "Reviewed and approved",
            },
        }


class MockPolicyClient:
    """Returns mock policy responses keyed on policy number prefix."""

    LAPSED_PREFIX = "LAPSED"
    NOT_FOUND_PREFIX = "NOTFOUND"
    AMBIGUOUS_PREFIX = "AMBIG"

    def get_policy_details(self, policy_number: str) -> dict:
        pn = policy_number.upper()
        if pn.startswith(self.NOT_FOUND_PREFIX):
            status = "not_found"
        elif pn.startswith(self.LAPSED_PREFIX):
            status = "lapsed"
        else:
            status = "active"
        return {
            "policy_number": policy_number,
            "policy_status": status,
            "coverage_types": ["property_damage", "theft", "liability"],
            "coverage_limit": 250000.0,
            "deductible": 1000.0,
        }

    def validate_coverage(
        self, policy_number: str, loss_type: str, claim_amount: Optional[float]
    ) -> dict:
        pn = policy_number.upper()
        if pn.startswith(self.AMBIGUOUS_PREFIX):
            return {"loss_type_covered": None, "coverage_notes": "Possible exclusion — requires underwriter review"}
        return {"loss_type_covered": True, "coverage_notes": None}


class MockDMSClient:
    def upload_claim(self, claim_id: str, raw_content: str, extracted: dict, audit_log: list) -> dict:
        return {"doc_id": str(uuid.uuid4()), "status": "stored"}

    def get_document(self, doc_id: str) -> dict:
        return {"doc_id": doc_id, "status": "found"}
