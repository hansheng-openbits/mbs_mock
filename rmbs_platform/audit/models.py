"""
Audit System Data Models
========================

Comprehensive data models for the RMBS Auditor Integration system.
Based on Web3_Tokenization_Design.md specifications.

Features:
- Auditor Registry with certification and reputation tracking
- Time-limited, scoped access grants
- Audit trail with cryptographic hash chain
- Findings and attestations workflow
- Dispute resolution mechanism
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


# =============================================================================
# Enumerations
# =============================================================================


class AuditorType(str, Enum):
    """Types of auditors in the system."""
    FINANCIAL_AUDITOR = "FINANCIAL_AUDITOR"
    INTERNAL_AUDITOR = "INTERNAL_AUDITOR"
    RATING_AGENCY = "RATING_AGENCY"
    REGULATORY_EXAMINER = "REGULATORY_EXAMINER"
    FORENSIC_AUDITOR = "FORENSIC_AUDITOR"
    SMART_CONTRACT_AUDITOR = "SMART_CONTRACT_AUDITOR"


class AccessScope(str, Enum):
    """Access scope levels for auditors."""
    PERFORMANCE_ONLY = "PERFORMANCE_ONLY"           # Pool metrics, waterfall results
    LOAN_TAPE_ANONYMIZED = "LOAN_TAPE_ANONYMIZED"   # Loan data without PII
    LOAN_TAPE_FULL = "LOAN_TAPE_FULL"               # Full loan tape (requires TEE)
    FULL_DEAL_ACCESS = "FULL_DEAL_ACCESS"           # Everything including legal docs
    REGULATORY_SUBPOENA = "REGULATORY_SUBPOENA"     # Unrestricted (regulator only)


class AttestationType(str, Enum):
    """Types of auditor attestations."""
    UNQUALIFIED = "UNQUALIFIED"     # Clean opinion
    QUALIFIED = "QUALIFIED"         # With exceptions
    ADVERSE = "ADVERSE"             # Material misstatement
    DISCLAIMER = "DISCLAIMER"       # Unable to audit


class FindingSeverity(str, Enum):
    """Severity levels for audit findings."""
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, Enum):
    """Status of audit findings."""
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISPUTED = "DISPUTED"
    CLOSED = "CLOSED"


class DisputeType(str, Enum):
    """Types of disputes."""
    DATA_ACCURACY = "DATA_ACCURACY"             # Servicer data challenged
    WATERFALL_CALCULATION = "WATERFALL_CALCULATION"  # Waterfall execution challenged
    COMPLIANCE_VIOLATION = "COMPLIANCE_VIOLATION"    # Compliance breach alleged
    ACCESS_DENIAL = "ACCESS_DENIAL"             # Auditor access improperly denied
    FINDING_CONTESTED = "FINDING_CONTESTED"     # Audit finding contested


class DisputeStatus(str, Enum):
    """Status of disputes."""
    OPENED = "OPENED"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    ARBITRATION = "ARBITRATION"
    RESOLVED = "RESOLVED"
    APPEALED = "APPEALED"


class AuditEventType(str, Enum):
    """Types of audit trail events."""
    # Deal events
    DEAL_CREATED = "DEAL_CREATED"
    TOKENS_MINTED = "TOKENS_MINTED"
    WATERFALL_EXECUTED = "WATERFALL_EXECUTED"
    PERFORMANCE_SUBMITTED = "PERFORMANCE_SUBMITTED"
    YIELD_DISTRIBUTED = "YIELD_DISTRIBUTED"
    PRINCIPAL_PAID = "PRINCIPAL_PAID"
    LOSS_ALLOCATED = "LOSS_ALLOCATED"
    TRIGGER_BREACHED = "TRIGGER_BREACHED"
    TRIGGER_CURED = "TRIGGER_CURED"
    # Compliance events
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    TRANSFER_EXECUTED = "TRANSFER_EXECUTED"
    ACCOUNT_FROZEN = "ACCOUNT_FROZEN"
    # Audit events
    AUDITOR_ATTESTATION = "AUDITOR_ATTESTATION"
    FINDING_CREATED = "FINDING_CREATED"
    FINDING_STATUS_CHANGED = "FINDING_STATUS_CHANGED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED"
    # Access events
    ACCESS_GRANTED = "ACCESS_GRANTED"
    ACCESS_REVOKED = "ACCESS_REVOKED"
    DATA_ACCESSED = "DATA_ACCESSED"


# =============================================================================
# Auditor Registry Models
# =============================================================================


class AuditorCertification(BaseModel):
    """Certification held by an auditor."""
    certification_type: str = Field(description="Type of certification (CPA, CIA, CFE, etc.)")
    issuing_body: str = Field(description="Organization that issued certification")
    issue_date: datetime
    expiry_date: Optional[datetime] = None
    certification_number: Optional[str] = None
    document_hash: Optional[str] = Field(default=None, description="Hash of certification document")


class AuditorProfile(BaseModel):
    """Complete auditor profile."""
    auditor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    address: str = Field(description="Wallet address or unique identifier")
    name: str
    email: str
    firm: str
    auditor_type: AuditorType
    certifications: List[AuditorCertification] = Field(default_factory=list)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: Optional[datetime] = None
    is_active: bool = True
    reputation_score: int = Field(default=500, ge=0, le=1000, description="0-1000 reputation score")
    completed_audits: int = 0
    disputes_lost: int = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "auditor_id": "aud_12345",
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f1000",
                "name": "John Smith",
                "email": "john.smith@bigfour.com",
                "firm": "Big Four LLP",
                "auditor_type": "FINANCIAL_AUDITOR",
                "reputation_score": 750,
                "completed_audits": 25,
            }
        }


class AuditorRegistration(BaseModel):
    """Request to register a new auditor."""
    address: str
    name: str
    email: str
    firm: str
    auditor_type: AuditorType
    certifications: List[AuditorCertification] = Field(default_factory=list)


# =============================================================================
# Access Control Models
# =============================================================================


class AccessGrant(BaseModel):
    """Time-limited, scoped access grant for auditors."""
    grant_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    auditor_id: str
    deal_id: str
    scope: AccessScope
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    granted_by: str
    purpose_description: str = Field(description="Audit engagement description")
    purpose_hash: Optional[str] = Field(default=None, description="Hash of engagement letter")
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoke_reason: Optional[str] = None
    
    @computed_field
    @property
    def is_valid(self) -> bool:
        """Check if grant is currently valid."""
        now = datetime.now(timezone.utc)
        return not self.revoked and now <= self.expires_at


class AccessGrantRequest(BaseModel):
    """Request to grant audit access."""
    auditor_id: str
    deal_id: str
    scope: AccessScope
    duration_days: int = Field(ge=1, le=365, description="Grant duration in days")
    purpose_description: str


class AccessLog(BaseModel):
    """Log entry for data access by auditor."""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    grant_id: str
    auditor_id: str
    deal_id: str
    data_type: str = Field(description="Type of data accessed")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    query_description: Optional[str] = None
    query_hash: Optional[str] = None


# =============================================================================
# Audit Trail Models (with Hash Chain)
# =============================================================================


class AuditTrailEvent(BaseModel):
    """Single event in the audit trail with cryptographic linkage."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deal_id: Optional[str] = None
    event_type: AuditEventType
    actor: str = Field(description="Who performed the action")
    actor_role: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific data")
    data_hash: str = Field(default="", description="Hash of event data")
    previous_hash: str = Field(default="", description="Hash of previous event (chain)")
    signature: Optional[str] = Field(default=None, description="Actor's signature")
    
    def compute_data_hash(self) -> str:
        """Compute hash of the event data."""
        import json
        data_str = json.dumps(self.data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def compute_event_hash(self) -> str:
        """Compute hash for chain linking."""
        content = f"{self.event_id}|{self.deal_id}|{self.event_type}|{self.actor}|{self.timestamp.isoformat()}|{self.data_hash}|{self.previous_hash}"
        return hashlib.sha256(content.encode()).hexdigest()


class AuditTrailQuery(BaseModel):
    """Query parameters for audit trail search."""
    deal_id: Optional[str] = None
    event_types: Optional[List[AuditEventType]] = None
    actor: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# Findings & Attestations Models
# =============================================================================


class AuditFinding(BaseModel):
    """Audit finding record."""
    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    auditor_id: str
    deal_id: str
    severity: FindingSeverity
    title: str = Field(max_length=200)
    description: str
    affected_periods: Optional[List[int]] = None
    evidence_hashes: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    status: FindingStatus = FindingStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


class AuditFindingCreate(BaseModel):
    """Request to create a new finding."""
    deal_id: str
    severity: FindingSeverity
    title: str = Field(max_length=200)
    description: str
    affected_periods: Optional[List[int]] = None
    recommendation: Optional[str] = None


class AuditFindingUpdate(BaseModel):
    """Request to update a finding."""
    status: Optional[FindingStatus] = None
    resolution_notes: Optional[str] = None


class AuditAttestation(BaseModel):
    """Auditor attestation record."""
    attestation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    auditor_id: str
    deal_id: str
    period_start: int = Field(description="Starting period number")
    period_end: int = Field(description="Ending period number")
    attestation_type: AttestationType
    summary: str
    findings_summary: Optional[str] = None
    findings_count: int = 0
    report_hash: Optional[str] = Field(default=None, description="Hash of detailed report")
    report_uri: Optional[str] = Field(default=None, description="IPFS or URL to full report")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signature: Optional[str] = None


class AuditAttestationCreate(BaseModel):
    """Request to create an attestation."""
    deal_id: str
    period_start: int
    period_end: int
    attestation_type: AttestationType
    summary: str
    findings_summary: Optional[str] = None


# =============================================================================
# Dispute Resolution Models
# =============================================================================


class DisputeVote(BaseModel):
    """Arbitrator vote on a dispute."""
    arbitrator_id: str
    in_favor_of_initiator: bool
    reason: str
    voted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Dispute(BaseModel):
    """Dispute record."""
    dispute_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deal_id: str
    initiator_id: str
    respondent_id: str
    dispute_type: DisputeType
    title: str
    description: str
    evidence_hash: Optional[str] = None
    response_evidence_hash: Optional[str] = None
    status: DisputeStatus = DisputeStatus.OPENED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_deadline: datetime
    resolution_deadline: Optional[datetime] = None
    arbitrators: List[str] = Field(default_factory=list)
    votes: List[DisputeVote] = Field(default_factory=list)
    resolution: Optional[str] = None
    in_favor_of_initiator: Optional[bool] = None
    resolved_at: Optional[datetime] = None


class DisputeCreate(BaseModel):
    """Request to create a dispute."""
    deal_id: str
    respondent_id: str
    dispute_type: DisputeType
    title: str
    description: str


class DisputeResponse(BaseModel):
    """Response to a dispute."""
    response_description: str


class DisputeVoteRequest(BaseModel):
    """Arbitrator vote submission."""
    in_favor_of_initiator: bool
    reason: str


# =============================================================================
# Verification & Report Models
# =============================================================================


class WaterfallVerificationRequest(BaseModel):
    """Request to verify waterfall calculations."""
    deal_id: str
    periods: List[int] = Field(description="Periods to verify")


class WaterfallVerificationResult(BaseModel):
    """Result of waterfall verification."""
    deal_id: str
    period: int
    verified: bool
    discrepancies: List[Dict[str, Any]] = Field(default_factory=list)
    expected_interest: Dict[str, float] = Field(default_factory=dict)
    actual_interest: Dict[str, float] = Field(default_factory=dict)
    expected_principal: Dict[str, float] = Field(default_factory=dict)
    actual_principal: Dict[str, float] = Field(default_factory=dict)
    verification_hash: Optional[str] = None


class StratificationRequest(BaseModel):
    """Request loan tape stratification analysis."""
    deal_id: str
    stratify_by: List[str] = Field(
        description="Fields to stratify by",
        examples=[["fico_bucket", "ltv_bucket", "loan_purpose"]]
    )
    period: Optional[int] = None


class StratificationResult(BaseModel):
    """Result of stratification analysis."""
    deal_id: str
    period: Optional[int]
    stratifications: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    total_balance: float
    total_count: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditReportSection(BaseModel):
    """Section of an audit report."""
    title: str
    content: str
    verification_method: str = Field(
        description="Method used for verification",
        examples=["ZK_PROOF", "TEE_ATTESTATION", "ON_CHAIN_QUERY", "MANUAL_REVIEW"]
    )
    evidence_hashes: List[str] = Field(default_factory=list)
    conclusion: str = Field(examples=["VERIFIED", "EXCEPTION_NOTED", "UNABLE_TO_VERIFY"])


class AuditReport(BaseModel):
    """Complete audit report."""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deal_id: str
    auditor_id: str
    period_start: int
    period_end: int
    scope: AccessScope
    sections: List[AuditReportSection] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list, description="Finding IDs")
    attestation_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    report_hash: Optional[str] = None


# =============================================================================
# Dashboard & Summary Models
# =============================================================================


class AuditorDashboard(BaseModel):
    """Auditor dashboard summary."""
    active_engagements: int
    pending_reviews: int
    open_findings: int
    findings_by_severity: Dict[str, int]
    attestations_due: int
    recent_activity: List[Dict[str, Any]]


class DealAuditSummary(BaseModel):
    """Summary of audit status for a deal."""
    deal_id: str
    deal_name: Optional[str]
    current_period: int
    last_audit_period: Optional[int]
    last_attestation_type: Optional[AttestationType]
    open_findings_count: int
    has_critical_findings: bool
    compliance_status: str = Field(examples=["COMPLIANT", "EXCEPTIONS", "NON_COMPLIANT"])
    waterfall_verification_status: str
    next_attestation_due: Optional[datetime]
