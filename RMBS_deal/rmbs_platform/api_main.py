# api_main.py
"""FastAPI service for uploading deals, running simulations, and viewing results."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import re
import uuid
import pandas as pd
import io
import math

# Import our engine
try:
    from .engine import run_simulation
except ImportError:  # Fallback for running as a script
    from rmbs_platform.engine import run_simulation

app = FastAPI(title="RMBS Engine API", version="1.0")

# --- DATABASE (In-Memory for Demo) ---
DEALS_DB = {}   # Stores JSON structures
JOBS_DB = {}    # Stores simulation results
COLLATERAL_DB = {}  # Stores initial collateral attributes
PERFORMANCE_DB = {}  # Stores servicer performance rows

# --- PERSISTENT STORAGE ---
DEALS_DIR = Path(__file__).resolve().parent / "deals"
DEALS_DIR.mkdir(parents=True, exist_ok=True)
COLLATERAL_DIR = Path(__file__).resolve().parent / "collateral"
COLLATERAL_DIR.mkdir(parents=True, exist_ok=True)
PERFORMANCE_DIR = Path(__file__).resolve().parent / "performance"
PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)

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

_load_persisted_deals()
_load_persisted_collateral()
_load_persisted_performance()

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
    """Normalize performance tape column names."""
    if "BondID" in df.columns and "BondId" not in df.columns:
        df = df.rename(columns={"BondID": "BondId"})
    if "LoanID" in df.columns and "LoanId" not in df.columns:
        df = df.rename(columns={"LoanID": "LoanId"})
    return df

def _aggregate_performance(performance_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate loan-level or pool-level performance into period totals."""
    if not performance_rows:
        return []
    df = pd.DataFrame(performance_rows)
    if df.empty or "Period" not in df.columns:
        return []
    df = _normalize_perf_df(df)

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
    numeric_cols = [c for c in numeric_candidates if c in df.columns]
    for col in numeric_candidates:
        if col not in df.columns:
            df[col] = 0.0
    numeric_cols = list(numeric_candidates)

    if "LoanId" in df.columns:
        loan_df = df[df["LoanId"].notna()].copy()
        if loan_df.empty:
            return []
        agg = loan_df.groupby("Period", as_index=False)[numeric_cols].sum(numeric_only=True)
        if "PoolStatus" in loan_df.columns:
            pool_status = loan_df.groupby("Period")["PoolStatus"].last().reset_index(drop=True)
            agg["PoolStatus"] = pool_status
        return agg.to_dict(orient="records")

    agg = df.groupby("Period", as_index=False)[numeric_cols].sum(numeric_only=True)
    if "PoolStatus" in df.columns:
        pool_status = df.groupby("Period")["PoolStatus"].last().reset_index(drop=True)
        agg["PoolStatus"] = pool_status
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
    """Payload for uploading a deal structure."""
    deal_id: str
    spec: Dict[str, Any]

class CollateralUpload(BaseModel):
    """Payload for uploading initial collateral attributes."""
    deal_id: str
    collateral: Dict[str, Any]

class SimRequest(BaseModel):
    """Simulation request with modeling assumptions and ML overrides."""
    deal_id: str
    cpr: float = 0.10
    cdr: float = 0.01
    severity: float = 0.40
    use_ml_models: bool = False
    prepay_model_key: Optional[str] = None
    default_model_key: Optional[str] = None
    rate_scenario: Optional[str] = None
    start_rate: Optional[float] = None
    rate_sensitivity: Optional[float] = None
    feature_source: Optional[str] = None
    origination_source_uri: Optional[str] = None

# --- ENDPOINTS ---

@app.post("/deals", tags=["Arranger"])
async def upload_deal(deal: DealUpload) -> Dict[str, Any]:
    """Arranger uploads a new deal structure."""
    if "meta" not in deal.spec:
        deal.spec["meta"] = {}
    deal.spec["meta"]["deal_id"] = deal.deal_id
    deal.spec.pop("collateral", None)
    DEALS_DB[deal.deal_id] = deal.spec
    path = _deal_file_path(deal.deal_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump(deal.spec, f, indent=2)
    return {"message": f"Deal {deal.deal_id} stored successfully."}

@app.post("/collateral", tags=["Arranger"])
async def upload_collateral(payload: CollateralUpload) -> Dict[str, Any]:
    """Arranger uploads initial collateral attributes."""
    COLLATERAL_DB[payload.deal_id] = payload.collateral
    path = _collateral_file_path(payload.deal_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"deal_id": payload.deal_id, "data": payload.collateral}, f, indent=2)
    return {"message": f"Collateral for {payload.deal_id} stored successfully."}

@app.get("/collateral/{deal_id}", tags=["Arranger", "Investor"])
async def get_collateral(deal_id: str) -> Dict[str, Any]:
    collateral = COLLATERAL_DB.get(deal_id)
    if collateral is None:
        raise HTTPException(404, "Collateral not found")
    return {"deal_id": deal_id, "collateral": collateral}

@app.post("/performance/{deal_id}", tags=["Servicer"])
async def upload_performance(deal_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    """Servicer uploads monthly performance tape as CSV."""
    try:
        content = await file.read()
        df_new = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Invalid CSV: {e}")

    if "Period" not in df_new.columns:
        raise HTTPException(400, "CSV must include a Period column.")

    df_new = _normalize_perf_df(df_new)

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

    latest_period = int(df_all["Period"].max()) if not df_all.empty else None
    return {"message": f"Performance for {deal_id} stored successfully.",
            "rows": int(len(df_all)),
            "latest_period": latest_period}

@app.delete("/performance/{deal_id}", tags=["Servicer"])
async def clear_performance(deal_id: str) -> Dict[str, Any]:
    """Clear all stored performance rows for a deal."""
    PERFORMANCE_DB.pop(deal_id, None)
    path = _performance_file_path(deal_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            raise HTTPException(500, f"Failed to delete performance file: {e}")
    return {"message": f"Performance for {deal_id} cleared."}

@app.get("/deals", tags=["Arranger", "Investor"])
async def list_deals() -> Dict[str, Any]:
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

@app.post("/simulate", tags=["Investor"])
async def start_simulation(req: SimRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
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
    JOBS_DB[job_id] = {"status": "RUNNING", "ml_overrides": ml_overrides}
    
    # Send to background
    background_tasks.add_task(worker, job_id, req.deal_id, req.cpr, req.cdr, req.severity)
    
    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/results/{job_id}", tags=["Reporting"])
async def get_results(job_id: str) -> Dict[str, Any]:
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

# --- WORKER ---
def worker(job_id: str, deal_id: str, cpr: float, cdr: float, sev: float) -> None:
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
            prepay_path = registry.get(prepay_key, {}).get("path") if prepay_key else None
            default_path = registry.get(default_key, {}).get("path") if default_key else None
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
        df, reconciliation = run_simulation(deal_json, collateral_json, performance_rows, cpr, cdr, sev)
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
            "data": data_records,
            "reconciliation": reconciliation,
            "actuals_data": actuals_report,
            "actuals_summary": actuals_summary,
            "simulated_summary": simulated_summary,
            "last_actual_period": last_actual_period,
            "warnings": warnings,
            "model_info": model_info
        }
    except Exception as e:
        JOBS_DB[job_id] = {"status": "FAILED", "error": str(e)}


@app.get("/models/registry", tags=["Models"])
async def get_model_registry() -> Dict[str, Any]:
    return {"registry": _load_model_registry()}