# api_main.py
"""
RMBS Platform API
=================

FastAPI service providing REST endpoints for RMBS deal management, simulation,
and audit functionality. This module implements a persona-based architecture
supporting Arranger, Servicer, Investor, and Auditor workflows.

Endpoints Overview
------------------
**Arranger (Deal Structuring)**:
- POST /deals : Upload a new deal structure
- POST /collateral : Upload initial collateral attributes
- GET /deals/{deal_id}/versions : List deal version history
- POST /deal/validate : Validate deal specification

**Servicer (Operations)**:
- POST /performance/{deal_id} : Upload monthly performance tape
- DELETE /performance/{deal_id} : Clear performance data
- GET /performance/{deal_id}/versions : List performance version history
- POST /validation/performance : Validate performance data

**Investor (Analytics)**:
- POST /simulate : Run cashflow simulation
- GET /results/{job_id} : Retrieve simulation results
- POST /scenarios : Create scenario definition
- GET /scenarios : List saved scenarios
- PUT /scenarios/{scenario_id} : Update scenario
- POST /scenarios/{scenario_id}/approve : Approve scenario

**Auditor (Compliance)**:
- GET /audit/events : List audit trail events
- GET /audit/events/download : Download audit log
- GET /audit/run/{job_id}/bundle : Download audit bundle

RBAC (Role-Based Access Control)
--------------------------------
All endpoints require an ``X-User-Role`` header specifying the user's role.
Unauthorized access returns 401 (missing header) or 403 (wrong role).

Storage Architecture
--------------------
- In-memory databases for active session data
- Persisted JSON/CSV files for durability
- Versioned storage for audit trail and rollback

Example
-------
>>> import requests
>>> # Upload a deal as an Arranger
>>> headers = {"X-User-Role": "arranger"}
>>> response = requests.post(
...     "http://localhost:8000/deals",
...     json={"deal_id": "TEST_2024", "spec": deal_json},
...     headers=headers
... )
>>> print(response.json())
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
)
from pydantic import BaseModel

# Bootstrap sys.path for package resolution
if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

# Import simulation engine and configuration
try:
    from .engine import run_simulation
    from .config import settings, get_severity_parameters, validate_storage_paths
except ImportError:
    from rmbs_platform.engine import run_simulation
    from rmbs_platform.config import settings, get_severity_parameters, validate_storage_paths

# API Version
API_VERSION = "1.2.0"

# OpenAPI Tags for documentation organization
OPENAPI_TAGS = [
    {
        "name": "System",
        "description": "Health checks, status monitoring, and system metrics for orchestration and monitoring systems.",
    },
    {
        "name": "Arranger",
        "description": """
**Deal Structuring Endpoints**

Arrangers use these endpoints to upload and manage deal structures:
- Upload deal specifications (waterfall rules, bond definitions)
- Upload initial collateral attributes
- Validate deal structures before execution
- View version history for audit trail

*Requires X-User-Role: arranger*
        """,
    },
    {
        "name": "Servicer",
        "description": """
**Operations Endpoints**

Servicers use these endpoints for ongoing deal operations:
- Upload monthly performance tapes (loan-level data)
- Clear/reset performance data for reprocessing
- Validate performance data quality
- View performance version history

*Requires X-User-Role: servicer*
        """,
    },
    {
        "name": "Investor",
        "description": """
**Analytics Endpoints**

Investors use these endpoints for deal analysis:
- Run cashflow simulations with various scenarios
- Retrieve simulation results and reports
- Create and manage scenario definitions
- Compare scenario outcomes

*Requires X-User-Role: investor*
        """,
    },
    {
        "name": "Auditor",
        "description": """
**Compliance Endpoints**

Auditors use these endpoints for regulatory compliance:
- View audit trail event logs
- Download audit bundles for specific runs
- Access version history across all data types
- Export compliance reports

*Requires X-User-Role: auditor*
        """,
    },
    {
        "name": "Scenarios",
        "description": """
**Scenario Management**

Endpoints for creating, managing, and versioning simulation scenarios.
Scenarios capture assumption sets that can be saved, shared, and compared.
        """,
    },
    {
        "name": "Validation",
        "description": "Data validation endpoints for checking deal and performance data integrity.",
    },
    {
        "name": "Models",
        "description": "ML model registry and configuration endpoints.",
    },
]

app = FastAPI(
    title="RMBS Engine API",
    version=API_VERSION,
    description="""
# RMBS Platform API

A comprehensive REST API for Residential Mortgage-Backed Securities (RMBS) deal simulation and analysis.

## Overview

This API supports the full RMBS deal lifecycle:

1. **Deal Structuring** (Arranger): Upload deal specifications, define tranches, and configure waterfalls.
2. **Ongoing Operations** (Servicer): Submit monthly performance data and track loan-level metrics.
3. **Analytics** (Investor): Run cashflow projections under various prepayment/default scenarios.
4. **Compliance** (Auditor): Access audit trails, version history, and compliance reports.

## Authentication

All endpoints require an `X-User-Role` header specifying the caller's role:
- `arranger` - Deal structuring operations
- `servicer` - Performance data management
- `investor` - Simulation and analytics
- `auditor` - Compliance and audit access

## Key Features

- **ML-Driven Projections**: Integrated prepayment and default models
- **Versioned Storage**: Full audit trail with version history
- **Scenario Management**: Save, compare, and approve simulation scenarios
- **Industry-Standard Reports**: Factor reports, distribution statements

## API Documentation

- **Swagger UI**: `/docs` (interactive documentation)
- **ReDoc**: `/redoc` (detailed reference)
- **OpenAPI Schema**: `/openapi.json`

## Rate Limits

Standard rate limits apply:
- 100 requests/minute for read operations
- 10 requests/minute for simulation jobs
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "RMBS Platform Support",
        "email": "support@rmbs-platform.example.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://rmbs-platform.example.com/license",
    },
)

def _require_role(
    allowed_roles: List[str],
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> None:
    """
    Enforce role-based access control for API endpoints.

    This dependency function validates that the request includes a valid
    ``X-User-Role`` header and that the role is authorized for the action.

    Parameters
    ----------
    allowed_roles : list of str
        Roles permitted to access this endpoint (e.g., ["arranger", "investor"]).
    x_user_role : str, optional
        The role header value from the request.

    Raises
    ------
    HTTPException
        401 if header is missing, 403 if role is not permitted.

    Example
    -------
    >>> @app.get("/protected")
    ... async def protected_endpoint(
    ...     _: None = Depends(lambda r=Header(...): _require_role(["admin"], r))
    ... ):
    ...     return {"status": "authorized"}
    """
    if x_user_role is None:
        raise HTTPException(401, "Missing X-User-Role header.")
    role = x_user_role.strip().lower()
    if role not in {r.lower() for r in allowed_roles}:
        raise HTTPException(403, f"Role '{x_user_role}' not permitted for this action.")

# --- DATABASE (In-Memory for Demo) ---
DEALS_DB: Dict[str, Any] = {}   # Stores JSON structures
JOBS_DB: Dict[str, Any] = {}    # Stores simulation results
COLLATERAL_DB: Dict[str, Any] = {}  # Stores initial collateral attributes
PERFORMANCE_DB: Dict[str, List[Dict[str, Any]]] = {}  # Stores servicer performance rows
SCENARIO_DB: Dict[str, Any] = {}  # Stores scenario definitions

# --- PERSISTENT STORAGE (from configuration) ---
DEALS_DIR = Path(settings.deals_dir)
DEALS_DIR.mkdir(parents=True, exist_ok=True)
COLLATERAL_DIR = Path(settings.collateral_dir)
COLLATERAL_DIR.mkdir(parents=True, exist_ok=True)
PERFORMANCE_DIR = Path(settings.performance_dir)
PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
SCENARIOS_DIR = Path(settings.scenarios_dir)
SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
SCENARIOS_VERSIONS_DIR = Path(settings.scenarios_versions_dir)
SCENARIOS_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_PATH = Path(settings.audit_log_path)
AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
DEALS_VERSIONS_DIR = Path(settings.deals_versions_dir)
DEALS_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
COLLATERAL_VERSIONS_DIR = Path(settings.collateral_versions_dir)
COLLATERAL_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
PERFORMANCE_VERSIONS_DIR = Path(settings.performance_versions_dir)
PERFORMANCE_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Application startup time for health check
_STARTUP_TIME = datetime.now(timezone.utc)

def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()

def _next_version_number(version_dir: Path, deal_id: str) -> int:
    """Return the next integer version for a deal artifact."""
    safe_id = _safe_deal_id(deal_id)
    prefix = f"{safe_id}_v"
    max_version = 0
    for path in version_dir.glob(f"{prefix}*"):
        stem = path.stem
        match = re.match(rf"^{re.escape(prefix)}(\d+)", stem)
        if match:
            try:
                max_version = max(max_version, int(match.group(1)))
            except ValueError:
                continue
    return max_version + 1

def _write_versioned_json(
    version_dir: Path,
    deal_id: str,
    payload: Dict[str, Any],
    *,
    created_by: Optional[str] = None,
    source_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a versioned JSON artifact and return metadata."""
    version = _next_version_number(version_dir, deal_id)
    safe_id = _safe_deal_id(deal_id)
    version_tag = f"{version:04d}"
    data_path = version_dir / f"{safe_id}_v{version_tag}.json"
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    data_path.write_text(serialized, encoding="utf-8")
    content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    metadata = {
        "deal_id": deal_id,
        "version": version,
        "created_at": _utc_now_iso(),
        "created_by": created_by or "unknown",
        "source_name": source_name or "",
        "content_hash": content_hash,
        "path": str(data_path),
    }
    meta_path = version_dir / f"{safe_id}_v{version_tag}.meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata

def _write_versioned_bytes(
    version_dir: Path,
    deal_id: str,
    content: bytes,
    *,
    extension: str,
    created_by: Optional[str] = None,
    source_name: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a versioned binary artifact and return metadata."""
    version = _next_version_number(version_dir, deal_id)
    safe_id = _safe_deal_id(deal_id)
    version_tag = f"{version:04d}"
    data_path = version_dir / f"{safe_id}_v{version_tag}.{extension}"
    data_path.write_bytes(content)
    content_hash = hashlib.sha256(content).hexdigest()
    metadata = {
        "deal_id": deal_id,
        "version": version,
        "created_at": _utc_now_iso(),
        "created_by": created_by or "unknown",
        "source_name": source_name or "",
        "content_hash": content_hash,
        "path": str(data_path),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    meta_path = version_dir / f"{safe_id}_v{version_tag}.meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata

def _log_audit_event(
    event_type: str,
    *,
    actor: Optional[str] = None,
    deal_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    job_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a structured audit event to the audit log."""
    event = {
        "timestamp": _utc_now_iso(),
        "event_type": event_type,
        "actor": actor or "unknown",
        "deal_id": deal_id,
        "scenario_id": scenario_id,
        "job_id": job_id,
        "details": details or {},
    }
    try:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        # Audit logging must not break core flows.
        pass

def _read_audit_events(
    *,
    limit: int = 200,
    event_type: Optional[str] = None,
    deal_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    job_id: Optional[str] = None,
    actor: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read audit events from disk with optional filtering."""
    if not AUDIT_LOG_PATH.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(event)
    except Exception:
        return []

    def _match(value: Optional[str], candidate: Optional[str]) -> bool:
        if value is None:
            return True
        return str(candidate or "") == str(value)

    filtered = [
        e for e in events
        if _match(event_type, e.get("event_type"))
        and _match(deal_id, e.get("deal_id"))
        and _match(scenario_id, e.get("scenario_id"))
        and _match(job_id, e.get("job_id"))
        and _match(actor, e.get("actor"))
    ]
    if limit <= 0:
        return filtered
    return filtered[-limit:]

def _list_version_metadata(version_dir: Path, deal_id: str) -> List[Dict[str, Any]]:
    """Return sorted version metadata entries for a deal."""
    safe_id = _safe_deal_id(deal_id)
    metadata_files = sorted(version_dir.glob(f"{safe_id}_v*.meta.json"))
    results: List[Dict[str, Any]] = []
    for path in metadata_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        results.append(data)
    results.sort(key=lambda row: row.get("version", 0))
    return results

def _safe_deal_id(deal_id: str) -> str:
    """Normalize a deal ID for filesystem-safe storage."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", deal_id or "").strip("_")
    return safe or "deal"

def _deal_file_path(deal_id: str) -> Path:
    """Return the path where a deal spec is persisted."""
    return DEALS_DIR / f"{_safe_deal_id(deal_id)}.json"

def _collateral_file_path(deal_id: str) -> Path:
    """Return the path where collateral data is persisted."""
    return COLLATERAL_DIR / f"{_safe_deal_id(deal_id)}.json"

def _performance_file_path(deal_id: str) -> Path:
    """Return the path where performance data is persisted."""
    return PERFORMANCE_DIR / f"{_safe_deal_id(deal_id)}.csv"

def _load_persisted_deals() -> None:
    """Load persisted deals into the in-memory store on startup."""
    for path in DEALS_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                spec = json.load(f)
            deal_id = spec.get("meta", {}).get("deal_id") or path.stem
            DEALS_DB[deal_id] = spec
        except Exception:
            continue

def _load_persisted_collateral() -> None:
    """Load persisted collateral into the in-memory store on startup."""
    for path in COLLATERAL_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                collateral = json.load(f)
            deal_id = collateral.get("deal_id") or path.stem
            COLLATERAL_DB[deal_id] = collateral.get("data", collateral)
        except Exception:
            continue

def _load_persisted_performance() -> None:
    """Load persisted performance data into the in-memory store on startup."""
    for path in PERFORMANCE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(path)
            deal_id = path.stem
            PERFORMANCE_DB[deal_id] = df.to_dict(orient="records")
        except Exception:
            continue

def _scenario_file_path(scenario_id: str) -> Path:
    """Return the path where a scenario is persisted."""
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", scenario_id or "").strip("_") or "scenario"
    return SCENARIOS_DIR / f"{safe_id}.json"

def _load_persisted_scenarios() -> None:
    """Load persisted scenarios into the in-memory store on startup."""
    for path in SCENARIOS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        # Normalize legacy scenario schema variants:
        # - Some curated scenarios use "parameters" instead of "params"
        if "params" not in payload and "parameters" in payload and isinstance(payload.get("parameters"), dict):
            payload = dict(payload)
            payload["params"] = payload.pop("parameters")

        scenario_id = payload.get("scenario_id") or path.stem
        payload["scenario_id"] = scenario_id
        SCENARIO_DB[scenario_id] = payload

_load_persisted_deals()
_load_persisted_collateral()
_load_persisted_performance()
_load_persisted_scenarios()

def _sanitize_json(value: Any) -> Any:
    """Replace non-finite values to keep API output JSON-safe."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    return value

def _load_model_registry() -> Dict[str, Any]:
    """Load the ML model registry definition."""
    registry_path = Path(__file__).resolve().parent / "models" / "model_registry.json"
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text())
    except Exception:
        return {}

def _normalize_perf_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize performance tape column names and compute derived columns."""
    # Standard ID column renames
    if "BondID" in df.columns and "BondId" not in df.columns:
        df = df.rename(columns={"BondID": "BondId"})
    if "LoanID" in df.columns and "LoanId" not in df.columns:
        df = df.rename(columns={"LoanID": "LoanId"})
    
    # Common column name variations
    col_renames = {
        "EndingBalance": "EndBalance",
        "Prepayments": "Prepayment",
        "Recovery": "Recoveries",
    }
    for old_col, new_col in col_renames.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Compute PrincipalCollected from component columns if not present
    if "PrincipalCollected" not in df.columns and "Period" in df.columns:
        sched_prin = pd.to_numeric(df.get("ScheduledPrincipal", 0.0), errors="coerce").fillna(0.0)
        prepay = pd.to_numeric(df.get("Prepayment", 0.0), errors="coerce").fillna(0.0)
        df["PrincipalCollected"] = sched_prin + prepay
    
    return df

def _aggregate_performance(performance_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate loan-level or pool-level performance into period totals."""
    if not performance_rows:
        return []
    df = pd.DataFrame(performance_rows)
    if df.empty or "Period" not in df.columns:
        return []
    df = _normalize_perf_df(df)

    # Convert Period to numeric for proper sorting
    df["Period"] = pd.to_numeric(df["Period"], errors="coerce")
    df = df.dropna(subset=["Period"])
    df["Period"] = df["Period"].astype(int)

    # Summable columns (cashflows, losses, etc.)
    sum_candidates = [
        "InterestCollected",
        "PrincipalCollected",
        "Prepayment",
        "ScheduledPrincipal",
        "RealizedLoss",
        "Recoveries",
        "ScheduledInterest",
        "ServicerAdvances",
        "Defaults",
    ]
    # Rate/balance columns (take last value, not sum)
    rate_candidates = [
        "EndBalance",
        "Delinq30",
        "Delinq60",
        "Delinq90Plus",
        "Delinq60Plus",
        "CPR",
        "CDR",
        "Severity",
        "PoolStatus",
    ]

    # Convert all numeric columns to proper numeric types
    all_numeric_cols = sum_candidates + [c for c in rate_candidates if c != "PoolStatus"]
    for col in all_numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    sum_cols = [c for c in sum_candidates if c in df.columns]
    rate_cols = [c for c in rate_candidates if c in df.columns]
    
    # Fill missing sum columns with 0
    for col in sum_candidates:
        if col not in df.columns:
            df[col] = 0.0
    sum_cols = sum_candidates

    if "LoanId" in df.columns:
        loan_df = df[df["LoanId"].notna()].copy()
        if loan_df.empty:
            return []
        # Build aggregation dict
        agg_dict = {c: "sum" for c in sum_cols if c in loan_df.columns}
        for c in rate_cols:
            if c in loan_df.columns:
                # For loan-level data, sum balances, take last for rates/status
                if c == "EndBalance":
                    agg_dict[c] = "sum"  # Sum loan balances to get pool balance
                else:
                    agg_dict[c] = "last"
        agg = loan_df.groupby("Period", as_index=False).agg(agg_dict)
        agg = agg.sort_values("Period")
        return agg.to_dict(orient="records")

    # Pool-level data
    agg_dict = {c: "sum" for c in sum_cols if c in df.columns}
    for c in rate_cols:
        if c in df.columns:
            agg_dict[c] = "last"
    agg = df.groupby("Period", as_index=False).agg(agg_dict)
    agg = agg.sort_values("Period")
    return agg.to_dict(orient="records")

def _latest_actual_period(actuals_data: List[Dict[str, Any]]) -> Optional[int]:
    """Return the most recent period number from actuals data."""
    if not actuals_data:
        return None
    periods = [row.get("Period") for row in actuals_data if row.get("Period") is not None]
    if not periods:
        return None
    try:
        return int(max(periods))
    except (TypeError, ValueError):
        return None

# --- DATA MODELS ---
class DealUpload(BaseModel):
    """
    Request payload for uploading a deal structure.

    Attributes
    ----------
    deal_id : str
        Unique identifier for the deal.
    spec : dict
        Deal specification containing meta, bonds, waterfalls, etc.
    created_by : str, optional
        User or system that created this upload.
    source_name : str, optional
        Name of the source file or system.
    """

    deal_id: str
    spec: Dict[str, Any]
    created_by: Optional[str] = None
    source_name: Optional[str] = None


class CollateralUpload(BaseModel):
    """
    Request payload for uploading initial collateral attributes.

    Attributes
    ----------
    deal_id : str
        Deal identifier to associate collateral with.
    collateral : dict
        Collateral specification (balance, WAC, WAM, ml_config, etc.).
    created_by : str, optional
        User or system that created this upload.
    source_name : str, optional
        Name of the source file or system.
    """

    deal_id: str
    collateral: Dict[str, Any]
    created_by: Optional[str] = None
    source_name: Optional[str] = None


class SimRequest(BaseModel):
    """
    Simulation request with modeling assumptions and ML overrides.

    Attributes
    ----------
    deal_id : str
        Deal identifier to simulate.
    cpr : float
        Constant Prepayment Rate (annual, decimal). Default: 0.10 (10%).
    cdr : float
        Constant Default Rate (annual, decimal). Default: 0.01 (1%).
    severity : float
        Loss severity on defaults. Default: 0.40 (40%).
    use_ml_models : bool
        Whether to use ML prepay/default models. Default: False.
    scenario_id : str, optional
        Scenario identifier to log with this run.
    prepay_model_key : str, optional
        Key in model registry for prepayment model.
    default_model_key : str, optional
        Key in model registry for default model.
    rate_scenario : str, optional
        Rate path scenario: "rally", "selloff", or "base".
    start_rate : float, optional
        Starting short rate for Vasicek model.
    rate_sensitivity : float, optional
        Multiplier for rate incentive effect on prepayment.
    feature_source : str, optional
        How to compute ML features: "simulated" or "market_rates".
    origination_source_uri : str, optional
        Path to origination tape for ML features.
    horizon_periods : int, optional
        Number of monthly periods to project (default 60).
    """

    deal_id: str
    cpr: float = 0.10
    cdr: float = 0.01
    severity: float = 0.40
    use_ml_models: bool = False
    scenario_id: Optional[str] = None
    horizon_periods: int = 60
    prepay_model_key: Optional[str] = None
    default_model_key: Optional[str] = None
    rate_scenario: Optional[str] = None
    start_rate: Optional[float] = None
    rate_sensitivity: Optional[float] = None
    feature_source: Optional[str] = None
    origination_source_uri: Optional[str] = None


class DealValidateRequest(BaseModel):
    """
    Request to validate a deal specification.

    Provide either deal_id (to validate stored deal) or spec (to validate
    a new specification without storing it).

    Attributes
    ----------
    deal_id : str, optional
        Stored deal to validate.
    spec : dict, optional
        Deal specification to validate inline.
    """

    deal_id: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None


class PerformanceValidateRequest(BaseModel):
    """
    Request to validate performance data.

    Provide either deal_id (to validate stored performance) or rows
    (to validate inline data).

    Attributes
    ----------
    deal_id : str, optional
        Deal whose performance to validate.
    rows : list of dict, optional
        Performance rows to validate inline.
    """

    deal_id: Optional[str] = None
    rows: Optional[List[Dict[str, Any]]] = None


class ScenarioCreateRequest(BaseModel):
    """
    Request to create or store a scenario definition.

    Attributes
    ----------
    name : str
        Human-readable scenario name.
    description : str, optional
        Detailed description of the scenario.
    params : dict
        Simulation parameters (cpr, cdr, severity, ml settings, etc.).
    created_by : str, optional
        User who created the scenario.
    tags : list of str, optional
        Searchable tags for categorization.
    status : str, optional
        Initial status: "draft", "approved", etc.
    """

    name: str
    description: Optional[str] = None
    params: Dict[str, Any]
    created_by: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


class ScenarioUpdateRequest(BaseModel):
    """
    Request to update an existing scenario definition.

    All fields are optional; only provided fields will be updated.

    Attributes
    ----------
    name : str, optional
        Updated scenario name.
    description : str, optional
        Updated description.
    params : dict, optional
        Updated simulation parameters.
    updated_by : str, optional
        User making the update.
    tags : list of str, optional
        Updated tags.
    status : str, optional
        Updated status.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    updated_by: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


class ScenarioActionRequest(BaseModel):
    """
    Request to approve, archive, or perform other actions on a scenario.

    Attributes
    ----------
    actor : str, optional
        User performing the action.
    note : str, optional
        Optional note or reason for the action.
    """

    actor: Optional[str] = None
    note: Optional[str] = None


# ============================================================================
# SYSTEM ENDPOINTS (Health, Status, Metrics)
# ============================================================================

@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    Return system health status for monitoring and orchestration.

    This endpoint is designed for Kubernetes liveness/readiness probes,
    load balancer health checks, and monitoring systems. It returns:

    - **status**: Overall health ("healthy" or "degraded")
    - **version**: API version string
    - **uptime_seconds**: Seconds since server start
    - **components**: Status of individual subsystems
    - **metrics**: Key operational metrics

    Returns
    -------
    dict
        Health status response with component details.

    Example Response
    ----------------
    ```json
    {
        "status": "healthy",
        "version": "1.1.0",
        "uptime_seconds": 3600,
        "timestamp": "2026-01-18T12:00:00Z",
        "components": {
            "database": "healthy",
            "storage": "healthy",
            "models": "healthy"
        },
        "metrics": {
            "deals_loaded": 5,
            "active_jobs": 2,
            "scenarios_count": 10
        }
    }
    ```
    """
    uptime = (datetime.now(timezone.utc) - _STARTUP_TIME).total_seconds()

    # Check component health
    components = {
        "database": "healthy",  # In-memory DB is always healthy
        "storage": "healthy",
        "models": "unknown",
    }

    # Verify storage directories are accessible
    try:
        for dir_path in [DEALS_DIR, COLLATERAL_DIR, PERFORMANCE_DIR]:
            if not dir_path.exists():
                components["storage"] = "degraded"
                break
    except Exception:
        components["storage"] = "degraded"

    # Check model registry availability
    try:
        registry = _load_model_registry()
        if registry:
            components["models"] = "healthy"
            # Verify model files exist
            base_dir = Path(settings.models_dir)
            for key, meta in registry.items():
                model_path = meta.get("path")
                if model_path:
                    full_path = base_dir / model_path if not Path(model_path).is_absolute() else Path(model_path)
                    if not full_path.exists():
                        components["models"] = "degraded"
                        break
        else:
            components["models"] = "not_configured"
    except Exception:
        components["models"] = "error"

    # Determine overall status
    overall_status = "healthy"
    if any(v == "degraded" for v in components.values()):
        overall_status = "degraded"
    if any(v == "error" for v in components.values()):
        overall_status = "unhealthy"

    return {
        "status": overall_status,
        "version": API_VERSION,
        "uptime_seconds": round(uptime, 2),
        "timestamp": _utc_now_iso(),
        "components": components,
        "metrics": {
            "deals_loaded": len(DEALS_DB),
            "collateral_loaded": len(COLLATERAL_DB),
            "active_jobs": sum(1 for j in JOBS_DB.values() if j.get("status") == "RUNNING"),
            "completed_jobs": sum(1 for j in JOBS_DB.values() if j.get("status") == "COMPLETED"),
            "scenarios_count": len(SCENARIO_DB),
        },
        "configuration": {
            "log_level": settings.log_level,
            "ml_enabled_default": settings.ml_enabled_by_default,
            "severity_model_enabled": settings.severity_model_enabled,
            "cleanup_call_enabled": settings.cleanup_call_enabled,
        },
    }


@app.get("/health/ready", tags=["System"])
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the service is ready to accept traffic, 503 otherwise.
    Unlike /health, this endpoint focuses solely on readiness without
    detailed diagnostics.

    Returns
    -------
    dict
        Simple readiness status.

    Raises
    ------
    HTTPException
        503 if the service is not ready.
    """
    # Check critical dependencies
    try:
        if not DEALS_DIR.exists():
            raise HTTPException(503, "Storage not ready")
        return {"status": "ready", "timestamp": _utc_now_iso()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Service not ready: {e}")


@app.get("/health/live", tags=["System"])
async def liveness_check() -> Dict[str, Any]:
    """
    Kubernetes liveness probe endpoint.

    Returns 200 if the service process is running. This is a minimal
    check that should rarely fail - it only indicates the process is alive.

    Returns
    -------
    dict
        Simple liveness status.
    """
    return {"status": "alive", "timestamp": _utc_now_iso()}


# --- ENDPOINTS ---

@app.post("/deals", tags=["Arranger"])
async def upload_deal(
    deal: DealUpload,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    """Arranger uploads a new deal structure."""
    if "meta" not in deal.spec:
        deal.spec["meta"] = {}
    deal.spec["meta"]["deal_id"] = deal.deal_id
    deal.spec.pop("collateral", None)
    DEALS_DB[deal.deal_id] = deal.spec
    path = _deal_file_path(deal.deal_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump(deal.spec, f, indent=2)
    _write_versioned_json(
        DEALS_VERSIONS_DIR,
        deal.deal_id,
        deal.spec,
        created_by=deal.created_by,
        source_name=deal.source_name,
    )
    _log_audit_event(
        "deal.upload",
        actor=deal.created_by,
        deal_id=deal.deal_id,
        details={"source_name": deal.source_name},
    )
    return {"message": f"Deal {deal.deal_id} stored successfully."}

@app.post("/collateral", tags=["Arranger"])
async def upload_collateral(
    payload: CollateralUpload,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    """Arranger uploads initial collateral attributes."""
    # Normalize collateral payloads to avoid double-wrapping:
    # Some callers may send {"deal_id": "...", "data": {...}} while the API also wraps.
    coll = payload.collateral or {}
    if isinstance(coll, dict):
        depth = 0
        while "data" in coll and isinstance(coll.get("data"), dict) and depth < 5:
            coll = coll.get("data") or {}
            depth += 1
    if not isinstance(coll, dict):
        raise HTTPException(400, "Collateral payload must be a JSON object")

    COLLATERAL_DB[payload.deal_id] = coll
    path = _collateral_file_path(payload.deal_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"deal_id": payload.deal_id, "data": coll}, f, indent=2)
    _write_versioned_json(
        COLLATERAL_VERSIONS_DIR,
        payload.deal_id,
        {"deal_id": payload.deal_id, "data": coll},
        created_by=payload.created_by,
        source_name=payload.source_name,
    )
    _log_audit_event(
        "collateral.upload",
        actor=payload.created_by,
        deal_id=payload.deal_id,
        details={"source_name": payload.source_name},
    )
    return {"message": f"Collateral for {payload.deal_id} stored successfully."}

@app.get("/collateral/{deal_id}", tags=["Arranger", "Investor"])
async def get_collateral(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor"], x_user_role)),
) -> Dict[str, Any]:
    collateral = COLLATERAL_DB.get(deal_id)
    if collateral is None:
        raise HTTPException(404, "Collateral not found")
    return {"deal_id": deal_id, "collateral": collateral}

@app.post("/performance/{deal_id}", tags=["Servicer"])
async def upload_performance(
    deal_id: str,
    file: UploadFile = File(...),
    created_by: Optional[str] = None,
    source_name: Optional[str] = None,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Dict[str, Any]:
    """Servicer uploads monthly performance tape as CSV."""
    try:
        content = await file.read()
        df_new = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Invalid CSV: {e}")

    if "Period" not in df_new.columns:
        raise HTTPException(400, "CSV must include a Period column.")

    df_new = _normalize_perf_df(df_new)

    # Infer tape shape (pool-level vs bond-level vs loan-level) and period coverage
    schema_type = "pool_level"
    if "BondId" in df_new.columns:
        schema_type = "bond_level"
    elif "LoanId" in df_new.columns:
        schema_type = "loan_level"

    period_min = None
    period_max = None
    n_periods = None
    if "Period" in df_new.columns and not df_new.empty:
        try:
            # Period is normalized to numeric by _normalize_perf_df (best-effort)
            period_min = int(pd.to_numeric(df_new["Period"], errors="coerce").min())
            period_max = int(pd.to_numeric(df_new["Period"], errors="coerce").max())
            n_periods = int(pd.to_numeric(df_new["Period"], errors="coerce").nunique())
        except Exception:
            period_min = None
            period_max = None
            n_periods = None

    df_existing = pd.DataFrame(PERFORMANCE_DB.get(deal_id, []))
    df_all = pd.concat([df_existing, df_new], ignore_index=True)

    if "BondId" in df_all.columns:
        subset = ["Period", "BondId"]
    elif "LoanId" in df_all.columns:
        subset = ["Period", "LoanId"]
    else:
        subset = ["Period"]
    df_all = df_all.drop_duplicates(subset=subset, keep="last").sort_values(subset)

    PERFORMANCE_DB[deal_id] = df_all.to_dict(orient="records")
    path = _performance_file_path(deal_id)
    df_all.to_csv(path, index=False)
    _write_versioned_bytes(
        PERFORMANCE_VERSIONS_DIR,
        deal_id,
        content,
        extension="csv",
        created_by=created_by,
        source_name=source_name or file.filename,
        extra_metadata={
            "rows_new": int(len(df_new)),
            "rows_total": int(len(df_all)),
            "schema_type": schema_type,
            "period_min": period_min,
            "period_max": period_max,
            "n_periods": n_periods,
            "columns": list(df_new.columns),
        },
    )
    _log_audit_event(
        "performance.upload",
        actor=created_by,
        deal_id=deal_id,
        details={
            "source_name": source_name or file.filename,
            "rows_new": int(len(df_new)),
            "schema_type": schema_type,
            "period_min": period_min,
            "period_max": period_max,
            "n_periods": n_periods,
        },
    )

    latest_period = int(df_all["Period"].max()) if not df_all.empty else None
    return {"message": f"Performance for {deal_id} stored successfully.",
            "rows": int(len(df_all)),
            "latest_period": latest_period}

@app.delete("/performance/{deal_id}", tags=["Servicer"])
async def clear_performance(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Dict[str, Any]:
    """Clear all stored performance rows for a deal."""
    PERFORMANCE_DB.pop(deal_id, None)
    path = _performance_file_path(deal_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            raise HTTPException(500, f"Failed to delete performance file: {e}")
    _log_audit_event("performance.clear", deal_id=deal_id)
    return {"message": f"Performance for {deal_id} cleared."}

@app.get("/deals", tags=["Arranger", "Investor", "Servicer", "Auditor"])
async def list_deals(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor", "servicer", "auditor"], x_user_role)),
) -> Dict[str, Any]:
    """List all available deals."""
    deals: List[Dict[str, str]] = []
    for deal_id, spec in DEALS_DB.items():
        meta = spec.get("meta", {})
        perf_rows = PERFORMANCE_DB.get(deal_id, [])
        latest_period = None
        if perf_rows:
            perf_df = pd.DataFrame(perf_rows)
            if "Period" in perf_df.columns and not perf_df.empty:
                latest_period = int(perf_df["Period"].max())
        deals.append({
            "deal_id": deal_id,
            "deal_name": meta.get("deal_name", ""),
            "asset_type": meta.get("asset_type", ""),
            "has_collateral": deal_id in COLLATERAL_DB,
            "latest_period": latest_period
        })
    deals.sort(key=lambda d: d["deal_id"])
    return {"deals": deals}

@app.get("/deals/{deal_id}/versions", tags=["Arranger", "Investor"])
async def list_deal_versions(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor"], x_user_role)),
) -> Dict[str, Any]:
    """List stored deal spec versions for a deal."""
    versions = _list_version_metadata(DEALS_VERSIONS_DIR, deal_id)
    return {"deal_id": deal_id, "versions": versions}

@app.get("/collateral/{deal_id}/versions", tags=["Arranger", "Investor"])
async def list_collateral_versions(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor"], x_user_role)),
) -> Dict[str, Any]:
    """List stored collateral versions for a deal."""
    versions = _list_version_metadata(COLLATERAL_VERSIONS_DIR, deal_id)
    return {"deal_id": deal_id, "versions": versions}

@app.get("/performance/{deal_id}/versions", tags=["Servicer", "Investor"])
async def list_performance_versions(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer", "investor"], x_user_role)),
) -> Dict[str, Any]:
    """List stored performance tape versions for a deal."""
    versions = _list_version_metadata(PERFORMANCE_VERSIONS_DIR, deal_id)
    return {"deal_id": deal_id, "versions": versions}

@app.post("/scenarios", tags=["Investor"])
async def create_scenario(
    payload: ScenarioCreateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Create and persist a scenario definition."""
    scenario_id = str(uuid.uuid4())
    scenario = {
        "scenario_id": scenario_id,
        "name": payload.name,
        "description": payload.description or "",
        "params": payload.params,
        "created_by": payload.created_by or "unknown",
        "tags": payload.tags or [],
        "status": payload.status or "draft",
        "created_at": _utc_now_iso(),
    }
    SCENARIO_DB[scenario_id] = scenario
    path = _scenario_file_path(scenario_id)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    _write_versioned_json(
        SCENARIOS_VERSIONS_DIR,
        scenario_id,
        scenario,
        created_by=payload.created_by,
        source_name=payload.name,
    )
    _log_audit_event(
        "scenario.create",
        actor=payload.created_by,
        scenario_id=scenario_id,
        details={"name": payload.name, "status": scenario.get("status")},
    )
    return {"scenario_id": scenario_id, "scenario": scenario}

@app.get("/scenarios", tags=["Investor"])
async def list_scenarios(
    include_archived: bool = True,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """List stored scenario definitions."""
    scenarios = list(SCENARIO_DB.values())
    if not include_archived:
        scenarios = [s for s in scenarios if s.get("status") not in {"archived", "deleted"}]
    scenarios.sort(key=lambda row: row.get("created_at", ""))
    return {"scenarios": scenarios}

@app.get("/scenarios/{scenario_id}/versions", tags=["Investor"])
async def list_scenario_versions(
    scenario_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """List stored versions for a scenario definition."""
    versions = _list_version_metadata(SCENARIOS_VERSIONS_DIR, scenario_id)
    return {"scenario_id": scenario_id, "versions": versions}

@app.put("/scenarios/{scenario_id}", tags=["Investor"])
async def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Update and version an existing scenario definition."""
    scenario = SCENARIO_DB.get(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found.")

    if payload.name is not None:
        scenario["name"] = payload.name
    if payload.description is not None:
        scenario["description"] = payload.description
    if payload.params is not None:
        scenario["params"] = payload.params
    if payload.tags is not None:
        scenario["tags"] = payload.tags
    if payload.status is not None:
        scenario["status"] = payload.status
    scenario["updated_by"] = payload.updated_by or "unknown"
    scenario["updated_at"] = _utc_now_iso()

    SCENARIO_DB[scenario_id] = scenario
    path = _scenario_file_path(scenario_id)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    _write_versioned_json(
        SCENARIOS_VERSIONS_DIR,
        scenario_id,
        scenario,
        created_by=payload.updated_by,
        source_name=scenario.get("name"),
    )
    _log_audit_event(
        "scenario.update",
        actor=payload.updated_by,
        scenario_id=scenario_id,
        details={"status": scenario.get("status")},
    )
    return {"scenario_id": scenario_id, "scenario": scenario}

@app.post("/scenarios/{scenario_id}/approve", tags=["Investor"])
async def approve_scenario(
    scenario_id: str,
    payload: ScenarioActionRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Approve a scenario for governed use."""
    scenario = SCENARIO_DB.get(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found.")
    scenario["status"] = "approved"
    scenario["approved_by"] = payload.actor or "unknown"
    scenario["approved_at"] = _utc_now_iso()
    if payload.note:
        scenario["approval_note"] = payload.note
    SCENARIO_DB[scenario_id] = scenario
    path = _scenario_file_path(scenario_id)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    _write_versioned_json(
        SCENARIOS_VERSIONS_DIR,
        scenario_id,
        scenario,
        created_by=payload.actor,
        source_name=scenario.get("name"),
    )
    _log_audit_event(
        "scenario.approve",
        actor=payload.actor,
        scenario_id=scenario_id,
    )
    return {"scenario_id": scenario_id, "scenario": scenario}

@app.post("/scenarios/{scenario_id}/archive", tags=["Investor"])
async def archive_scenario(
    scenario_id: str,
    payload: ScenarioActionRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Archive a scenario definition."""
    scenario = SCENARIO_DB.get(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found.")
    scenario["status"] = "archived"
    scenario["archived_by"] = payload.actor or "unknown"
    scenario["archived_at"] = _utc_now_iso()
    if payload.note:
        scenario["archive_note"] = payload.note
    SCENARIO_DB[scenario_id] = scenario
    path = _scenario_file_path(scenario_id)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    _write_versioned_json(
        SCENARIOS_VERSIONS_DIR,
        scenario_id,
        scenario,
        created_by=payload.actor,
        source_name=scenario.get("name"),
    )
    _log_audit_event(
        "scenario.archive",
        actor=payload.actor,
        scenario_id=scenario_id,
    )
    return {"scenario_id": scenario_id, "scenario": scenario}

@app.delete("/scenarios/{scenario_id}", tags=["Investor"])
async def delete_scenario(
    scenario_id: str,
    actor: Optional[str] = None,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Soft-delete a scenario definition."""
    scenario = SCENARIO_DB.get(scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found.")
    scenario["status"] = "deleted"
    scenario["deleted_by"] = actor or "unknown"
    scenario["deleted_at"] = _utc_now_iso()
    SCENARIO_DB[scenario_id] = scenario
    path = _scenario_file_path(scenario_id)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    _write_versioned_json(
        SCENARIOS_VERSIONS_DIR,
        scenario_id,
        scenario,
        created_by=actor,
        source_name=scenario.get("name"),
    )
    _log_audit_event(
        "scenario.delete",
        actor=actor,
        scenario_id=scenario_id,
    )
    return {"scenario_id": scenario_id, "scenario": scenario}

@app.post("/deal/validate", tags=["Arranger"])
async def validate_deal(
    payload: DealValidateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    """Validate a deal specification with basic schema checks."""
    spec = payload.spec
    if spec is None and payload.deal_id:
        spec = DEALS_DB.get(payload.deal_id)
    if spec is None:
        raise HTTPException(400, "Provide a deal_id or spec to validate.")

    issues: List[Dict[str, Any]] = []
    if "meta" not in spec:
        issues.append({"level": "error", "message": "Missing meta section."})
    if "bonds" not in spec:
        issues.append({"level": "error", "message": "Missing bonds section."})
    if "waterfalls" not in spec:
        issues.append({"level": "error", "message": "Missing waterfalls section."})
    if "collateral" in spec:
        issues.append({"level": "warning", "message": "Collateral found in deal spec; upload separately."})
    meta = spec.get("meta", {}) if isinstance(spec, dict) else {}
    if isinstance(meta, dict) and not meta.get("deal_id"):
        issues.append({"level": "warning", "message": "meta.deal_id is missing or empty."})
    bonds = spec.get("bonds") if isinstance(spec, dict) else None
    if isinstance(bonds, list):
        if not bonds:
            issues.append({"level": "error", "message": "bonds is empty."})
        else:
            for idx, bond in enumerate(bonds, start=1):
                if not isinstance(bond, dict):
                    issues.append({"level": "error", "message": f"bond[{idx}] is not an object."})
                    continue
                if not bond.get("id"):
                    issues.append({"level": "error", "message": f"bond[{idx}].id is missing."})
                if "original_balance" not in bond:
                    issues.append({"level": "error", "message": f"bond[{idx}].original_balance is missing."})
                if "priority" not in bond:
                    issues.append({"level": "warning", "message": f"bond[{idx}].priority is missing."})
                if "coupon" not in bond:
                    issues.append({"level": "warning", "message": f"bond[{idx}].coupon is missing."})
    waterfalls = spec.get("waterfalls") if isinstance(spec, dict) else None
    if isinstance(waterfalls, dict):
        for key in ("interest", "principal"):
            wf = waterfalls.get(key)
            if not isinstance(wf, dict):
                issues.append({"level": "warning", "message": f"waterfalls.{key} is missing or not an object."})
                continue
            steps = wf.get("steps")
            if steps is None:
                issues.append({"level": "warning", "message": f"waterfalls.{key}.steps is missing."})
            elif not isinstance(steps, list):
                issues.append({"level": "warning", "message": f"waterfalls.{key}.steps is not a list."})

    status = "OK" if not any(i["level"] == "error" for i in issues) else "FAILED"
    _log_audit_event(
        "deal.validate",
        deal_id=payload.deal_id or spec.get("meta", {}).get("deal_id") if isinstance(spec, dict) else None,
        details={"status": status, "issue_count": len(issues)},
    )
    return {"status": status, "issues": issues}

@app.post("/validation/performance", tags=["Servicer"])
async def validate_performance(
    payload: PerformanceValidateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Dict[str, Any]:
    """Validate performance rows with basic schema checks."""
    rows = payload.rows
    if rows is None and payload.deal_id:
        rows = PERFORMANCE_DB.get(payload.deal_id, [])
    if rows is None:
        raise HTTPException(400, "Provide a deal_id or rows to validate.")

    issues: List[Dict[str, Any]] = []
    if not rows:
        issues.append({"level": "warning", "message": "No performance rows found."})
        return {"status": "OK", "issues": issues}

    df = pd.DataFrame(rows)
    if "Period" not in df.columns:
        issues.append({"level": "error", "message": "Missing required Period column."})
    if "LoanId" not in df.columns and "BondId" not in df.columns:
        issues.append({"level": "warning", "message": "Neither LoanId nor BondId present."})
    if "Period" in df.columns:
        try:
            periods = pd.to_numeric(df["Period"], errors="coerce").dropna()
            if not periods.empty:
                period_min = int(periods.min())
                period_max = int(periods.max())
                if period_min < 0:
                    issues.append({"level": "warning", "message": "Period contains negative values."})
                unique_periods = sorted(set(int(p) for p in periods.tolist()))
                if len(unique_periods) > 1:
                    expected = list(range(unique_periods[0], unique_periods[-1] + 1))
                    if unique_periods != expected:
                        issues.append({"level": "warning", "message": "Period sequence has gaps."})
        except Exception:
            issues.append({"level": "warning", "message": "Period column contains invalid values."})
    numeric_candidates = [
        "InterestCollected",
        "PrincipalCollected",
        "Prepayment",
        "ScheduledPrincipal",
        "RealizedLoss",
        "EndBalance",
        "Recoveries",
        "ScheduledInterest",
        "ServicerAdvances",
    ]
    present_numeric = [c for c in numeric_candidates if c in df.columns]
    if not present_numeric:
        issues.append({"level": "warning", "message": "No standard numeric performance fields present."})
    else:
        negative_mask = df[present_numeric].apply(pd.to_numeric, errors="coerce") < 0
        if negative_mask.any().any():
            issues.append({"level": "warning", "message": "Negative values detected in numeric fields."})

    status = "OK" if not any(i["level"] == "error" for i in issues) else "FAILED"
    _log_audit_event(
        "performance.validate",
        deal_id=payload.deal_id,
        details={"status": status, "issue_count": len(issues)},
    )
    return {"status": status, "issues": issues}

@app.post("/simulate", tags=["Investor"])
async def start_simulation(
    req: SimRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """Investor requests a simulation run (Async)."""
    if req.deal_id not in DEALS_DB:
        raise HTTPException(404, "Deal ID not found")
    if req.deal_id not in COLLATERAL_DB:
        raise HTTPException(400, "Collateral not uploaded for this deal")

    if req.use_ml_models:
        registry = _load_model_registry()
        prepay_key = req.prepay_model_key or (COLLATERAL_DB.get(req.deal_id, {}).get("ml_config") or {}).get("prepay_model_key")
        default_key = req.default_model_key or (COLLATERAL_DB.get(req.deal_id, {}).get("ml_config") or {}).get("default_model_key")
        missing = []
        if prepay_key and prepay_key not in registry:
            missing.append(f"prepay_model_key '{prepay_key}'")
        if default_key and default_key not in registry:
            missing.append(f"default_model_key '{default_key}'")
        if missing:
            raise HTTPException(400, f"Invalid model keys: {', '.join(missing)}")
        if req.feature_source and req.feature_source not in {"simulated", "market_rates"}:
            raise HTTPException(400, f"Invalid feature_source '{req.feature_source}'")
    
    job_id = str(uuid.uuid4())
    ml_overrides = {}
    if req.use_ml_models:
        ml_overrides["enabled"] = True
        if req.prepay_model_key:
            ml_overrides["prepay_model_key"] = req.prepay_model_key
        if req.default_model_key:
            ml_overrides["default_model_key"] = req.default_model_key
        if req.rate_scenario:
            ml_overrides["rate_scenario"] = req.rate_scenario
        if req.start_rate is not None:
            ml_overrides["start_rate"] = req.start_rate
        if req.rate_sensitivity is not None:
            ml_overrides["rate_sensitivity"] = req.rate_sensitivity
        if req.feature_source:
            ml_overrides["feature_source"] = req.feature_source
        if req.origination_source_uri:
            ml_overrides["origination_source_uri"] = req.origination_source_uri
    JOBS_DB[job_id] = {
        "status": "RUNNING",
        "ml_overrides": ml_overrides,
        "scenario_id": req.scenario_id,
        "request": {
            "deal_id": req.deal_id,
            "cpr": req.cpr,
            "cdr": req.cdr,
            "severity": req.severity,
            "use_ml_models": req.use_ml_models,
            "scenario_id": req.scenario_id,
            "horizon_periods": req.horizon_periods,
            "prepay_model_key": req.prepay_model_key,
            "default_model_key": req.default_model_key,
            "rate_scenario": req.rate_scenario,
            "start_rate": req.start_rate,
            "rate_sensitivity": req.rate_sensitivity,
            "feature_source": req.feature_source,
            "origination_source_uri": req.origination_source_uri,
        },
    }
    _log_audit_event(
        "simulation.start",
        actor=None,
        deal_id=req.deal_id,
        scenario_id=req.scenario_id,
        job_id=job_id,
    )
    
    # Send to background
    background_tasks.add_task(worker, job_id, req.deal_id, req.cpr, req.cdr, req.severity, req.horizon_periods)
    
    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/results/{job_id}", tags=["Reporting"])
async def get_results(
    job_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor", "auditor", "servicer", "arranger"], x_user_role)),
) -> Dict[str, Any]:
    """Retrieve simulation results."""
    job = JOBS_DB.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    
    if job['status'] == "COMPLETED":
        # Convert JSON string back to dict for API response
        return {
            "status": "COMPLETED",
            "data": job['data'],
            "reconciliation": job.get("reconciliation", []),
            "actuals_data": job.get("actuals_data", []),
            "actuals_summary": job.get("actuals_summary", []),
            "simulated_summary": job.get("simulated_summary", []),
            "last_actual_period": job.get("last_actual_period"),
            "warnings": job.get("warnings", []),
            "model_info": job.get("model_info", {})
        }
    if job['status'] == "FAILED":
        return {"status": "FAILED", "error": job.get("error", "Unknown error")}
    return {"status": job['status']}

@app.get("/audit/run/{job_id}/bundle", tags=["Reporting", "Auditor"])
async def download_audit_bundle(
    job_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor", "auditor"], x_user_role)),
) -> Response:
    """Download an audit bundle with inputs, outputs, and metadata."""
    job = JOBS_DB.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "COMPLETED":
        raise HTTPException(400, "Job is not completed")

    deal_id = job.get("request", {}).get("deal_id")
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps({
            "job_id": job_id,
            "deal_id": deal_id,
            "created_at": job.get("created_at"),
            "request": job.get("request", {}),
            "model_info": job.get("model_info", {}),
        }, indent=2))
        if AUDIT_LOG_PATH.exists():
            zf.writestr("audit_events.jsonl", AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        zf.writestr("warnings.json", json.dumps(job.get("warnings", []), indent=2))
        zf.writestr("reconciliation.json", json.dumps(job.get("reconciliation", []), indent=2))
        zf.writestr("actuals_summary.json", json.dumps(job.get("actuals_summary", []), indent=2))
        zf.writestr("simulated_summary.json", json.dumps(job.get("simulated_summary", []), indent=2))
        if job.get("data"):
            df = pd.DataFrame(job.get("data"))
            zf.writestr("detailed_tape.csv", df.to_csv(index=False))
        if deal_id and deal_id in DEALS_DB:
            zf.writestr("deal_spec.json", json.dumps(DEALS_DB[deal_id], indent=2))
        if deal_id and deal_id in COLLATERAL_DB:
            zf.writestr("collateral.json", json.dumps(COLLATERAL_DB[deal_id], indent=2))
        if deal_id and deal_id in PERFORMANCE_DB:
            perf_df = pd.DataFrame(PERFORMANCE_DB[deal_id])
            zf.writestr("performance.csv", perf_df.to_csv(index=False))

    bundle.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=audit_bundle_{job_id}.zip"
    }
    _log_audit_event(
        "audit.bundle.download",
        job_id=job_id,
        deal_id=deal_id,
    )
    return Response(content=bundle.read(), media_type="application/zip", headers=headers)

@app.get("/audit/events", tags=["Auditor"])
async def list_audit_events(
    limit: int = 200,
    event_type: Optional[str] = None,
    deal_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    job_id: Optional[str] = None,
    actor: Optional[str] = None,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "investor"], x_user_role)),
) -> Dict[str, Any]:
    """List recent audit events with optional filters."""
    events = _read_audit_events(
        limit=limit,
        event_type=event_type,
        deal_id=deal_id,
        scenario_id=scenario_id,
        job_id=job_id,
        actor=actor,
    )
    _log_audit_event(
        "audit.events.list",
        actor=actor,
        deal_id=deal_id,
        scenario_id=scenario_id,
        job_id=job_id,
        details={"limit": limit, "event_type": event_type},
    )
    return {"events": events}

@app.get("/audit/events/download", tags=["Auditor"])
async def download_audit_events(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["auditor", "investor"], x_user_role)),
) -> Response:
    """Download the raw audit event log."""
    if not AUDIT_LOG_PATH.exists():
        raise HTTPException(404, "Audit log not found.")
    content = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    headers = {
        "Content-Disposition": "attachment; filename=audit_events.jsonl"
    }
    _log_audit_event("audit.events.download")
    return Response(content=content, media_type="application/jsonl", headers=headers)

# --- WORKER ---
def worker(job_id: str, deal_id: str, cpr: float, cdr: float, sev: float, horizon_periods: int = 60) -> None:
    """
    Background worker that executes a simulation job.

    This function runs in a background task to avoid blocking the API.
    It loads deal/collateral/performance data, runs the simulation engine,
    processes results, and stores them in JOBS_DB.

    Parameters
    ----------
    job_id : str
        Unique identifier for this simulation job.
    deal_id : str
        Deal identifier to simulate.
    cpr : float
        Constant Prepayment Rate assumption (annual, decimal).
    cdr : float
        Constant Default Rate assumption (annual, decimal).
    sev : float
        Loss severity assumption (decimal).

    Notes
    -----
    **Result Storage**: On completion, updates JOBS_DB[job_id] with:

    - ``status``: "COMPLETED" or "FAILED"
    - ``data``: List of period records (detailed tape)
    - ``reconciliation``: Model vs. tape balance comparisons
    - ``actuals_summary``: Aggregated servicer tape data
    - ``simulated_summary``: Aggregated projection data
    - ``warnings``: Data quality and model warnings
    - ``model_info``: ML configuration and diagnostics

    **Error Handling**: Exceptions are caught and stored in the job
    record with status "FAILED" rather than propagating.

    **Audit Trail**: Logs simulation start, completion, and failure events.
    """
    try:
        deal_json = DEALS_DB[deal_id]
        collateral_json = COLLATERAL_DB.get(deal_id, deal_json.get("collateral", {}))
        performance_rows = PERFORMANCE_DB.get(deal_id, [])
        ml_overrides = JOBS_DB.get(job_id, {}).get("ml_overrides", {})
        ml_requested = bool(ml_overrides.get("enabled"))
        collateral_json = dict(collateral_json)
        ml_config = dict(collateral_json.get("ml_config") or {})
        if ml_requested:
            ml_config.update(ml_overrides)
        else:
            ml_config["enabled"] = False
        collateral_json["ml_config"] = ml_config

        registry = _load_model_registry()
        model_info = {}
        if ml_requested:
            prepay_key = ml_overrides.get("prepay_model_key") or (collateral_json.get("ml_config") or {}).get("prepay_model_key")
            default_key = ml_overrides.get("default_model_key") or (collateral_json.get("ml_config") or {}).get("default_model_key")
            base_dir = Path(__file__).resolve().parent
            prepay_path = registry.get(prepay_key, {}).get("path") if prepay_key else None
            default_path = registry.get(default_key, {}).get("path") if default_key else None
            if prepay_path:
                prepay_path = str((base_dir / prepay_path).resolve()) if not Path(prepay_path).is_absolute() else prepay_path
            if default_path:
                default_path = str((base_dir / default_path).resolve()) if not Path(default_path).is_absolute() else default_path
            model_info = {
                "ml_requested": True,
                "prepay_key": prepay_key,
                "default_key": default_key,
                "prepay_path": prepay_path,
                "default_path": default_path,
                "rate_scenario": ml_overrides.get("rate_scenario") or (collateral_json.get("ml_config") or {}).get("rate_scenario"),
                "start_rate": ml_overrides.get("start_rate") or (collateral_json.get("ml_config") or {}).get("start_rate"),
                "feature_source": ml_overrides.get("feature_source") or (collateral_json.get("ml_config") or {}).get("feature_source"),
                "origination_source_uri": ml_overrides.get("origination_source_uri") or (collateral_json.get("ml_config") or {}).get("origination_source_uri"),
            }
        else:
            model_info = {"ml_requested": False}
        scenario_id = JOBS_DB.get(job_id, {}).get("scenario_id")
        if scenario_id:
            model_info["scenario_id"] = scenario_id
        df, reconciliation = run_simulation(
            deal_json,
            collateral_json,
            performance_rows,
            cpr,
            cdr,
            sev,
            horizon_periods=int(horizon_periods or 60),
        )
        if model_info:
            model_info["ml_used"] = False
            if not df.empty and "Var.MLUsed" in df.columns:
                ml_rows = df[df["Period"] > _latest_actual_period(_aggregate_performance(performance_rows))]
                if not ml_rows.empty:
                    model_info["ml_used"] = bool(ml_rows["Var.MLUsed"].any())

        actuals_summary = _aggregate_performance(performance_rows)
        last_actual_period = _latest_actual_period(actuals_summary)
        actuals_report = []
        simulated_summary = []
        if last_actual_period is not None and not df.empty:
            actuals_report = df[df["Period"] <= last_actual_period].to_dict(orient="records")
        if not df.empty:
            sim_df = df if last_actual_period is None else df[df["Period"] > last_actual_period]
            summary_cols = [
                "Period",
                "Var.InputInterestCollected",
                "Var.InputPrincipalCollected",
                "Var.InputRealizedLoss",
                "Var.InputEndBalance",
                "Var.InputPrepayment",
                "Var.InputScheduledPrincipal",
                "Var.InputScheduledInterest",
                "Var.InputServicerAdvances",
                "Var.InputRecoveries",
            ]
            existing_cols = [c for c in summary_cols if c in sim_df.columns]
            if "Period" in existing_cols:
                summary_df = sim_df[existing_cols].copy()
                summary_df = summary_df.rename(columns={
                    "Var.InputInterestCollected": "InterestCollected",
                    "Var.InputPrincipalCollected": "PrincipalCollected",
                    "Var.InputRealizedLoss": "RealizedLoss",
                    "Var.InputEndBalance": "EndBalance",
                    "Var.InputPrepayment": "Prepayment",
                    "Var.InputScheduledPrincipal": "ScheduledPrincipal",
                    "Var.InputScheduledInterest": "ScheduledInterest",
                    "Var.InputServicerAdvances": "ServicerAdvances",
                    "Var.InputRecoveries": "Recoveries",
                })
                simulated_summary = summary_df.to_dict(orient="records")

        warnings: List[Dict[str, Any]] = []
        if ml_overrides.get("enabled"):
            feature_source = model_info.get("feature_source")
            rate_scenario = model_info.get("rate_scenario")
            start_rate = model_info.get("start_rate")
            if feature_source and feature_source != "simulated" and (rate_scenario or start_rate is not None):
                warnings.append({
                    "type": "ML_RATE_SCENARIO_IGNORED",
                    "message": "Rate scenario/start rate do not affect ML when feature_source is not 'simulated'."
                })
            if model_info.get("prepay_path") and not Path(model_info["prepay_path"]).exists():
                warnings.append({
                    "type": "ML_MODEL_MISSING",
                    "message": f"Prepay model file not found: {model_info['prepay_path']}"
                })
            if model_info.get("default_path") and not Path(model_info["default_path"]).exists():
                warnings.append({
                    "type": "ML_MODEL_MISSING",
                    "message": f"Default model file not found: {model_info['default_path']}"
                })
            loan_data = (collateral_json or {}).get("loan_data", {})
            schema_ref = loan_data.get("schema_ref", {}) if isinstance(loan_data, dict) else {}
            source_uri = schema_ref.get("source_uri")
            if not source_uri:
                warnings.append({
                    "type": "ML_MISSING_SOURCE_URI",
                    "message": "ML models enabled but no loan_data.schema_ref.source_uri provided. Falling back to rule-based cashflows."
                })

            if "Var.ModelSource" in df.columns and last_actual_period is not None:
                sim_flags = df[df["Period"] > last_actual_period]["Var.ModelSource"]
                if not sim_flags.empty and "ML" not in sim_flags.unique():
                    warnings.append({
                        "type": "ML_NOT_APPLIED",
                        "message": "ML models enabled but simulation used rule-based cashflows. Check model files and input tapes."
                    })
        if actuals_summary and "Var.PoolEndBalance" in df.columns:
            actuals_df = pd.DataFrame(actuals_summary)
            compare_cols = ["Period", "EndBalance", "RealizedLoss"]
            actuals_df = actuals_df[[c for c in compare_cols if c in actuals_df.columns]]
            merged = actuals_df.merge(
                df[["Period", "Var.PoolEndBalance", "Var.RealizedLoss"]],
                on="Period",
                how="left"
            )
            if "EndBalance" in merged.columns:
                merged["EndBalanceDelta"] = merged["EndBalance"] - merged["Var.PoolEndBalance"]
                large_delta = merged[merged["EndBalanceDelta"].abs() > 1.0]
                if not large_delta.empty:
                    warnings.append({
                        "type": "POOL_END_BALANCE_MISMATCH",
                        "message": "Servicer tape aggregate EndBalance differs from Var.PoolEndBalance.",
                        "sample_rows": large_delta.head(5).to_dict(orient="records")
                    })
            if "RealizedLoss" in merged.columns:
                merged["RealizedLossDelta"] = merged["RealizedLoss"] - merged["Var.RealizedLoss"]
                loss_delta = merged[merged["RealizedLossDelta"].abs() > 1.0]
                if not loss_delta.empty:
                    warnings.append({
                        "type": "REALIZED_LOSS_MISMATCH",
                        "message": "Servicer tape aggregate RealizedLoss differs from Var.RealizedLoss.",
                        "sample_rows": loss_delta.head(5).to_dict(orient="records")
                    })

        data_records = df.replace([float("inf"), float("-inf")], float("nan")).where(pd.notnull(df), None)
        data_records = data_records.to_dict(orient="records")
        data_records = _sanitize_json(data_records)
        reconciliation = _sanitize_json(reconciliation)
        actuals_report = _sanitize_json(actuals_report)
        simulated_summary = _sanitize_json(simulated_summary)
        actuals_summary = _sanitize_json(actuals_summary)
        warnings = _sanitize_json(warnings)

        # Store result as JSON compatible list
        JOBS_DB[job_id] = {
            "status": "COMPLETED",
            "created_at": _utc_now_iso(),
            "request": JOBS_DB.get(job_id, {}).get("request", {}),
            "scenario_id": JOBS_DB.get(job_id, {}).get("scenario_id"),
            "data": data_records,
            "reconciliation": reconciliation,
            "actuals_data": actuals_report,
            "actuals_summary": actuals_summary,
            "simulated_summary": simulated_summary,
            "last_actual_period": last_actual_period,
            "warnings": warnings,
            "model_info": model_info
        }
        _log_audit_event(
            "simulation.complete",
            deal_id=JOBS_DB.get(job_id, {}).get("request", {}).get("deal_id"),
            scenario_id=JOBS_DB.get(job_id, {}).get("scenario_id"),
            job_id=job_id,
        )
    except Exception as e:
        JOBS_DB[job_id] = {"status": "FAILED", "error": str(e)}
        _log_audit_event("simulation.failed", job_id=job_id, details={"error": str(e)})


@app.get("/models/registry", tags=["Models"])
async def get_model_registry() -> Dict[str, Any]:
    return {"registry": _load_model_registry()}