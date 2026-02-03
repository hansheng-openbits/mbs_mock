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
    status,
)
from pydantic import BaseModel, Field

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
- Upload initial collateral attributes and loan tapes
- Validate deal structures before execution
- View version history for audit trail

*Requires X-User-Role: arranger*
        """,
    },
    {
        "name": "Issuer",
        "description": """
**Token Issuance Endpoints**

Issuers use these endpoints to mint and manage tokens:
- Mint loan NFTs for individual loans
- Mint tranche tokens based on deal structure
- Update token metadata
- Manage token holder registry

*Requires X-User-Role: issuer*
        """,
    },
    {
        "name": "Trustee",
        "description": """
**Deal Administration Endpoints**

Trustees use these endpoints for deal administration:
- Execute waterfall distributions
- Update tranche factors after paydowns
- Distribute yield to investors
- Manage deal lifecycle events

*Requires X-User-Role: trustee*
        """,
    },
    {
        "name": "Servicer",
        "description": """
**Operations Endpoints**

Servicers use these endpoints for ongoing deal operations:
- Upload monthly performance tapes (loan-level data)
- Update loan status on-chain
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
- Claim yield from tranche tokens

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
    {
        "name": "Web3",
        "description": "Web3 integration endpoints for on-chain tokenization and payouts.",
    },
]

try:
    from .api_models import (
        Web3DealCreate,
        Web3DealResponse,
        Web3TrancheCreate,
        Web3TranchePublishRequest,
        Web3TrancheRegistryUpdate,
        Web3InvestorUpdate,
        Web3LoanTapeSubmit,
        Web3WaterfallConfig,
        Web3WaterfallExecute,
        Web3WaterfallPublishRequest,
        Web3OraclePublishRange,
        Web3TransactionResponse,
        Web3BatchResponse,
        Web3PublishDealRequest,
        Web3LoanNFTMintRequest,
        Web3LoanNFTMintParams,
        Web3LoanNFTMintResponse,
        Web3TrancheTokenMintRequest,
    )
except ImportError:
    from api_models import (
        Web3DealCreate,
        Web3DealResponse,
        Web3TrancheCreate,
        Web3TranchePublishRequest,
        Web3TrancheRegistryUpdate,
        Web3InvestorUpdate,
        Web3LoanTapeSubmit,
        Web3WaterfallConfig,
        Web3WaterfallExecute,
        Web3WaterfallPublishRequest,
        Web3OraclePublishRange,
        Web3TransactionResponse,
        Web3BatchResponse,
        Web3PublishDealRequest,
        Web3LoanNFTMintRequest,
        Web3LoanNFTMintParams,
        Web3LoanNFTMintResponse,
        Web3TrancheTokenMintRequest,
    )

try:
    from .web3_integration.web3_client import get_web3_client
except ImportError:
    from web3_integration.web3_client import get_web3_client

# Import audit router
try:
    from .audit.routes import router as audit_router
except ImportError:
    from audit.routes import router as audit_router

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

# Include the audit router for comprehensive auditor functionality
app.include_router(audit_router)

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

# Web3 directory structure for production-ready architecture
WEB3_SYNC_DIR = settings.package_root / "web3_sync"
WEB3_SYNC_DIR.mkdir(parents=True, exist_ok=True)
DEPLOYMENTS_DIR = settings.package_root / "deployments"
DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_NETWORK = "localhost"  # Change to "polygon" or "mainnet" for production
WEB3_REGISTRY_PATH = DEPLOYMENTS_DIR / ACTIVE_NETWORK / "contracts.json"
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

def _loan_tape_file_path(deal_id: str) -> Path:
    """Return the path where loan tape data should be stored."""
    datasets_dir = settings.package_root / "datasets"
    return datasets_dir / deal_id / "loan_tape.csv"

def _sync_to_datasets(deal_id: str, filename: str, content: Any, is_json: bool = True) -> None:
    """
    Sync a file to the datasets/{deal_id}/ folder for user convenience.
    
    Parameters
    ----------
    deal_id : str
        Deal identifier
    filename : str
        Filename to save (e.g., "deal_spec.json", "collateral.json")
    content : Any
        Content to write (dict for JSON, bytes/str for CSV)
    is_json : bool
        If True, write as JSON; otherwise write as binary/text
    """
    try:
        datasets_dir = settings.package_root / "datasets"
        deal_dir = datasets_dir / deal_id
        deal_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = deal_dir / filename
        if is_json:
            with target_path.open("w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
        else:
            mode = "wb" if isinstance(content, bytes) else "w"
            with target_path.open(mode, encoding="utf-8" if mode == "w" else None) as f:
                f.write(content)
    except Exception as e:
        # Don't fail the upload if sync fails - just log it
        print(f"Warning: Failed to sync {filename} to datasets/{deal_id}/: {e}")

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
    
    # Sync to datasets/ folder for user convenience
    _sync_to_datasets(deal.deal_id, "deal_spec.json", deal.spec, is_json=True)
    
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
    collateral_wrapped = {"deal_id": payload.deal_id, "data": coll}
    with path.open("w", encoding="utf-8") as f:
        json.dump(collateral_wrapped, f, indent=2)
    
    # Sync to datasets/ folder for user convenience
    _sync_to_datasets(payload.deal_id, "collateral.json", collateral_wrapped, is_json=True)
    
    _write_versioned_json(
        COLLATERAL_VERSIONS_DIR,
        payload.deal_id,
        collateral_wrapped,
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

@app.post("/loan-tape/{deal_id}", tags=["Arranger"])
async def upload_loan_tape(
    deal_id: str,
    file: UploadFile = File(...),
    created_by: Optional[str] = None,
    source_name: Optional[str] = None,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    """Arranger uploads origination loan tape as CSV."""
    # Check role
    _require_role(["arranger"], x_user_role)
    """Arranger uploads origination loan tape as CSV."""
    try:
        # Read file content
        content = await file.read()

        # Parse CSV
        try:
            # Try different separators and encodings
            df = pd.read_csv(io.BytesIO(content), sep=None, engine='python')
        except Exception as e:
            raise HTTPException(400, f"Invalid CSV format: {e}. Please ensure the file is a valid CSV.")

        # Validate required columns for ML features
        required_cols = ["LoanId", "OriginalBalance", "CurrentBalance", "NoteRate", "RemainingTermMonths", "FICO", "LTV"]
        available_cols = list(df.columns)
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise HTTPException(400, f"Missing required columns for ML features: {', '.join(missing_cols)}. Available columns: {', '.join(available_cols)}")

        # Save the loan tape
        try:
            loan_tape_path = _loan_tape_file_path(deal_id)
            loan_tape_path.parent.mkdir(parents=True, exist_ok=True)
            with loan_tape_path.open("wb") as f:
                f.write(content)
        except Exception as e:
            raise HTTPException(500, f"Failed to save loan tape file: {e}")

        # Log audit event
        try:
            _log_audit_event(
                "loan_tape.upload",
                actor=created_by,
                deal_id=deal_id,
                details={"source_name": source_name or file.filename, "rows": len(df)},
            )
        except Exception as e:
            # Don't fail the upload if audit logging fails
            print(f"Warning: Audit logging failed: {e}")

        return {"message": f"Loan tape for {deal_id} stored successfully.", "rows": len(df)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unexpected error: {e}")

@app.post("/performance/{deal_id}", tags=["Servicer"])
async def upload_performance(
    deal_id: str,
    file: UploadFile = File(...),
    created_by: Optional[str] = None,
    source_name: Optional[str] = None,
    update_nfts: bool = False,
    loan_nft_contract: Optional[str] = None,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Dict[str, Any]:
    """
    Servicer uploads monthly performance tape as CSV.
    
    **Optional Web3 Integration**: Set `update_nfts=true` to automatically update
    loan NFT statuses on-chain after uploading performance data.
    
    Parameters
    ----------
    update_nfts : bool
        If True, automatically update loan NFT statuses based on uploaded data.
        Requires loan_nft_contract or RMBS_WEB3_LOAN_NFT environment variable.
    loan_nft_contract : str, optional
        LoanNFT contract address. If not provided, uses RMBS_WEB3_LOAN_NFT config.
    """
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
    
    # Sync consolidated performance data to datasets/ folder for user convenience
    try:
        datasets_dir = settings.package_root / "datasets"
        deal_dir = datasets_dir / deal_id
        deal_dir.mkdir(parents=True, exist_ok=True)
        servicer_tape_path = deal_dir / "servicer_tape.csv"
        df_all.to_csv(servicer_tape_path, index=False)
    except Exception as e:
        print(f"Warning: Failed to sync servicer_tape.csv to datasets/{deal_id}/: {e}")
    
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
    
    # Build response
    response: Dict[str, Any] = {
        "message": f"Performance for {deal_id} stored successfully.",
        "rows": int(len(df_all)),  # Total rows in database (for backward compatibility)
        "rows_new": int(len(df_new)),  # Rows in this upload
        "rows_total": int(len(df_all)),  # Total rows after merge
        "latest_period": latest_period,
    }
    
    # ALWAYS update local NFT records if loan-level data and records file exists
    if schema_type == "loan_level":
        local_update_result = _update_local_nft_records(deal_id, df_all, latest_period)
        if local_update_result.get("updated"):
            response["nft_records_updated"] = local_update_result
    
    # Auto-update on-chain NFTs if requested
    if update_nfts:
        nft_result = await _auto_update_loan_nfts(
            deal_id=deal_id,
            df_perf=df_all,
            period=latest_period,
            loan_nft_contract=loan_nft_contract,
        )
        response["nft_update"] = nft_result
    
    # Create pending distribution period for trustee to process
    if latest_period is not None:
        try:
            from engine.distribution_cycle import get_distribution_manager
            
            # Extract collection data from performance tape
            period_data = df_all[df_all["Period"] == latest_period]
            
            # Aggregate collections (handle both pool-level and loan-level)
            collections = {
                "interest_collected": float(period_data.get("InterestCollected", period_data.get("ScheduledInterest", pd.Series([0]))).sum()),
                "principal_collected": float(period_data.get("PrincipalCollected", period_data.get("ScheduledPrincipal", pd.Series([0]))).sum()),
                "prepayments": float(period_data.get("Prepayment", period_data.get("PrepaymentAmount", pd.Series([0]))).sum()),
                "defaults": float(period_data.get("DefaultAmount", period_data.get("Default", pd.Series([0]))).sum()),
                "losses": float(period_data.get("RealizedLoss", period_data.get("LossAmount", pd.Series([0]))).sum()),
                "recoveries": float(period_data.get("Recoveries", period_data.get("RecoveryAmount", pd.Series([0]))).sum()),
                "beginning_balance": float(period_data.get("BeginBalance", period_data.get("BeginningBalance", pd.Series([0]))).sum()),
                "ending_balance": float(period_data.get("EndBalance", period_data.get("EndingBalance", pd.Series([0]))).sum()),
            }
            
            dist_manager = get_distribution_manager(WEB3_SYNC_DIR)
            dist_period = dist_manager.create_distribution_period(
                deal_id=deal_id,
                period_number=latest_period,
                collections=collections,
                servicer_tape_version=source_name or file.filename,
                created_by=created_by,
            )
            
            response["distribution_period"] = {
                "period_id": dist_period.period_id,
                "period_number": dist_period.period_number,
                "status": dist_period.status.value,
                "total_collections": dist_period.total_collections,
                "message": "Pending distribution period created. Trustee must execute waterfall to distribute.",
            }
        except Exception as e:
            print(f"Warning: Failed to create distribution period: {e}")
            response["distribution_period_error"] = str(e)
    
    return response


def _update_local_nft_records(deal_id: str, df_perf: pd.DataFrame, period: int) -> Dict[str, Any]:
    """
    Update local loan_nft_records.json based on performance data.
    This runs ALWAYS when loan-level performance data is uploaded,
    regardless of blockchain connectivity.
    """
    result: Dict[str, Any] = {"updated": False, "loans_updated": 0, "errors": []}
    
    records_path = settings.package_root / "datasets" / deal_id / "loan_nft_records.json"
    mapping_path = settings.package_root / "datasets" / deal_id / "loan_token_mapping.json"
    
    if not records_path.exists():
        return result  # No NFT records file - skip
    
    if not mapping_path.exists():
        result["errors"].append("loan_token_mapping.json not found")
        return result
    
    # Load existing records
    try:
        with open(records_path, "r") as f:
            nft_records = json.load(f)
        with open(mapping_path, "r") as f:
            loan_id_to_token = json.load(f)
    except Exception as e:
        result["errors"].append(f"Failed to load NFT records: {e}")
        return result
    
    # Filter to latest period
    df_period = df_perf[df_perf["Period"] == period].copy()
    if df_period.empty:
        result["errors"].append(f"No data found for period {period}")
        return result
    
    loans_data = nft_records.get("loans", {})
    status_summary: Dict[str, int] = {}
    loans_updated = 0
    
    for _, loan in df_period.iterrows():
        loan_id = str(loan.get("LoanId", ""))
        if loan_id not in loan_id_to_token:
            continue
        
        token_id = loan_id_to_token[loan_id]
        token_key = str(token_id)
        
        if token_key not in loans_data:
            continue
        
        # Determine status from DQStatus and LoanStatus columns
        dq_status = int(loan.get("DQStatus", loan.get("DPD", 0)))
        loan_status_str = str(loan.get("LoanStatus", "")).upper()
        
        # Map status
        is_defaulted = loan_status_str in ("DEFAULT", "FORECLOSURE", "REO", "BANKRUPT")
        is_paid_off = loan_status_str in ("PAID", "PAID_OFF", "PAIDOFF", "FULL", "MATURED")
        is_prepaid = loan_status_str in ("PREPAID", "PREPAY", "EARLY_PAYOFF", "VOLUNTARY_PAYOFF")
        
        status_code = _map_dpd_to_status(dq_status, is_defaulted, is_paid_off, is_prepaid)
        status_name = _get_status_name(status_code)
        status_summary[status_name] = status_summary.get(status_name, 0) + 1
        
        # Get current balance from performance data
        current_balance = loan.get("EndBalance", loan.get("CurrentBalance", loan.get("ScheduledBalance", 0)))
        # Convert to cents (same unit as original_balance)
        balance_cents = int(float(current_balance) * 100)
        
        # Update the loan record
        loans_data[token_key]["status_code"] = status_code
        loans_data[token_key]["status"] = status_name
        loans_data[token_key]["current_balance"] = balance_cents / 100  # Convert to dollars
        loans_data[token_key]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        loans_updated += 1
    
    # Update metadata
    nft_records["last_status_update"] = datetime.now(timezone.utc).isoformat()
    nft_records["last_period_updated"] = period
    
    # Save updated records
    try:
        with open(records_path, "w") as f:
            json.dump(nft_records, f, indent=2)
        
        result["updated"] = True
        result["loans_updated"] = loans_updated
        result["period"] = period
        result["status_summary"] = status_summary
        print(f"Updated loan_nft_records.json for deal {deal_id}: {loans_updated} loans, period {period}")
    except Exception as e:
        result["errors"].append(f"Failed to save NFT records: {e}")
    
    return result


async def _auto_update_loan_nfts(
    deal_id: str,
    df_perf: pd.DataFrame,
    period: int,
    loan_nft_contract: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Automatically update loan NFT statuses after performance upload.
    
    Returns a dict with update results or error information.
    """
    result: Dict[str, Any] = {
        "enabled": True,
        "success": False,
        "loans_updated": 0,
        "tx_hashes": [],
        "errors": [],
    }
    
    # Check Web3 is enabled
    if not settings.web3_enabled:
        result["errors"].append("Web3 integration is disabled (RMBS_WEB3_ENABLED=false)")
        return result
    
    # Determine contract address
    contract_address = loan_nft_contract or getattr(settings, "web3_loan_nft", "")
    if not contract_address:
        result["errors"].append(
            "No LoanNFT contract address. Provide loan_nft_contract parameter or set RMBS_WEB3_LOAN_NFT"
        )
        return result
    
    # Check if loan-level data
    if "LoanId" not in df_perf.columns:
        result["errors"].append("Performance data is not loan-level (missing LoanId column)")
        return result
    
    # Load loan-to-token mapping
    mapping_path = settings.package_root / "datasets" / deal_id / "loan_token_mapping.json"
    if not mapping_path.exists():
        result["errors"].append(
            f"Loan-to-token mapping not found: {mapping_path}. "
            "Create this file after minting loan NFTs."
        )
        return result
    
    try:
        with open(mapping_path, "r") as f:
            loan_id_to_token = json.load(f)
    except Exception as e:
        result["errors"].append(f"Failed to load loan_token_mapping.json: {e}")
        return result
    
    # Import Web3 client
    try:
        from web3_integration.web3_client import get_web3_client
    except ImportError:
        try:
            from rmbs_platform.web3_integration.web3_client import get_web3_client
        except ImportError:
            result["errors"].append("Web3 client not available")
            return result
    
    try:
        web3_client = get_web3_client()
    except Exception as e:
        result["errors"].append(f"Failed to initialize Web3 client: {e}")
        return result
    
    # Filter to latest period
    df_period = df_perf[df_perf["Period"] == period].copy()
    if df_period.empty:
        result["errors"].append(f"No data found for period {period}")
        return result
    
    # Prepare batch updates
    token_ids: List[int] = []
    statuses: List[int] = []
    balances: List[int] = []
    status_summary: Dict[str, int] = {}
    
    for _, loan in df_period.iterrows():
        loan_id = str(loan.get("LoanId", ""))
        if loan_id not in loan_id_to_token:
            continue  # Skip loans without token mapping
        
        token_id = int(loan_id_to_token[loan_id])
        
        # Determine status from DQStatus and LoanStatus columns
        dq_status = int(loan.get("DQStatus", loan.get("DPD", 0)))
        loan_status_str = str(loan.get("LoanStatus", "")).upper()
        
        # Map status
        is_defaulted = loan_status_str in ("DEFAULT", "FORECLOSURE", "REO", "BANKRUPT")
        is_paid_off = loan_status_str in ("PAID", "PAID_OFF", "PAIDOFF", "FULL", "MATURED")
        is_prepaid = loan_status_str in ("PREPAID", "PREPAY", "EARLY_PAYOFF", "VOLUNTARY_PAYOFF")
        
        status = _map_dpd_to_status(dq_status, is_defaulted, is_paid_off, is_prepaid)
        status_name = _get_status_name(status)
        status_summary[status_name] = status_summary.get(status_name, 0) + 1
        
        # Get current balance
        current_balance = loan.get("EndBalance", loan.get("CurrentBalance", loan.get("ScheduledBalance", 0)))
        balance_wei = int(float(current_balance) * 1e18)
        
        token_ids.append(token_id)
        statuses.append(status)
        balances.append(balance_wei)
    
    if not token_ids:
        result["errors"].append("No loans found with token mappings")
        return result
    
    # Execute batch updates
    batch_size = 100
    tx_hashes: List[str] = []
    
    for i in range(0, len(token_ids), batch_size):
        batch_token_ids = token_ids[i:i+batch_size]
        batch_statuses = statuses[i:i+batch_size]
        batch_balances = balances[i:i+batch_size]
        
        try:
            tx_hash = web3_client.update_loan_nfts_batch(
                contract_address,
                batch_token_ids,
                batch_statuses,
                batch_balances,
            )
            tx_hashes.append(tx_hash)
        except Exception as e:
            result["errors"].append(f"Batch {i//batch_size + 1} failed: {str(e)}")
    
    # Update local NFT records file to stay in sync
    records_path = settings.package_root / "datasets" / deal_id / "loan_nft_records.json"
    if records_path.exists():
        try:
            with open(records_path, "r") as f:
                nft_records = json.load(f)
            
            # Update each loan's status and balance
            loans_data = nft_records.get("loans", {})
            for i, token_id in enumerate(token_ids):
                token_key = str(token_id)
                if token_key in loans_data:
                    loans_data[token_key]["status_code"] = statuses[i]
                    loans_data[token_key]["status"] = _get_status_name(statuses[i])
                    loans_data[token_key]["current_balance"] = balances[i]
                    loans_data[token_key]["last_updated"] = int(datetime.now(timezone.utc).timestamp())
            
            nft_records["last_status_update"] = datetime.now(timezone.utc).isoformat()
            nft_records["last_period_updated"] = period
            
            with open(records_path, "w") as f:
                json.dump(nft_records, f, indent=2)
            print(f"Updated loan_nft_records.json for deal {deal_id} (period {period})")
        except Exception as e:
            result["errors"].append(f"Failed to update local NFT records: {e}")
    
    # Log audit event
    _log_audit_event(
        "web3.auto_loan_nft_status_update",
        deal_id=deal_id,
        details={
            "period": period,
            "loans_updated": len(token_ids),
            "tx_hashes": tx_hashes,
            "status_summary": status_summary,
        },
    )
    
    result["success"] = len(tx_hashes) > 0
    result["loans_updated"] = len(token_ids)
    result["tx_hashes"] = tx_hashes
    result["status_summary"] = status_summary
    result["period"] = period
    
    return result


@app.get("/performance/{deal_id}", tags=["Servicer", "Trustee", "Investor"])
async def get_performance(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer", "trustee", "investor", "auditor"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get performance data for a deal.
    
    Returns all uploaded performance rows for the specified deal.
    """
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    performance_rows = PERFORMANCE_DB.get(deal_id, [])
    
    # Group by period
    periods = {}
    for row in performance_rows:
        period = row.get("period", 0)
        if period not in periods:
            periods[period] = {
                "period": period,
                "loan_count": 0,
                "total_collections": 0,
                "scheduled_principal": 0,
                "scheduled_interest": 0,
                "prepayments": 0,
                "defaults": 0,
                "losses": 0,
            }
        periods[period]["loan_count"] += 1
        periods[period]["total_collections"] += row.get("ActualPayment", 0)
        periods[period]["scheduled_principal"] += row.get("SchedPrin", 0)
        periods[period]["scheduled_interest"] += row.get("SchedInt", 0)
        periods[period]["prepayments"] += row.get("Prepay", 0)
        periods[period]["defaults"] += row.get("Default", 0)
        periods[period]["losses"] += row.get("Loss", 0)
    
    return {
        "deal_id": deal_id,
        "periods": list(periods.values()),
        "total_rows": len(performance_rows),
        "latest_period": max(periods.keys()) if periods else None,
    }


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


# =============================================================================
# WEB3: LOAN NFT STATUS UPDATES
# =============================================================================


class LoanNFTStatusUpdateRequest(BaseModel):
    """Request model for updating loan NFT statuses from performance data."""
    loan_nft_contract: str
    period: Optional[int] = None  # If None, use latest period
    loan_id_to_token_map: Optional[Dict[str, int]] = None  # Map of LoanId -> tokenId


class LoanNFTStatusUpdateResponse(BaseModel):
    """Response model for loan NFT status updates."""
    deal_id: str
    period: int
    loans_updated: int
    tx_hashes: List[str]
    status_summary: Dict[str, int]
    errors: List[str]


def _map_dpd_to_status(dpd: int, is_defaulted: bool = False, is_paid_off: bool = False, is_prepaid: bool = False) -> int:
    """
    Map Days Past Due (DPD) to LoanStatus enum value.
    
    Parameters
    ----------
    dpd : int
        Days past due (0 for current)
    is_defaulted : bool
        True if loan is in foreclosure
    is_paid_off : bool
        True if loan is fully paid off
    is_prepaid : bool
        True if loan was prepaid
    
    Returns
    -------
    int
        LoanStatus enum value (0=Current, 1=30DPD, 2=60DPD, 3=90DPD, 4=Default, 5=PaidOff, 6=Prepaid)
    """
    if is_defaulted:
        return 4  # DEFAULT
    if is_paid_off:
        return 5  # PAID_OFF
    if is_prepaid:
        return 6  # PREPAID
    if dpd >= 90:
        return 3  # DELINQUENT_90
    if dpd >= 60:
        return 2  # DELINQUENT_60
    if dpd >= 30:
        return 1  # DELINQUENT_30
    return 0  # CURRENT


def _get_status_name(status: int) -> str:
    """Convert status enum to human-readable string."""
    names = {
        0: "Current",
        1: "30+ DPD",
        2: "60+ DPD",
        3: "90+ DPD",
        4: "Default",
        5: "Paid Off",
        6: "Prepaid",
    }
    return names.get(status, "Unknown")


@app.post("/web3/loans/{deal_id}/update-status", response_model=LoanNFTStatusUpdateResponse, tags=["Servicer", "Web3"])
async def update_loan_nft_statuses(
    deal_id: str,
    request: LoanNFTStatusUpdateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> LoanNFTStatusUpdateResponse:
    """
    Update loan NFT statuses based on performance data (Servicer role).
    
    This endpoint reads the performance data for a deal and updates the on-chain
    loan NFT statuses to reflect current loan health (delinquency, default, etc.).
    
    **Monthly Workflow**:
    1. Servicer uploads performance CSV via POST /performance/{deal_id}
    2. Servicer calls this endpoint to sync NFT statuses on-chain
    3. Smart contract emits LoanStatusUpdated events for audit trail
    
    **Mapping Logic**:
    - DPD 0-29 → Current
    - DPD 30-59 → 30+ DPD
    - DPD 60-89 → 60+ DPD
    - DPD 90+ → 90+ DPD
    - LoanStatus="Default" → Default
    - LoanStatus="Paid" → Paid Off
    - LoanStatus="Prepaid" → Prepaid
    
    **Gas Optimization**: Updates are batched (max 100 per transaction).
    """
    if not settings.web3_enabled:
        raise HTTPException(400, "Web3 integration is disabled. Set RMBS_WEB3_ENABLED=true")
    
    # Get performance data
    perf_data = PERFORMANCE_DB.get(deal_id)
    if not perf_data:
        raise HTTPException(404, f"No performance data found for deal {deal_id}")
    
    df = pd.DataFrame(perf_data)
    
    # Check if loan-level data
    if "LoanId" not in df.columns:
        raise HTTPException(400, "Performance data must be loan-level (include LoanId column)")
    
    # Determine period to use
    period = request.period
    if period is None:
        period = int(df["Period"].max())
    
    # Filter to the specific period
    df_period = df[df["Period"] == period].copy()
    if df_period.empty:
        raise HTTPException(404, f"No data found for period {period}")
    
    # Load loan_id_to_token mapping if not provided
    loan_id_to_token = request.loan_id_to_token_map
    if loan_id_to_token is None:
        # Try to load from datasets folder
        mapping_path = settings.package_root / "datasets" / deal_id / "loan_token_mapping.json"
        if mapping_path.exists():
            with open(mapping_path, "r") as f:
                loan_id_to_token = json.load(f)
        else:
            raise HTTPException(
                400, 
                "loan_id_to_token_map required. Either provide in request or save to "
                f"datasets/{deal_id}/loan_token_mapping.json"
            )
    
    # Import Web3 client
    try:
        from web3_integration.web3_client import get_web3_client
    except ImportError:
        from rmbs_platform.web3_integration.web3_client import get_web3_client
    
    try:
        web3_client = get_web3_client()
    except Exception as e:
        raise HTTPException(500, f"Failed to initialize Web3 client: {e}")
    
    # Prepare batch updates
    token_ids: List[int] = []
    statuses: List[int] = []
    balances: List[int] = []
    status_summary: Dict[str, int] = {}
    errors: List[str] = []
    
    for _, loan in df_period.iterrows():
        loan_id = str(loan.get("LoanId", ""))
        if loan_id not in loan_id_to_token:
            errors.append(f"No token mapping for loan {loan_id}")
            continue
        
        token_id = int(loan_id_to_token[loan_id])
        
        # Determine status from DPD and flags
        dpd = int(loan.get("DPD", loan.get("DaysPastDue", 0)))
        loan_status_str = str(loan.get("LoanStatus", "")).lower()
        
        is_defaulted = loan_status_str in ("default", "foreclosure", "reo")
        is_paid_off = loan_status_str in ("paid", "paid_off", "paidoff", "full")
        is_prepaid = loan_status_str in ("prepaid", "prepay", "early_payoff")
        
        status = _map_dpd_to_status(dpd, is_defaulted, is_paid_off, is_prepaid)
        status_name = _get_status_name(status)
        status_summary[status_name] = status_summary.get(status_name, 0) + 1
        
        # Get current balance (convert to wei - assuming 18 decimals)
        current_balance = loan.get("CurrentBalance", loan.get("ScheduledBalance", 0))
        # Convert to integer (wei representation)
        balance_wei = int(float(current_balance) * 1e18)
        
        token_ids.append(token_id)
        statuses.append(status)
        balances.append(balance_wei)
    
    if not token_ids:
        raise HTTPException(400, "No valid loans to update")
    
    # Execute batch updates (max 100 per tx)
    tx_hashes: List[str] = []
    batch_size = 100
    
    for i in range(0, len(token_ids), batch_size):
        batch_token_ids = token_ids[i:i+batch_size]
        batch_statuses = statuses[i:i+batch_size]
        batch_balances = balances[i:i+batch_size]
        
        try:
            tx_hash = web3_client.update_loan_nfts_batch(
                request.loan_nft_contract,
                batch_token_ids,
                batch_statuses,
                batch_balances,
            )
            tx_hashes.append(tx_hash)
        except Exception as e:
            errors.append(f"Batch {i//batch_size + 1} failed: {str(e)}")
    
    # Log audit event
    _log_audit_event(
        "web3.loan_nft_status_update",
        deal_id=deal_id,
        details={
            "period": period,
            "loans_updated": len(token_ids),
            "tx_hashes": tx_hashes,
            "status_summary": status_summary,
            "errors": errors,
        },
    )
    
    return LoanNFTStatusUpdateResponse(
        deal_id=deal_id,
        period=period,
        loans_updated=len(token_ids) - len([e for e in errors if "failed" in e.lower()]),
        tx_hashes=tx_hashes,
        status_summary=status_summary,
        errors=errors,
    )


@app.get("/deals", tags=["Arranger", "Issuer", "Trustee", "Investor", "Servicer", "Auditor"])
async def list_deals(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "issuer", "trustee", "investor", "servicer", "auditor"], x_user_role)),
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

@app.get("/deals/{deal_id}", tags=["Arranger", "Investor", "Issuer", "Trustee", "Servicer", "Auditor"])
async def get_deal(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor", "issuer", "trustee", "servicer", "auditor"], x_user_role)),
) -> Dict[str, Any]:
    """Get a specific deal by ID."""
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    spec = DEALS_DB[deal_id]
    meta = spec.get("meta", {})
    
    # Get performance info if available
    perf_rows = PERFORMANCE_DB.get(deal_id, [])
    latest_period = None
    if perf_rows:
        perf_df = pd.DataFrame(perf_rows)
        if "Period" in perf_df.columns and not perf_df.empty:
            latest_period = int(perf_df["Period"].max())
    
    return {
        "deal_id": deal_id,
        "deal_name": meta.get("deal_name", ""),
        "asset_type": meta.get("asset_type", ""),
        "has_collateral": deal_id in COLLATERAL_DB,
        "latest_period": latest_period,
        "spec": spec  # Full deal specification
    }


class ResetDealDataRequest(BaseModel):
    """Request model for resetting deal data."""
    reset_token_holders: bool = Field(default=True, description="Reset token holder records for this deal")
    reset_distributions: bool = Field(default=True, description="Reset distribution cycles for this deal")
    reset_yield_distributions: bool = Field(default=True, description="Reset yield distribution records for this deal")
    reset_performance: bool = Field(default=False, description="Reset performance data for this deal")
    reset_nft_records: bool = Field(default=False, description="Reset loan NFT records for this deal")
    reset_tranche_registry: bool = Field(default=False, description="Reset tranche registry for this deal")


@app.post("/deals/{deal_id}/reset", tags=["Arranger"])
async def reset_deal_data(
    deal_id: str,
    payload: ResetDealDataRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    """
    Reset all data associated with a deal for testing purposes.
    
    This endpoint clears:
    - Token holder records (holdings for this deal)
    - Distribution cycle records
    - Yield distribution records
    - Optionally: Performance data, NFT records, tranche registry
    
    USE WITH CAUTION - this operation cannot be undone!
    """
    if deal_id not in DEALS_DB:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    
    reset_summary = {
        "deal_id": deal_id,
        "actions": [],
        "warnings": []
    }
    
    # 1. Reset token holders for this deal
    if payload.reset_token_holders:
        try:
            registry = _load_token_holders_registry()
            holders = registry.get("holders", {})
            holders_cleared = 0
            holdings_cleared = 0
            
            for holder_key, holder_data in holders.items():
                holdings = holder_data.get("holdings", {})
                if deal_id in holdings:
                    holdings_count = len(holdings[deal_id])
                    del holdings[deal_id]
                    holders_cleared += 1
                    holdings_cleared += holdings_count
            
            registry["updated_at"] = _utc_now_iso()
            _save_token_holders_registry(registry)
            reset_summary["actions"].append(f"Cleared {holdings_cleared} token holdings from {holders_cleared} holders")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset token holders: {e}")
    
    # 2. Reset distribution cycles for this deal
    if payload.reset_distributions:
        try:
            dist_path = WEB3_SYNC_DIR / "distribution_cycles.json"
            if dist_path.exists():
                with open(dist_path, "r") as f:
                    dist_data = json.load(f)
                
                deals = dist_data.get("deals", {})
                if deal_id in deals:
                    period_count = len(deals[deal_id].get("periods", []))
                    del deals[deal_id]
                    
                    with open(dist_path, "w") as f:
                        json.dump(dist_data, f, indent=2)
                    
                    reset_summary["actions"].append(f"Cleared {period_count} distribution periods")
                else:
                    reset_summary["actions"].append("No distribution cycles found for this deal")
            else:
                reset_summary["actions"].append("No distribution cycles file exists")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset distribution cycles: {e}")
    
    # 3. Reset yield distributions for this deal
    if payload.reset_yield_distributions:
        try:
            yield_path = WEB3_SYNC_DIR / "yield_distributions.json"
            if yield_path.exists():
                with open(yield_path, "r") as f:
                    yield_data = json.load(f)
                
                distributions = yield_data.get("distributions", [])
                original_count = len(distributions)
                # Filter out distributions for this deal
                yield_data["distributions"] = [
                    d for d in distributions 
                    if d.get("deal_id") != deal_id
                ]
                removed_count = original_count - len(yield_data["distributions"])
                yield_data["updated_at"] = _utc_now_iso()
                
                with open(yield_path, "w") as f:
                    json.dump(yield_data, f, indent=2)
                
                reset_summary["actions"].append(f"Cleared {removed_count} yield distributions")
            else:
                reset_summary["actions"].append("No yield distributions file exists")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset yield distributions: {e}")
    
    # 4. Optional: Reset performance data
    if payload.reset_performance:
        try:
            datasets_dir = settings.package_root / "datasets"
            row_count = 0
            
            if deal_id in PERFORMANCE_DB:
                row_count = len(PERFORMANCE_DB[deal_id])
                del PERFORMANCE_DB[deal_id]
            
            # Also remove performance CSV files
            perf_folder = datasets_dir / deal_id / "performance"
            if perf_folder.exists():
                import shutil
                shutil.rmtree(perf_folder)
            
            # Also remove servicer folder if it exists
            servicer_folder = datasets_dir / deal_id / "servicer"
            if servicer_folder.exists():
                import shutil
                shutil.rmtree(servicer_folder)
            
            if row_count > 0:
                reset_summary["actions"].append(f"Cleared {row_count} performance records from memory")
            reset_summary["actions"].append("Cleared performance data files")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset performance data: {e}")
    
    # 5. Optional: Reset loan NFT records
    if payload.reset_nft_records:
        try:
            datasets_dir = settings.package_root / "datasets"
            nft_records_path = datasets_dir / deal_id / "loan_nft_records.json"
            if nft_records_path.exists():
                nft_records_path.unlink()
                reset_summary["actions"].append("Cleared loan NFT records")
            else:
                reset_summary["actions"].append("No loan NFT records found")
            
            # Also clear loan_token_mapping.json
            mapping_path = datasets_dir / deal_id / "loan_token_mapping.json"
            if mapping_path.exists():
                mapping_path.unlink()
                reset_summary["actions"].append("Cleared loan token mapping")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset NFT records: {e}")
    
    # 6. Optional: Reset tranche registry
    if payload.reset_tranche_registry:
        try:
            datasets_dir = settings.package_root / "datasets"
            registry_path = datasets_dir / deal_id / "tranche_registry.json"
            if registry_path.exists():
                registry_path.unlink()
                reset_summary["actions"].append("Cleared tranche registry")
            else:
                reset_summary["actions"].append("No tranche registry found")
        except Exception as e:
            reset_summary["warnings"].append(f"Failed to reset tranche registry: {e}")
    
    # Log the reset action
    _log_audit_event(
        "deal.reset",
        deal_id=deal_id,
        details={
            "options": payload.model_dump(),
            "actions": reset_summary["actions"],
            "warnings": reset_summary["warnings"]
        }
    )
    
    reset_summary["success"] = len(reset_summary["warnings"]) == 0
    reset_summary["message"] = f"Deal {deal_id} data reset completed with {len(reset_summary['actions'])} actions"
    
    return reset_summary


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


# ────────────────────────────────────────────────────────────────────────────────
# MODEL-DRIVEN ESTIMATES ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────────

class ModelEstimateRequest(BaseModel):
    """Request for model-driven CPR/CDR/Severity estimates."""
    # Pool characteristics
    wa_fico: float = Field(default=720.0, description="Weighted-average FICO score")
    wa_ltv: float = Field(default=75.0, description="Weighted-average LTV ratio")
    wa_dti: float = Field(default=36.0, description="Weighted-average DTI ratio")
    wa_coupon: float = Field(default=0.05, description="Weighted-average coupon rate (decimal)")
    wa_seasoning: int = Field(default=12, description="Average loan age in months")
    
    # Market conditions
    current_market_rate: float = Field(default=0.065, description="Current mortgage rate (decimal)")
    rate_scenario: str = Field(default="base", description="Rate scenario: rally, base, selloff")
    economic_scenario: str = Field(default="stable", description="Economic scenario: expansion, stable, mild_recession, severe_recession")
    
    # Pool composition
    pct_high_ltv: float = Field(default=0.20, description="% of pool with LTV > 80")
    pct_investor: float = Field(default=0.05, description="% investment properties")
    pct_condo: float = Field(default=0.10, description="% condos/co-ops")
    pct_judicial_states: float = Field(default=0.30, description="% in judicial foreclosure states")


class SensitivityRequest(BaseModel):
    """Request for sensitivity analysis."""
    base_params: ModelEstimateRequest = Field(default_factory=ModelEstimateRequest)
    vary_param: str = Field(..., description="Parameter to vary")
    vary_values: List[float] = Field(..., description="Values to test")


@app.post("/pricing/model-estimates", tags=["Investor"])
async def get_model_driven_estimates(
    payload: ModelEstimateRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get model-driven estimates for CPR, CDR, and Loss Severity.
    
    Uses ML model coefficients trained on historical loan performance to estimate
    prepayment, default, and severity rates based on pool characteristics and
    market conditions.
    """
    from engine.model_driven_estimates import ModelDrivenEstimator
    
    estimator = ModelDrivenEstimator()
    result = estimator.estimate(
        wa_fico=payload.wa_fico,
        wa_ltv=payload.wa_ltv,
        wa_dti=payload.wa_dti,
        wa_coupon=payload.wa_coupon,
        wa_seasoning=payload.wa_seasoning,
        current_market_rate=payload.current_market_rate,
        rate_scenario=payload.rate_scenario,
        economic_scenario=payload.economic_scenario,
        pct_high_ltv=payload.pct_high_ltv,
        pct_investor=payload.pct_investor,
        pct_condo=payload.pct_condo,
        pct_judicial_states=payload.pct_judicial_states,
    )
    
    return {
        "cpr": result.cpr,
        "cdr": result.cdr,
        "severity": result.severity,
        "cpr_range": result.cpr_range,
        "cdr_range": result.cdr_range,
        "severity_range": result.severity_range,
        "inputs": result.inputs,
        "components": {
            "cpr": result.cpr_components,
            "cdr": result.cdr_components,
            "severity": result.severity_components,
        }
    }


@app.post("/pricing/sensitivity", tags=["Investor"])
async def run_sensitivity_analysis(
    payload: SensitivityRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """
    Run sensitivity analysis by varying one parameter.
    
    Returns CPR/CDR/Severity for each value of the varied parameter.
    """
    from engine.model_driven_estimates import ModelDrivenEstimator
    
    estimator = ModelDrivenEstimator()
    base_params = payload.base_params.model_dump()
    results = estimator.run_sensitivity_analysis(
        base_params=base_params,
        vary_param=payload.vary_param,
        vary_values=payload.vary_values,
    )
    
    return {
        "base_params": base_params,
        "vary_param": payload.vary_param,
        "results": results,
    }


@app.get("/pricing/scenarios", tags=["Investor"])
async def list_pricing_scenarios(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Dict[str, Any]:
    """List available rate and economic scenarios for model-driven pricing."""
    from engine.model_driven_estimates import ModelDrivenEstimator
    
    estimator = ModelDrivenEstimator()
    return {
        "rate_scenarios": estimator.RATE_SCENARIOS,
        "economic_scenarios": estimator.ECONOMIC_SCENARIOS,
    }


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

# =============================================================================
# Web3 Integration Endpoints
# =============================================================================


def _get_web3_client_or_503() -> Any:
    try:
        return get_web3_client()
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Web3 unavailable: {exc}") from exc


def _get_deal_spec_or_404(deal_id: str) -> Dict[str, Any]:
    spec = DEALS_DB.get(deal_id)
    if not spec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Deal {deal_id} not found.")
    return spec


def _load_web3_registry() -> Dict[str, Any]:
    if not WEB3_REGISTRY_PATH.exists():
        return {"deals": {}}
    try:
        return json.loads(WEB3_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"deals": {}}


def _save_web3_registry(data: Dict[str, Any]) -> None:
    WEB3_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB3_REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _update_tranche_registry(deal_id: str, tranches: Dict[str, str]) -> None:
    """
    Update tranche registry with mapping of tranche_id -> contract_address.
    """
    registry = _load_web3_registry()
    deals = registry.setdefault("deals", {})
    deal_entry = deals.setdefault(deal_id, {})
    # Merge with existing tranches (don't overwrite)
    existing = deal_entry.get("tranches", {})
    if isinstance(existing, list):
        existing = {}  # Reset if old format
    existing.update(tranches)
    deal_entry["tranches"] = existing
    deal_entry["updated_at"] = _utc_now_iso()
    _save_web3_registry(registry)


def _get_token_holders_registry_path() -> Path:
    """Get path to token holders registry file (cached blockchain state)."""
    return WEB3_SYNC_DIR / "token_balances.json"


def _load_token_holders_registry() -> Dict[str, Any]:
    """Load token holders registry from disk."""
    path = _get_token_holders_registry_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"holders": {}, "updated_at": None}


def _save_token_holders_registry(registry: Dict[str, Any]) -> None:
    """Save token holders registry to disk."""
    path = _get_token_holders_registry_path()
    registry["updated_at"] = _utc_now_iso()
    path.write_text(json.dumps(registry, indent=2, default=str))


def _record_token_issuance(
    deal_id: str,
    tranche_id: str,
    holder_address: str,
    amount: int,
    tranche_address: str,
    tx_hash: str
) -> None:
    """
    Record token issuance to a holder.
    
    This creates a local mirror of on-chain token balances.
    """
    registry = _load_token_holders_registry()
    holders = registry.setdefault("holders", {})
    
    # Normalize address
    holder_key = holder_address.lower()
    
    holder_entry = holders.setdefault(holder_key, {
        "address": holder_address,
        "holdings": {},
        "created_at": _utc_now_iso()
    })
    
    holdings = holder_entry.setdefault("holdings", {})
    deal_holdings = holdings.setdefault(deal_id, {})
    
    # Update or create tranche holding
    if tranche_id in deal_holdings:
        # Already issued - warn and skip to prevent inflation
        existing_balance = deal_holdings[tranche_id].get("balance", 0)
        print(f"Warning: Tokens already issued to {holder_address} for {deal_id}/{tranche_id} (balance: {existing_balance}). Skipping to prevent double-issuance.")
        _save_token_holders_registry(registry)
        return
    else:
        deal_holdings[tranche_id] = {
            "tranche_id": tranche_id,
            "tranche_address": tranche_address,
            "balance": amount,
            "initial_balance": amount,
            "issued_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "last_tx_hash": tx_hash
        }
    
    holder_entry["updated_at"] = _utc_now_iso()
    _save_token_holders_registry(registry)


def _get_holder_portfolio(holder_address: str) -> Dict[str, Any]:
    """
    Get portfolio holdings for a specific holder.
    
    Returns dict with holdings by deal and tranche.
    """
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.get(holder_key)
    if not holder_entry:
        return {"address": holder_address, "holdings": {}, "cash_balance": 0.0, "total_value": 0}
    
    # Ensure cash_balance exists
    if "cash_balance" not in holder_entry:
        holder_entry["cash_balance"] = 0.0
    
    return holder_entry


def _get_holder_cash_balance(holder_address: str) -> float:
    """Get cash balance for a holder."""
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.get(holder_key, {})
    return holder_entry.get("cash_balance", 0.0)


def _update_holder_cash_balance(holder_address: str, amount: float, operation: str = "add") -> float:
    """
    Update cash balance for a holder.
    
    Args:
        holder_address: The investor's wallet address
        amount: Amount to add or set
        operation: "add" to add to balance, "set" to set absolute value
    
    Returns:
        New cash balance
    """
    registry = _load_token_holders_registry()
    holders = registry.setdefault("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.setdefault(holder_key, {
        "address": holder_address,
        "holdings": {},
        "cash_balance": 0.0,
        "created_at": _utc_now_iso()
    })
    
    current_balance = holder_entry.get("cash_balance", 0.0)
    
    if operation == "add":
        new_balance = current_balance + amount
    elif operation == "set":
        new_balance = amount
    else:
        new_balance = current_balance + amount
    
    holder_entry["cash_balance"] = new_balance
    holder_entry["updated_at"] = _utc_now_iso()
    
    _save_token_holders_registry(registry)
    return new_balance


def _record_yield_claim(
    holder_address: str,
    claims: List[Dict[str, Any]],
    total_amount: float
) -> Dict[str, Any]:
    """
    Record a yield claim and update cash balance.
    
    Args:
        holder_address: The investor's wallet address
        claims: List of individual yield claims with token/amount/period
        total_amount: Total amount being claimed
    
    Returns:
        Dict with claim details and new balance
    """
    registry = _load_token_holders_registry()
    holders = registry.setdefault("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.setdefault(holder_key, {
        "address": holder_address,
        "holdings": {},
        "cash_balance": 0.0,
        "yield_claims": [],
        "created_at": _utc_now_iso()
    })
    
    # Update cash balance
    current_balance = holder_entry.get("cash_balance", 0.0)
    new_balance = current_balance + total_amount
    holder_entry["cash_balance"] = new_balance
    
    # Record the claim
    claim_time = _utc_now_iso()
    claim_record = {
        "claim_id": f"CLAIM_{claim_time.replace(':', '').replace('-', '')}",
        "claimed_at": claim_time,
        "total_amount": total_amount,
        "claims": claims,
        "previous_balance": current_balance,
        "new_balance": new_balance
    }
    
    yield_claims = holder_entry.setdefault("yield_claims", [])
    yield_claims.append(claim_record)
    
    # Keep only last 100 claims
    if len(yield_claims) > 100:
        holder_entry["yield_claims"] = yield_claims[-100:]
    
    # Update last_yield_claimed timestamp for each holding that was claimed
    holdings = holder_entry.get("holdings", {})
    for claim in claims:
        deal_id = claim.get("deal_id")
        tranche_id = claim.get("tranche_id")
        if deal_id and tranche_id and deal_id in holdings and tranche_id in holdings[deal_id]:
            holdings[deal_id][tranche_id]["last_yield_claimed"] = claim_time
    
    holder_entry["updated_at"] = _utc_now_iso()
    _save_token_holders_registry(registry)
    
    return {
        "claim_id": claim_record["claim_id"],
        "total_claimed": total_amount,
        "new_cash_balance": new_balance,
        "claims_count": len(claims)
    }


def _get_holder_yield_history(holder_address: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Get yield claim history for a holder."""
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.get(holder_key, {})
    claims = holder_entry.get("yield_claims", [])
    
    # Return most recent first
    return list(reversed(claims[-limit:]))


def _get_yield_distributions_path() -> Path:
    """Get path to yield distributions file (cached blockchain events)."""
    return WEB3_SYNC_DIR / "yield_distributions.json"


def _load_yield_distributions() -> Dict[str, Any]:
    """Load yield distributions from disk."""
    path = _get_yield_distributions_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"distributions": [], "updated_at": None}


def _save_yield_distributions(data: Dict[str, Any]) -> None:
    """Save yield distributions to disk."""
    path = _get_yield_distributions_path()
    data["updated_at"] = _utc_now_iso()
    path.write_text(json.dumps(data, indent=2, default=str))


def _distribute_yield_to_holders(
    deal_id: str,
    tranche_id: str,
    total_amount: float,
    period: int
) -> Dict[str, Any]:
    """
    Distribute yield to all holders of a tranche.
    
    Creates pending yield records for each holder proportional to their holdings.
    Returns distribution summary.
    """
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    
    # Find all holders of this tranche
    tranche_holders = []
    total_tranche_balance = 0
    
    for holder_key, holder_entry in holders.items():
        holdings = holder_entry.get("holdings", {})
        deal_holdings = holdings.get(deal_id, {})
        tranche_holding = deal_holdings.get(tranche_id)
        
        if tranche_holding:
            balance = tranche_holding.get("balance", 0)
            if balance > 0:
                tranche_holders.append({
                    "address": holder_entry.get("address"),
                    "holder_key": holder_key,
                    "balance": balance
                })
                total_tranche_balance += balance
    
    if not tranche_holders:
        return {
            "status": "no_holders",
            "message": f"No holders found for {deal_id}/{tranche_id}",
            "distributed_to": 0,
            "total_amount": 0
        }
    
    # Calculate and distribute yields pro-rata
    distributions = []
    distribution_time = _utc_now_iso()
    
    for holder in tranche_holders:
        # Pro-rata share
        share = holder["balance"] / total_tranche_balance if total_tranche_balance > 0 else 0
        yield_amount = total_amount * share
        
        # Add to holder's pending yields
        holder_key = holder["holder_key"]
        holder_entry = holders[holder_key]
        
        pending_yields = holder_entry.setdefault("pending_yield_distributions", [])
        
        # IMPORTANT: Remove any existing UNCLAIMED distribution for the same deal/tranche/period
        # This prevents duplicate yields when re-processing a period
        pending_yields[:] = [
            d for d in pending_yields
            if not (
                d.get("deal_id") == deal_id and
                d.get("tranche_id") == tranche_id and
                d.get("period") == period and
                not d.get("claimed", False)  # Only remove unclaimed distributions
            )
        ]
        
        pending_yields.append({
            "distribution_id": f"DIST_{distribution_time.replace(':', '').replace('-', '')}_{tranche_id}",
            "deal_id": deal_id,
            "tranche_id": tranche_id,
            "period": period,
            "amount": yield_amount,
            "distributed_at": distribution_time,
            "claimed": False
        })
        
        distributions.append({
            "address": holder["address"],
            "balance": holder["balance"],
            "share": share,
            "yield_amount": yield_amount
        })
    
    # Save updated registry
    registry["updated_at"] = _utc_now_iso()
    _save_token_holders_registry(registry)
    
    # Also record in distributions log (remove existing entries for same deal/tranche/period first)
    dist_log = _load_yield_distributions()
    
    # Remove existing distribution for same deal/tranche/period to prevent duplicates
    dist_log["distributions"] = [
        d for d in dist_log.get("distributions", [])
        if not (
            d.get("deal_id") == deal_id and
            d.get("tranche_id") == tranche_id and
            d.get("period") == period
        )
    ]
    
    dist_log["distributions"].append({
        "distribution_id": f"DIST_{distribution_time.replace(':', '').replace('-', '')}",
        "deal_id": deal_id,
        "tranche_id": tranche_id,
        "period": period,
        "total_amount": total_amount,
        "distributed_at": distribution_time,
        "holder_count": len(distributions),
        "distributions": distributions
    })
    _save_yield_distributions(dist_log)
    
    return {
        "status": "success",
        "distribution_id": f"DIST_{distribution_time.replace(':', '').replace('-', '')}",
        "deal_id": deal_id,
        "tranche_id": tranche_id,
        "period": period,
        "total_amount": total_amount,
        "distributed_to": len(distributions),
        "distributions": distributions
    }


def _get_pending_yield_distributions(holder_address: str) -> List[Dict[str, Any]]:
    """Get unclaimed yield distributions for a holder."""
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.get(holder_key, {})
    pending = holder_entry.get("pending_yield_distributions", [])
    
    # Return only unclaimed distributions
    return [d for d in pending if not d.get("claimed", False)]


def _claim_yield_distributions(holder_address: str, distribution_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Claim yield distributions for a holder.
    
    If distribution_ids is None, claims all pending distributions.
    """
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    holder_key = holder_address.lower()
    
    holder_entry = holders.get(holder_key)
    if not holder_entry:
        return {"status": "error", "message": "Holder not found", "claimed": 0}
    
    pending = holder_entry.get("pending_yield_distributions", [])
    
    claimed_amount = 0.0
    claimed_count = 0
    claimed_distributions = []
    
    for dist in pending:
        if dist.get("claimed"):
            continue
        
        # If specific IDs provided, only claim those
        if distribution_ids and dist.get("distribution_id") not in distribution_ids:
            continue
        
        dist["claimed"] = True
        dist["claimed_at"] = _utc_now_iso()
        claimed_amount += dist.get("amount", 0)
        claimed_count += 1
        claimed_distributions.append(dist)
    
    # Update cash balance
    current_balance = holder_entry.get("cash_balance", 0.0)
    new_balance = current_balance + claimed_amount
    holder_entry["cash_balance"] = new_balance
    holder_entry["updated_at"] = _utc_now_iso()
    
    _save_token_holders_registry(registry)
    
    return {
        "status": "success",
        "claimed_count": claimed_count,
        "claimed_amount": claimed_amount,
        "previous_balance": current_balance,
        "new_balance": new_balance,
        "distributions": claimed_distributions
    }


def _get_all_token_holders() -> List[Dict[str, Any]]:
    """Get all registered token holders."""
    registry = _load_token_holders_registry()
    return list(registry.get("holders", {}).values())


def _get_tranche_registry(deal_id: str) -> Dict[str, str]:
    """
    Get tranche registry for a deal: mapping tranche_id -> contract_address.
    
    Returns empty dict if no tranches are registered.
    """
    registry = _load_web3_registry()
    tranches = registry.get("deals", {}).get(deal_id, {}).get("tranches", {})
    # Handle both old list format and new dict format
    if isinstance(tranches, list):
        # Legacy format: list of addresses - convert to dict
        return {}
    return tranches or {}


def _iter_bonds(spec: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    bonds = spec.get("bonds") or {}
    if isinstance(bonds, dict):
        return [(bond_id, bond_def or {}) for bond_id, bond_def in bonds.items()]
    if isinstance(bonds, list):
        items: List[Tuple[str, Dict[str, Any]]] = []
        for idx, bond_def in enumerate(bonds):
            bond_id = str(bond_def.get("id") or bond_def.get("tranche_id") or idx)
            items.append((bond_id, bond_def or {}))
        return items
    return []


def _bond_fixed_rate(bond_def: Dict[str, Any]) -> float:
    coupon = bond_def.get("coupon") or {}
    fixed_rate = coupon.get("fixed_rate")
    if fixed_rate is None:
        fixed_rate = bond_def.get("fixed_rate")
    if fixed_rate is None:
        fixed_rate = bond_def.get("coupon_rate")
    try:
        return float(fixed_rate or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_tranche_params_from_spec(
    deal_id: str,
    spec: Dict[str, Any],
    payload: Web3TranchePublishRequest,
) -> List[Dict[str, Any]]:
    bonds = _iter_bonds(spec)
    if payload.tranche_ids:
        allowed = {tid for tid in payload.tranche_ids}
        bonds = [(bond_id, bond_def) for bond_id, bond_def in bonds if bond_id in allowed]
    if not bonds:
        return []

    meta = spec.get("meta") or {}
    maturity_date = payload.maturity_date or meta.get("maturity_date") or meta.get("maturity")
    if maturity_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "maturity_date is required (payload or deal meta).",
        )

    params_list: List[Dict[str, Any]] = []
    for bond_id, bond_def in bonds:
        original_balance = bond_def.get("original_balance") or bond_def.get("balance") or 0
        try:
            original_balance = int(original_balance)
        except (TypeError, ValueError):
            original_balance = 0
        if original_balance <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bond {bond_id} is missing a valid original_balance.",
            )

        coupon_rate_bps = int(_bond_fixed_rate(bond_def) * 10_000)
        tranche_name = bond_def.get("name") or f"{deal_id}-{bond_id}"
        tranche_symbol = str(bond_def.get("symbol") or bond_id).upper()[:10]

        params_list.append(
            {
                "deal_id": deal_id,
                "tranche_id": bond_id,
                "name": tranche_name,
                "symbol": tranche_symbol,
                "original_face_value": original_balance,
                "coupon_rate_bps": coupon_rate_bps,
                "payment_frequency": payload.payment_frequency,
                "maturity_date": int(maturity_date),
                "payment_token": payload.payment_token,
                "transfer_validator": payload.transfer_validator,
                "admin": payload.admin,
                "issuer": payload.issuer,
                "trustee": payload.trustee,
            }
        )
    return params_list


def _build_waterfall_payload_from_spec(
    deal_id: str,
    spec: Dict[str, Any],
    payload: Web3WaterfallPublishRequest,
    tranche_addresses: List[str],
) -> Web3WaterfallConfig:
    bonds = _iter_bonds(spec)
    if not bonds:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Deal {deal_id} has no bonds to publish.")
    bonds_sorted = sorted(
        bonds,
        key=lambda item: int(item[1].get("seniority", 0)),
    )
    if len(tranche_addresses) != len(bonds_sorted):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Number of tranche addresses must match number of bonds in the deal spec.",
        )

    interest_rates_bps = payload.interest_rates_bps or [
        int(_bond_fixed_rate(bond_def) * 10_000) for _, bond_def in bonds_sorted
    ]
    seniorities = payload.seniorities or [
        int(bond_def.get("seniority", 0)) for _, bond_def in bonds_sorted
    ]
    if not (len(interest_rates_bps) == len(seniorities) == len(tranche_addresses)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "interest_rates_bps, seniorities, and tranches must have matching lengths.",
        )

    return Web3WaterfallConfig(
        deal_id=deal_id,
        payment_token=payload.payment_token,
        tranches=tranche_addresses,
        seniorities=seniorities,
        interest_rates_bps=interest_rates_bps,
        trustee_fees_bps=payload.trustee_fees_bps,
        servicer_fees_bps=payload.servicer_fees_bps,
        trustee_address=payload.trustee_address,
        servicer_address=payload.servicer_address,
        principal_sequential=payload.principal_sequential,
    )


@app.get("/web3/health", tags=["Web3"])
async def web3_health() -> Dict[str, Any]:
    client = _get_web3_client_or_503()
    return {
        "connected": client.is_connected(),
        "rpc_url": settings.web3_rpc_url,
    }


@app.get("/web3/deals", response_model=List[Web3DealResponse], tags=["Web3"])
async def web3_list_deals(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor", "auditor"], x_user_role)),
) -> List[Web3DealResponse]:
    client = _get_web3_client_or_503()
    deals = []
    for deal_id in client.list_deals():
        deals.append(Web3DealResponse(**client.get_deal_info(deal_id)))
    return deals


@app.get("/web3/deals/{deal_id}", response_model=Web3DealResponse, tags=["Web3"])
async def web3_get_deal(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor", "auditor"], x_user_role)),
) -> Web3DealResponse:
    client = _get_web3_client_or_503()
    return Web3DealResponse(**client.get_deal_info(deal_id))


@app.post("/web3/deals", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_register_deal(
    deal: Web3DealCreate,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    tx_hash = client.register_deal(
        deal_id=deal.deal_id,
        deal_name=deal.deal_name,
        arranger=deal.arranger,
        closing_date=deal.closing_date,
        maturity_date=deal.maturity_date,
    )
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/deals/{deal_id}/tranches", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_deploy_tranche(
    deal_id: str,
    tranche: Web3TrancheCreate,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    params = tranche.dict()
    params["deal_id"] = deal_id
    tx_hash = client.deploy_tranche(params)
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/deals/{deal_id}/tranches/publish", response_model=Web3BatchResponse, tags=["Web3"])
async def web3_publish_tranches_from_deal(
    deal_id: str,
    payload: Web3TranchePublishRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3BatchResponse:
    spec = _get_deal_spec_or_404(deal_id)
    params_list = _build_tranche_params_from_spec(deal_id, spec, payload)
    if not params_list:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Deal {deal_id} has no bonds to publish.")

    client = _get_web3_client_or_503()
    tx_hashes: List[str] = []
    for params in params_list:
        tx_hashes.append(client.deploy_tranche(params))

    return Web3BatchResponse(transactions=tx_hashes, count=len(tx_hashes))


@app.post("/web3/deals/{deal_id}/tranches/register", response_model=Dict[str, Any], tags=["Web3"])
async def web3_register_tranche_addresses(
    deal_id: str,
    payload: Web3TrancheRegistryUpdate,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    if not payload.tranches:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tranches list is required.")
    _update_tranche_registry(deal_id, payload.tranches)
    return {"deal_id": deal_id, "tranches": payload.tranches}


@app.get("/web3/deals/{deal_id}/tranches/registry", response_model=Dict[str, Any], tags=["Web3", "Issuer"])
async def web3_get_tranche_registry(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger", "investor", "issuer", "trustee", "auditor"], x_user_role)),
) -> Dict[str, Any]:
    return {"deal_id": deal_id, "tranches": _get_tranche_registry(deal_id)}


@app.get("/web3/portfolio/{holder_address}", response_model=Dict[str, Any], tags=["Web3", "Investor"])
async def web3_get_investor_portfolio(
    holder_address: str,
    cpr: float = 0.10,
    cdr: float = 0.02,
    severity: float = 0.35,
    use_full_pricing: bool = True,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor", "arranger", "auditor", "issuer", "trustee"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get token holdings portfolio for an investor with full pricing analytics.
    
    Returns all token holdings across all deals for the specified wallet address,
    enriched with YTM, OAS, duration, and other risk metrics.
    
    Parameters
    ----------
    holder_address : str
        Investor wallet address
    cpr : float
        CPR assumption for pricing (default 10%)
    cdr : float
        CDR assumption for pricing (default 2%)
    severity : float
        Loss severity assumption (default 35%)
    use_full_pricing : bool
        If True, uses full pricing engine with cashflow projection.
        If False, uses simplified approximation.
    """
    portfolio = _get_holder_portfolio(holder_address)
    holdings = portfolio.get("holdings", {})
    
    # Enrich with deal and tranche details
    enriched_holdings = []
    total_value = 0
    
    # Try to use full pricing engine
    pricing_engine_available = False
    yield_curve = None
    market_data = None
    
    if use_full_pricing:
        try:
            from engine.portfolio_pricing import (
                build_default_yield_curve,
                price_tranche,
                DEFAULT_MARKET_DATA,
            )
            yield_curve = build_default_yield_curve()
            market_data = DEFAULT_MARKET_DATA
            pricing_engine_available = True
        except Exception as e:
            # Pricing engine unavailable, will use simplified fallback
            print(f"Full pricing engine not available: {e}")
    
    for deal_id, deal_holdings in holdings.items():
        # Get deal spec for enrichment
        deal_spec = DEALS_DB.get(deal_id, {})
        bonds_by_id = {b.get("id"): b for b in deal_spec.get("bonds", [])}
        
        for tranche_id, holding in deal_holdings.items():
            bond_info = bonds_by_id.get(tranche_id, {})
            original_balance = bond_info.get("original_balance", holding.get("initial_balance", 0))
            current_balance = holding.get("balance", 0)
            
            # Calculate factor (balance / original)
            factor = current_balance / original_balance if original_balance > 0 else 1.0
            
            # Get coupon info
            coupon = bond_info.get("coupon", {})
            coupon_kind = coupon.get("kind", "FIXED")
            
            if coupon_kind == "FIXED":
                coupon_rate = coupon.get("fixed_rate", 0.05)
                margin = 0.0
            elif coupon_kind == "FLOAT":
                coupon_rate = 0.0
                margin = coupon.get("margin", 0.0175)
            elif coupon_kind == "WAC":
                coupon_rate = coupon.get("wac_spread", 0.0) + 0.055
                margin = 0.0
            else:
                coupon_rate = 0.05
                margin = 0.0
            
            rating = bond_info.get("rating", "NR")
            wam_months = int(bond_info.get("wam_months", 300))
            
            # Use full pricing engine if available
            if pricing_engine_available and current_balance > 0:
                try:
                    pricing_result = price_tranche(
                        original_balance=original_balance,
                        current_balance=current_balance,
                        coupon_rate=coupon_rate,
                        coupon_type=coupon_kind,
                        wam_months=wam_months,
                        rating=rating,
                        cpr=cpr,
                        cdr=cdr,
                        severity=severity,
                        yield_curve=yield_curve,
                        market_data=market_data,
                        margin=margin,
                    )
                    ytm = pricing_result.ytm
                    oas_bps = pricing_result.oas_bps
                    z_spread_bps = pricing_result.z_spread_bps
                    credit_spread_bps = pricing_result.credit_spread_bps
                    duration = pricing_result.duration
                    fair_value = pricing_result.fair_value
                    pricing_methodology = pricing_result.pricing_methodology
                    cashflow_count = pricing_result.cashflow_count
                except Exception as e:
                    # Pricing failed, fall back to simplified pricing
                    print(f"Pricing failed for {deal_id}/{tranche_id}: {e}")
                    ytm = coupon_rate if coupon_kind == "FIXED" else 0.052 + margin
                    oas_bps = max(0, int((ytm - 0.045) * 10000))
                    z_spread_bps = oas_bps
                    credit_spread_bps = 25
                    duration = wam_months / 12 / 2
                    fair_value = current_balance
                    pricing_methodology = f"Simplified (pricing error: {e})"
                    cashflow_count = 0
            else:
                # Simplified pricing fallback
                if coupon_kind == "FIXED":
                    ytm = coupon_rate
                elif coupon_kind == "FLOAT":
                    ytm = 0.052 + margin
                else:
                    ytm = 0.06
                oas_bps = max(0, int((ytm - 0.045) * 10000))
                z_spread_bps = oas_bps
                credit_spread_bps = 25
                duration = wam_months / 12 / 2
                fair_value = current_balance
                pricing_methodology = "Simplified (coupon-based approximation)"
                cashflow_count = 0
            
            total_value += current_balance
            
            enriched_holdings.append({
                "deal_id": deal_id,
                "tranche_id": tranche_id,
                "token_symbol": f"{deal_id[:8]}-{tranche_id}",
                "balance": current_balance,
                "initial_balance": holding.get("initial_balance", 0),
                "factor": factor,
                "current_value": current_balance,
                "fair_value": fair_value,
                "ytm": ytm,
                "oas_bps": oas_bps,
                "z_spread_bps": z_spread_bps,
                "credit_spread_bps": credit_spread_bps,
                "duration": duration,
                "coupon_type": coupon_kind,
                "rating": rating,
                "pricing_methodology": pricing_methodology,
                "cashflow_count": cashflow_count,
                "tranche_address": holding.get("tranche_address", ""),
                "issued_at": holding.get("issued_at"),
                "last_tx_hash": holding.get("last_tx_hash"),
                "last_yield_claimed": holding.get("last_yield_claimed"),
            })
    
    # Get actual pending yield distributions (from Trustee distributions)
    pending_distributions = _get_pending_yield_distributions(holder_address)
    
    # Convert to pending yields format
    pending_yields = []
    total_pending = 0.0
    
    for dist in pending_distributions:
        amount = dist.get("amount", 0)
        if amount > 0:
            total_pending += amount
            deal_id = dist.get("deal_id", "")
            tranche_id = dist.get("tranche_id", "")
            pending_yields.append({
                "token": f"{deal_id[:8]}-{tranche_id}" if deal_id else "Unknown",
                "deal_id": deal_id,
                "tranche_id": tranche_id,
                "amount": amount,
                "period": f"Period {dist.get('period', 0)}",
                "distribution_id": dist.get("distribution_id"),
                "distributed_at": dist.get("distributed_at"),
            })
    
    # Calculate weighted average metrics
    weighted_ytm = 0.0
    weighted_duration = 0.0
    weighted_oas = 0.0
    if total_value > 0:
        for h in enriched_holdings:
            weight = h.get("current_value", 0) / total_value
            weighted_ytm += h.get("ytm", 0) * weight
            weighted_duration += h.get("duration", 0) * weight
            weighted_oas += h.get("oas_bps", 0) * weight
    
    return {
        "address": holder_address,
        "holdings": enriched_holdings,
        "total_value": total_value,
        "holding_count": len(enriched_holdings),
        "cash_balance": portfolio.get("cash_balance", 0.0),
        "pending_yields": pending_yields,
        "total_pending_yields": total_pending,
        "yield_claims_count": len(pending_yields),
        "updated_at": portfolio.get("updated_at"),
        # Portfolio-level analytics
        "weighted_ytm": weighted_ytm,
        "weighted_duration": weighted_duration,
        "weighted_oas_bps": int(weighted_oas),
        # Pricing assumptions used
        "pricing_assumptions": {
            "cpr": cpr,
            "cdr": cdr,
            "severity": severity,
            "use_full_pricing": use_full_pricing and pricing_engine_available,
            "curve_date": market_data.curve_date if market_data else None,
        },
    }


class Web3YieldClaimRequest(BaseModel):
    """Request to claim pending yields."""
    holder_address: str = Field(description="Investor wallet address")
    claim_all: bool = Field(default=True, description="Claim all pending yields")
    specific_tokens: Optional[List[str]] = Field(default=None, description="Specific token symbols to claim (if not claiming all)")


class Web3YieldClaimResponse(BaseModel):
    """Response from yield claim."""
    claim_id: str
    total_claimed: float
    new_cash_balance: float
    claims_count: int
    transaction_hash: str


@app.post("/web3/portfolio/{holder_address}/claim-yields", response_model=Web3YieldClaimResponse, tags=["Web3", "Investor"])
async def web3_claim_yields(
    holder_address: str,
    payload: Web3YieldClaimRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Web3YieldClaimResponse:
    """
    Claim pending yield distributions for an investor.
    
    This endpoint processes yield claims and adds the amount to the investor's cash balance.
    Yields must first be distributed by the Trustee via the /web3/yield/distribute endpoint.
    """
    # Get pending yield distributions
    pending = _get_pending_yield_distributions(holder_address)
    
    if not pending:
        raise HTTPException(400, "No pending yields to claim. The Trustee must distribute yields first.")
    
    # Filter by specific tokens if requested
    if payload.specific_tokens:
        pending = [
            d for d in pending 
            if f"{d.get('deal_id', '')[:8]}-{d.get('tranche_id', '')}" in payload.specific_tokens
        ]
    
    if not pending:
        raise HTTPException(400, "No pending yields for the specified tokens.")
    
    # Claim the distributions
    distribution_ids = [d.get("distribution_id") for d in pending]
    claim_result = _claim_yield_distributions(holder_address, distribution_ids)
    
    if claim_result["status"] != "success":
        raise HTTPException(500, f"Failed to claim yields: {claim_result.get('message', 'Unknown error')}")
    
    total_claimed = claim_result["claimed_amount"]
    claims_count = claim_result["claimed_count"]
    
    # Generate mock transaction hash
    tx_data = f"claim_yields_{holder_address}_{total_claimed}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the claim
    _log_audit_event({
        "event_type": "yield_claimed",
        "role": "investor",
        "holder_address": holder_address,
        "total_claimed": total_claimed,
        "claims_count": claims_count,
        "tx_hash": tx_hash,
    })
    
    return Web3YieldClaimResponse(
        claim_id=f"CLAIM_{_utc_now_iso().replace(':', '').replace('-', '')}",
        total_claimed=total_claimed,
        new_cash_balance=claim_result["new_balance"],
        claims_count=claims_count,
        transaction_hash=tx_hash
    )


@app.get("/web3/portfolio/{holder_address}/cash", response_model=Dict[str, Any], tags=["Web3", "Investor"])
async def web3_get_cash_balance(
    holder_address: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor", "arranger", "auditor", "issuer", "trustee"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get cash balance for an investor.
    """
    balance = _get_holder_cash_balance(holder_address)
    return {
        "address": holder_address,
        "cash_balance": balance,
    }


class Web3DepositCashRequest(BaseModel):
    """Request to deposit cash."""
    amount: float = Field(description="Amount to deposit", gt=0)


class Web3DepositCashResponse(BaseModel):
    """Response from cash deposit."""
    previous_balance: float
    deposited_amount: float
    new_balance: float
    transaction_hash: str


@app.post("/web3/portfolio/{holder_address}/deposit", response_model=Web3DepositCashResponse, tags=["Web3", "Investor"])
async def web3_deposit_cash(
    holder_address: str,
    payload: Web3DepositCashRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Web3DepositCashResponse:
    """
    Deposit cash into an investor's account.
    
    In production, this would interact with a stablecoin contract (USDC, USDT, etc.)
    to transfer funds from the investor's wallet to the platform.
    """
    # Get current balance
    previous_balance = _get_holder_cash_balance(holder_address)
    
    # Update balance
    new_balance = _update_holder_cash_balance(holder_address, payload.amount, operation="add")
    
    # Generate mock transaction hash
    tx_data = f"deposit_{holder_address}_{payload.amount}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the deposit
    _log_audit_event({
        "event_type": "cash_deposited",
        "role": "investor",
        "holder_address": holder_address,
        "amount": payload.amount,
        "previous_balance": previous_balance,
        "new_balance": new_balance,
        "tx_hash": tx_hash,
    })
    
    return Web3DepositCashResponse(
        previous_balance=previous_balance,
        deposited_amount=payload.amount,
        new_balance=new_balance,
        transaction_hash=tx_hash
    )


class Web3WithdrawCashRequest(BaseModel):
    """Request to withdraw cash."""
    amount: float = Field(description="Amount to withdraw", gt=0)


class Web3WithdrawCashResponse(BaseModel):
    """Response from cash withdrawal."""
    previous_balance: float
    withdrawn_amount: float
    new_balance: float
    transaction_hash: str


@app.post("/web3/portfolio/{holder_address}/withdraw", response_model=Web3WithdrawCashResponse, tags=["Web3", "Investor"])
async def web3_withdraw_cash(
    holder_address: str,
    payload: Web3WithdrawCashRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor"], x_user_role)),
) -> Web3WithdrawCashResponse:
    """
    Withdraw cash from an investor's account.
    
    In production, this would transfer stablecoins back to the investor's wallet.
    """
    # Get current balance
    previous_balance = _get_holder_cash_balance(holder_address)
    
    if payload.amount > previous_balance:
        raise HTTPException(400, f"Insufficient balance. Available: ${previous_balance:,.2f}, Requested: ${payload.amount:,.2f}")
    
    # Update balance (subtract)
    new_balance = _update_holder_cash_balance(holder_address, -payload.amount, operation="add")
    
    # Generate mock transaction hash
    tx_data = f"withdraw_{holder_address}_{payload.amount}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the withdrawal
    _log_audit_event({
        "event_type": "cash_withdrawn",
        "role": "investor",
        "holder_address": holder_address,
        "amount": payload.amount,
        "previous_balance": previous_balance,
        "new_balance": new_balance,
        "tx_hash": tx_hash,
    })
    
    return Web3WithdrawCashResponse(
        previous_balance=previous_balance,
        withdrawn_amount=payload.amount,
        new_balance=new_balance,
        transaction_hash=tx_hash
    )


@app.get("/web3/portfolio/{holder_address}/yield-history", response_model=List[Dict[str, Any]], tags=["Web3", "Investor"])
async def web3_get_yield_history(
    holder_address: str,
    limit: int = 20,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["investor", "arranger", "auditor"], x_user_role)),
) -> List[Dict[str, Any]]:
    """
    Get yield claim history for an investor.
    """
    return _get_holder_yield_history(holder_address, limit)


class Web3DistributeYieldRequest(BaseModel):
    """Request to distribute yield to tranche holders."""
    deal_id: str = Field(description="Deal identifier")
    tranche_id: str = Field(description="Tranche identifier")
    amount: float = Field(description="Total yield amount to distribute", gt=0)
    period: int = Field(description="Payment period number", ge=1)


class Web3DistributeYieldResponse(BaseModel):
    """Response from yield distribution."""
    status: str
    distribution_id: str
    deal_id: str
    tranche_id: str
    period: int
    total_amount: float
    distributed_to: int
    transaction_hash: str


@app.post("/web3/yield/distribute", response_model=Web3DistributeYieldResponse, tags=["Web3", "Trustee"])
async def web3_distribute_yield(
    payload: Web3DistributeYieldRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["trustee"], x_user_role)),
) -> Web3DistributeYieldResponse:
    """
    Distribute yield to all holders of a tranche (Trustee role).
    
    This creates pending yield distribution records for each token holder
    proportional to their holdings. Investors can then claim these yields
    via the Investor portal.
    """
    # Verify deal exists
    if payload.deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {payload.deal_id} not found")
    
    # Verify tranche exists
    deal_spec = DEALS_DB[payload.deal_id]
    bonds = deal_spec.get("bonds", [])
    tranche = next((b for b in bonds if b.get("id") == payload.tranche_id), None)
    if not tranche:
        raise HTTPException(404, f"Tranche {payload.tranche_id} not found in deal {payload.deal_id}")
    
    # Distribute yields to holders
    result = _distribute_yield_to_holders(
        deal_id=payload.deal_id,
        tranche_id=payload.tranche_id,
        total_amount=payload.amount,
        period=payload.period
    )
    
    if result["status"] == "no_holders":
        raise HTTPException(400, result["message"])
    
    # Generate mock transaction hash
    tx_data = f"distribute_yield_{payload.deal_id}_{payload.tranche_id}_{payload.amount}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the distribution
    _log_audit_event({
        "event_type": "yield_distributed",
        "role": "trustee",
        "deal_id": payload.deal_id,
        "tranche_id": payload.tranche_id,
        "period": payload.period,
        "total_amount": payload.amount,
        "distributed_to": result["distributed_to"],
        "tx_hash": tx_hash,
    })
    
    return Web3DistributeYieldResponse(
        status="success",
        distribution_id=result["distribution_id"],
        deal_id=payload.deal_id,
        tranche_id=payload.tranche_id,
        period=payload.period,
        total_amount=payload.amount,
        distributed_to=result["distributed_to"],
        transaction_hash=tx_hash
    )


@app.get("/web3/token-holders", response_model=List[Dict[str, Any]], tags=["Web3", "Issuer"])
async def web3_list_token_holders(
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["issuer", "arranger", "auditor", "trustee"], x_user_role)),
) -> List[Dict[str, Any]]:
    """
    List all registered token holders with their holdings summary.
    """
    holders = _get_all_token_holders()
    result = []
    
    for holder in holders:
        total_balance = 0
        holding_count = 0
        
        for deal_id, deal_holdings in holder.get("holdings", {}).items():
            for tranche_id, tranche_holding in deal_holdings.items():
                total_balance += tranche_holding.get("balance", 0)
                holding_count += 1
        
        result.append({
            "address": holder.get("address"),
            "total_balance": total_balance,
            "cash_balance": holder.get("cash_balance", 0.0),
            "holding_count": holding_count,
            "yield_claims_count": len(holder.get("yield_claims", [])),
            "created_at": holder.get("created_at"),
            "updated_at": holder.get("updated_at"),
        })
    
    return result


@app.post("/web3/investors/update", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_update_investor(
    payload: Web3InvestorUpdate,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    if not any(
        [
            payload.jurisdiction,
            payload.is_accredited is not None,
            payload.kyc_expiration is not None,
            payload.sanctioned is not None,
            payload.lockup_expiration is not None,
        ]
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No investor updates provided.")
    tx_hashes = client.update_investor(
        investor=payload.investor,
        jurisdiction=payload.jurisdiction,
        is_accredited=payload.is_accredited,
        kyc_expiration=payload.kyc_expiration,
        sanctioned=payload.sanctioned,
        lockup_expiration=payload.lockup_expiration,
    )
    return Web3TransactionResponse(transaction_hash=tx_hashes[-1] if tx_hashes else "")


@app.post("/web3/oracle/loan-tape", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_submit_loan_tape(
    payload: Web3LoanTapeSubmit,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    tx_hash = client.submit_loan_tape(payload.dict())
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/oracle/publish/{deal_id}/{period}", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_publish_loan_tape_from_platform(
    deal_id: str,
    period: int,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    performance_rows = PERFORMANCE_DB.get(deal_id)
    if not performance_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No performance data for deal {deal_id}.")
    aggregated = _aggregate_performance(performance_rows)
    match = next((row for row in aggregated if row.get("Period") == period), None)
    if not match:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Period {period} not found in aggregated performance for deal {deal_id}.",
        )
    loan_tape_data = {
        "deal_id": deal_id,
        "period_number": period,
        "reporting_date": int(datetime.now(timezone.utc).timestamp()),
        "scheduled_principal": int(match.get("ScheduledPrincipal", 0)),
        "scheduled_interest": int(match.get("ScheduledInterest", 0)),
        "actual_principal": int(match.get("PrincipalCollected", 0)),
        "actual_interest": int(match.get("InterestCollected", 0)),
        "prepayments": int(match.get("Prepayment", 0)),
        "curtailments": 0,
        "defaults": int(match.get("Defaults", 0)),
        "loss_severity": int(match.get("RealizedLoss", 0)),
        "recoveries": int(match.get("Recoveries", 0)),
    }
    tx_hash = client.submit_loan_tape(loan_tape_data)
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/oracle/publish/{deal_id}", response_model=Web3BatchResponse, tags=["Web3"])
async def web3_publish_loan_tape_range(
    deal_id: str,
    payload: Web3OraclePublishRange,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["servicer"], x_user_role)),
) -> Web3BatchResponse:
    if payload.end_period < payload.start_period:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_period must be >= start_period.")
    performance_rows = PERFORMANCE_DB.get(deal_id)
    if not performance_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No performance data for deal {deal_id}.")
    aggregated = _aggregate_performance(performance_rows)
    if not aggregated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No aggregated performance data for deal {deal_id}.")

    by_period = {row.get("Period"): row for row in aggregated if row.get("Period") is not None}
    client = _get_web3_client_or_503()
    tx_hashes: List[str] = []
    for period in range(payload.start_period, payload.end_period + 1):
        match = by_period.get(period)
        if not match:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Period {period} not found in aggregated performance for deal {deal_id}.",
            )
        loan_tape_data = {
            "deal_id": deal_id,
            "period_number": period,
            "reporting_date": int(datetime.now(timezone.utc).timestamp()),
            "scheduled_principal": int(match.get("ScheduledPrincipal", 0)),
            "scheduled_interest": int(match.get("ScheduledInterest", 0)),
            "actual_principal": int(match.get("PrincipalCollected", 0)),
            "actual_interest": int(match.get("InterestCollected", 0)),
            "prepayments": int(match.get("Prepayment", 0)),
            "curtailments": 0,
            "defaults": int(match.get("Defaults", 0)),
            "loss_severity": int(match.get("RealizedLoss", 0)),
            "recoveries": int(match.get("Recoveries", 0)),
        }
        tx_hashes.append(client.submit_loan_tape(loan_tape_data))

    return Web3BatchResponse(transactions=tx_hashes, count=len(tx_hashes))


@app.post("/web3/waterfall/configure", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_configure_waterfall(
    payload: Web3WaterfallConfig,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3TransactionResponse:
    client = _get_web3_client_or_503()
    tx_hash = client.configure_waterfall(payload.dict())
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/waterfall/publish/{deal_id}", response_model=Web3TransactionResponse, tags=["Web3"])
async def web3_publish_waterfall_from_deal(
    deal_id: str,
    payload: Web3WaterfallPublishRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3TransactionResponse:
    spec = _get_deal_spec_or_404(deal_id)
    config = _build_waterfall_payload_from_spec(
        deal_id,
        spec,
        payload,
        payload.tranches,
    )
    client = _get_web3_client_or_503()
    tx_hash = client.configure_waterfall(config.dict())
    return Web3TransactionResponse(transaction_hash=tx_hash)


@app.post("/web3/deals/{deal_id}/publish", response_model=Dict[str, Any], tags=["Web3"])
async def web3_publish_full_deal(
    deal_id: str,
    payload: Web3PublishDealRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Dict[str, Any]:
    spec = _get_deal_spec_or_404(deal_id)
    client = _get_web3_client_or_503()

    register_tx = client.register_deal(
        deal_id=deal_id,
        deal_name=payload.deal_name,
        arranger=payload.arranger,
        closing_date=payload.closing_date,
        maturity_date=payload.maturity_date,
    )

    tranche_payload = Web3TranchePublishRequest(
        payment_token=payload.payment_token,
        transfer_validator=payload.transfer_validator,
        admin=payload.admin,
        issuer=payload.issuer,
        trustee=payload.trustee,
        payment_frequency=payload.payment_frequency,
        maturity_date=payload.maturity_date,
        tranche_ids=payload.tranche_ids,
    )
    tranche_params = _build_tranche_params_from_spec(deal_id, spec, tranche_payload)
    tranche_txs: List[str] = []
    for params in tranche_params:
        tranche_txs.append(client.deploy_tranche(params))

    tranche_addresses = payload.tranche_addresses or _get_tranche_registry(deal_id)
    waterfall_tx = None
    if tranche_addresses:
        waterfall_payload = Web3WaterfallPublishRequest(
            payment_token=payload.payment_token,
            tranches=tranche_addresses,
            trustee_address=payload.trustee_address,
            servicer_address=payload.servicer_address,
            trustee_fees_bps=payload.trustee_fees_bps,
            servicer_fees_bps=payload.servicer_fees_bps,
            principal_sequential=payload.principal_sequential,
        )
        config = _build_waterfall_payload_from_spec(
            deal_id,
            spec,
            waterfall_payload,
            tranche_addresses,
        )
        waterfall_tx = client.configure_waterfall(config.dict())

    return {
        "deal_id": deal_id,
        "register_tx": register_tx,
        "tranche_txs": tranche_txs,
        "waterfall_tx": waterfall_tx,
        "tranche_addresses_used": tranche_addresses,
    }


@app.post("/web3/waterfall/execute", response_model=Web3TransactionResponse, tags=["Web3", "Trustee"])
async def web3_execute_waterfall(
    payload: Web3WaterfallExecute,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["trustee"], x_user_role)),
) -> Web3TransactionResponse:
    """
    Execute waterfall distribution for a payment period (Trustee role).
    
    This processes cashflows according to the deal's waterfall structure,
    distributing principal and interest to tranche holders in priority order.
    """
    # Verify deal exists
    if payload.deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {payload.deal_id} not found")
    
    # Try to use real Web3 client, fallback to mock
    try:
        client = _get_web3_client_or_503()
        tx_hash = client.execute_waterfall(payload.deal_id, payload.period_number)
    except Exception:
        # Mock execution when Web3 client not available
        tx_data = f"waterfall_{payload.deal_id}_{payload.period_number}_{_utc_now_iso()}"
        tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the execution
    _log_audit_event({
        "event_type": "waterfall_executed",
        "role": "trustee",
        "deal_id": payload.deal_id,
        "period_number": payload.period_number,
        "tx_hash": tx_hash,
    })
    
    return Web3TransactionResponse(transaction_hash=tx_hash)


# --- ARRANGER ENDPOINTS: LOAN NFT MINTING ---

@app.get("/distributions/{deal_id}", tags=["Trustee", "Investor"])
async def get_distribution_periods(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["trustee", "investor", "servicer", "arranger"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get all distribution periods for a deal.
    
    Returns the history of monthly distribution cycles including:
    - Collections from servicer
    - Waterfall distributions by trustee
    - Token balance updates
    """
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    try:
        from engine.distribution_cycle import get_distribution_manager
        dist_manager = get_distribution_manager(WEB3_SYNC_DIR)
        periods = dist_manager.get_all_periods(deal_id)
        
        return {
            "deal_id": deal_id,
            "periods": [p.to_dict() for p in periods],
            "total_periods": len(periods),
            "pending_count": sum(1 for p in periods if p.status.value == "pending"),
            "distributed_count": sum(1 for p in periods if p.status.value == "distributed"),
        }
    except Exception as e:
        return {
            "deal_id": deal_id,
            "periods": [],
            "total_periods": 0,
            "error": str(e),
        }


@app.get("/distributions/{deal_id}/pending", tags=["Trustee"])
async def get_pending_distributions(
    deal_id: str,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["trustee"], x_user_role)),
) -> Dict[str, Any]:
    """
    Get pending distribution periods awaiting trustee action.
    
    The trustee should execute waterfall for each pending period
    to distribute collections to token holders.
    """
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    try:
        from engine.distribution_cycle import get_distribution_manager
        dist_manager = get_distribution_manager(WEB3_SYNC_DIR)
        pending = dist_manager.get_pending_periods(deal_id)
        
        return {
            "deal_id": deal_id,
            "pending_periods": [p.to_dict() for p in pending],
            "count": len(pending),
            "message": f"{len(pending)} period(s) awaiting waterfall execution" if pending else "No pending distributions",
        }
    except Exception as e:
        return {
            "deal_id": deal_id,
            "pending_periods": [],
            "count": 0,
            "error": str(e),
        }


@app.post("/web3/waterfall/execute-distribution", tags=["Trustee"])
async def execute_waterfall_distribution(
    payload: Web3WaterfallExecute,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["trustee"], x_user_role)),
) -> Dict[str, Any]:
    """
    Execute waterfall and distribute to token holders (Trustee role).
    
    This is the complete distribution cycle endpoint that:
    1. Retrieves the pending distribution period from servicer upload
    2. Runs the waterfall engine with actual collections
    3. Updates token balances based on principal payments and losses
    4. Creates yield distributions for token holders to claim
    
    **Industry Flow**: This should be called after servicer uploads monthly tape.
    """
    deal_id = payload.deal_id
    period_number = payload.period_number
    
    # Verify deal exists
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    deal_spec = DEALS_DB[deal_id]
    bonds = deal_spec.get("bonds", [])
    
    # Get distribution manager
    from engine.distribution_cycle import get_distribution_manager, DistributionStatus
    dist_manager = get_distribution_manager(WEB3_SYNC_DIR)
    
    # Get the pending distribution period
    dist_period = dist_manager.get_period(deal_id, period_number)
    if not dist_period:
        raise HTTPException(404, f"No distribution period {period_number} found. Servicer must upload tape first.")
    
    # Check if already processed (allow force reprocess for testing)
    if dist_period.status not in [DistributionStatus.PENDING, DistributionStatus.PROCESSING]:
        if not payload.force_reprocess:
            raise HTTPException(400, f"Period {period_number} already processed (status: {dist_period.status.value}). "
                               f"Use force_reprocess=true to re-process for testing.")
        else:
            # Reset the period status for re-processing
            print(f"INFO: Force re-processing period {period_number} for deal {deal_id}")
    
    # Get token holders registry
    registry = _load_token_holders_registry()
    holders = registry.get("holders", {})
    
    # Get tranche registry to find who holds what
    tranche_registry = _get_tranche_registry(deal_id)
    
    # Calculate distributions based on collections
    interest_available = dist_period.interest_collected
    principal_available = dist_period.principal_collected
    losses_to_allocate = dist_period.losses
    
    # Build waterfall results
    bond_cashflows = {}
    beginning_balances = {}
    ending_balances = {}
    original_balances = {}
    losses_allocated = {}
    
    # Sort bonds by priority (senior first), using bond ID as tiebreaker
    # Priority can be a dict with 'interest' and 'principal' keys, or a simple int
    def get_priority(bond: Dict[str, Any]) -> int:
        priority = bond.get("priority")
        if priority is None:
            return 999
        if isinstance(priority, dict):
            # Use interest priority for waterfall order (or principal if not present)
            return priority.get("interest", priority.get("principal", 999))
        return int(priority)
    
    sorted_bonds = sorted(bonds, key=lambda b: (get_priority(b), b.get("id", "")))
    
    # Interest waterfall (pay senior first)
    remaining_interest = interest_available
    for bond in sorted_bonds:
        bond_id = bond.get("id", "")
        orig_bal = bond.get("original_balance", 0)
        original_balances[bond_id] = orig_bal
        
        # Get TOTAL current balance across ALL token holders for this tranche
        total_tranche_bal = 0.0
        for holder_data in holders.values():
            holdings = holder_data.get("holdings", {}).get(deal_id, {})
            if bond_id in holdings:
                total_tranche_bal += holdings[bond_id].get("balance", 0)
        
        # Use original balance if no tokens have been issued yet
        if total_tranche_bal == 0:
            total_tranche_bal = orig_bal
        
        beginning_balances[bond_id] = total_tranche_bal
        
        # Calculate interest due
        coupon = bond.get("coupon", {})
        coupon_kind = coupon.get("kind", "FIXED")
        if coupon_kind == "FIXED":
            rate = coupon.get("fixed_rate", 0.05)
        elif coupon_kind == "FLOAT":
            rate = 0.052 + coupon.get("margin", 0.0175)  # SOFR + margin
        elif coupon_kind == "WAC":
            rate = 0.055  # Estimate
        else:
            rate = 0.05
        
        interest_due = total_tranche_bal * rate / 12  # Monthly
        interest_paid = min(interest_due, remaining_interest)
        remaining_interest -= interest_paid
        
        bond_cashflows[bond_id] = {
            "interest_due": interest_due,
            "interest_paid": interest_paid,
            "principal_due": 0,
            "principal_paid": 0,
        }
    
    # Principal waterfall (sequential - pay senior until retired)
    remaining_principal = principal_available
    for bond in sorted_bonds:
        bond_id = bond.get("id", "")
        current_bal = beginning_balances.get(bond_id, 0)
        
        # Principal paid is min of available and balance
        principal_paid = min(remaining_principal, current_bal)
        remaining_principal -= principal_paid
        
        bond_cashflows[bond_id]["principal_due"] = principal_paid  # In sequential, due = paid
        bond_cashflows[bond_id]["principal_paid"] = principal_paid
        
        # Update ending balance
        ending_balances[bond_id] = current_bal - principal_paid
    
    # Loss allocation (reverse priority - junior absorbs first)
    remaining_losses = losses_to_allocate
    for bond in reversed(sorted_bonds):
        bond_id = bond.get("id", "")
        current_bal = ending_balances.get(bond_id, 0)
        
        # Losses reduce balance
        loss_to_allocate = min(remaining_losses, current_bal)
        remaining_losses -= loss_to_allocate
        
        losses_allocated[bond_id] = loss_to_allocate
        ending_balances[bond_id] = current_bal - loss_to_allocate
    
    # Calculate excess spread
    excess_spread = remaining_interest + remaining_principal
    
    # Build waterfall results
    waterfall_results = {
        "bond_cashflows": bond_cashflows,
        "losses_allocated": losses_allocated,
        "beginning_balances": beginning_balances,
        "ending_balances": ending_balances,
        "original_balances": original_balances,
        "reserve_deposit": 0,  # Could add reserve logic
        "excess_spread": excess_spread,
    }
    
    # Process distribution through manager
    updated_period, tranche_dists = dist_manager.execute_waterfall_distribution(
        deal_id=deal_id,
        period_number=period_number,
        waterfall_results=waterfall_results,
        processed_by="trustee",
    )
    
    # Update token holder balances
    token_updates = []
    # Track total interest per tranche (for yield distribution, aggregate at tranche level)
    tranche_interest_totals: Dict[str, float] = {}
    
    for holder_address, holder_data in holders.items():
        holdings = holder_data.get("holdings", {}).get(deal_id, {})
        
        for tranche_id, holding in holdings.items():
            if tranche_id in tranche_dists:
                dist = tranche_dists[tranche_id]
                old_balance = holding.get("balance", 0)
                
                # Calculate holder's share (pro-rata if multiple holders)
                total_tranche_balance = sum(
                    h.get("holdings", {}).get(deal_id, {}).get(tranche_id, {}).get("balance", 0)
                    for h in holders.values()
                )
                
                if total_tranche_balance > 0:
                    share = old_balance / total_tranche_balance
                else:
                    share = 1.0
                
                # Principal reduction
                principal_reduction = dist.principal_paid * share
                
                # Loss reduction
                loss_reduction = dist.loss_allocation * share
                
                # New balance
                new_balance = max(0, old_balance - principal_reduction - loss_reduction)
                
                # Interest yield (for logging only - distribution happens at tranche level)
                interest_yield = dist.interest_paid * share
                
                # Update holding balance
                holding["balance"] = new_balance
                holding["updated_at"] = _utc_now_iso()
                
                token_updates.append({
                    "holder": holder_address,
                    "tranche_id": tranche_id,
                    "old_balance": old_balance,
                    "new_balance": new_balance,
                    "principal_paid": principal_reduction,
                    "loss_allocated": loss_reduction,
                    "interest_earned": interest_yield,
                })
                
                # Track total interest per tranche (use tranche-level total, only add once)
                if tranche_id not in tranche_interest_totals:
                    tranche_interest_totals[tranche_id] = dist.interest_paid
    
    # IMPORTANT: Save balance updates FIRST (before yield distributions reload the registry)
    _save_token_holders_registry(registry)
    
    # Now create yield distributions - ONE call per tranche with total interest
    for tranche_id, total_interest in tranche_interest_totals.items():
        if total_interest > 0:
            _distribute_yield_to_holders(
                deal_id=deal_id,
                tranche_id=tranche_id,
                total_amount=total_interest,
                period=period_number,
            )
    
    # Generate transaction hash
    tx_data = f"distribution_{deal_id}_{period_number}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Log the execution
    _log_audit_event({
        "event_type": "distribution_executed",
        "role": "trustee",
        "deal_id": deal_id,
        "period_number": period_number,
        "total_interest": updated_period.total_interest_distributed,
        "total_principal": updated_period.total_principal_distributed,
        "token_updates": len(token_updates),
        "tx_hash": tx_hash,
    })
    
    return {
        "transaction_hash": tx_hash,
        "deal_id": deal_id,
        "period_number": period_number,
        "status": "distributed",
        "collections": {
            "interest_collected": dist_period.interest_collected,
            "principal_collected": dist_period.principal_collected,
            "losses": dist_period.losses,
        },
        "distributions": {
            "total_interest_distributed": updated_period.total_interest_distributed,
            "total_principal_distributed": updated_period.total_principal_distributed,
            "excess_spread": updated_period.excess_spread,
        },
        "token_updates": token_updates,
        "message": f"Period {period_number} distributed. Token balances updated. Yields available for claim.",
    }


@app.post("/web3/deals/{deal_id}/loans/mint", response_model=Web3LoanNFTMintResponse, tags=["Arranger"])
async def mint_loan_nfts_for_deal(
    deal_id: str,
    payload: Web3LoanNFTMintRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["arranger"], x_user_role)),
) -> Web3LoanNFTMintResponse:
    """
    Mint loan NFTs for all loans in a deal (Arranger role).
    
    This endpoint reads the loan tape for a deal and mints an NFT for each loan.
    The NFTs are privacy-preserving: only loan IDs and hashes are stored on-chain.
    
    **Workflow**: Arranger packages the collateral pool and mints NFTs representing
    each loan. This happens during deal setup, before securities are issued.
    """
    # Load loan tape from datasets
    deal_folder = settings.package_root / "datasets" / deal_id
    loan_tape_path = deal_folder / "loan_tape.csv"
    
    if not loan_tape_path.exists():
        raise HTTPException(404, f"Loan tape not found for deal {deal_id}. Upload loan tape first.")
    
    # Read loan tape
    import pandas as pd
    loan_df = pd.read_csv(loan_tape_path)
    
    if loan_df.empty:
        raise HTTPException(400, "Loan tape is empty.")
    
    # Build mint params for each loan
    mint_params_list: List[Web3LoanNFTMintParams] = []
    for _, loan in loan_df.iterrows():
        # Compute data hash for loan
        loan_data_str = json.dumps({
            "LoanId": str(loan.get("LoanId", "")),
            "OriginalBalance": float(loan.get("OriginalBalance", 0)),
            "CurrentBalance": float(loan.get("CurrentBalance", 0)),
            "NoteRate": float(loan.get("NoteRate", 0)),
        }, sort_keys=True)
        data_hash = hashlib.sha256(loan_data_str.encode()).hexdigest()
        
        # Convert dates to timestamps if available
        orig_date = loan.get("FIRST_PAYMENT_DATE", "2024-01-01")
        if isinstance(orig_date, str):
            from datetime import datetime
            try:
                orig_timestamp = int(datetime.fromisoformat(orig_date.replace("Z", "+00:00")).timestamp())
            except:
                orig_timestamp = 1704067200  # Default: 2024-01-01
        else:
            orig_timestamp = 1704067200
        
        # Maturity is typically 30 years from origination for mortgages
        maturity_timestamp = orig_timestamp + (30 * 365 * 24 * 60 * 60)
        
        mint_params = Web3LoanNFTMintParams(
            deal_id=deal_id,
            loan_id=str(loan.get("LoanId", "")),
            original_balance=int(float(loan.get("OriginalBalance", 0)) * 100),  # Convert to cents
            current_balance=int(float(loan.get("CurrentBalance", 0)) * 100),
            note_rate=int(float(loan.get("NoteRate", 0)) * 10000),  # Convert to bps
            origination_date=orig_timestamp,
            maturity_date=maturity_timestamp,
            data_hash=data_hash,
            metadata_uri=f"ipfs://QmLoanMetadata/{deal_id}/{loan.get('LoanId', '')}"  # Placeholder
        )
        mint_params_list.append(mint_params)
    
    # Generate token IDs (sequential starting from 1)
    token_ids = list(range(1, len(mint_params_list) + 1))
    
    # Build loan_id -> token_id mapping
    loan_token_mapping: Dict[str, int] = {}
    for i, params in enumerate(mint_params_list):
        loan_token_mapping[params.loan_id] = token_ids[i]
    
    # Helper to convert Unix timestamp to ISO date string
    def _timestamp_to_date(ts: int) -> str:
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return "N/A"
    
    # Build comprehensive NFT records (mirrors on-chain LoanMetadata struct)
    loan_nft_records: Dict[str, Dict[str, Any]] = {}
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    for i, params in enumerate(mint_params_list):
        token_id = token_ids[i]
        loan_nft_records[str(token_id)] = {
            "token_id": token_id,
            "deal_id": params.deal_id,
            "loan_id": params.loan_id,
            "original_balance": params.original_balance / 100,  # Convert cents to dollars
            "current_balance": params.current_balance / 100,    # Convert cents to dollars
            "note_rate_percent": params.note_rate / 100,        # Convert bps to percent
            "origination_date": _timestamp_to_date(params.origination_date),
            "maturity_date": _timestamp_to_date(params.maturity_date),
            "status": "CURRENT",
            "status_code": 0,
            "data_hash": params.data_hash,
            "metadata_uri": params.metadata_uri,
            "minted_at": now_iso,
            "last_updated": now_iso,
            "recipient": payload.recipient_address,
            "contract": payload.loan_nft_contract,
        }
    
    # Save the simple mapping file
    mapping_path = deal_folder / "loan_token_mapping.json"
    try:
        with open(mapping_path, "w") as f:
            json.dump(loan_token_mapping, f, indent=2)
        print(f"Saved loan_token_mapping.json for deal {deal_id} ({len(loan_token_mapping)} loans)")
    except Exception as e:
        print(f"Warning: Failed to save loan_token_mapping.json: {e}")
    
    # Save the comprehensive NFT records file
    records_path = deal_folder / "loan_nft_records.json"
    try:
        with open(records_path, "w") as f:
            json.dump({
                "deal_id": deal_id,
                "contract_address": payload.loan_nft_contract,
                "recipient": payload.recipient_address,
                "minted_at": datetime.now(timezone.utc).isoformat(),
                "total_loans": len(loan_nft_records),
                "status_enum": {
                    "CURRENT": 0,
                    "DELINQUENT_30": 1,
                    "DELINQUENT_60": 2,
                    "DELINQUENT_90": 3,
                    "DEFAULT": 4,
                    "PAID_OFF": 5,
                    "PREPAID": 6,
                },
                "loans": loan_nft_records,
            }, f, indent=2)
        print(f"Saved loan_nft_records.json for deal {deal_id} ({len(loan_nft_records)} NFTs)")
    except Exception as e:
        print(f"Warning: Failed to save loan_nft_records.json: {e}")
    
    # Log audit event
    _log_audit_event(
        "web3.loan_nft_mint",
        deal_id=deal_id,
        details={
            "loan_count": len(mint_params_list),
            "recipient": payload.recipient_address,
            "contract": payload.loan_nft_contract,
            "mapping_file": str(mapping_path),
        },
    )
    
    # Call Web3 client to mint if enabled (otherwise return mock response)
    tx_hash = "0x" + hashlib.sha256(f"mint_loans_{deal_id}".encode()).hexdigest()
    
    if settings.web3_enabled and payload.loan_nft_contract:
        try:
            from web3_integration.web3_client import get_web3_client
            web3_client = get_web3_client()
            # In a real implementation, this would call the batch mint function
            # tx_hash = web3_client.mint_loan_nfts_batch(...)
            print(f"Web3 enabled: would mint {len(mint_params_list)} loan NFTs to {payload.recipient_address}")
        except Exception as e:
            print(f"Warning: Web3 minting skipped: {e}")
    
    return Web3LoanNFTMintResponse(
        transaction_hash=tx_hash,
        token_ids=token_ids,
        count=len(mint_params_list),
        status="submitted"
    )


# --- ISSUER ENDPOINTS: TRANCHE DEPLOYMENT AND TOKEN ISSUANCE ---

class Web3DeployTranchesRequest(BaseModel):
    """Request to deploy tranche contracts on-chain."""
    payment_token: str = Field(default="0x0000000000000000000000000000000000000000", description="Payment token address (stablecoin)")
    admin: str = Field(default="0x0000000000000000000000000000000000000001", description="Admin/issuer address")


class Web3DeployTranchesResponse(BaseModel):
    """Response after deploying tranche contracts."""
    deal_id: str
    tranches: Dict[str, str] = Field(description="Mapping of tranche_id -> contract_address")
    transaction_hashes: List[str]
    count: int


@app.post("/web3/deals/{deal_id}/tranches/deploy", response_model=Web3DeployTranchesResponse, tags=["Issuer"])
async def deploy_tranche_contracts(
    deal_id: str,
    payload: Web3DeployTranchesRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["issuer"], x_user_role)),
) -> Web3DeployTranchesResponse:
    """
    Deploy tranche contracts for a deal (Issuer role).
    
    This endpoint deploys ERC-1400 security token contracts for each tranche
    defined in the deal structure. Must be called before issuing tokens.
    
    **Workflow**:
    1. Arranger uploads deal spec with tranche definitions
    2. Issuer deploys tranche contracts (this endpoint)
    3. Issuer issues tokens to investors
    """
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    deal_spec = DEALS_DB[deal_id]
    bonds = deal_spec.get("bonds", [])
    
    if not bonds:
        raise HTTPException(400, f"Deal {deal_id} has no tranches defined.")
    
    # Check if already deployed
    existing_registry = _get_tranche_registry(deal_id)
    if existing_registry:
        raise HTTPException(400, f"Tranches already deployed for {deal_id}. Registry: {list(existing_registry.keys())}")
    
    # Deploy mock contracts for each tranche
    tranche_addresses: Dict[str, str] = {}
    tx_hashes: List[str] = []
    
    for bond in bonds:
        bond_id = bond.get("id")
        original_balance = int(bond.get("original_balance", 0))
        
        # Generate mock contract address
        addr_data = f"tranche_{deal_id}_{bond_id}"
        mock_address = "0x" + hashlib.sha256(addr_data.encode()).hexdigest()[:40]
        tranche_addresses[bond_id] = mock_address
        
        # Generate mock tx hash
        tx_data = f"deploy_{deal_id}_{bond_id}_{original_balance}"
        tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
        tx_hashes.append(tx_hash)
    
    # Save to registry
    _update_tranche_registry(deal_id, tranche_addresses)
    
    _log_audit_event("issuer.tranches.deploy", deal_id=deal_id, details={
        "tranche_count": len(tranche_addresses),
        "tranches": list(tranche_addresses.keys()),
    })
    
    return Web3DeployTranchesResponse(
        deal_id=deal_id,
        tranches=tranche_addresses,
        transaction_hashes=tx_hashes,
        count=len(tranche_addresses)
    )


@app.post("/web3/deals/{deal_id}/tranches/{tranche_id}/tokens/issue", response_model=Web3TransactionResponse, tags=["Issuer"])
async def issue_tranche_tokens(
    deal_id: str,
    tranche_id: str,
    payload: Web3TrancheTokenMintRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["issuer"], x_user_role)),
) -> Web3TransactionResponse:
    """
    Issue tranche tokens to investors.
    
    This endpoint mints ERC-1400 security tokens for a tranche and distributes them
    to the specified token holders based on the deal structure.
    """
    if len(payload.token_holders) != len(payload.token_amounts):
        raise HTTPException(400, "token_holders and token_amounts must have the same length.")
    
    # Get tranche address from registry
    tranche_addresses = _get_tranche_registry(deal_id)
    if tranche_id not in tranche_addresses:
        raise HTTPException(404, f"Tranche {tranche_id} not found in registry for deal {deal_id}.")
    
    tranche_address = tranche_addresses[tranche_id]
    
    # In a real implementation, this would call the RMBSTranche.issue() function
    # for each holder with their allocation
    # For now, return a mock transaction
    
    total_issued = sum(payload.token_amounts)
    tx_data = f"issue_tokens_{deal_id}_{tranche_id}_{total_issued}_{_utc_now_iso()}"
    tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
    
    # Record token issuance for each holder
    for holder, amount in zip(payload.token_holders, payload.token_amounts):
        if amount > 0:
            _record_token_issuance(
                deal_id=deal_id,
                tranche_id=tranche_id,
                holder_address=holder,
                amount=amount,
                tranche_address=tranche_address,
                tx_hash=tx_hash
            )
    
    # Log the issuance
    _log_audit_event({
        "event_type": "tranche_tokens_issued",
        "role": "issuer",
        "deal_id": deal_id,
        "tranche_id": tranche_id,
        "tranche_address": tranche_address,
        "total_amount": total_issued,
        "holder_count": len(payload.token_holders),
    })
    
    return Web3TransactionResponse(transaction_hash=tx_hash)


class Web3IssueAllTranchesRequest(BaseModel):
    """Request to issue tokens for all tranches at deal closing."""
    token_holders: List[str] = Field(description="List of investor addresses")
    token_allocations: Optional[Dict[str, List[int]]] = Field(
        default=None,
        description="Optional dict mapping tranche_id to amounts per holder"
    )


@app.post("/web3/deals/{deal_id}/tranches/issue-all", response_model=Web3BatchResponse, tags=["Issuer"])
async def issue_all_tranche_tokens(
    deal_id: str,
    payload: Web3IssueAllTranchesRequest,
    _: None = Depends(lambda x_user_role=Header(default=None, alias="X-User-Role"): _require_role(["issuer"], x_user_role)),
) -> Web3BatchResponse:
    """
    Issue tokens for all tranches in a deal.
    
    This is a convenience endpoint that issues tokens for all tranches at once,
    typically used at deal closing when the initial allocation is known.
    
    Parameters:
    - token_holders: List of investor addresses
    - token_allocations: Optional dict mapping tranche_id to list of amounts per holder
      If not provided, tokens are issued based on the deal's waterfall structure.
    """
    token_holders = payload.token_holders
    token_allocations = payload.token_allocations
    
    # Get deal spec
    if deal_id not in DEALS_DB:
        raise HTTPException(404, f"Deal {deal_id} not found")
    
    deal_spec = DEALS_DB[deal_id]
    bonds = deal_spec.get("bonds", [])
    
    if not bonds:
        raise HTTPException(400, f"Deal {deal_id} has no bonds/tranches defined.")
    
    # Get tranche addresses
    tranche_addresses = _get_tranche_registry(deal_id)
    
    tx_hashes = []
    for bond in bonds:
        bond_id = bond.get("id")
        original_balance = int(bond.get("original_balance", 0))
        tranche_address = tranche_addresses.get(bond_id, "")
        
        if bond_id not in tranche_addresses:
            continue  # Skip if tranche not deployed
        
        # If allocations provided, use them; otherwise issue full balance to first holder
        if token_allocations and bond_id in token_allocations:
            amounts = token_allocations[bond_id]
        elif token_holders:
            # Default: issue full balance to first holder (simplified)
            amounts = [original_balance] + [0] * (len(token_holders) - 1)
        else:
            continue
        
        # Mock transaction
        tx_data = f"issue_all_{deal_id}_{bond_id}_{original_balance}_{_utc_now_iso()}"
        tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
        tx_hashes.append(tx_hash)
        
        # Record token issuance for each holder
        for holder, amount in zip(token_holders, amounts):
            if amount > 0:
                _record_token_issuance(
                    deal_id=deal_id,
                    tranche_id=bond_id,
                    holder_address=holder,
                    amount=amount,
                    tranche_address=tranche_address,
                    tx_hash=tx_hash
                )
        
        # Log the issuance
        _log_audit_event({
            "event_type": "tranche_tokens_issued_batch",
            "role": "issuer",
            "deal_id": deal_id,
            "tranche_id": bond_id,
            "tranche_address": tranche_address,
            "total_amount": sum(amounts),
            "holder_count": len([a for a in amounts if a > 0]),
        })
    
    return Web3BatchResponse(transactions=tx_hashes, count=len(tx_hashes))


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