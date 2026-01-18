"""Core simulation entry points for the RMBS engine."""

from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
from .loader import DealLoader
from .state import DealState
from .compute import ExpressionEngine
from .waterfall import WaterfallRunner
from .reporting import ReportGenerator
from .collateral import CollateralModel

def _prepare_performance(performance_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Normalize a performance tape into a DataFrame with standard columns."""
    if not performance_rows:
        return pd.DataFrame()
    df = pd.DataFrame(performance_rows)
    if "BondID" in df.columns and "BondId" not in df.columns:
        df = df.rename(columns={"BondID": "BondId"})
    if "LoanID" in df.columns and "LoanId" not in df.columns:
        df = df.rename(columns={"LoanID": "LoanId"})
    return df


def _aggregate_loan_performance(loan_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate loan-level performance rows into pool-level totals."""
    if loan_df.empty:
        return pd.DataFrame()

    asset_cols = [c for c in ["InterestCollected", "PrincipalCollected", "RealizedLoss", "EndBalance"] if c in loan_df.columns]
    if not asset_cols:
        return pd.DataFrame()

    agg = loan_df.groupby("Period", as_index=False)[asset_cols].sum(numeric_only=True)
    if "PoolStatus" in loan_df.columns:
        pool_status = loan_df.groupby("Period")["PoolStatus"].last().reset_index(drop=True)
        agg["PoolStatus"] = pool_status
    return agg


def _aggregate_collateral(collateral_json: Dict[str, Any]) -> Dict[str, Any]:
    """Derive pool-level collateral stats from loan-level attributes."""
    loans = collateral_json.get("loans")
    if not loans:
        return collateral_json

    def _get_num(entry: Dict[str, Any], keys: List[str]) -> Optional[float]:
        """Return the first numeric field found in a loan record."""
        for key in keys:
            if key in entry and entry[key] is not None:
                try:
                    return float(entry[key])
                except (TypeError, ValueError):
                    return None
        return None

    orig_sum = 0.0
    curr_sum = 0.0
    wac_num = 0.0
    wam_num = 0.0

    for loan in loans:
        orig = _get_num(loan, ["original_balance", "OriginalBalance", "orig_balance"])
        curr = _get_num(loan, ["current_balance", "CurrentBalance", "end_balance"])
        rate = _get_num(loan, ["note_rate", "NoteRate", "coupon"])
        term = _get_num(loan, ["remaining_term_months", "RemainingTermMonths", "remaining_term"])

        if orig is not None:
            orig_sum += orig
        if curr is None and orig is not None:
            curr = orig
        if curr is not None:
            curr_sum += curr
            if rate is not None:
                wac_num += rate * curr
            if term is not None:
                wam_num += term * curr

    if curr_sum > 0:
        collateral_json = dict(collateral_json)
        collateral_json["original_balance"] = round(orig_sum, 2)
        collateral_json["current_balance"] = round(curr_sum, 2)
        if wac_num > 0:
            collateral_json["wac"] = round(wac_num / curr_sum, 6)
        if wam_num > 0:
            collateral_json["wam"] = int(round(wam_num / curr_sum))

    return collateral_json

def run_simulation(
    deal_json: Dict[str, Any],
    collateral_json: Dict[str, Any],
    performance_rows: List[Dict[str, Any]],
    cpr: float,
    cdr: float,
    severity: float,
    horizon_periods: int = 60,
    strict_balance_check: bool = True,
    apply_waterfall_to_actuals: bool = True
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Run a full deal simulation and return the detailed cashflow report."""
    # 1. Load Deal
    loader = DealLoader()
    merged_deal = dict(deal_json)
    collateral_json = _aggregate_collateral(collateral_json or {})
    merged_deal["collateral"] = collateral_json
    # We load directly from the dict passed by the API
    deal_def = loader.load_from_json(merged_deal)
    
    # 2. Init Engine
    state = DealState(deal_def)
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)
    
    # 3. Prepare Performance (Actuals)
    perf_df = _prepare_performance(performance_rows)
    asset_cols = [c for c in ["InterestCollected", "PrincipalCollected", "RealizedLoss", "EndBalance", "PoolStatus"] if c in perf_df.columns]
    df_asset = pd.DataFrame()
    if not perf_df.empty and asset_cols:
        if "LoanId" in perf_df.columns:
            loan_df = perf_df[perf_df["LoanId"].notna()].copy()
            df_asset = _aggregate_loan_performance(loan_df)
        else:
            df_asset = perf_df[["Period"] + asset_cols].copy()
            df_asset = df_asset.dropna(how="all", subset=asset_cols)
            df_asset = df_asset.groupby("Period", as_index=False).sum(numeric_only=True)

    df_bonds = pd.DataFrame()
    has_loan_level = "LoanId" in perf_df.columns and perf_df["LoanId"].notna().any()
    if not has_loan_level and not perf_df.empty and {"BondId", "BondBalance"}.issubset(perf_df.columns):
        df_bonds = perf_df[["Period", "BondId", "BondBalance"]].dropna()
        df_bonds["Period"] = df_bonds["Period"].astype(int)
        df_bonds["BondBalance"] = df_bonds["BondBalance"].astype(float)
    bond_balances_by_period = {}
    if not df_bonds.empty:
        for period, rows in df_bonds.groupby("Period"):
            bond_balances_by_period[int(period)] = {
                row["BondId"]: float(row["BondBalance"])
                for _, row in rows.iterrows()
            }

    start_date = date.today()

    reconciliation: List[Dict[str, Any]] = []

    # 4. Apply Actuals (Do not simulate the past)
    if not df_asset.empty:
        df_asset = df_asset.sort_values("Period")
        for _, row in df_asset.iterrows():
            period = int(row["Period"])
            interest_collected = float(row.get("InterestCollected", 0.0) or 0.0)
            principal_collected = float(row.get("PrincipalCollected", 0.0) or 0.0)
            realized_loss = float(row.get("RealizedLoss", 0.0) or 0.0)
            prepayment = float(row.get("Prepayment", 0.0) or 0.0)
            scheduled_principal = float(row.get("ScheduledPrincipal", 0.0) or 0.0)
            scheduled_interest = float(row.get("ScheduledInterest", 0.0) or 0.0)
            servicer_advances = float(row.get("ServicerAdvances", 0.0) or 0.0)
            recoveries = float(row.get("Recoveries", 0.0) or 0.0)
            state.deposit_funds("IAF", interest_collected)
            state.deposit_funds("PAF", principal_collected)
            state.set_variable("RealizedLoss", realized_loss)
            state.set_variable("InputInterestCollected", interest_collected)
            state.set_variable("InputPrincipalCollected", principal_collected)
            state.set_variable("InputRealizedLoss", realized_loss)
            state.set_variable("InputPrepayment", prepayment)
            state.set_variable("InputScheduledPrincipal", scheduled_principal)
            state.set_variable("InputScheduledInterest", scheduled_interest)
            state.set_variable("InputServicerAdvances", servicer_advances)
            state.set_variable("InputRecoveries", recoveries)
            if "EndBalance" in row and row.get("EndBalance") is not None:
                try:
                    end_bal = float(row.get("EndBalance"))
                except (TypeError, ValueError):
                    end_bal = None
                if end_bal is not None:
                    state.collateral["current_balance"] = end_bal
                    state.set_variable("PoolEndBalance", end_bal)
                    state.set_variable("InputEndBalance", end_bal)
            if "PoolStatus" in row and row.get("PoolStatus") is not None:
                state.set_variable("PoolStatus", str(row.get("PoolStatus")))
            state.set_variable("ModelSource", "Actuals")
            state.set_variable("MLUsed", False)
            if apply_waterfall_to_actuals:
                runner.run_period(state)
            else:
                runner.evaluate_period(state)
            tape_balances = bond_balances_by_period.get(period, {})
            if tape_balances:
                for bond_id, bal in tape_balances.items():
                    if bond_id in state.bonds:
                        model_bal = state.bonds[bond_id].current_balance
                        delta = model_bal - bal
                        if abs(delta) > 1.0:
                            reconciliation.append({
                                "period": period,
                                "bond_id": bond_id,
                                "model_balance": model_bal,
                                "tape_balance": bal,
                                "delta": delta,
                                "status": "BALANCE_MISMATCH"
                            })
                    else:
                        reconciliation.append({
                            "period": period,
                            "bond_id": bond_id,
                            "model_balance": None,
                            "tape_balance": bal,
                            "delta": None,
                            "status": "UNKNOWN_BOND"
                        })
                for bond_id, bond_state in state.bonds.items():
                    if bond_id not in tape_balances:
                        reconciliation.append({
                            "period": period,
                            "bond_id": bond_id,
                            "model_balance": bond_state.current_balance,
                            "tape_balance": None,
                            "delta": None,
                            "status": "MISSING_IN_TAPE"
                        })
            current_date = start_date + timedelta(days=30 * period)
            state.snapshot(current_date)

    # 5. Align State to Latest Actual Period
    latest_periods = []
    if not df_asset.empty:
        latest_periods.append(int(df_asset["Period"].max()))
    if not df_bonds.empty:
        latest_periods.append(int(df_bonds["Period"].max()))
    if latest_periods:
        latest_period = max(latest_periods)
        state.period_index = max(state.period_index, latest_period)
        if not apply_waterfall_to_actuals and latest_period in bond_balances_by_period:
            for bond_id, bal in bond_balances_by_period[latest_period].items():
                if bond_id in state.bonds:
                    state.bonds[bond_id].current_balance = bal

    # 6. Simulate Future Cashflows
    orig_bal = float((collateral_json or {}).get("original_balance", 0.0) or 0.0)
    model = CollateralModel(orig_bal, wac=0.06, wam=360)
    latest_end_balance = None
    if not df_asset.empty and "EndBalance" in df_asset.columns:
        latest_end_balance = float(df_asset.sort_values("Period").iloc[-1]["EndBalance"])
    if latest_end_balance is None:
        latest_end_balance = float((collateral_json or {}).get("current_balance", 0.0) or 0.0)
    if latest_end_balance == 0.0 and not df_asset.empty and "PrincipalCollected" in df_asset.columns:
        latest_end_balance = max(0.0, orig_bal - float(df_asset["PrincipalCollected"].sum()))

    remaining = max(0, horizon_periods - state.period_index)
    if remaining > 0:
        future_cfs = None
        ml_used = False
        ml_kind = (collateral_json or {}).get("model_interface", {}).get("kind")
        ml_config = (collateral_json or {}).get("ml_config", {}) or {}
        ml_enabled = ml_config.get("enabled", False) or ml_kind in {"FREDDIE_MAC_ML", "ML_PORTFOLIO"}
        loan_data = (collateral_json or {}).get("loan_data", {})
        schema_ref = loan_data.get("schema_ref", {}) if isinstance(loan_data, dict) else {}
        source_uri = schema_ref.get("source_uri") or ml_config.get("origination_source_uri")
        perf_uri = loan_data.get("performance_uri")
        if ml_enabled and not source_uri:
            raise ValueError("ML models enabled but no origination source URI provided.")
        if ml_enabled and source_uri:
            try:
                from pathlib import Path
                try:
                    from ..ml.models import StochasticRateModel, UniversalModel
                    from ..ml.portfolio import DataManager, SurveillanceEngine
                except ImportError:
                    from rmbs_platform.ml.models import StochasticRateModel, UniversalModel
                    from rmbs_platform.ml.portfolio import DataManager, SurveillanceEngine
                import json

                base_dir = Path(__file__).resolve().parents[1]
                def _resolve(p: str) -> str:
                    path = Path(p)
                    return str(path if path.is_absolute() else (base_dir / p).resolve())

                feature_source = ml_config.get("feature_source", "simulated")
                orig_source = ml_config.get("origination_source_uri")
                static_file = _resolve(orig_source) if orig_source else _resolve(source_uri)
                perf_file = _resolve(perf_uri) if perf_uri else None
                registry_path = (base_dir / "models" / "model_registry.json").resolve()
                if registry_path.exists():
                    registry = json.loads(registry_path.read_text())
                else:
                    registry = {}

                prepay_key = ml_config.get("prepay_model_key", "prepay")
                default_key = ml_config.get("default_model_key", "default")
                prepay_path = registry.get(prepay_key, {}).get("path", str(base_dir / "models" / "rsf_prepayment_model.pkl"))
                default_path = registry.get(default_key, {}).get("path", str(base_dir / "models" / "cox_default_model.pkl"))

                data_mgr = DataManager(
                    static_file,
                    perf_file if perf_file and Path(perf_file).exists() else None,
                    feature_source=feature_source,
                )
                pool = data_mgr.get_pool()
                if pool.empty:
                    raise ValueError("ML pool is empty after loading origination tape.")
                pool_balance = float(pool.get("CURRENT_UPB", 0).sum())
                if pool_balance <= 0:
                    raise ValueError("ML pool has non-positive balance after loading origination tape.")
                prepay_model = UniversalModel(prepay_path, "Prepay")
                default_model = UniversalModel(default_path, "Default")
                state.set_variable("MLPoolCount", int(len(pool)))
                state.set_variable("MLPoolBalance", pool_balance)
                state.set_variable("MLSourceURI", static_file)
                state.set_variable("MLFeatureSource", feature_source)
                state.set_variable("MLPrepayStrategy", prepay_model.strategy)
                state.set_variable("MLDefaultStrategy", default_model.strategy)

                rate_scenario = ml_config.get("rate_scenario", "rally")
                start_rate = ml_config.get("start_rate", 0.045)
                rate_sensitivity = ml_config.get("rate_sensitivity", 1.0)
                base_cpr = ml_config.get("base_cpr", cpr)
                base_cdr = ml_config.get("base_cdr", cdr)
                vasicek = StochasticRateModel()
                rates = vasicek.generate_paths(n_months=remaining, start_rate=start_rate, shock_scenario=rate_scenario)
                state.set_variable("MLRateScenario", rate_scenario)
                state.set_variable("MLStartRate", float(start_rate))
                state.set_variable("MLRateFirst", float(rates[0]) if len(rates) > 0 else None)
                state.set_variable("MLRateMean", float(np.mean(rates)) if len(rates) > 0 else None)
                state.set_variable("MLRateSensitivity", float(rate_sensitivity))
                state.set_variable("MLBaseCPR", float(base_cpr))
                state.set_variable("MLBaseCDR", float(base_cdr))
                surv = SurveillanceEngine(
                    pool,
                    prepay_model,
                    default_model,
                    feature_source=feature_source,
                    rate_sensitivity=rate_sensitivity,
                    base_cpr=base_cpr,
                    base_cdr=base_cdr,
                )
                future_cfs = surv.run(rates)
                if future_cfs.empty:
                    raise ValueError("ML cashflow generation returned no rows.")
                ml_used = True
                future_cfs = future_cfs.rename(columns={
                    "Interest": "InterestCollected",
                    "Principal": "PrincipalCollected",
                    "Loss": "RealizedLoss",
                    "EndBalance": "EndBalance",
                })
            except Exception as exc:
                raise RuntimeError(f"ML cashflow generation failed: {exc}") from exc

        if future_cfs is None:
            future_cfs = model.generate_cashflows(
                remaining, cpr, cdr, severity,
                start_balance=latest_end_balance if latest_end_balance > 0 else None
            )
        for _, row in future_cfs.iterrows():
            period = int(row['Period']) + state.period_index
            interest_collected = float(row["InterestCollected"] or 0.0)
            principal_collected = float(row["PrincipalCollected"] or 0.0)
            realized_loss = float(row["RealizedLoss"] or 0.0)
            end_balance = float(row["EndBalance"] or 0.0)
            prepayment = float(row.get("Prepayment", 0.0) or 0.0)
            scheduled_principal = float(row.get("ScheduledPrincipal", 0.0) or 0.0)
            scheduled_interest = float(row.get("ScheduledInterest", 0.0) or 0.0)
            servicer_advances = float(row.get("ServicerAdvances", 0.0) or 0.0)
            recoveries = float(row.get("Recoveries", 0.0) or 0.0)
            state.deposit_funds("IAF", interest_collected)
            state.deposit_funds("PAF", principal_collected)
            state.set_variable("RealizedLoss", realized_loss)
            state.set_variable("InputInterestCollected", interest_collected)
            state.set_variable("InputPrincipalCollected", principal_collected)
            state.set_variable("InputRealizedLoss", realized_loss)
            state.set_variable("InputEndBalance", end_balance)
            state.set_variable("InputPrepayment", prepayment)
            state.set_variable("InputScheduledPrincipal", scheduled_principal)
            state.set_variable("InputScheduledInterest", scheduled_interest)
            state.set_variable("InputServicerAdvances", servicer_advances)
            state.set_variable("InputRecoveries", recoveries)
            state.set_variable("ModelSource", "ML" if ml_used else "RuleBased")
            state.set_variable("MLUsed", ml_used)
            if "DelinqTrigger" in state.def_.variables:
                state.def_.variables['DelinqTrigger'] = "False"
            runner.run_period(state)
            current_date = start_date + timedelta(days=30 * period)
            state.snapshot(current_date)
        
    # 7. Report
    reporter = ReportGenerator(state.history)
    return reporter.generate_cashflow_report(), reconciliation