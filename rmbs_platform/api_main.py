# api_main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import re
import uuid
import pandas as pd
import io
import math

# Import our engine
from engine import run_simulation

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
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", deal_id or "").strip("_")
    return safe or "deal"

def _deal_file_path(deal_id: str) -> Path:
    return DEALS_DIR / f"{_safe_deal_id(deal_id)}.json"

def _collateral_file_path(deal_id: str) -> Path:
    return COLLATERAL_DIR / f"{_safe_deal_id(deal_id)}.json"

def _performance_file_path(deal_id: str) -> Path:
    return PERFORMANCE_DIR / f"{_safe_deal_id(deal_id)}.csv"

def _load_persisted_deals() -> None:
    for path in DEALS_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                spec = json.load(f)
            deal_id = spec.get("meta", {}).get("deal_id") or path.stem
            DEALS_DB[deal_id] = spec
        except Exception:
            continue

def _load_persisted_collateral() -> None:
    for path in COLLATERAL_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                collateral = json.load(f)
            deal_id = collateral.get("deal_id") or path.stem
            COLLATERAL_DB[deal_id] = collateral.get("data", collateral)
        except Exception:
            continue

def _load_persisted_performance() -> None:
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
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    return value

def _normalize_perf_df(df: pd.DataFrame) -> pd.DataFrame:
    if "BondID" in df.columns and "BondId" not in df.columns:
        df = df.rename(columns={"BondID": "BondId"})
    if "LoanID" in df.columns and "LoanId" not in df.columns:
        df = df.rename(columns={"LoanID": "LoanId"})
    return df

def _aggregate_performance(performance_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    deal_id: str
    spec: Dict[str, Any]

class CollateralUpload(BaseModel):
    deal_id: str
    collateral: Dict[str, Any]

class SimRequest(BaseModel):
    deal_id: str
    cpr: float = 0.10
    cdr: float = 0.01
    severity: float = 0.40

# --- ENDPOINTS ---

@app.post("/deals", tags=["Arranger"])
async def upload_deal(deal: DealUpload):
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
async def upload_collateral(payload: CollateralUpload):
    """Arranger uploads initial collateral attributes."""
    COLLATERAL_DB[payload.deal_id] = payload.collateral
    path = _collateral_file_path(payload.deal_id)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"deal_id": payload.deal_id, "data": payload.collateral}, f, indent=2)
    return {"message": f"Collateral for {payload.deal_id} stored successfully."}

@app.get("/collateral/{deal_id}", tags=["Arranger", "Investor"])
async def get_collateral(deal_id: str):
    collateral = COLLATERAL_DB.get(deal_id)
    if collateral is None:
        raise HTTPException(404, "Collateral not found")
    return {"deal_id": deal_id, "collateral": collateral}

@app.post("/performance/{deal_id}", tags=["Servicer"])
async def upload_performance(deal_id: str, file: UploadFile = File(...)):
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
async def clear_performance(deal_id: str):
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
async def list_deals():
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
async def start_simulation(req: SimRequest, background_tasks: BackgroundTasks):
    """Investor requests a simulation run (Async)."""
    if req.deal_id not in DEALS_DB:
        raise HTTPException(404, "Deal ID not found")
    if req.deal_id not in COLLATERAL_DB:
        raise HTTPException(400, "Collateral not uploaded for this deal")
    
    job_id = str(uuid.uuid4())
    JOBS_DB[job_id] = {"status": "RUNNING"}
    
    # Send to background
    background_tasks.add_task(worker, job_id, req.deal_id, req.cpr, req.cdr, req.severity)
    
    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/results/{job_id}", tags=["Reporting"])
async def get_results(job_id: str):
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
            "last_actual_period": job.get("last_actual_period"),
            "warnings": job.get("warnings", [])
        }
    if job['status'] == "FAILED":
        return {"status": "FAILED", "error": job.get("error", "Unknown error")}
    return {"status": job['status']}

# --- WORKER ---
def worker(job_id, deal_id, cpr, cdr, sev):
    try:
        deal_json = DEALS_DB[deal_id]
        collateral_json = COLLATERAL_DB.get(deal_id, deal_json.get("collateral", {}))
        performance_rows = PERFORMANCE_DB.get(deal_id, [])
        df, reconciliation = run_simulation(deal_json, collateral_json, performance_rows, cpr, cdr, sev)

        actuals_data = _aggregate_performance(performance_rows)
        last_actual_period = _latest_actual_period(actuals_data)

        warnings: List[Dict[str, Any]] = []
        if actuals_data and "Var.PoolEndBalance" in df.columns:
            actuals_df = pd.DataFrame(actuals_data)
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
        actuals_data = _sanitize_json(actuals_data)
        warnings = _sanitize_json(warnings)

        # Store result as JSON compatible list
        JOBS_DB[job_id] = {
            "status": "COMPLETED",
            "data": data_records,
            "reconciliation": reconciliation,
            "actuals_data": actuals_data,
            "last_actual_period": last_actual_period,
            "warnings": warnings
        }
    except Exception as e:
        JOBS_DB[job_id] = {"status": "FAILED", "error": str(e)}