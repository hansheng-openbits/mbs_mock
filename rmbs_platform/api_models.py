"""
API Request/Response Models
===========================

Pydantic models for API request validation and response serialization.
These models provide:

1. **Input Validation**: Automatic validation of request payloads.
2. **Documentation**: OpenAPI schema generation with examples.
3. **Type Safety**: Runtime type checking for API contracts.

Usage
-----
Import these models in api_main.py for endpoint definitions:

>>> from api_models import DealUploadRequest, SimulationResponse
>>> @app.post("/deals")
... async def upload_deal(request: DealUploadRequest) -> DealUploadResponse:
...     ...

See Also
--------
api_main : Main API module using these models.
pydantic.BaseModel : Base class for all models.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Health Check Models
# =============================================================================


class ComponentHealth(BaseModel):
    """Health status of an individual component."""

    database: str = Field(
        description="Database connection status",
        examples=["healthy", "degraded", "error"],
    )
    storage: str = Field(
        description="File storage system status",
        examples=["healthy", "degraded"],
    )
    models: str = Field(
        description="ML model availability status",
        examples=["healthy", "not_configured"],
    )


class SystemMetrics(BaseModel):
    """Key operational metrics."""

    deals_loaded: int = Field(description="Number of deals in memory")
    collateral_loaded: int = Field(description="Number of collateral sets loaded")
    active_jobs: int = Field(description="Currently running simulation jobs")
    completed_jobs: int = Field(description="Completed simulation jobs")
    scenarios_count: int = Field(description="Total saved scenarios")


class HealthResponse(BaseModel):
    """
    Health check response for monitoring systems.

    Example
    -------
    >>> response = requests.get("/health")
    >>> if response.json()["status"] == "healthy":
    ...     print("System operational")
    """

    status: str = Field(
        description="Overall system health",
        examples=["healthy", "degraded", "unhealthy"],
    )
    version: str = Field(description="API version", examples=["1.2.0"])
    uptime_seconds: float = Field(description="Seconds since server start")
    timestamp: str = Field(description="Current UTC timestamp")
    components: ComponentHealth = Field(description="Component-level health")
    metrics: SystemMetrics = Field(description="Operational metrics")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.2.0",
                "uptime_seconds": 3600.5,
                "timestamp": "2026-01-19T12:00:00+00:00",
                "components": {
                    "database": "healthy",
                    "storage": "healthy",
                    "models": "healthy",
                },
                "metrics": {
                    "deals_loaded": 5,
                    "collateral_loaded": 5,
                    "active_jobs": 2,
                    "completed_jobs": 15,
                    "scenarios_count": 10,
                },
            }
        }


# =============================================================================
# Deal Models
# =============================================================================


class BondDefinition(BaseModel):
    """Bond/tranche definition within a deal."""

    id: str = Field(description="Bond identifier", examples=["A", "M1", "B"])
    original_balance: float = Field(
        description="Original face value", examples=[10000000.0]
    )
    coupon: Dict[str, Any] = Field(
        description="Coupon definition (fixed_rate or floating)",
        examples=[{"fixed_rate": 0.05}],
    )
    seniority: int = Field(
        description="Payment priority (lower = senior)", examples=[1, 2, 3]
    )


class WaterfallStep(BaseModel):
    """Single step in a waterfall definition."""

    action: str = Field(
        description="Step action type",
        examples=["PAY_BOND_INTEREST", "PAY_BOND_PRINCIPAL", "TRANSFER_FUND"],
    )
    from_fund: str = Field(description="Source fund", examples=["IAF", "PAF"])
    group: Optional[str] = Field(
        default=None, description="Target bond group", examples=["Senior", "Mezz"]
    )
    amount_rule: Optional[str] = Field(
        default=None, description="Amount calculation", examples=["ALL", "bonds.A.interest_due"]
    )
    condition: Optional[str] = Field(
        default=None, description="Execution condition", examples=["true", "tests.OC.passed"]
    )


class DealSpecification(BaseModel):
    """Complete deal specification."""

    meta: Dict[str, Any] = Field(
        description="Deal metadata",
        examples=[{"deal_id": "DEAL_2024_001", "issuer": "ABC Mortgage Trust"}],
    )
    bonds: Dict[str, BondDefinition] = Field(description="Bond definitions by ID")
    funds: List[str] = Field(
        description="Cash fund identifiers", examples=[["IAF", "PAF", "Reserve"]]
    )
    waterfalls: Dict[str, Any] = Field(description="Waterfall definitions")
    tests: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Trigger test definitions"
    )
    variables: Optional[Dict[str, str]] = Field(
        default=None, description="Variable calculation rules"
    )


class DealUploadRequest(BaseModel):
    """
    Request to upload a new deal structure.

    Example
    -------
    >>> request = DealUploadRequest(
    ...     deal_id="DEAL_2024_001",
    ...     spec={
    ...         "meta": {"issuer": "ABC Trust"},
    ...         "bonds": {"A": {"original_balance": 10000000, ...}},
    ...         ...
    ...     }
    ... )
    """

    deal_id: str = Field(
        description="Unique deal identifier",
        examples=["DEAL_2024_001", "SAMPLE_RMBS_2024"],
    )
    spec: Dict[str, Any] = Field(description="Full deal specification JSON")

    class Config:
        json_schema_extra = {
            "example": {
                "deal_id": "DEAL_2024_001",
                "spec": {
                    "meta": {"deal_id": "DEAL_2024_001", "issuer": "ABC Mortgage Trust"},
                    "bonds": {
                        "A": {
                            "original_balance": 80000000,
                            "coupon": {"fixed_rate": 0.045},
                            "seniority": 1,
                        },
                        "M": {
                            "original_balance": 15000000,
                            "coupon": {"fixed_rate": 0.055},
                            "seniority": 2,
                        },
                        "B": {
                            "original_balance": 5000000,
                            "coupon": {"fixed_rate": 0.075},
                            "seniority": 3,
                        },
                    },
                    "funds": ["IAF", "PAF"],
                    "waterfalls": {
                        "interest": {"steps": []},
                        "principal": {"steps": []},
                    },
                },
            }
        }


class DealUploadResponse(BaseModel):
    """Response after uploading a deal."""

    status: str = Field(examples=["deal_uploaded"])
    deal_id: str = Field(examples=["DEAL_2024_001"])
    version: int = Field(description="Version number assigned", examples=[1])
    hash: str = Field(description="Content hash for change detection")


# =============================================================================
# Collateral Models
# =============================================================================


class CollateralUploadRequest(BaseModel):
    """Request to upload initial collateral attributes."""

    deal_id: str = Field(description="Associated deal ID", examples=["DEAL_2024_001"])
    collateral: Dict[str, Any] = Field(description="Collateral attributes")

    class Config:
        json_schema_extra = {
            "example": {
                "deal_id": "DEAL_2024_001",
                "collateral": {
                    "original_balance": 100000000,
                    "current_balance": 95000000,
                    "wac": 0.065,
                    "wam": 340,
                    "loan_count": 500,
                    "avg_fico": 720,
                    "avg_ltv": 75,
                    "source_uri": "datasets/SAMPLE_RMBS_2024/loan_tape.csv",
                },
            }
        }


# =============================================================================
# Simulation Models
# =============================================================================


class SimulationRequest(BaseModel):
    """
    Request to run a cashflow simulation.

    This is the primary analytics endpoint for investors to project
    deal cashflows under various scenarios.
    """

    deal_id: str = Field(
        description="Deal to simulate", examples=["DEAL_2024_001"]
    )
    horizon: int = Field(
        default=60,
        description="Projection horizon in months",
        ge=1,
        le=360,
        examples=[60, 120, 360],
    )
    cpr: float = Field(
        default=0.10,
        description="Constant Prepayment Rate (annual)",
        ge=0.0,
        le=1.0,
        examples=[0.08, 0.10, 0.15],
    )
    cdr: float = Field(
        default=0.01,
        description="Constant Default Rate (annual)",
        ge=0.0,
        le=1.0,
        examples=[0.005, 0.01, 0.02],
    )
    severity: float = Field(
        default=0.35,
        description="Loss severity on defaults",
        ge=0.0,
        le=1.0,
        examples=[0.30, 0.35, 0.45],
    )
    use_ml_models: bool = Field(
        default=False,
        description="Use ML models for prepay/default prediction",
    )
    rate_scenario: Optional[str] = Field(
        default="base",
        description="Interest rate scenario for ML models",
        examples=["rally", "base", "selloff"],
    )
    start_rate: Optional[float] = Field(
        default=0.045,
        description="Starting interest rate for ML scenarios",
        examples=[0.035, 0.045, 0.055],
    )
    rate_sensitivity: Optional[float] = Field(
        default=1.0,
        description="Rate sensitivity multiplier for ML",
        ge=0.0,
        le=5.0,
    )
    scenario_id: Optional[str] = Field(
        default=None,
        description="Saved scenario ID to use",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "deal_id": "DEAL_2024_001",
                "horizon": 60,
                "cpr": 0.10,
                "cdr": 0.01,
                "severity": 0.35,
                "use_ml_models": True,
                "rate_scenario": "base",
                "start_rate": 0.045,
            }
        }


class SimulationResult(BaseModel):
    """Simulation result payload."""

    status: str = Field(examples=["COMPLETED", "FAILED"])
    detailed_tape: List[Dict[str, Any]] = Field(
        description="Period-by-period cashflow details"
    )
    actuals_tape: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Historical actuals periods"
    )
    reconciliation: Optional[Dict[str, Any]] = Field(
        default=None, description="Actuals vs. model reconciliation"
    )
    summary: Dict[str, Any] = Field(description="Aggregate metrics")
    warnings: Optional[List[str]] = Field(
        default=None, description="Non-fatal warnings"
    )
    model_info: Optional[Dict[str, Any]] = Field(
        default=None, description="ML model diagnostics"
    )


# =============================================================================
# Scenario Models
# =============================================================================


class ScenarioCreateRequest(BaseModel):
    """Request to create a new scenario."""

    name: str = Field(description="Scenario name", examples=["Base Case Q1 2026"])
    description: Optional[str] = Field(
        default=None, description="Detailed description"
    )
    parameters: Dict[str, Any] = Field(description="Scenario parameters")
    tags: Optional[List[str]] = Field(
        default=None, examples=[["base", "quarterly", "approved"]]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Stress Test - Rising Rates",
                "description": "Scenario with 200bp rate increase and elevated defaults",
                "parameters": {
                    "cpr": 0.08,
                    "cdr": 0.025,
                    "severity": 0.40,
                    "rate_scenario": "selloff",
                    "start_rate": 0.065,
                },
                "tags": ["stress", "rates", "2026Q1"],
            }
        }


class ScenarioResponse(BaseModel):
    """Scenario data response."""

    scenario_id: str = Field(description="Unique scenario identifier")
    name: str = Field(description="Scenario name")
    description: Optional[str] = Field(default=None)
    parameters: Dict[str, Any] = Field(description="Scenario parameters")
    status: str = Field(
        description="Workflow status",
        examples=["draft", "approved", "archived"],
    )
    created_at: str = Field(description="Creation timestamp")
    created_by: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    version: int = Field(description="Current version number")


# =============================================================================
# Validation Models
# =============================================================================


class ValidationResult(BaseModel):
    """Result of a validation check."""

    valid: bool = Field(description="Whether validation passed")
    errors: List[str] = Field(description="List of validation errors")
    warnings: List[str] = Field(description="List of non-fatal warnings")


class DealValidationResponse(BaseModel):
    """Response from deal validation endpoint."""

    deal_id: str = Field(description="Validated deal ID")
    valid: bool = Field(description="Overall validation status")
    bond_checks: ValidationResult = Field(description="Bond definition checks")
    waterfall_checks: ValidationResult = Field(description="Waterfall rule checks")
    overall_errors: List[str] = Field(description="Top-level errors")
    overall_warnings: List[str] = Field(description="Top-level warnings")


class PerformanceValidationResponse(BaseModel):
    """Response from performance validation endpoint."""

    deal_id: str = Field(description="Deal ID for performance data")
    valid: bool = Field(description="Overall validation status")
    row_count: int = Field(description="Number of rows validated")
    errors: List[str] = Field(description="Validation errors")
    warnings: List[str] = Field(description="Validation warnings")
    statistics: Optional[Dict[str, Any]] = Field(
        default=None, description="Data quality statistics"
    )


# =============================================================================
# Audit Models
# =============================================================================


class AuditEvent(BaseModel):
    """Single audit trail event."""

    timestamp: str = Field(description="Event timestamp")
    event_type: str = Field(
        description="Type of event",
        examples=["deal_upload", "simulation_start", "scenario_approved"],
    )
    actor: Optional[str] = Field(default=None, description="User who triggered event")
    role: Optional[str] = Field(default=None, description="User's role")
    resource_type: Optional[str] = Field(
        default=None, examples=["deal", "scenario", "simulation"]
    )
    resource_id: Optional[str] = Field(default=None, description="Resource identifier")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Event details")


class AuditEventsResponse(BaseModel):
    """Response containing audit events."""

    total: int = Field(description="Total matching events")
    events: List[AuditEvent] = Field(description="List of events")
    filters_applied: Optional[Dict[str, Any]] = Field(
        default=None, description="Active filters"
    )


# =============================================================================
# Version History Models
# =============================================================================


class VersionMetadata(BaseModel):
    """Metadata for a versioned resource."""

    version: int = Field(description="Version number")
    timestamp: str = Field(description="Version creation time")
    hash: str = Field(description="Content hash")
    actor: Optional[str] = Field(default=None, description="Who created this version")
    comment: Optional[str] = Field(default=None, description="Version comment")


class VersionListResponse(BaseModel):
    """Response listing version history."""

    resource_type: str = Field(examples=["deal", "collateral", "performance"])
    resource_id: str = Field(description="Resource identifier")
    current_version: int = Field(description="Latest version number")
    versions: List[VersionMetadata] = Field(description="Version history")


# =============================================================================
# Error Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(description="Error message")
    error_code: Optional[str] = Field(default=None, description="Machine-readable code")
    field: Optional[str] = Field(default=None, description="Field causing error")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Deal not found: INVALID_ID",
                "error_code": "DEAL_NOT_FOUND",
            }
        }


class ValidationErrorResponse(BaseModel):
    """Validation error response with field details."""

    detail: str = Field(default="Validation failed")
    errors: List[Dict[str, Any]] = Field(description="Field-level errors")

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Validation failed",
                "errors": [
                    {"loc": ["body", "deal_id"], "msg": "field required", "type": "value_error.missing"},
                ],
            }
        }
