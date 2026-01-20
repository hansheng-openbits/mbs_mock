"""
Portfolio Simulation and Structuring
=====================================

This module provides loan pool management and ML-driven cashflow projection
for RMBS portfolio analysis. It bridges raw loan data with trained ML models
to generate realistic prepayment and default scenarios.

Key Classes
-----------
DataManager
    Loads, normalizes, and manages loan-level origination data.
SurveillanceEngine
    Runs period-by-period cashflow projection using ML models.
Tranche
    Simple tranche container for waterfall demonstration.

The portfolio module is used when ML models are enabled in the simulation
configuration. It replaces the rule-based CollateralModel with a more
sophisticated loan-level projection.

Example
-------
>>> from rmbs_platform.ml.portfolio import DataManager, SurveillanceEngine
>>> from rmbs_platform.ml.models import UniversalModel, StochasticRateModel
>>> # Load loan pool
>>> data_mgr = DataManager("origination.csv")
>>> pool = data_mgr.get_pool()
>>> # Initialize models
>>> prepay = UniversalModel("models/prepay.pkl", "Prepay")
>>> default = UniversalModel("models/default.pkl", "Default")
>>> # Generate rate path
>>> vasicek = StochasticRateModel()
>>> rates = vasicek.generate_paths(60, start_rate=0.045, shock_scenario="rally")
>>> # Run projection
>>> engine = SurveillanceEngine(pool, prepay, default)
>>> cashflows = engine.run(rates)
>>> print(cashflows[["Period", "Interest", "Principal", "Loss"]].head())

See Also
--------
models.UniversalModel : ML model wrappers.
models.StochasticRateModel : Interest rate path generator.
engine : Core simulation engine that integrates ML cashflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from .features import add_default_features, add_prepay_features
from .models import UniversalModel
from .severity import SeverityModel, SeverityModelConfig


class DataManager:
    """
    Load and normalize loan tapes for portfolio-level ML simulation.

    This class handles the complexity of reading different loan data formats
    (Freddie Mac origination files, normalized CSV tapes) and producing a
    consistent internal representation for ML prediction.

    Parameters
    ----------
    static_file : str
        Path to the origination tape (loan attributes at origination).
    perf_file : str, optional
        Path to the performance tape (current balances, status).
    feature_source : str, default "simulated"
        How to compute rate incentive features:
        - "simulated": Derive from rate path during projection
        - "market_rates": Compute from historical market data

    Attributes
    ----------
    static_file : str
        Path to the origination tape.
    perf_file : str or None
        Path to the performance tape.
    feature_source : str
        Feature computation strategy.
    raw_df : pd.DataFrame or None
        Loaded and normalized loan data.

    Notes
    -----
    **Supported Formats**:

    1. Freddie Mac pipe-delimited files with standard column names.
    2. Normalized CSV with columns: LoanId, OriginalBalance, NoteRate, etc.

    **Normalization**:

    The loader maps various column naming conventions to a standard schema:
    - ``LOAN_ID``: Unique loan identifier
    - ``ORIG_UPB``: Original unpaid principal balance
    - ``CURRENT_UPB``: Current unpaid principal balance
    - ``NOTE_RATE``: Interest rate (decimal)
    - ``TERM``: Original loan term (months)
    - ``FICO``: Credit score at origination
    - ``LTV``: Loan-to-value ratio at origination

    Example
    -------
    >>> data_mgr = DataManager(
    ...     "data/origination.csv",
    ...     perf_file="data/performance.csv",
    ...     feature_source="market_rates"
    ... )
    >>> pool = data_mgr.get_pool()
    >>> print(f"Pool size: {len(pool)} loans, ${pool['CURRENT_UPB'].sum():,.0f} balance")
    """

    def __init__(
        self,
        static_file: str,
        perf_file: Optional[str] = None,
        feature_source: str = "simulated",
    ) -> None:
        """
        Initialize the data manager with file paths and options.

        Parameters
        ----------
        static_file : str
            Path to the origination tape.
        perf_file : str, optional
            Path to the performance tape.
        feature_source : str, default "simulated"
            Feature computation strategy.
        """
        self.static_file = static_file
        self.perf_file = perf_file
        self.feature_source = feature_source
        self.raw_df: Optional[pd.DataFrame] = None
        self._load()

    @staticmethod
    def _read_static(path: Path) -> pd.DataFrame:
        """
        Read a Freddie or normalized origination tape from disk.

        Parameters
        ----------
        path : Path
            File path to read.

        Returns
        -------
        pd.DataFrame
            Raw loan data (column names not yet normalized).
        """
        df = pd.read_csv(path, sep="|", low_memory=False)
        if len(df.columns) == 1 and "," in df.columns[0]:
            df = pd.read_csv(path, sep=",", low_memory=False)
        elif "LoanId" not in df.columns and "LOAN_SEQUENCE_NUMBER" not in df.columns:
            df = pd.read_csv(path, sep=",", low_memory=False)
        return df

    @staticmethod
    def _normalize_static(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize origination columns into the model's feature schema.

        Parameters
        ----------
        df : pd.DataFrame
            Raw origination data.

        Returns
        -------
        pd.DataFrame
            Normalized DataFrame with standard column names.
        """
        if "LoanId" in df.columns:
            df = df.rename(
                columns={
                    "LoanId": "LOAN_ID",
                    "OriginalBalance": "ORIG_UPB",
                    "CurrentBalance": "CURRENT_UPB",
                    "NoteRate": "NOTE_RATE",
                    "RemainingTermMonths": "TERM",
                    "LTV": "LTV",
                    "FICO": "FICO",
                    "DTI": "DTI",
                }
            )
            df["LOAN_ID"] = df["LOAN_ID"].astype(str)
        else:
            col_map = {
                "LOAN_SEQUENCE_NUMBER": "LOAN_ID",
                "ORIGINAL_UPB": "ORIG_UPB",
                "ORIGINAL_INTEREST_RATE": "NOTE_RATE",
                "CREDIT_SCORE": "FICO",
                "ORIGINAL_LOAN_TERM": "TERM",
                "ORIGINAL_LTV": "LTV",
                "PROPERTY_STATE": "STATE",
                "ORIGINAL_DEBT_TO_INCOME_RATIO": "DTI",
            }
            df = df.rename(columns=col_map)

        for c in ["ORIG_UPB", "FICO", "LTV", "DTI", "TERM"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        if "DURATION" not in df.columns and "TERM" in df.columns:
            df["DURATION"] = df["TERM"]

        if "NOTE_RATE" not in df.columns:
            for alt in ["OriginalInterestRate", "ORIGINAL_INTEREST_RATE", "NoteRate"]:
                if alt in df.columns:
                    df["NOTE_RATE"] = pd.to_numeric(df[alt], errors="coerce").fillna(0)
                    break
        if "NOTE_RATE" in df.columns:
            df["NOTE_RATE"] = df["NOTE_RATE"].apply(lambda x: x / 100 if x > 1 else x)

        if "CURRENT_UPB" not in df.columns:
            df["CURRENT_UPB"] = df.get("ORIG_UPB", 0)

        return df

    def _load(self) -> None:
        """
        Load tapes and populate normalized loan pool.

        Raises
        ------
        FileNotFoundError
            If the origination tape does not exist.
        """
        if not Path(self.static_file).exists():
            raise FileNotFoundError(f"Origination tape not found: {self.static_file}")

        df = self._read_static(Path(self.static_file))
        df = self._normalize_static(df)

        if self.feature_source == "market_rates":
            df = add_prepay_features(df)
            df = add_default_features(df)

        # Ensure required features exist with defaults
        if "RATE_INCENTIVE" not in df.columns:
            df["RATE_INCENTIVE"] = (df.get("NOTE_RATE", 0) * 100) - 4.0
        if "SATO" not in df.columns:
            df["SATO"] = df["RATE_INCENTIVE"]
        if "FICO_BUCKET" not in df.columns:
            df["FICO_BUCKET"] = np.select(
                [df.get("FICO", 0) >= 750, df.get("FICO", 0) >= 700],
                [1, 2],
                default=3,
            )
        if "HIGH_LTV_FLAG" not in df.columns:
            df["HIGH_LTV_FLAG"] = (df.get("LTV", 0) > 80).astype(int)
        if "BURNOUT_PROXY" not in df.columns:
            df["BURNOUT_PROXY"] = 0.0

        # Map to standard model feature names
        df["ORIGINAL_INTEREST_RATE"] = df.get("NOTE_RATE", 0)
        df["CREDIT_SCORE"] = df.get("FICO", 0)
        df["ORIGINAL_LTV"] = df.get("LTV", 0)
        df["ORIGINAL_DEBT_TO_INCOME_RATIO"] = df.get("DTI", 0)

        # Update balances from performance tape if available
        if self.perf_file and Path(self.perf_file).exists():
            perf_latest = self._load_perf_balance(Path(self.perf_file))
            if perf_latest is not None and not perf_latest.empty:
                df = pd.merge(df, perf_latest, on="LOAN_ID", how="left")
                df["CURRENT_UPB"] = df["CURRENT_UPB"].fillna(df["ORIG_UPB"])
                df = df[df["CURRENT_UPB"] > 0]
            else:
                df["CURRENT_UPB"] = df["ORIG_UPB"]
        else:
            df["CURRENT_UPB"] = df["ORIG_UPB"]

        self.raw_df = df

    def _generate_mock(self, n: int) -> pd.DataFrame:
        """
        Create a synthetic pool (used only for diagnostics).

        Parameters
        ----------
        n : int
            Number of mock loans to generate.

        Returns
        -------
        pd.DataFrame
            Synthetic loan data.
        """
        return pd.DataFrame({"ORIG_UPB": [300000] * n, "CURRENT_UPB": [300000] * n})

    @staticmethod
    def _load_perf_balance(path: Path) -> Optional[pd.DataFrame]:
        """
        Load current UPB from a performance tape if available.

        Parameters
        ----------
        path : Path
            Path to the performance tape.

        Returns
        -------
        pd.DataFrame or None
            DataFrame with LOAN_ID and CURRENT_UPB columns,
            or None if loading fails.
        """
        # Try Freddie performance format (pipe-delimited)
        try:
            df_perf = pd.read_csv(
                path,
                sep="|",
                usecols=["LOAN_SEQUENCE_NUMBER", "CURRENT_ACTUAL_UPB"],
                low_memory=False,
            )
            df_perf.rename(
                columns={
                    "LOAN_SEQUENCE_NUMBER": "LOAN_ID",
                    "CURRENT_ACTUAL_UPB": "CURRENT_UPB",
                },
                inplace=True,
            )
            latest = df_perf.groupby("LOAN_ID")["CURRENT_UPB"].last().reset_index()
            return latest
        except Exception:
            pass

        # Try normalized loan-level perf (comma-delimited)
        try:
            df_perf = pd.read_csv(path, sep=",", low_memory=False)
        except Exception:
            return None

        if "LoanId" in df_perf.columns:
            df_perf = df_perf.rename(columns={"LoanId": "LOAN_ID"})
        if "LOAN_ID" not in df_perf.columns:
            return None

        balance_col = None
        for candidate in ["EndBalance", "CURRENT_UPB", "CURRENT_ACTUAL_UPB"]:
            if candidate in df_perf.columns:
                balance_col = candidate
                break
        if balance_col is None:
            return None

        df_perf = df_perf.rename(columns={balance_col: "CURRENT_UPB"})
        latest = df_perf.groupby("LOAN_ID")["CURRENT_UPB"].last().reset_index()
        return latest

    def get_pool(self) -> pd.DataFrame:
        """
        Return the normalized loan pool with positive balances.

        Returns
        -------
        pd.DataFrame
            Active loans with CURRENT_UPB > 0.
        """
        return self.raw_df[self.raw_df["CURRENT_UPB"] > 0].copy()


class SurveillanceEngine:
    """
    Run a portfolio projection using ML prepay/default models.

    This engine generates period-by-period cashflows for a loan pool
    using trained machine learning models. It updates rate-sensitive
    features each period based on the simulated rate path.

    Parameters
    ----------
    pool : pd.DataFrame
        Loan-level DataFrame from DataManager.get_pool().
    prepay_model : UniversalModel
        Prepayment hazard model.
    default_model : UniversalModel
        Default hazard model.
    feature_source : str, default "simulated"
        How to compute rate incentive:
        - "simulated": Update each period from the rate path
        - "market_rates": Use pre-computed historical values
    rate_sensitivity : float, default 1.0
        Multiplier for rate incentive effect on prepayment.
    base_cpr : float, default 0.06
        Baseline annual prepayment rate.
    base_cdr : float, default 0.005
        Baseline annual default rate.

    Attributes
    ----------
    pool : pd.DataFrame
        Working copy of loan data.
    prepay : UniversalModel
        Prepayment model reference.
    default : UniversalModel
        Default model reference.
    feature_source : str
        Feature computation strategy.
    rate_sensitivity : float
        Rate incentive sensitivity multiplier.
    base_cpr : float
        Baseline prepayment rate.
    base_cdr : float
        Baseline default rate.

    Notes
    -----
    **Projection Methodology**:

    1. For each period, update rate-sensitive features (if simulated).
    2. Predict prepay/default hazard multipliers from ML models.
    3. Apply SMM/MDR rates to loan balances.
    4. Calculate interest, principal, losses, recoveries.
    5. Update loan balances for next period.

    Example
    -------
    >>> engine = SurveillanceEngine(
    ...     pool, prepay_model, default_model,
    ...     feature_source="simulated",
    ...     rate_sensitivity=1.5,
    ...     base_cpr=0.08
    ... )
    >>> cashflows = engine.run(rate_path)
    """

    def __init__(
        self,
        pool: pd.DataFrame,
        prepay_model: UniversalModel,
        default_model: UniversalModel,
        feature_source: str = "simulated",
        rate_sensitivity: float = 1.0,
        base_cpr: float = 0.06,
        base_cdr: float = 0.005,
        severity_model: Optional[SeverityModel] = None,
        base_severity: float = 0.35,
    ) -> None:
        """
        Initialize the surveillance engine with pool and models.

        Parameters
        ----------
        pool : pd.DataFrame
            Normalized loan pool from DataManager.
        prepay_model : UniversalModel
            Prepayment prediction model.
        default_model : UniversalModel
            Default prediction model.
        feature_source : str, default "simulated"
            Feature update strategy.
        rate_sensitivity : float, default 1.0
            Rate incentive effect multiplier.
        base_cpr : float, default 0.06
            Baseline prepayment rate.
        base_cdr : float, default 0.005
            Baseline default rate.
        severity_model : SeverityModel, optional
            Loan-level severity model. If None, uses base_severity.
        base_severity : float, default 0.35
            Fixed severity rate when severity_model is None.
        """
        self.pool = pool.copy()
        self.prepay = prepay_model
        self.default = default_model
        self.feature_source = feature_source
        self.rate_sensitivity = rate_sensitivity
        self.base_cpr = base_cpr
        self.base_cdr = base_cdr
        self.severity_model = severity_model or SeverityModel()
        self.base_severity = base_severity

    def run(self, rate_path: np.ndarray) -> pd.DataFrame:
        """
        Generate portfolio-level cashflows for a given rate path.

        Parameters
        ----------
        rate_path : np.ndarray
            Monthly short-rate path, shape (n_periods,) or (n_periods, 1).

        Returns
        -------
        pd.DataFrame
            Period-by-period cashflow summary with columns:
            - ``Period``: Period number (1-indexed)
            - ``Market_Rate``: Rate for this period
            - ``Interest``: Total interest collected
            - ``Principal``: Total principal (sched + prepay + recovery - loss)
            - ``Loss``: Realized credit losses
            - ``CPR``: Average CPR for this period
            - ``EndBalance``: Remaining pool balance
            - ``ScheduledPrincipal``, ``Prepayment``, ``Recoveries``, etc.

        Notes
        -----
        The projection terminates early if the pool balance falls below $1,000.

        Example
        -------
        >>> rates = vasicek.generate_paths(60, shock_scenario="rally")
        >>> cfs = engine.run(rates)
        >>> total_loss = cfs["Loss"].sum()
        >>> print(f"Cumulative loss: ${total_loss:,.0f}")
        """
        loans = self.pool.copy()

        # Ensure required columns exist
        if "NOTE_RATE" not in loans.columns:
            loans["NOTE_RATE"] = 0.0
        if "BURNOUT_PROXY" not in loans.columns:
            loans["BURNOUT_PROXY"] = 0.0
        if "FICO" not in loans.columns:
            loans["FICO"] = 0.0
        if "LTV" not in loans.columns:
            loans["LTV"] = 0.0
        if "FICO_BUCKET" not in loans.columns:
            loans["FICO_BUCKET"] = np.select(
                [loans["FICO"] >= 750, loans["FICO"] >= 700], [1, 2], default=3
            )
        if "HIGH_LTV_FLAG" not in loans.columns:
            loans["HIGH_LTV_FLAG"] = (loans["LTV"] > 80).astype(int)
        if "SATO" not in loans.columns:
            loans["SATO"] = (loans["NOTE_RATE"] * 100) - 4.0

        loans["Active_Bal"] = loans["CURRENT_UPB"]
        history: List[dict] = []

        # Flatten rate path if 2D
        if len(rate_path.shape) > 1:
            rate_path = rate_path.flatten()

        for t, curr_rate in enumerate(rate_path):
            if loans["Active_Bal"].sum() < 1000:
                break

            # Update rate-sensitive features if using simulated approach
            if self.feature_source == "simulated":
                loans["RATE_INCENTIVE"] = (loans["NOTE_RATE"] - curr_rate) * 100
                loans["BURNOUT_PROXY"] += np.where(
                    loans["RATE_INCENTIVE"] > 0.5, 1.0, 0.0
                )

            # Predict hazard multipliers from ML models
            cpr_mult = np.clip(self.prepay.predict_multiplier(loans), 0.1, 20.0)
            cdr_mult = np.clip(self.default.predict_multiplier(loans), 0.1, 10.0)

            # Apply base rates with multipliers
            cpr = np.clip(self.base_cpr * cpr_mult, 0.0, 1.0)
            cdr = np.clip(self.base_cdr * cdr_mult, 0.0, 1.0)

            # Apply rate sensitivity adjustment if simulated
            if self.feature_source == "simulated":
                rate_adj = 1.0 + (loans["RATE_INCENTIVE"] / 100.0) * float(
                    self.rate_sensitivity
                )
                rate_adj = np.clip(rate_adj, 0.1, 3.0)
                cpr = np.clip(cpr * rate_adj, 0.0, 1.0)

            # Convert annual rates to monthly
            smm = 1 - (1 - cpr) ** (1 / 12)
            mdr = 1 - (1 - cdr) ** (1 / 12)

            # Calculate cashflows
            int_paid = loans["Active_Bal"] * (loans["NOTE_RATE"] / 12)
            r = loans["NOTE_RATE"] / 12
            denom = 1 - (1 + r) ** (-loans["TERM"])
            sched_pmt = loans["Active_Bal"] * r / np.where(denom == 0, 1e-9, denom)
            sched_prin = (sched_pmt - int_paid).clip(lower=0)

            prepay = (loans["Active_Bal"] - sched_prin) * smm
            default = (loans["Active_Bal"] - sched_prin - prepay) * mdr

            # Calculate loan-level severity using the severity model
            if self.severity_model is not None and self.severity_model.config.enabled:
                # Predict severity for each loan based on characteristics
                severities = self.severity_model.predict(loans, hpi_change=0.0)
            else:
                # Use fixed severity rate
                severities = np.full(len(loans), self.base_severity)

            loss = default * severities
            recoveries = default - loss

            # Update balances
            loans["Active_Bal"] -= sched_prin + prepay + default
            loans["Active_Bal"] = loans["Active_Bal"].clip(lower=0)

            # Calculate weighted average severity for reporting
            default_balance = default.sum()
            avg_severity = (
                float((severities * default).sum() / default_balance)
                if default_balance > 0
                else self.base_severity
            )

            history.append({
                "Period": t + 1,
                "Market_Rate": float(curr_rate),
                "RateMean": float(curr_rate),
                "RateIncentiveMean": float(loans["RATE_INCENTIVE"].mean()),
                "BurnoutMean": float(loans["BURNOUT_PROXY"].mean()),
                "Interest": float(int_paid.sum()),
                "Principal": float((sched_prin + prepay + default - loss).sum()),
                "Loss": float(loss.sum()),
                "CPR": float(cpr.mean()),
                "CDR": float(cdr.mean()),
                "Severity": avg_severity,
                "EndBalance": float(loans["Active_Bal"].sum()),
                "ScheduledInterest": float(int_paid.sum()),
                "ScheduledPrincipal": float(sched_prin.sum()),
                "Prepayment": float(prepay.sum()),
                "Recoveries": float(recoveries.sum()),
                "DefaultAmount": float(default.sum()),
                "ServicerAdvances": 0.0,
            })

        return pd.DataFrame(history)


@dataclass
class Tranche:
    """
    Simple tranche container used by the demo waterfall.

    This is a minimal tranche representation for demonstrating waterfall
    mechanics. Production implementations would use the full DealState/BondState
    classes from the engine module.

    Attributes
    ----------
    name : str
        Tranche identifier.
    balance : float
        Current outstanding balance.
    coupon : float
        Annual coupon rate (decimal).
    orig : float
        Original balance at closing.
    cfs : list of float
        Period-by-period cashflows received.

    Example
    -------
    >>> tranche_a = Tranche.create("A", 1_000_000, 0.05)
    >>> print(f"Factor: {tranche_a.balance / tranche_a.orig:.2%}")
    """

    name: str
    balance: float
    coupon: float
    orig: float
    cfs: List[float]

    @classmethod
    def create(cls, name: str, balance: float, coupon: float) -> "Tranche":
        """
        Construct a tranche with original balance set to current balance.

        Parameters
        ----------
        name : str
            Tranche identifier.
        balance : float
            Initial balance.
        coupon : float
            Annual coupon rate.

        Returns
        -------
        Tranche
            New tranche instance.
        """
        return cls(name=name, balance=balance, coupon=coupon, orig=balance, cfs=[])


def run_waterfall(tranches: List[Tranche], cfs: pd.DataFrame) -> List[Tranche]:
    """
    Apply a simple interest/principal waterfall to tranche cashflows.

    This is a demonstration waterfall that allocates pool cashflows to
    tranches in seniority order. Production waterfalls use the full
    WaterfallRunner from the engine module.

    Parameters
    ----------
    tranches : list of Tranche
        Tranches in priority order (senior first, equity last).
    cfs : pd.DataFrame
        Pool-level cashflows with Interest and Principal columns.

    Returns
    -------
    list of Tranche
        Updated tranches with populated cfs lists.

    Notes
    -----
    The equity tranche (last in list) receives all excess cashflows
    after senior tranches are paid.

    Example
    -------
    >>> tranches = [
    ...     Tranche.create("A", 800000, 0.04),
    ...     Tranche.create("B", 150000, 0.06),
    ...     Tranche.create("Equity", 50000, 0.0)
    ... ]
    >>> tranches = run_waterfall(tranches, pool_cashflows)
    """
    equity = tranches[-1]
    for row in cfs.itertuples():
        avail_int = row.Interest
        avail_prin = row.Principal

        # Pay interest to senior tranches
        for t in tranches[:-1]:
            pay = min(avail_int, t.balance * t.coupon / 12) if t.balance > 0 else 0
            avail_int -= pay
            t.cfs.append(pay)

        # Pay principal to senior tranches
        for t in tranches[:-1]:
            pay = min(t.balance, avail_prin) if t.balance > 0 else 0
            t.balance -= pay
            avail_prin -= pay
            t.cfs[-1] += pay

        # Remainder to equity
        equity.cfs.append(avail_int + avail_prin)

    return tranches
