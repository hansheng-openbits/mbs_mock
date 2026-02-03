"""
RMBS Audit System
=================

Comprehensive audit infrastructure for the RMBS Platform.

This module provides:
- Auditor Registry with certification tracking
- Time-limited, scoped access grants
- Immutable audit trail with hash chain
- Findings and attestations workflow
- Dispute resolution mechanism

Usage
-----
>>> from audit import AuditService
>>> audit_service = AuditService()
>>> audit_service.register_auditor(...)
>>> audit_service.record_event(...)
"""

from .models import (
    # Enums
    AuditorType,
    AccessScope,
    AttestationType,
    FindingSeverity,
    FindingStatus,
    DisputeType,
    DisputeStatus,
    AuditEventType,
    # Auditor Registry
    AuditorProfile,
    AuditorCertification,
    AuditorRegistration,
    # Access Control
    AccessGrant,
    AccessGrantRequest,
    AccessLog,
    # Audit Trail
    AuditTrailEvent,
    AuditTrailQuery,
    # Findings & Attestations
    AuditFinding,
    AuditFindingCreate,
    AuditFindingUpdate,
    AuditAttestation,
    AuditAttestationCreate,
    # Disputes
    Dispute,
    DisputeCreate,
    DisputeResponse,
    DisputeVote,
    DisputeVoteRequest,
    # Verification
    WaterfallVerificationRequest,
    WaterfallVerificationResult,
    StratificationRequest,
    StratificationResult,
    # Reports
    AuditReport,
    AuditReportSection,
    # Dashboard
    AuditorDashboard,
    DealAuditSummary,
)

from .service import AuditService

__all__ = [
    # Main service
    "AuditService",
    # Enums
    "AuditorType",
    "AccessScope",
    "AttestationType",
    "FindingSeverity",
    "FindingStatus",
    "DisputeType",
    "DisputeStatus",
    "AuditEventType",
    # Models
    "AuditorProfile",
    "AuditorCertification",
    "AuditorRegistration",
    "AccessGrant",
    "AccessGrantRequest",
    "AccessLog",
    "AuditTrailEvent",
    "AuditTrailQuery",
    "AuditFinding",
    "AuditFindingCreate",
    "AuditFindingUpdate",
    "AuditAttestation",
    "AuditAttestationCreate",
    "Dispute",
    "DisputeCreate",
    "DisputeResponse",
    "DisputeVote",
    "DisputeVoteRequest",
    "WaterfallVerificationRequest",
    "WaterfallVerificationResult",
    "StratificationRequest",
    "StratificationResult",
    "AuditReport",
    "AuditReportSection",
    "AuditorDashboard",
    "DealAuditSummary",
]
