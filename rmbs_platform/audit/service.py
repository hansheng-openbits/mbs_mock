"""
Audit Service
=============

Core service implementing all audit functionality for the RMBS Platform.

This service manages:
- Auditor registration and certification tracking
- Access grants with time limits and scope restrictions
- Immutable audit trail with cryptographic hash chain
- Findings and attestations workflow
- Dispute resolution

Storage is file-based (JSON) for simplicity, following the pattern
used by web3_sync/ for Web3 integration data.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AccessGrant,
    AccessGrantRequest,
    AccessLog,
    AccessScope,
    AuditAttestation,
    AuditAttestationCreate,
    AuditEventType,
    AuditFinding,
    AuditFindingCreate,
    AuditFindingUpdate,
    AuditReport,
    AuditReportSection,
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
    DisputeVote,
    DisputeVoteRequest,
    FindingSeverity,
    FindingStatus,
    StratificationRequest,
    StratificationResult,
    WaterfallVerificationRequest,
    WaterfallVerificationResult,
)


class AuditService:
    """
    Central service for all audit operations.
    
    Handles:
    - Auditor registry management
    - Access control with time-limited grants
    - Audit trail recording with hash chain integrity
    - Findings and attestations lifecycle
    - Dispute resolution workflow
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the audit service.
        
        Args:
            storage_path: Path to audit storage directory.
                         Defaults to 'audit_storage/' in project root.
        """
        if storage_path is None:
            # Default to audit_storage in project root
            project_root = Path(__file__).parent.parent
            storage_path = str(project_root / "audit_storage")
        
        self.storage_path = Path(storage_path)
        self._ensure_storage()
        
        # Latest hash for chain integrity
        self._latest_hash = self._load_latest_hash()
    
    def _ensure_storage(self) -> None:
        """Ensure storage directory and files exist."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize storage files if they don't exist
        files = {
            "auditors.json": [],
            "access_grants.json": [],
            "access_logs.json": [],
            "audit_trail.json": [],
            "findings.json": [],
            "attestations.json": [],
            "disputes.json": [],
            "chain_state.json": {"latest_hash": "", "event_count": 0},
        }
        
        for filename, default_content in files.items():
            filepath = self.storage_path / filename
            if not filepath.exists():
                with open(filepath, "w") as f:
                    json.dump(default_content, f, indent=2)
    
    def _load_json(self, filename: str) -> Any:
        """Load JSON file from storage."""
        filepath = self.storage_path / filename
        with open(filepath, "r") as f:
            return json.load(f)
    
    def _save_json(self, filename: str, data: Any) -> None:
        """Save data to JSON file."""
        filepath = self.storage_path / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def _load_latest_hash(self) -> str:
        """Load the latest hash from chain state."""
        state = self._load_json("chain_state.json")
        return state.get("latest_hash", "")
    
    def _update_chain_state(self, new_hash: str, event_count: int) -> None:
        """Update chain state with new hash."""
        self._save_json("chain_state.json", {
            "latest_hash": new_hash,
            "event_count": event_count,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        self._latest_hash = new_hash
    
    # =========================================================================
    # Auditor Registry
    # =========================================================================
    
    def register_auditor(self, registration: AuditorRegistration, registered_by: str = "system") -> AuditorProfile:
        """
        Register a new auditor in the system.
        
        Args:
            registration: Auditor registration details
            registered_by: Who is registering this auditor
            
        Returns:
            Created AuditorProfile
        """
        auditors = self._load_json("auditors.json")
        
        # Check for duplicate address
        for auditor in auditors:
            if auditor["address"] == registration.address:
                raise ValueError(f"Auditor already registered: {registration.address}")
        
        # Create profile
        profile = AuditorProfile(
            address=registration.address,
            name=registration.name,
            email=registration.email,
            firm=registration.firm,
            auditor_type=registration.auditor_type,
            certifications=[c.model_dump() for c in registration.certifications],
        )
        
        auditors.append(profile.model_dump())
        self._save_json("auditors.json", auditors)
        
        # Record event
        self.record_event(
            event_type=AuditEventType.ACCESS_GRANTED,
            actor=registered_by,
            data={
                "action": "auditor_registered",
                "auditor_id": profile.auditor_id,
                "auditor_type": profile.auditor_type,
                "firm": profile.firm,
            }
        )
        
        return profile
    
    def get_auditor(self, auditor_id: str) -> Optional[AuditorProfile]:
        """Get auditor by ID."""
        auditors = self._load_json("auditors.json")
        for auditor in auditors:
            if auditor["auditor_id"] == auditor_id:
                return AuditorProfile(**auditor)
        return None
    
    def get_auditor_by_address(self, address: str) -> Optional[AuditorProfile]:
        """Get auditor by wallet address."""
        auditors = self._load_json("auditors.json")
        for auditor in auditors:
            if auditor["address"] == address:
                return AuditorProfile(**auditor)
        return None
    
    def list_auditors(
        self,
        auditor_type: Optional[AuditorType] = None,
        min_reputation: int = 0,
        active_only: bool = True
    ) -> List[AuditorProfile]:
        """List auditors with optional filters."""
        auditors = self._load_json("auditors.json")
        result = []
        
        for auditor in auditors:
            if active_only and not auditor.get("is_active", True):
                continue
            if auditor_type and auditor.get("auditor_type") != auditor_type:
                continue
            if auditor.get("reputation_score", 500) < min_reputation:
                continue
            result.append(AuditorProfile(**auditor))
        
        return result
    
    def update_auditor_reputation(
        self,
        auditor_id: str,
        delta: int,
        reason: str,
        updated_by: str = "system"
    ) -> AuditorProfile:
        """Update auditor reputation score."""
        auditors = self._load_json("auditors.json")
        
        for i, auditor in enumerate(auditors):
            if auditor["auditor_id"] == auditor_id:
                old_score = auditor.get("reputation_score", 500)
                new_score = max(0, min(1000, old_score + delta))
                auditors[i]["reputation_score"] = new_score
                auditors[i]["last_activity_at"] = datetime.now(timezone.utc).isoformat()
                
                self._save_json("auditors.json", auditors)
                
                # Record event
                self.record_event(
                    event_type=AuditEventType.COMPLIANCE_CHECK,
                    actor=updated_by,
                    data={
                        "action": "reputation_updated",
                        "auditor_id": auditor_id,
                        "old_score": old_score,
                        "new_score": new_score,
                        "delta": delta,
                        "reason": reason,
                    }
                )
                
                return AuditorProfile(**auditors[i])
        
        raise ValueError(f"Auditor not found: {auditor_id}")
    
    def suspend_auditor(self, auditor_id: str, reason: str, suspended_by: str) -> None:
        """Suspend an auditor."""
        auditors = self._load_json("auditors.json")
        
        for i, auditor in enumerate(auditors):
            if auditor["auditor_id"] == auditor_id:
                auditors[i]["is_active"] = False
                self._save_json("auditors.json", auditors)
                
                # Revoke all active grants
                grants = self._load_json("access_grants.json")
                for j, grant in enumerate(grants):
                    if grant["auditor_id"] == auditor_id and not grant.get("revoked"):
                        grants[j]["revoked"] = True
                        grants[j]["revoked_at"] = datetime.now(timezone.utc).isoformat()
                        grants[j]["revoked_by"] = suspended_by
                        grants[j]["revoke_reason"] = f"Auditor suspended: {reason}"
                
                self._save_json("access_grants.json", grants)
                
                self.record_event(
                    event_type=AuditEventType.ACCESS_REVOKED,
                    actor=suspended_by,
                    data={
                        "action": "auditor_suspended",
                        "auditor_id": auditor_id,
                        "reason": reason,
                    }
                )
                return
        
        raise ValueError(f"Auditor not found: {auditor_id}")
    
    # =========================================================================
    # Access Control
    # =========================================================================
    
    def grant_access(self, request: AccessGrantRequest, granted_by: str) -> AccessGrant:
        """
        Grant time-limited access to an auditor.
        
        Args:
            request: Access grant request details
            granted_by: Who is granting access
            
        Returns:
            Created AccessGrant
        """
        # Verify auditor exists and is active
        auditor = self.get_auditor(request.auditor_id)
        if not auditor:
            raise ValueError(f"Auditor not found: {request.auditor_id}")
        if not auditor.is_active:
            raise ValueError(f"Auditor is suspended: {request.auditor_id}")
        
        # Check for regulatory scope restrictions
        if request.scope == AccessScope.REGULATORY_SUBPOENA:
            raise ValueError("Use grant_regulatory_access for REGULATORY_SUBPOENA scope")
        
        # Create grant
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.duration_days)
        
        grant = AccessGrant(
            auditor_id=request.auditor_id,
            deal_id=request.deal_id,
            scope=request.scope,
            expires_at=expires_at,
            granted_by=granted_by,
            purpose_description=request.purpose_description,
            purpose_hash=hashlib.sha256(request.purpose_description.encode()).hexdigest(),
        )
        
        grants = self._load_json("access_grants.json")
        grants.append(grant.model_dump())
        self._save_json("access_grants.json", grants)
        
        # Record event
        self.record_event(
            event_type=AuditEventType.ACCESS_GRANTED,
            actor=granted_by,
            deal_id=request.deal_id,
            data={
                "grant_id": grant.grant_id,
                "auditor_id": request.auditor_id,
                "scope": request.scope,
                "duration_days": request.duration_days,
            }
        )
        
        return grant
    
    def grant_regulatory_access(
        self,
        auditor_id: str,
        deal_id: str,
        subpoena_reference: str,
        granted_by: str,
        duration_days: int = 90
    ) -> AccessGrant:
        """Grant regulatory/subpoena access with elevated privileges."""
        auditor = self.get_auditor(auditor_id)
        if not auditor:
            raise ValueError(f"Auditor not found: {auditor_id}")
        
        if auditor.auditor_type != AuditorType.REGULATORY_EXAMINER:
            raise ValueError("Only REGULATORY_EXAMINER can receive REGULATORY_SUBPOENA access")
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
        
        grant = AccessGrant(
            auditor_id=auditor_id,
            deal_id=deal_id,
            scope=AccessScope.REGULATORY_SUBPOENA,
            expires_at=expires_at,
            granted_by=granted_by,
            purpose_description=f"Regulatory examination - Subpoena ref: {subpoena_reference}",
            purpose_hash=hashlib.sha256(subpoena_reference.encode()).hexdigest(),
        )
        
        grants = self._load_json("access_grants.json")
        grants.append(grant.model_dump())
        self._save_json("access_grants.json", grants)
        
        self.record_event(
            event_type=AuditEventType.ACCESS_GRANTED,
            actor=granted_by,
            deal_id=deal_id,
            data={
                "grant_id": grant.grant_id,
                "auditor_id": auditor_id,
                "scope": AccessScope.REGULATORY_SUBPOENA,
                "subpoena_reference": subpoena_reference,
            }
        )
        
        return grant
    
    def revoke_access(self, grant_id: str, reason: str, revoked_by: str) -> None:
        """Revoke an access grant."""
        grants = self._load_json("access_grants.json")
        
        for i, grant in enumerate(grants):
            if grant["grant_id"] == grant_id:
                if grant.get("revoked"):
                    raise ValueError("Grant already revoked")
                
                grants[i]["revoked"] = True
                grants[i]["revoked_at"] = datetime.now(timezone.utc).isoformat()
                grants[i]["revoked_by"] = revoked_by
                grants[i]["revoke_reason"] = reason
                
                self._save_json("access_grants.json", grants)
                
                self.record_event(
                    event_type=AuditEventType.ACCESS_REVOKED,
                    actor=revoked_by,
                    deal_id=grant.get("deal_id"),
                    data={
                        "grant_id": grant_id,
                        "auditor_id": grant.get("auditor_id"),
                        "reason": reason,
                    }
                )
                return
        
        raise ValueError(f"Grant not found: {grant_id}")
    
    def check_access(
        self,
        auditor_id: str,
        deal_id: str,
        required_scope: AccessScope
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if auditor has valid access to a deal.
        
        Args:
            auditor_id: Auditor to check
            deal_id: Deal to access
            required_scope: Minimum scope required
            
        Returns:
            Tuple of (has_access, grant_id)
        """
        grants = self._load_json("access_grants.json")
        now = datetime.now(timezone.utc)
        
        scope_hierarchy = [
            AccessScope.PERFORMANCE_ONLY,
            AccessScope.LOAN_TAPE_ANONYMIZED,
            AccessScope.LOAN_TAPE_FULL,
            AccessScope.FULL_DEAL_ACCESS,
            AccessScope.REGULATORY_SUBPOENA,
        ]
        required_level = scope_hierarchy.index(required_scope)
        
        for grant in grants:
            if grant["auditor_id"] != auditor_id:
                continue
            if grant["deal_id"] != deal_id:
                continue
            if grant.get("revoked"):
                continue
            
            expires_at = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
            if now > expires_at:
                continue
            
            grant_scope = AccessScope(grant["scope"])
            grant_level = scope_hierarchy.index(grant_scope)
            
            if grant_level >= required_level:
                return True, grant["grant_id"]
        
        return False, None
    
    def log_access(
        self,
        grant_id: str,
        data_type: str,
        query_description: Optional[str] = None
    ) -> AccessLog:
        """Log data access by an auditor."""
        grants = self._load_json("access_grants.json")
        grant = None
        
        for g in grants:
            if g["grant_id"] == grant_id:
                grant = g
                break
        
        if not grant:
            raise ValueError(f"Grant not found: {grant_id}")
        
        log = AccessLog(
            grant_id=grant_id,
            auditor_id=grant["auditor_id"],
            deal_id=grant["deal_id"],
            data_type=data_type,
            query_description=query_description,
            query_hash=hashlib.sha256((query_description or "").encode()).hexdigest() if query_description else None,
        )
        
        logs = self._load_json("access_logs.json")
        logs.append(log.model_dump())
        self._save_json("access_logs.json", logs)
        
        self.record_event(
            event_type=AuditEventType.DATA_ACCESSED,
            actor=grant["auditor_id"],
            deal_id=grant["deal_id"],
            data={
                "grant_id": grant_id,
                "data_type": data_type,
            }
        )
        
        return log
    
    def get_auditor_grants(self, auditor_id: str, active_only: bool = True) -> List[AccessGrant]:
        """Get all access grants for an auditor."""
        grants = self._load_json("access_grants.json")
        now = datetime.now(timezone.utc)
        result = []
        
        for grant in grants:
            if grant["auditor_id"] != auditor_id:
                continue
            
            if active_only:
                if grant.get("revoked"):
                    continue
                expires_at = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
                if now > expires_at:
                    continue
            
            result.append(AccessGrant(**grant))
        
        return result
    
    # =========================================================================
    # Audit Trail (with Hash Chain)
    # =========================================================================
    
    def record_event(
        self,
        event_type: AuditEventType,
        actor: str,
        deal_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        actor_role: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> AuditTrailEvent:
        """
        Record an event in the audit trail with hash chain integrity.
        
        Args:
            event_type: Type of event
            actor: Who performed the action
            deal_id: Associated deal (if any)
            data: Event-specific data
            actor_role: Role of the actor
            signature: Digital signature (optional)
            
        Returns:
            Created AuditTrailEvent
        """
        event = AuditTrailEvent(
            event_type=event_type,
            actor=actor,
            deal_id=deal_id,
            actor_role=actor_role,
            data=data or {},
            previous_hash=self._latest_hash,
            signature=signature,
        )
        
        # Compute hashes
        event.data_hash = event.compute_data_hash()
        new_hash = event.compute_event_hash()
        
        # Save event
        trail = self._load_json("audit_trail.json")
        trail.append(event.model_dump())
        self._save_json("audit_trail.json", trail)
        
        # Update chain state
        self._update_chain_state(new_hash, len(trail))
        
        return event
    
    def query_audit_trail(self, query: AuditTrailQuery) -> List[AuditTrailEvent]:
        """Query the audit trail with filters."""
        trail = self._load_json("audit_trail.json")
        result = []
        
        for event in trail:
            # Apply filters
            if query.deal_id and event.get("deal_id") != query.deal_id:
                continue
            
            if query.event_types:
                event_type = event.get("event_type")
                if event_type not in [et.value for et in query.event_types]:
                    continue
            
            if query.actor and event.get("actor") != query.actor:
                continue
            
            if query.start_time:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if event_time < query.start_time:
                    continue
            
            if query.end_time:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                if event_time > query.end_time:
                    continue
            
            result.append(AuditTrailEvent(**event))
        
        # Apply pagination
        result = result[query.offset:query.offset + query.limit]
        
        return result
    
    def get_deal_events(self, deal_id: str, limit: int = 100) -> List[AuditTrailEvent]:
        """Get all events for a specific deal."""
        query = AuditTrailQuery(deal_id=deal_id, limit=limit)
        return self.query_audit_trail(query)
    
    def verify_chain_integrity(self, start_index: int = 0, end_index: Optional[int] = None) -> Tuple[bool, str]:
        """
        Verify the hash chain integrity.
        
        Args:
            start_index: Starting event index
            end_index: Ending event index (None = all)
            
        Returns:
            Tuple of (is_valid, message)
        """
        trail = self._load_json("audit_trail.json")
        
        if not trail:
            return True, "Empty audit trail"
        
        if end_index is None:
            end_index = len(trail)
        
        computed_hash = trail[start_index].get("previous_hash", "") if start_index > 0 else ""
        
        for i in range(start_index, end_index):
            event = trail[i]
            
            # Verify previous hash matches
            if event.get("previous_hash") != computed_hash:
                return False, f"Chain broken at event {i}: previous hash mismatch"
            
            # Compute this event's hash
            event_obj = AuditTrailEvent(**event)
            computed_hash = event_obj.compute_event_hash()
        
        # Verify final hash matches stored state
        state = self._load_json("chain_state.json")
        if computed_hash != state.get("latest_hash"):
            return False, "Latest hash mismatch"
        
        return True, f"Chain verified: {end_index - start_index} events"
    
    # =========================================================================
    # Findings & Attestations
    # =========================================================================
    
    def create_finding(self, auditor_id: str, finding: AuditFindingCreate) -> AuditFinding:
        """Create a new audit finding."""
        # Verify auditor has access
        has_access, grant_id = self.check_access(
            auditor_id, finding.deal_id, AccessScope.PERFORMANCE_ONLY
        )
        if not has_access:
            raise ValueError(f"Auditor {auditor_id} does not have access to deal {finding.deal_id}")
        
        audit_finding = AuditFinding(
            auditor_id=auditor_id,
            deal_id=finding.deal_id,
            severity=finding.severity,
            title=finding.title,
            description=finding.description,
            affected_periods=finding.affected_periods,
            recommendation=finding.recommendation,
        )
        
        findings = self._load_json("findings.json")
        findings.append(audit_finding.model_dump())
        self._save_json("findings.json", findings)
        
        self.record_event(
            event_type=AuditEventType.FINDING_CREATED,
            actor=auditor_id,
            deal_id=finding.deal_id,
            data={
                "finding_id": audit_finding.finding_id,
                "severity": finding.severity,
                "title": finding.title,
            }
        )
        
        return audit_finding
    
    def update_finding(
        self,
        finding_id: str,
        update: AuditFindingUpdate,
        updated_by: str
    ) -> AuditFinding:
        """Update a finding's status."""
        findings = self._load_json("findings.json")
        
        for i, finding in enumerate(findings):
            if finding["finding_id"] == finding_id:
                old_status = finding.get("status")
                
                if update.status:
                    findings[i]["status"] = update.status
                    
                    if update.status in [FindingStatus.RESOLVED, FindingStatus.CLOSED]:
                        findings[i]["resolved_at"] = datetime.now(timezone.utc).isoformat()
                        findings[i]["resolved_by"] = updated_by
                    
                    if update.status == FindingStatus.ACKNOWLEDGED:
                        findings[i]["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                        findings[i]["acknowledged_by"] = updated_by
                
                if update.resolution_notes:
                    findings[i]["resolution_notes"] = update.resolution_notes
                
                self._save_json("findings.json", findings)
                
                self.record_event(
                    event_type=AuditEventType.FINDING_STATUS_CHANGED,
                    actor=updated_by,
                    deal_id=finding.get("deal_id"),
                    data={
                        "finding_id": finding_id,
                        "old_status": old_status,
                        "new_status": update.status,
                    }
                )
                
                return AuditFinding(**findings[i])
        
        raise ValueError(f"Finding not found: {finding_id}")
    
    def get_finding(self, finding_id: str) -> Optional[AuditFinding]:
        """Get a finding by ID."""
        findings = self._load_json("findings.json")
        for finding in findings:
            if finding["finding_id"] == finding_id:
                return AuditFinding(**finding)
        return None
    
    def list_findings(
        self,
        deal_id: Optional[str] = None,
        auditor_id: Optional[str] = None,
        status: Optional[FindingStatus] = None,
        severity: Optional[FindingSeverity] = None,
    ) -> List[AuditFinding]:
        """List findings with filters."""
        findings = self._load_json("findings.json")
        result = []
        
        for finding in findings:
            if deal_id and finding.get("deal_id") != deal_id:
                continue
            if auditor_id and finding.get("auditor_id") != auditor_id:
                continue
            if status and finding.get("status") != status:
                continue
            if severity and finding.get("severity") != severity:
                continue
            
            result.append(AuditFinding(**finding))
        
        return result
    
    def create_attestation(
        self,
        auditor_id: str,
        attestation: AuditAttestationCreate
    ) -> AuditAttestation:
        """Create an audit attestation."""
        # Verify auditor has access
        has_access, _ = self.check_access(
            auditor_id, attestation.deal_id, AccessScope.PERFORMANCE_ONLY
        )
        if not has_access:
            raise ValueError(f"Auditor {auditor_id} does not have access to deal {attestation.deal_id}")
        
        # Count open findings for the deal in the period range
        findings = self.list_findings(deal_id=attestation.deal_id)
        relevant_findings = [
            f for f in findings
            if f.status not in [FindingStatus.RESOLVED, FindingStatus.CLOSED]
        ]
        
        audit_attestation = AuditAttestation(
            auditor_id=auditor_id,
            deal_id=attestation.deal_id,
            period_start=attestation.period_start,
            period_end=attestation.period_end,
            attestation_type=attestation.attestation_type,
            summary=attestation.summary,
            findings_summary=attestation.findings_summary,
            findings_count=len(relevant_findings),
        )
        
        attestations = self._load_json("attestations.json")
        attestations.append(audit_attestation.model_dump())
        self._save_json("attestations.json", attestations)
        
        self.record_event(
            event_type=AuditEventType.AUDITOR_ATTESTATION,
            actor=auditor_id,
            deal_id=attestation.deal_id,
            data={
                "attestation_id": audit_attestation.attestation_id,
                "attestation_type": attestation.attestation_type,
                "period_start": attestation.period_start,
                "period_end": attestation.period_end,
            }
        )
        
        # Update auditor reputation based on attestation
        if attestation.attestation_type == AttestationType.UNQUALIFIED:
            self.update_auditor_reputation(auditor_id, 5, "Clean attestation issued")
        elif attestation.attestation_type in [AttestationType.QUALIFIED, AttestationType.ADVERSE]:
            self.update_auditor_reputation(auditor_id, 10, "Material findings identified")
        
        return audit_attestation
    
    def list_attestations(
        self,
        deal_id: Optional[str] = None,
        auditor_id: Optional[str] = None,
    ) -> List[AuditAttestation]:
        """List attestations with filters."""
        attestations = self._load_json("attestations.json")
        result = []
        
        for attestation in attestations:
            if deal_id and attestation.get("deal_id") != deal_id:
                continue
            if auditor_id and attestation.get("auditor_id") != auditor_id:
                continue
            result.append(AuditAttestation(**attestation))
        
        return result
    
    # =========================================================================
    # Dispute Resolution
    # =========================================================================
    
    def create_dispute(self, initiator_id: str, dispute: DisputeCreate) -> Dispute:
        """Create a new dispute."""
        evidence_deadline = datetime.now(timezone.utc) + timedelta(days=7)
        
        new_dispute = Dispute(
            deal_id=dispute.deal_id,
            initiator_id=initiator_id,
            respondent_id=dispute.respondent_id,
            dispute_type=dispute.dispute_type,
            title=dispute.title,
            description=dispute.description,
            evidence_deadline=evidence_deadline,
        )
        
        disputes = self._load_json("disputes.json")
        disputes.append(new_dispute.model_dump())
        self._save_json("disputes.json", disputes)
        
        self.record_event(
            event_type=AuditEventType.DISPUTE_OPENED,
            actor=initiator_id,
            deal_id=dispute.deal_id,
            data={
                "dispute_id": new_dispute.dispute_id,
                "dispute_type": dispute.dispute_type,
                "respondent_id": dispute.respondent_id,
            }
        )
        
        return new_dispute
    
    def respond_to_dispute(
        self,
        dispute_id: str,
        response: DisputeResponse,
        respondent_id: str
    ) -> Dispute:
        """Submit response to a dispute."""
        disputes = self._load_json("disputes.json")
        
        for i, dispute in enumerate(disputes):
            if dispute["dispute_id"] == dispute_id:
                if dispute.get("respondent_id") != respondent_id:
                    raise ValueError("Only the respondent can submit a response")
                
                if dispute.get("status") != DisputeStatus.OPENED:
                    raise ValueError("Dispute is not in OPENED status")
                
                disputes[i]["response_evidence_hash"] = hashlib.sha256(
                    response.response_description.encode()
                ).hexdigest()
                disputes[i]["status"] = DisputeStatus.EVIDENCE_SUBMITTED
                disputes[i]["resolution_deadline"] = (
                    datetime.now(timezone.utc) + timedelta(days=14)
                ).isoformat()
                
                self._save_json("disputes.json", disputes)
                return Dispute(**disputes[i])
        
        raise ValueError(f"Dispute not found: {dispute_id}")
    
    def submit_dispute_vote(
        self,
        dispute_id: str,
        arbitrator_id: str,
        vote: DisputeVoteRequest
    ) -> Dispute:
        """Submit an arbitrator vote on a dispute."""
        disputes = self._load_json("disputes.json")
        
        for i, dispute in enumerate(disputes):
            if dispute["dispute_id"] == dispute_id:
                if dispute.get("status") not in [
                    DisputeStatus.EVIDENCE_SUBMITTED,
                    DisputeStatus.ARBITRATION
                ]:
                    raise ValueError("Dispute is not ready for voting")
                
                # Check if arbitrator already voted
                for v in dispute.get("votes", []):
                    if v.get("arbitrator_id") == arbitrator_id:
                        raise ValueError("Arbitrator has already voted")
                
                # Add vote
                dispute_vote = DisputeVote(
                    arbitrator_id=arbitrator_id,
                    in_favor_of_initiator=vote.in_favor_of_initiator,
                    reason=vote.reason,
                )
                
                if "votes" not in disputes[i]:
                    disputes[i]["votes"] = []
                disputes[i]["votes"].append(dispute_vote.model_dump())
                disputes[i]["status"] = DisputeStatus.ARBITRATION
                
                # Check for majority (2 of 3)
                votes_for = sum(1 for v in disputes[i]["votes"] if v.get("in_favor_of_initiator"))
                votes_against = len(disputes[i]["votes"]) - votes_for
                
                if votes_for >= 2:
                    disputes[i]["status"] = DisputeStatus.RESOLVED
                    disputes[i]["in_favor_of_initiator"] = True
                    disputes[i]["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    disputes[i]["resolution"] = "Resolved in favor of initiator"
                    
                    self.record_event(
                        event_type=AuditEventType.DISPUTE_RESOLVED,
                        actor="arbitration_system",
                        deal_id=dispute.get("deal_id"),
                        data={
                            "dispute_id": dispute_id,
                            "in_favor_of_initiator": True,
                            "votes_for": votes_for,
                            "votes_against": votes_against,
                        }
                    )
                elif votes_against >= 2:
                    disputes[i]["status"] = DisputeStatus.RESOLVED
                    disputes[i]["in_favor_of_initiator"] = False
                    disputes[i]["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    disputes[i]["resolution"] = "Resolved in favor of respondent"
                    
                    self.record_event(
                        event_type=AuditEventType.DISPUTE_RESOLVED,
                        actor="arbitration_system",
                        deal_id=dispute.get("deal_id"),
                        data={
                            "dispute_id": dispute_id,
                            "in_favor_of_initiator": False,
                            "votes_for": votes_for,
                            "votes_against": votes_against,
                        }
                    )
                
                self._save_json("disputes.json", disputes)
                return Dispute(**disputes[i])
        
        raise ValueError(f"Dispute not found: {dispute_id}")
    
    def get_dispute(self, dispute_id: str) -> Optional[Dispute]:
        """Get a dispute by ID."""
        disputes = self._load_json("disputes.json")
        for dispute in disputes:
            if dispute["dispute_id"] == dispute_id:
                return Dispute(**dispute)
        return None
    
    def list_disputes(
        self,
        deal_id: Optional[str] = None,
        status: Optional[DisputeStatus] = None,
    ) -> List[Dispute]:
        """List disputes with filters."""
        disputes = self._load_json("disputes.json")
        result = []
        
        for dispute in disputes:
            if deal_id and dispute.get("deal_id") != deal_id:
                continue
            if status and dispute.get("status") != status:
                continue
            result.append(Dispute(**dispute))
        
        return result
    
    # =========================================================================
    # Dashboard & Summaries
    # =========================================================================
    
    def get_auditor_dashboard(self, auditor_id: str) -> AuditorDashboard:
        """Get dashboard summary for an auditor."""
        # Get active engagements (grants)
        grants = self.get_auditor_grants(auditor_id, active_only=True)
        active_engagements = len(grants)
        
        # Get pending reviews (deals with grants but no recent attestation)
        deal_ids = {g.deal_id for g in grants}
        attestations = self.list_attestations(auditor_id=auditor_id)
        attested_deals = {a.deal_id for a in attestations}
        pending_reviews = len(deal_ids - attested_deals)
        
        # Get open findings
        findings = self.list_findings(auditor_id=auditor_id)
        open_findings = [f for f in findings if f.status not in [
            FindingStatus.RESOLVED, FindingStatus.CLOSED
        ]]
        
        # Count by severity
        severity_counts = {}
        for f in open_findings:
            sev = f.severity.value if hasattr(f.severity, 'value') else f.severity
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        # Get attestations due (deals with access expiring in 30 days)
        now = datetime.now(timezone.utc)
        expiring_soon = [
            g for g in grants
            if g.expires_at and (g.expires_at - now).days <= 30
        ]
        attestations_due = len(expiring_soon)
        
        # Recent activity from audit trail
        events = self.query_audit_trail(AuditTrailQuery(actor=auditor_id, limit=10))
        recent_activity = [
            {
                "timestamp": e.timestamp.isoformat() if hasattr(e.timestamp, 'isoformat') else e.timestamp,
                "event_type": e.event_type.value if hasattr(e.event_type, 'value') else e.event_type,
                "deal_id": e.deal_id,
            }
            for e in events
        ]
        
        return AuditorDashboard(
            active_engagements=active_engagements,
            pending_reviews=pending_reviews,
            open_findings=len(open_findings),
            findings_by_severity=severity_counts,
            attestations_due=attestations_due,
            recent_activity=recent_activity,
        )
    
    def get_deal_audit_summary(self, deal_id: str) -> DealAuditSummary:
        """Get audit summary for a deal."""
        # Get findings
        findings = self.list_findings(deal_id=deal_id)
        open_findings = [f for f in findings if f.status not in [
            FindingStatus.RESOLVED, FindingStatus.CLOSED
        ]]
        has_critical = any(
            f.severity == FindingSeverity.CRITICAL for f in open_findings
        )
        
        # Get attestations
        attestations = self.list_attestations(deal_id=deal_id)
        last_attestation = attestations[-1] if attestations else None
        
        # Determine compliance status
        if has_critical:
            compliance_status = "NON_COMPLIANT"
        elif open_findings:
            compliance_status = "EXCEPTIONS"
        else:
            compliance_status = "COMPLIANT"
        
        return DealAuditSummary(
            deal_id=deal_id,
            deal_name=None,  # Would need to fetch from deal registry
            current_period=0,  # Would need to fetch from performance data
            last_audit_period=last_attestation.period_end if last_attestation else None,
            last_attestation_type=AttestationType(last_attestation.attestation_type) if last_attestation else None,
            open_findings_count=len(open_findings),
            has_critical_findings=has_critical,
            compliance_status=compliance_status,
            waterfall_verification_status="PENDING",  # Would need verification results
            next_attestation_due=None,  # Would calculate based on schedule
        )
