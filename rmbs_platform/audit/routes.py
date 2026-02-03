"""
Audit API Routes
================

FastAPI router implementing the Auditor Integration endpoints as specified
in the Web3_Tokenization_Design.md document.

Endpoints include:
- Auditor Registry management
- Access Control with time-limited grants
- Audit Trail with hash chain integrity
- Findings and Attestations workflow
- Dispute Resolution
- Verification Tools
- Dashboard and Reports

All endpoints require appropriate role authentication via X-User-Role header.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from .models import (
    AccessGrant,
    AccessGrantRequest,
    AccessScope,
    AuditAttestation,
    AuditAttestationCreate,
    AuditEventType,
    AuditFinding,
    AuditFindingCreate,
    AuditFindingUpdate,
    AuditTrailEvent,
    AuditTrailQuery,
    AuditorDashboard,
    AuditorProfile,
    AuditorRegistration,
    AuditorType,
    AttestationType,
    DealAuditSummary,
    Dispute,
    DisputeCreate,
    DisputeResponse,
    DisputeStatus,
    DisputeVoteRequest,
    FindingSeverity,
    FindingStatus,
    StratificationRequest,
    StratificationResult,
    WaterfallVerificationRequest,
    WaterfallVerificationResult,
)
from .service import AuditService


# Create router with prefix
router = APIRouter(prefix="/audit/v2", tags=["Auditor"])

# Global audit service instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get or create the audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


def _require_role(
    allowed_roles: List[str],
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> str:
    """Validate user role and return it."""
    if x_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Role header required",
        )
    role = x_user_role.lower()
    if role not in [r.lower() for r in allowed_roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' not authorized. Allowed: {allowed_roles}",
        )
    return role


# =============================================================================
# Auditor Registry Endpoints
# =============================================================================


class AuditorRegistrationRequest(BaseModel):
    """Request to register a new auditor."""
    address: str = Field(description="Wallet address or unique identifier")
    name: str
    email: str
    firm: str
    auditor_type: AuditorType
    certifications: List[Dict[str, Any]] = Field(default_factory=list)


class AuditorListResponse(BaseModel):
    """Response containing list of auditors."""
    auditors: List[AuditorProfile]
    total: int


@router.post("/auditors", response_model=AuditorProfile)
async def register_auditor(
    request: AuditorRegistrationRequest,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditorProfile:
    """
    Register a new auditor in the system.
    
    Only admins and arrangers can register auditors.
    
    Args:
        request: Auditor registration details
        
    Returns:
        Created AuditorProfile
    """
    try:
        registration = AuditorRegistration(
            address=request.address,
            name=request.name,
            email=request.email,
            firm=request.firm,
            auditor_type=request.auditor_type,
        )
        return service.register_auditor(registration, registered_by=role)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/auditors", response_model=AuditorListResponse)
async def list_auditors(
    auditor_type: Optional[AuditorType] = None,
    min_reputation: int = 0,
    active_only: bool = True,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "arranger", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditorListResponse:
    """
    List registered auditors with optional filters.
    
    Args:
        auditor_type: Filter by auditor type
        min_reputation: Minimum reputation score (0-1000)
        active_only: Only return active auditors
        
    Returns:
        List of matching auditors
    """
    auditors = service.list_auditors(
        auditor_type=auditor_type,
        min_reputation=min_reputation,
        active_only=active_only,
    )
    return AuditorListResponse(auditors=auditors, total=len(auditors))


@router.get("/auditors/{auditor_id}", response_model=AuditorProfile)
async def get_auditor(
    auditor_id: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "arranger", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditorProfile:
    """Get auditor details by ID."""
    auditor = service.get_auditor(auditor_id)
    if not auditor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Auditor not found: {auditor_id}")
    return auditor


@router.post("/auditors/{auditor_id}/suspend")
async def suspend_auditor(
    auditor_id: str,
    reason: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """Suspend an auditor (admin only)."""
    try:
        service.suspend_auditor(auditor_id, reason, suspended_by=role)
        return {"status": "suspended", "auditor_id": auditor_id}
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# =============================================================================
# Access Control Endpoints
# =============================================================================


class AccessGrantResponse(BaseModel):
    """Response for access grant operations."""
    grant: AccessGrant
    message: str


class AccessGrantListResponse(BaseModel):
    """Response containing list of access grants."""
    grants: List[AccessGrant]
    total: int


class AccessCheckResponse(BaseModel):
    """Response for access check."""
    has_access: bool
    grant_id: Optional[str]
    scope: Optional[AccessScope]


@router.post("/access/grants", response_model=AccessGrantResponse)
async def grant_access(
    request: AccessGrantRequest,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin", "arranger", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AccessGrantResponse:
    """
    Grant time-limited access to an auditor for a specific deal.
    
    Args:
        request: Access grant details including auditor, deal, scope, duration
        
    Returns:
        Created access grant
    """
    try:
        grant = service.grant_access(request, granted_by=role)
        return AccessGrantResponse(
            grant=grant,
            message=f"Access granted to auditor {request.auditor_id} for deal {request.deal_id}"
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/access/grants/regulatory", response_model=AccessGrantResponse)
async def grant_regulatory_access(
    auditor_id: str,
    deal_id: str,
    subpoena_reference: str,
    duration_days: int = 90,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin", "regulator"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AccessGrantResponse:
    """
    Grant regulatory/subpoena access with elevated privileges.
    
    This endpoint is restricted to admins and regulators.
    """
    try:
        grant = service.grant_regulatory_access(
            auditor_id=auditor_id,
            deal_id=deal_id,
            subpoena_reference=subpoena_reference,
            granted_by=role,
            duration_days=duration_days,
        )
        return AccessGrantResponse(
            grant=grant,
            message=f"Regulatory access granted for subpoena {subpoena_reference}"
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete("/access/grants/{grant_id}")
async def revoke_access(
    grant_id: str,
    reason: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin", "arranger", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dict[str, str]:
    """Revoke an access grant."""
    try:
        service.revoke_access(grant_id, reason, revoked_by=role)
        return {"status": "revoked", "grant_id": grant_id}
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/access/check")
async def check_access(
    auditor_id: str,
    deal_id: str,
    required_scope: AccessScope,
    service: AuditService = Depends(get_audit_service),
) -> AccessCheckResponse:
    """
    Check if an auditor has valid access to a deal.
    
    Args:
        auditor_id: Auditor to check
        deal_id: Deal to access
        required_scope: Minimum scope required
        
    Returns:
        Access check result
    """
    has_access, grant_id = service.check_access(auditor_id, deal_id, required_scope)
    return AccessCheckResponse(
        has_access=has_access,
        grant_id=grant_id,
        scope=required_scope if has_access else None,
    )


@router.get("/access/grants/auditor/{auditor_id}", response_model=AccessGrantListResponse)
async def get_auditor_grants(
    auditor_id: str,
    active_only: bool = True,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AccessGrantListResponse:
    """Get all access grants for an auditor."""
    grants = service.get_auditor_grants(auditor_id, active_only=active_only)
    return AccessGrantListResponse(grants=grants, total=len(grants))


# =============================================================================
# Audit Trail Endpoints
# =============================================================================


class AuditTrailResponse(BaseModel):
    """Response containing audit trail events."""
    events: List[AuditTrailEvent]
    total: int
    chain_verified: bool


class ChainIntegrityResponse(BaseModel):
    """Response for chain integrity verification."""
    is_valid: bool
    message: str
    event_count: int


@router.post("/trail/events", response_model=AuditTrailEvent)
async def record_audit_event(
    event_type: AuditEventType,
    actor: str,
    deal_id: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["servicer", "trustee", "arranger", "admin"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditTrailEvent:
    """
    Record an event in the audit trail.
    
    Events are linked via hash chain for tamper-proof integrity.
    """
    return service.record_event(
        event_type=event_type,
        actor=actor,
        deal_id=deal_id,
        data=data or {},
        actor_role=role,
    )


@router.get("/trail/events", response_model=AuditTrailResponse)
async def query_audit_trail(
    deal_id: Optional[str] = None,
    event_types: Optional[str] = None,  # Comma-separated
    actor: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditTrailResponse:
    """
    Query the audit trail with filters.
    
    Args:
        deal_id: Filter by deal ID
        event_types: Comma-separated list of event types
        actor: Filter by actor
        start_time: Events after this time
        end_time: Events before this time
        limit: Max events to return (1-1000)
        offset: Pagination offset
        
    Returns:
        Matching audit trail events
    """
    parsed_types = None
    if event_types:
        parsed_types = [AuditEventType(et.strip()) for et in event_types.split(",")]
    
    query = AuditTrailQuery(
        deal_id=deal_id,
        event_types=parsed_types,
        actor=actor,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    
    events = service.query_audit_trail(query)
    
    # Quick chain verification
    is_valid, _ = service.verify_chain_integrity()
    
    return AuditTrailResponse(
        events=events,
        total=len(events),
        chain_verified=is_valid,
    )


@router.get("/trail/deals/{deal_id}", response_model=AuditTrailResponse)
async def get_deal_audit_trail(
    deal_id: str,
    limit: int = 100,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditTrailResponse:
    """Get all audit events for a specific deal."""
    events = service.get_deal_events(deal_id, limit=limit)
    is_valid, _ = service.verify_chain_integrity()
    return AuditTrailResponse(events=events, total=len(events), chain_verified=is_valid)


@router.get("/trail/verify", response_model=ChainIntegrityResponse)
async def verify_chain_integrity(
    start_index: int = 0,
    end_index: Optional[int] = None,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin"], x)),
    service: AuditService = Depends(get_audit_service),
) -> ChainIntegrityResponse:
    """
    Verify the hash chain integrity of the audit trail.
    
    This checks that no events have been tampered with.
    """
    is_valid, message = service.verify_chain_integrity(start_index, end_index)
    
    # Get event count from chain state
    state = service._load_json("chain_state.json")
    event_count = state.get("event_count", 0)
    
    return ChainIntegrityResponse(
        is_valid=is_valid,
        message=message,
        event_count=event_count,
    )


# =============================================================================
# Findings Endpoints
# =============================================================================


class FindingListResponse(BaseModel):
    """Response containing list of findings."""
    findings: List[AuditFinding]
    total: int


@router.post("/findings", response_model=AuditFinding)
async def create_finding(
    finding: AuditFindingCreate,
    x_auditor_id: str = Header(alias="X-Auditor-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditFinding:
    """
    Create a new audit finding.
    
    Requires X-Auditor-ID header to identify the auditor.
    Auditor must have valid access to the deal.
    """
    try:
        return service.create_finding(x_auditor_id, finding)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/findings", response_model=FindingListResponse)
async def list_findings(
    deal_id: Optional[str] = None,
    auditor_id: Optional[str] = None,
    status: Optional[FindingStatus] = None,
    severity: Optional[FindingSeverity] = None,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> FindingListResponse:
    """List findings with optional filters."""
    findings = service.list_findings(
        deal_id=deal_id,
        auditor_id=auditor_id,
        status=status,
        severity=severity,
    )
    return FindingListResponse(findings=findings, total=len(findings))


@router.get("/findings/{finding_id}", response_model=AuditFinding)
async def get_finding(
    finding_id: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditFinding:
    """Get a finding by ID."""
    finding = service.get_finding(finding_id)
    if not finding:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Finding not found: {finding_id}")
    return finding


@router.patch("/findings/{finding_id}", response_model=AuditFinding)
async def update_finding(
    finding_id: str,
    update: AuditFindingUpdate,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditFinding:
    """
    Update a finding's status.
    
    Auditors can change any status. Deal admins can acknowledge/resolve.
    """
    try:
        return service.update_finding(finding_id, update, updated_by=role)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# =============================================================================
# Attestations Endpoints
# =============================================================================


class AttestationListResponse(BaseModel):
    """Response containing list of attestations."""
    attestations: List[AuditAttestation]
    total: int


@router.post("/attestations", response_model=AuditAttestation)
async def create_attestation(
    attestation: AuditAttestationCreate,
    x_auditor_id: str = Header(alias="X-Auditor-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditAttestation:
    """
    Create an audit attestation.
    
    Attestations represent formal auditor opinions on deal performance.
    """
    try:
        return service.create_attestation(x_auditor_id, attestation)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/attestations", response_model=AttestationListResponse)
async def list_attestations(
    deal_id: Optional[str] = None,
    auditor_id: Optional[str] = None,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger", "investor"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AttestationListResponse:
    """List attestations with optional filters."""
    attestations = service.list_attestations(deal_id=deal_id, auditor_id=auditor_id)
    return AttestationListResponse(attestations=attestations, total=len(attestations))


# =============================================================================
# Disputes Endpoints
# =============================================================================


class DisputeListResponse(BaseModel):
    """Response containing list of disputes."""
    disputes: List[Dispute]
    total: int


@router.post("/disputes", response_model=Dispute)
async def create_dispute(
    dispute: DisputeCreate,
    x_auditor_id: str = Header(alias="X-Auditor-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "investor", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dispute:
    """
    Create a new dispute.
    
    Disputes can be initiated by auditors, investors, or trustees.
    """
    try:
        return service.create_dispute(x_auditor_id, dispute)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.get("/disputes", response_model=DisputeListResponse)
async def list_disputes(
    deal_id: Optional[str] = None,
    status: Optional[DisputeStatus] = None,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> DisputeListResponse:
    """List disputes with optional filters."""
    disputes = service.list_disputes(deal_id=deal_id, status=status)
    return DisputeListResponse(disputes=disputes, total=len(disputes))


@router.get("/disputes/{dispute_id}", response_model=Dispute)
async def get_dispute(
    dispute_id: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dispute:
    """Get dispute details."""
    dispute = service.get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Dispute not found: {dispute_id}")
    return dispute


@router.post("/disputes/{dispute_id}/respond", response_model=Dispute)
async def respond_to_dispute(
    dispute_id: str,
    response: DisputeResponse,
    x_respondent_id: str = Header(alias="X-Respondent-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["servicer", "arranger", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dispute:
    """Submit response to a dispute."""
    try:
        return service.respond_to_dispute(dispute_id, response, x_respondent_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/disputes/{dispute_id}/vote", response_model=Dispute)
async def vote_on_dispute(
    dispute_id: str,
    vote: DisputeVoteRequest,
    x_arbitrator_id: str = Header(alias="X-Arbitrator-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["admin", "trustee"], x)),
    service: AuditService = Depends(get_audit_service),
) -> Dispute:
    """Submit arbitrator vote on a dispute."""
    try:
        return service.submit_dispute_vote(dispute_id, x_arbitrator_id, vote)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# =============================================================================
# Dashboard & Summary Endpoints
# =============================================================================


@router.get("/dashboard/{auditor_id}", response_model=AuditorDashboard)
async def get_auditor_dashboard(
    auditor_id: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin"], x)),
    service: AuditService = Depends(get_audit_service),
) -> AuditorDashboard:
    """
    Get dashboard summary for an auditor.
    
    Returns:
        - Active engagements count
        - Pending reviews
        - Open findings by severity
        - Attestations due
        - Recent activity
    """
    return service.get_auditor_dashboard(auditor_id)


@router.get("/deals/{deal_id}/summary", response_model=DealAuditSummary)
async def get_deal_audit_summary(
    deal_id: str,
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "admin", "trustee", "arranger"], x)),
    service: AuditService = Depends(get_audit_service),
) -> DealAuditSummary:
    """
    Get audit summary for a deal.
    
    Returns:
        - Last audit period
        - Open findings count
        - Compliance status
        - Verification status
    """
    return service.get_deal_audit_summary(deal_id)


# =============================================================================
# Verification Endpoints
# =============================================================================


@router.post("/verify/waterfall", response_model=List[WaterfallVerificationResult])
async def verify_waterfall(
    request: WaterfallVerificationRequest,
    x_auditor_id: str = Header(alias="X-Auditor-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor"], x)),
    service: AuditService = Depends(get_audit_service),
) -> List[WaterfallVerificationResult]:
    """
    Verify waterfall calculations for specified periods.
    
    This recalculates the waterfall and compares to recorded distributions.
    """
    # Verify auditor has access
    has_access, grant_id = service.check_access(
        x_auditor_id, request.deal_id, AccessScope.PERFORMANCE_ONLY
    )
    if not has_access:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Auditor does not have access to deal {request.deal_id}"
        )
    
    # Log the access
    if grant_id:
        service.log_access(grant_id, "waterfall_verification", f"Periods: {request.periods}")
    
    # TODO: Implement actual waterfall verification by comparing
    # engine calculations with recorded distributions
    
    results = []
    for period in request.periods:
        results.append(WaterfallVerificationResult(
            deal_id=request.deal_id,
            period=period,
            verified=True,  # Placeholder - would implement real verification
            discrepancies=[],
            expected_interest={},
            actual_interest={},
            expected_principal={},
            actual_principal={},
        ))
    
    return results


@router.post("/verify/stratification", response_model=StratificationResult)
async def get_stratification(
    request: StratificationRequest,
    x_auditor_id: str = Header(alias="X-Auditor-ID"),
    role: str = Depends(lambda x=Header(default=None, alias="X-User-Role"): _require_role(["auditor"], x)),
    service: AuditService = Depends(get_audit_service),
) -> StratificationResult:
    """
    Generate loan tape stratification analysis.
    
    Returns aggregated statistics without revealing individual loan data.
    """
    # Verify auditor has access
    has_access, grant_id = service.check_access(
        x_auditor_id, request.deal_id, AccessScope.LOAN_TAPE_ANONYMIZED
    )
    if not has_access:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Auditor does not have loan tape access to deal {request.deal_id}"
        )
    
    # Log the access
    if grant_id:
        service.log_access(grant_id, "stratification", f"Fields: {request.stratify_by}")
    
    # TODO: Implement actual stratification by loading loan tape
    # and aggregating by requested fields
    
    return StratificationResult(
        deal_id=request.deal_id,
        period=request.period,
        stratifications={},  # Placeholder
        total_balance=0.0,
        total_count=0,
    )
