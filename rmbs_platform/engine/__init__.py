"""
RMBS Cashflow Simulation Engine
===============================

This module provides the core simulation entry points for Residential Mortgage-Backed
Securities (RMBS) deal analysis. It orchestrates the following steps:

1. **Deal Loading**: Parse and validate deal structures (tranches, waterfalls, triggers).
2. **Performance Ingestion**: Load servicer performance data (actuals) to reconcile model vs. tape.
3. **Collateral Projection**: Generate future cashflows via rule-based or ML-driven models.
4. **Waterfall Execution**: Allocate interest and principal to tranches according to deal rules.
5. **Reporting**: Produce period-by-period cashflow reports suitable for investor analysis.

The main entry point is :func:`run_simulation`, which accepts a deal definition,
collateral attributes, and optional servicer performance data, returning a detailed
cashflow tape and reconciliation report.

Example
-------
>>> from rmbs_platform.engine import run_simulation
>>> deal_json = {...}  # Deal definition dict
>>> collateral_json = {...}  # Collateral attributes
>>> performance_rows = [...]  # Servicer tape rows
>>> df, reconciliation = run_simulation(
...     deal_json, collateral_json, performance_rows,
...     cpr=0.10, cdr=0.01, severity=0.40
... )
>>> print(df.head())

See Also
--------
loader.DealLoader : Parses and validates deal JSON structures.
state.DealState : Manages mutable deal state during simulation.
waterfall.WaterfallRunner : Executes interest/principal allocation rules.
collateral.CollateralModel : Generates rule-based collateral cashflows.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .collateral import CollateralModel
from .compute import ExpressionEngine
from .loader import DealLoader
from .reporting import ReportGenerator
from .state import DealState
from .waterfall import WaterfallRunner

# Advanced modules (imported lazily to avoid circular dependencies)
# These are available via rmbs_platform.engine.<module_name>
# - currency: Multi-currency support (ExchangeRateProvider, CurrencyConverter, FXExposure)
# - credit_enhancement: OC/IC tracking (CreditEnhancementTracker, OCTestResult, ICTestResult)
# - loan_export: Loan-level exports (LoanLevelExporter, RegABExporter, EDWExporter)
# - comparison: Portfolio comparison (PortfolioComparator, ComparisonResult)
# - stress_testing: Stress testing (StressTestingEngine, StressScenario, StressResult)
# - structures: Advanced waterfalls (StructuredWaterfallEngine, ProRataGroup)
# - servicer: Servicer advances (ServicerAdvanceEngine, AdvanceRecoveryEngine)
# - swaps: Swap settlement (SwapSettlementEngine, SwapDefinition)
# - reports: Standard reports (FactorReport, DistributionReport, TrusteeReport)

# Import severity model (with fallback for import issues)
try:
    from ..ml.severity import SeverityModel
except ImportError:
    try:
        from rmbs_platform.ml.severity import SeverityModel
    except ImportError:
        SeverityModel = None  # type: ignore


def _prepare_performance(performance_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Normalize servicer performance data into a DataFrame with standard column names.

    This function standardizes column names from various servicer tape formats
    (e.g., BondID → BondId, LoanID → LoanId) so downstream processing can
    assume consistent naming conventions.

    Parameters
    ----------
    performance_rows : list of dict
        Raw servicer tape rows, typically containing Period, LoanId/BondId,
        InterestCollected, PrincipalCollected, RealizedLoss, EndBalance, etc.

    Returns
    -------
    pd.DataFrame
        Normalized DataFrame with standardized column names.
        Returns an empty DataFrame if no rows are provided.

    Notes
    -----
    Servicer tapes may be loan-level (one row per loan per period) or
    pool-level (one row per period). This function does not aggregate;
    it only normalizes column names.
    """
    if not performance_rows:
        return pd.DataFrame()
    df = pd.DataFrame(performance_rows)
    if "BondID" in df.columns and "BondId" not in df.columns:
        df = df.rename(columns={"BondID": "BondId"})
    if "LoanID" in df.columns and "LoanId" not in df.columns:
        df = df.rename(columns={"LoanID": "LoanId"})
    return df


def _aggregate_loan_performance(loan_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate loan-level performance rows into pool-level period totals.

    When servicer data is provided at loan granularity, this function sums
    numeric fields (InterestCollected, PrincipalCollected, RealizedLoss,
    EndBalance) by period to produce pool-level totals suitable for
    waterfall execution.

    Parameters
    ----------
    loan_df : pd.DataFrame
        Loan-level performance DataFrame with Period and numeric cashflow columns.

    Returns
    -------
    pd.DataFrame
        Pool-level DataFrame with one row per period containing summed cashflows.
        Returns an empty DataFrame if input is empty or lacks required columns.

    Examples
    --------
    >>> loan_data = pd.DataFrame({
    ...     "Period": [1, 1, 2, 2],
    ...     "LoanId": ["L1", "L2", "L1", "L2"],
    ...     "InterestCollected": [100, 150, 95, 145],
    ...     "PrincipalCollected": [500, 600, 510, 590],
    ... })
    >>> pool = _aggregate_loan_performance(loan_data)
    >>> print(pool["InterestCollected"].tolist())
    [250.0, 240.0]
    """
    if loan_df.empty:
        return pd.DataFrame()

    asset_cols = [
        c
        for c in ["InterestCollected", "PrincipalCollected", "RealizedLoss", "EndBalance"]
        if c in loan_df.columns
    ]
    if not asset_cols:
        return pd.DataFrame()

    agg = loan_df.groupby("Period", as_index=False)[asset_cols].sum(numeric_only=True)
    if "PoolStatus" in loan_df.columns:
        pool_status = loan_df.groupby("Period")["PoolStatus"].last().reset_index(drop=True)
        agg["PoolStatus"] = pool_status
    return agg


def _aggregate_collateral(collateral_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive pool-level collateral statistics from loan-level attributes.

    If the collateral JSON contains a `loans` array with individual loan records,
    this function computes aggregate metrics:

    - ``original_balance``: Sum of all loan original balances.
    - ``current_balance``: Sum of all loan current balances.
    - ``wac``: Weighted-average coupon (by current balance).
    - ``wam``: Weighted-average remaining term (by current balance).

    Parameters
    ----------
    collateral_json : dict
        Collateral specification, potentially containing a ``loans`` key
        with individual loan attributes.

    Returns
    -------
    dict
        Updated collateral dict with pool-level metrics added.
        If no loans are present, returns the input unchanged.

    Notes
    -----
    This is primarily used when originating from loan-level data
    (e.g., a loan tape) to compute pool summary statistics
    needed by the waterfall engine.
    """
    # Some datasets wrap collateral attributes under a top-level "data" key:
    #   {"deal_id": "...", "data": {...pool fields...}}
    # Normalize to the expected flat dict so rules like
    # `collateral.current_balance / collateral.original_balance` work consistently.
    # Some sources may double-wrap, so unwrap repeatedly (bounded).
    if isinstance(collateral_json, dict):
        depth = 0
        while "data" in collateral_json and isinstance(collateral_json.get("data"), dict) and depth < 5:
            wrapped = collateral_json.get("data") or {}
            # Preserve deal_id at the top-level if present (useful for UI/debugging)
            if "deal_id" in collateral_json and "deal_id" not in wrapped:
                wrapped = dict(wrapped)
                wrapped["deal_id"] = collateral_json.get("deal_id")
            collateral_json = wrapped
            depth += 1

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
    apply_waterfall_to_actuals: bool = True,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Run a full RMBS deal simulation and return period-by-period cashflow results.

    This is the primary entry point for cashflow analysis. The function:

    1. Loads and validates the deal structure (tranches, waterfalls, triggers).
    2. Processes servicer performance data (actuals) if provided.
    3. Generates future collateral cashflows using either:
       - **Rule-based model**: Uses CPR/CDR/Severity vectors.
       - **ML model**: Uses trained prepay/default models if enabled in collateral config.
    4. Executes the waterfall to allocate cashflows to tranches.
    5. Produces a detailed cashflow tape and reconciliation report.

    Parameters
    ----------
    deal_json : dict
        Deal specification containing:
        - ``meta``: Deal metadata (deal_id, deal_name, etc.)
        - ``bonds``: Tranche definitions with balances and priorities
        - ``waterfalls``: Interest/principal allocation rules
        - ``funds``: Cash bucket definitions (IAF, PAF, etc.)
        - ``tests``: Trigger conditions (delinquency, OC tests, etc.)
        - ``variables``: Computed variables used by waterfall rules
    collateral_json : dict
        Collateral pool attributes:
        - ``original_balance``: Initial pool balance
        - ``current_balance``: Current pool balance
        - ``wac``: Weighted-average coupon
        - ``wam``: Weighted-average maturity
        - ``ml_config``: Optional ML model configuration
        - ``loan_data``: Optional loan-level data references
    performance_rows : list of dict
        Servicer tape rows containing historical performance (actuals).
        Each row typically includes Period, InterestCollected,
        PrincipalCollected, RealizedLoss, EndBalance.
    cpr : float
        Constant Prepayment Rate (annualized), e.g., 0.10 for 10% CPR.
        Used by rule-based model or as base rate for ML model.
    cdr : float
        Constant Default Rate (annualized), e.g., 0.01 for 1% CDR.
        Used by rule-based model or as base rate for ML model.
    severity : float
        Loss severity on defaults, e.g., 0.40 means 40% loss given default.
    horizon_periods : int, default 60
        Number of periods to project forward from the latest actual period.
    strict_balance_check : bool, default True
        If True, enforces strict balance reconciliation checks.
    apply_waterfall_to_actuals : bool, default True
        If True, runs the full waterfall logic on actual periods
        (making historical cashflows flow through the deal structure).
        If False, only evaluates tests/variables without paying bonds.

    Returns
    -------
    df : pd.DataFrame
        Period-by-period cashflow report containing:
        - ``Period``, ``Date``: Period identifiers
        - ``Bond.<tranche>.Balance``: Tranche balances
        - ``Bond.<tranche>.Prin_Paid``: Principal paid to tranche
        - ``Fund.<bucket>.Balance``: Cash bucket balances
        - ``Var.<name>``: Computed variables and ML diagnostics
    reconciliation : list of dict
        Reconciliation entries comparing model balances to servicer tape.
        Each entry includes period, bond_id, model_balance, tape_balance,
        delta, and status (BALANCE_MISMATCH, UNKNOWN_BOND, MISSING_IN_TAPE).

    Raises
    ------
    ValueError
        If ML models are enabled but no origination source URI is provided,
        or if ML cashflow generation returns an invalid result.
    RuntimeError
        If ML model loading or prediction fails.

    Notes
    -----
    **ML Model Integration**: When ``ml_config.enabled`` is True in collateral_json,
    the engine attempts to load trained prepay/default models and generate
    loan-level cashflows using stochastic rate paths. The ML path requires:

    - A valid ``loan_data.schema_ref.source_uri`` pointing to an origination tape.
    - Trained model files (.pkl) referenced in ``models/model_registry.json``.
    - Feature columns (RATE_INCENTIVE, BURNOUT_PROXY, SATO, FICO_BUCKET, etc.)
      either pre-computed or derivable from the origination tape.

    **Waterfall Execution**: The waterfall runs in this order:

    1. Deposit collateral cashflows into IAF (interest) and PAF (principal).
    2. Execute interest waterfall: pay fees, then bond interest by priority.
    3. Execute principal waterfall: pay bonds by priority.
    4. Allocate losses: write down subordinate tranches as needed.

    Examples
    --------
    >>> deal = {
    ...     "meta": {"deal_id": "TEST_2024"},
    ...     "bonds": [{"id": "A", "type": "NOTE", "original_balance": 1e6, ...}],
    ...     "waterfalls": {"interest": {...}, "principal": {...}},
    ...     "funds": [{"id": "IAF", "description": "Interest"}],
    ...     ...
    ... }
    >>> collateral = {"original_balance": 1e6, "wac": 0.05, "wam": 360}
    >>> servicer_tape = [
    ...     {"Period": 1, "InterestCollected": 5000, "PrincipalCollected": 10000, ...},
    ...     ...
    ... ]
    >>> df, recon = run_simulation(deal, collateral, servicer_tape, cpr=0.10, cdr=0.01, severity=0.40)
    >>> print(df[["Period", "Bond.A.Balance"]].head())

    See Also
    --------
    CollateralModel : Rule-based cashflow generator.
    ml.portfolio.SurveillanceEngine : ML-driven cashflow generator.
    WaterfallRunner : Waterfall execution engine.
    """
    # 1. Load and validate deal structure
    loader = DealLoader()
    merged_deal = dict(deal_json)
    collateral_json = _aggregate_collateral(collateral_json or {})
    merged_deal["collateral"] = collateral_json
    deal_def = loader.load_from_json(merged_deal)

    # 2. Initialize simulation state
    state = DealState(deal_def)
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)

    # 3. Prepare servicer performance data (actuals)
    perf_df = _prepare_performance(performance_rows)

    # Normalize column names for common variations (do this early)
    col_renames = {
        "EndingBalance": "EndBalance",
        "Prepayments": "Prepayment",
        "Recovery": "Recoveries",
    }
    for old_col, new_col in col_renames.items():
        if old_col in perf_df.columns and new_col not in perf_df.columns:
            perf_df = perf_df.rename(columns={old_col: new_col})

    # Convert Period to numeric for proper sorting (critical!)
    if "Period" in perf_df.columns:
        perf_df["Period"] = pd.to_numeric(perf_df["Period"], errors="coerce")
        perf_df = perf_df.dropna(subset=["Period"])
        perf_df["Period"] = perf_df["Period"].astype(int)

    # Compute PrincipalCollected from component columns if not present
    if "PrincipalCollected" not in perf_df.columns and "Period" in perf_df.columns:
        sched_prin = pd.to_numeric(perf_df.get("ScheduledPrincipal", 0.0), errors="coerce").fillna(0.0)
        prepay = pd.to_numeric(perf_df.get("Prepayment", 0.0), errors="coerce").fillna(0.0)
        perf_df["PrincipalCollected"] = sched_prin + prepay

    # Extended list of columns to preserve for waterfall evaluation
    all_asset_cols = [
        "InterestCollected", "PrincipalCollected", "RealizedLoss", "EndBalance", "PoolStatus",
        "ScheduledPrincipal", "Prepayment", "ScheduledInterest", "ServicerAdvances", "Recoveries",
        "Delinq30", "Delinq60", "Delinq90Plus", "Delinq60Plus",  # Delinquency metrics
        "Defaults", "CPR", "CDR", "Severity",  # Additional performance metrics
    ]
    asset_cols = [c for c in all_asset_cols if c in perf_df.columns]

    df_asset = pd.DataFrame()
    if not perf_df.empty and asset_cols:
        if "LoanId" in perf_df.columns:
            loan_df = perf_df[perf_df["LoanId"].notna()].copy()
            df_asset = _aggregate_loan_performance(loan_df)
        else:
            keep_cols = ["Period"] + [c for c in asset_cols if c in perf_df.columns]
            df_asset = perf_df[keep_cols].copy()
            # Group and aggregate only the summable columns, keep last value for rates/percentages
            sum_cols = ["InterestCollected", "PrincipalCollected", "RealizedLoss", 
                        "ScheduledPrincipal", "Prepayment", "ScheduledInterest", 
                        "ServicerAdvances", "Recoveries", "Defaults"]
            rate_cols = ["Delinq30", "Delinq60", "Delinq90Plus", "Delinq60Plus", 
                         "CPR", "CDR", "Severity", "EndBalance", "PoolStatus"]
            
            sum_cols_present = [c for c in sum_cols if c in df_asset.columns]
            rate_cols_present = [c for c in rate_cols if c in df_asset.columns]
            
            if sum_cols_present or rate_cols_present:
                agg_dict = {}
                for c in sum_cols_present:
                    agg_dict[c] = "sum"
                for c in rate_cols_present:
                    agg_dict[c] = "last"  # Take last value for rates and balances
                df_asset = df_asset.groupby("Period", as_index=False).agg(agg_dict)

    # Extract bond-level balances from tape for reconciliation
    df_bonds = pd.DataFrame()
    has_loan_level = "LoanId" in perf_df.columns and perf_df["LoanId"].notna().any()
    if not has_loan_level and not perf_df.empty and {"BondId", "BondBalance"}.issubset(perf_df.columns):
        df_bonds = perf_df[["Period", "BondId", "BondBalance"]].dropna()
        df_bonds["Period"] = df_bonds["Period"].astype(int)
        df_bonds["BondBalance"] = df_bonds["BondBalance"].astype(float)
    bond_balances_by_period: Dict[int, Dict[str, float]] = {}
    if not df_bonds.empty:
        for period, rows in df_bonds.groupby("Period"):
            bond_balances_by_period[int(period)] = {
                row["BondId"]: float(row["BondBalance"]) for _, row in rows.iterrows()
            }

    start_date = date.today()
    reconciliation: List[Dict[str, Any]] = []

    # 4. Apply actuals (process historical servicer data)
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
            recoveries = float(row.get("Recoveries", row.get("Recovery", 0.0)) or 0.0)

            # Deposit cashflows into waterfall funds
            state.deposit_funds("IAF", interest_collected)
            state.deposit_funds("PAF", principal_collected)

            # Set period variables for waterfall evaluation
            state.set_variable("RealizedLoss", realized_loss)
            state.set_variable("InputInterestCollected", interest_collected)
            state.set_variable("InputPrincipalCollected", principal_collected)
            state.set_variable("InputRealizedLoss", realized_loss)
            state.set_variable("InputPrepayment", prepayment)
            state.set_variable("InputScheduledPrincipal", scheduled_principal)
            state.set_variable("InputScheduledInterest", scheduled_interest)
            state.set_variable("InputServicerAdvances", servicer_advances)
            state.set_variable("InputRecoveries", recoveries)

            # Set delinquency variables from performance tape
            for delinq_col in ["Delinq30", "Delinq60", "Delinq90Plus", "Delinq60Plus"]:
                if delinq_col in row and row.get(delinq_col) is not None:
                    try:
                        delinq_val = float(row.get(delinq_col))
                        state.set_variable(delinq_col, delinq_val)
                    except (TypeError, ValueError):
                        state.set_variable(delinq_col, 0.0)

            # Also compute Delinq60PlusBalance for trigger calculations
            if "Delinq60Plus" in row and row.get("Delinq60Plus") is not None:
                try:
                    delinq_rate = float(row.get("Delinq60Plus"))
                    current_bal = state.collateral.get("current_balance", 0.0)
                    state.set_variable("Delinq60PlusBalance", delinq_rate * current_bal)
                except (TypeError, ValueError):
                    state.set_variable("Delinq60PlusBalance", 0.0)

            # Handle EndBalance (with alias support)
            end_bal_value = row.get("EndBalance") or row.get("EndingBalance")
            if end_bal_value is not None:
                try:
                    end_bal = float(end_bal_value)
                    state.collateral["current_balance"] = end_bal
                    state.set_variable("PoolEndBalance", end_bal)
                    state.set_variable("InputEndBalance", end_bal)
                except (TypeError, ValueError):
                    pass

            if "PoolStatus" in row and row.get("PoolStatus") is not None:
                state.set_variable("PoolStatus", str(row.get("PoolStatus")))

            state.set_variable("ModelSource", "Actuals")
            state.set_variable("MLUsed", False)

            # Execute waterfall or just evaluate tests/variables
            if apply_waterfall_to_actuals:
                runner.run_period(state)
            else:
                runner.evaluate_period(state)

            # Reconcile model vs. tape bond balances
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
                                "status": "BALANCE_MISMATCH",
                            })
                    else:
                        reconciliation.append({
                            "period": period,
                            "bond_id": bond_id,
                            "model_balance": None,
                            "tape_balance": bal,
                            "delta": None,
                            "status": "UNKNOWN_BOND",
                        })
                for bond_id, bond_state in state.bonds.items():
                    if bond_id not in tape_balances:
                        reconciliation.append({
                            "period": period,
                            "bond_id": bond_id,
                            "model_balance": bond_state.current_balance,
                            "tape_balance": None,
                            "delta": None,
                            "status": "MISSING_IN_TAPE",
                        })

            current_date = start_date + timedelta(days=30 * period)
            state.snapshot(current_date)

    # 5. Align state to latest actual period
    latest_periods: List[int] = []
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

    # 6. Generate future cashflows (projection period)
    orig_bal = float((collateral_json or {}).get("original_balance", 0.0) or 0.0)
    model = CollateralModel(orig_bal, wac=0.06, wam=360)

    latest_end_balance: Optional[float] = None
    if not df_asset.empty and "EndBalance" in df_asset.columns:
        latest_end_balance = float(df_asset.sort_values("Period").iloc[-1]["EndBalance"])
    if latest_end_balance is None:
        latest_end_balance = float((collateral_json or {}).get("current_balance", 0.0) or 0.0)
    if latest_end_balance == 0.0 and not df_asset.empty and "PrincipalCollected" in df_asset.columns:
        latest_end_balance = max(0.0, orig_bal - float(df_asset["PrincipalCollected"].sum()))

    remaining = max(0, horizon_periods - state.period_index)
    if remaining > 0:
        future_cfs: Optional[pd.DataFrame] = None
        ml_used = False

        # Check for ML configuration
        ml_kind = (collateral_json or {}).get("model_interface", {}).get("kind")
        ml_config = (collateral_json or {}).get("ml_config", {}) or {}
        ml_enabled = ml_config.get("enabled", False) or ml_kind in {"FREDDIE_MAC_ML", "ML_PORTFOLIO"}
        loan_data = (collateral_json or {}).get("loan_data", {})
        schema_ref = loan_data.get("schema_ref", {}) if isinstance(loan_data, dict) else {}
        source_uri = schema_ref.get("source_uri") or ml_config.get("origination_source_uri")
        perf_uri = loan_data.get("performance_uri")

        if ml_enabled and not source_uri:
            raise ValueError("ML models enabled but no origination source URI provided.")

        # ML-driven cashflow generation
        if ml_enabled and source_uri:
            try:
                from pathlib import Path

                try:
                    from ..ml.models import StochasticRateModel, UniversalModel
                    from ..ml.portfolio import DataManager, SurveillanceEngine
                except ImportError:
                    from rmbs_platform.ml.models import StochasticRateModel, UniversalModel
                    from rmbs_platform.ml.portfolio import DataManager, SurveillanceEngine

                import json as json_module

                base_dir = Path(__file__).resolve().parents[1]

                def _resolve(p: str) -> str:
                    path = Path(p)
                    return str(path if path.is_absolute() else (base_dir / p).resolve())

                feature_source = ml_config.get("feature_source", "simulated")
                orig_source = ml_config.get("origination_source_uri")
                static_file = _resolve(orig_source) if orig_source else _resolve(source_uri)
                perf_file = _resolve(perf_uri) if perf_uri else None

                registry_path = (base_dir / "models" / "model_registry.json").resolve()
                registry: Dict[str, Any] = {}
                if registry_path.exists():
                    registry = json_module.loads(registry_path.read_text())

                prepay_key = ml_config.get("prepay_model_key", "prepay")
                default_key = ml_config.get("default_model_key", "default")
                prepay_path = registry.get(prepay_key, {}).get(
                    "path", str(base_dir / "models" / "rsf_prepayment_model.pkl")
                )
                default_path = registry.get(default_key, {}).get(
                    "path", str(base_dir / "models" / "cox_default_model.pkl")
                )

                # Load loan data
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

                # Load ML models
                prepay_model = UniversalModel(prepay_path, "Prepay")
                default_model = UniversalModel(default_path, "Default")

                # Set ML diagnostics
                state.set_variable("MLPoolCount", int(len(pool)))
                state.set_variable("MLPoolBalance", pool_balance)
                state.set_variable("MLSourceURI", static_file)
                state.set_variable("MLFeatureSource", feature_source)
                state.set_variable("MLPrepayStrategy", prepay_model.strategy)
                state.set_variable("MLDefaultStrategy", default_model.strategy)

                # Generate rate paths
                rate_scenario = ml_config.get("rate_scenario", "rally")
                start_rate = ml_config.get("start_rate", 0.045)
                rate_sensitivity = ml_config.get("rate_sensitivity", 1.0)
                base_cpr = ml_config.get("base_cpr", cpr)
                base_cdr = ml_config.get("base_cdr", cdr)

                vasicek = StochasticRateModel()
                rates = vasicek.generate_paths(
                    n_months=remaining, start_rate=start_rate, shock_scenario=rate_scenario
                )
                if isinstance(rates, np.ndarray) and rates.ndim > 1:
                    rates = rates[:, 0]

                state.set_variable("MLRateScenario", rate_scenario)
                state.set_variable("MLStartRate", float(start_rate))
                state.set_variable("MLRateFirst", float(rates[0]) if len(rates) > 0 else None)
                state.set_variable("MLRateMean", float(np.mean(rates)) if len(rates) > 0 else None)
                state.set_variable("MLRateSensitivity", float(rate_sensitivity))
                state.set_variable("MLBaseCPR", float(base_cpr))
                state.set_variable("MLBaseCDR", float(base_cdr))

                # Initialize severity model for loss calculations
                try:
                    from ..ml.severity import SeverityModel as SevModel
                except ImportError:
                    from rmbs_platform.ml.severity import SeverityModel as SevModel
                severity_model = SevModel()

                # Run ML simulation with severity model
                surv = SurveillanceEngine(
                    pool,
                    prepay_model,
                    default_model,
                    feature_source=feature_source,
                    rate_sensitivity=rate_sensitivity,
                    base_cpr=base_cpr,
                    base_cdr=base_cdr,
                    severity_model=severity_model,
                    base_severity=severity,
                )
                future_cfs = surv.run(rates)

                # Set severity model diagnostics
                state.set_variable("MLSeverityModelEnabled", severity_model.config.enabled)
                state.set_variable("MLBaseSeverity", float(severity))
                if future_cfs.empty:
                    raise ValueError("ML cashflow generation returned no rows.")
                ml_used = True
                future_cfs = future_cfs.rename(
                    columns={
                        "Interest": "InterestCollected",
                        "Principal": "PrincipalCollected",
                        "Loss": "RealizedLoss",
                        "EndBalance": "EndBalance",
                    }
                )
            except Exception as exc:
                raise RuntimeError(f"ML cashflow generation failed: {exc}") from exc

        # Fall back to rule-based model if ML not used
        if future_cfs is None:
            future_cfs = model.generate_cashflows(
                remaining,
                cpr,
                cdr,
                severity,
                start_balance=latest_end_balance,
            )

        # Process projected cashflows through waterfall
        for _, row in future_cfs.iterrows():
            period = int(row["Period"]) + state.period_index
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
                state.def_.variables["DelinqTrigger"] = "False"

            # Check clean-up call threshold before running waterfall
            cleanup_triggered = _check_cleanup_call(state, deal_json, collateral_json)
            state.set_variable("CleanupCallTriggered", cleanup_triggered)

            if cleanup_triggered:
                # Execute clean-up call: pay off all bonds at par and terminate
                state.set_variable("CleanupCallExercised", True)
                _execute_cleanup_call(state, engine, runner)
                current_date = start_date + timedelta(days=30 * period)
                state.snapshot(current_date)
                break  # Terminate simulation after clean-up call

            runner.run_period(state)
            current_date = start_date + timedelta(days=30 * period)
            state.snapshot(current_date)

    # 7. Generate report
    reporter = ReportGenerator(state.history)
    return reporter.generate_cashflow_report(), reconciliation


def _check_cleanup_call(
    state: DealState,
    deal_json: Dict[str, Any],
    collateral_json: Dict[str, Any],
) -> bool:
    """
    Check if the clean-up call threshold has been breached.

    The clean-up call allows the residual holder to purchase remaining
    collateral when the pool factor falls below a threshold (typically 10%).

    Parameters
    ----------
    state : DealState
        Current deal state.
    deal_json : dict
        Deal specification containing cleanup_call options.
    collateral_json : dict
        Collateral attributes with original/current balance.

    Returns
    -------
    bool
        True if clean-up call threshold is breached, False otherwise.

    Notes
    -----
    The clean-up call threshold is defined in ``deal_json.options.cleanup_call``
    with the following structure:

    ```json
    {
        "cleanup_call": {
            "enabled": true,
            "threshold_rule": "collateral.current_balance <= 0.1 * collateral.original_balance"
        }
    }
    ```

    If no cleanup_call option is defined, returns False.
    """
    # Check deal-level cleanup call options
    options = deal_json.get("options", {})
    cleanup_config = options.get("cleanup_call", {})

    if not cleanup_config.get("enabled", False):
        return False

    # Get threshold from deal spec or use default 10%
    threshold_rule = cleanup_config.get("threshold_rule")

    if threshold_rule:
        # Evaluate the threshold rule using the expression engine
        engine = ExpressionEngine()
        try:
            return engine.evaluate_condition(threshold_rule, state)
        except Exception:
            pass

    # Default: check if pool factor is below 10%
    original_balance = float(
        collateral_json.get("original_balance")
        or state.collateral.get("original_balance", 0)
    )
    current_balance = float(state.collateral.get("current_balance", 0))

    if original_balance > 0:
        pool_factor = current_balance / original_balance
        return pool_factor <= 0.10

    return False


def _execute_cleanup_call(
    state: DealState,
    engine: ExpressionEngine,
    runner: WaterfallRunner,
) -> None:
    """
    Execute the clean-up call, paying off all bonds and terminating the deal.

    When the clean-up call is exercised:

    1. The residual holder purchases remaining collateral at par.
    2. All outstanding bonds are paid in full (principal + accrued interest).
    3. The deal terminates.

    Parameters
    ----------
    state : DealState
        Current deal state to modify.
    engine : ExpressionEngine
        Expression evaluator for calculating interest due.
    runner : WaterfallRunner
        Waterfall runner (not used for cleanup, but available).

    Notes
    -----
    This function directly modifies the state to:

    - Set all bond balances to zero
    - Record the cleanup call payment
    - Set termination flags

    In a real implementation, the residual holder would need to fund
    the cleanup call amount, which equals:

        cleanup_amount = sum(bond_principal) + sum(accrued_interest)
    """
    cleanup_amount = 0.0

    for bond_id, bond_state in state.bonds.items():
        if bond_state.current_balance > 0:
            principal_payoff = bond_state.current_balance

            # Calculate accrued interest (simplified: 1 month at coupon rate)
            bond_def = state.def_.bonds.get(bond_id)
            if bond_def:
                coupon_rate = 0.0
                if hasattr(bond_def, "fixed_rate") and bond_def.fixed_rate:
                    coupon_rate = float(bond_def.fixed_rate)
                elif hasattr(bond_def, "margin") and bond_def.margin:
                    # Float: use a proxy rate
                    coupon_rate = 0.05 + float(bond_def.margin)
                else:
                    # Default coupon rate if not specified
                    coupon_rate = 0.05

                accrued_interest = principal_payoff * (coupon_rate / 12)
            else:
                accrued_interest = 0.0

            cleanup_amount += principal_payoff + accrued_interest

            # Pay off the bond
            bond_state.current_balance = 0.0
            bond_state.interest_shortfall = 0.0

    # Record cleanup call variables
    state.set_variable("CleanupCallAmount", cleanup_amount)
    state.set_variable("DealTerminated", True)

    # Clear remaining cash (goes to residual holder)
    for fund_id in state.cash_balances:
        state.cash_balances[fund_id] = 0.0

    # Set collateral to zero
    state.collateral["current_balance"] = 0.0
