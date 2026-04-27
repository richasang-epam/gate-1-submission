from enum import Enum
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
import uuid


class ClaimState(str, Enum):
    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    TRIAGED = "TRIAGED"
    ROUTING = "ROUTING"
    ROUTED = "ROUTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATED = "ESCALATED"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class ClaimantContact(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


class ExtractedData(BaseModel):
    claimant_name: Optional[str] = None
    claimant_contact: ClaimantContact = Field(default_factory=ClaimantContact)
    policy_number: Optional[str] = None
    incident_date: Optional[str] = None
    incident_description: Optional[str] = None
    loss_type: Optional[str] = None
    estimated_loss_amount: Optional[float] = None
    third_party_involved: Optional[bool] = None
    extraction_confidence: float = 0.0
    missing_fields: List[str] = Field(default_factory=list)


class PolicyResult(BaseModel):
    policy_number: str
    policy_status: str
    coverage_types: List[str] = Field(default_factory=list)
    coverage_limit: float = 0.0
    deductible: float = 0.0
    loss_type_covered: Optional[bool] = None
    coverage_notes: Optional[str] = None


class TriageResult(BaseModel):
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    severity_reason: str
    confidence: float
    requires_human_review: bool


class RoutingResult(BaseModel):
    assigned_adjuster_id: Optional[str] = None
    adjuster_name: Optional[str] = None
    adjuster_specialisation: str
    routing_algorithm_version: str = "1.0"
    routed_at: Optional[str] = None


class AcknowledgmentResult(BaseModel):
    sent_at: str
    channel: Literal["email", "sms", "portal"]
    template_id: str
    reference_number: str


class AuditEntry(BaseModel):
    timestamp: str
    action: str
    actor: str
    previous_state: str
    new_state: str
    metadata: dict = Field(default_factory=dict)


class ClaimRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str
    raw_content: str
    received_at: str
    extracted: Optional[ExtractedData] = None
    policy: Optional[PolicyResult] = None
    triage: Optional[TriageResult] = None
    routing: Optional[RoutingResult] = None
    acknowledgment: Optional[AcknowledgmentResult] = None
    state: ClaimState = ClaimState.RECEIVED
    escalation_reason: Optional[str] = None
    audit_log: List[AuditEntry] = Field(default_factory=list)
