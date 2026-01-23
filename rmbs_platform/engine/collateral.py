"""
Collateral Cashflow Generation
==============================

This module provides collateral cashflow models for RMBS simulation:

1. **CollateralModel** (Rep-Line): Treats pool as single loan. Fast but misses
   adverse selection effects when high-rate loans prepay first.

2. **LoanLevelCollateralModel** (Seriatim): Iterates through individual loans,
   calculating loan-specific SMM/MDR based on characteristics. Captures WAC
   drift and adverse selection. Required for industry-grade accuracy.

Both models implement standard RMBS prepayment and default assumptions
using CPR (Constant Prepayment Rate), CDR (Constant Default Rate), and loss
severity parameters, converted to SMM/MDR using standard formulas.

Industry Context
----------------
The **rep-line model** is suitable for:
- Quick scenario analysis
- DeFi retail applications where simplicity is preferred
- Deals with homogeneous collateral

The **loan-level model** is required for:
- Institutional RWA applications (Centrifuge, MakerDAO, etc.)
- Regulatory submissions (CCAR, DFAST)
- Deals with heterogeneous collateral (mixed rates, FICOs, LTVs)
- Web3 tokenization where investors expect loan-level transparency

Example
-------
>>> # Rep-line model (fast, less accurate)
>>> model = CollateralModel(original_balance=1e6, wac=0.05, wam=360)
>>> cashflows = model.generate_cashflows(periods=60, cpr_vector=0.10, cdr_vector=0.01, sev_vector=0.40)

>>> # Loan-level model (slower, industry-grade)
>>> loan_model = LoanLevelCollateralModel.from_csv("loan_tape.csv")
>>> cashflows = loan_model.generate_cashflows(periods=60, base_cpr=0.10, base_cdr=0.01, base_severity=0.40)
>>> print(f"WAC drift: {loan_model.get_wac_history()}")

See Also
--------
ml.portfolio.SurveillanceEngine : ML-driven cashflow generator with ML hazard models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd


@dataclass
class PeriodCashflow:
    """
    Single-period collateral cashflow summary.

    This dataclass captures all cashflow components for one month of
    collateral performance, before allocation through the waterfall.

    Attributes
    ----------
    period : int
        The period number (1-indexed).
    scheduled_interest : float
        Interest due based on pool balance and WAC.
    scheduled_principal : float
        Scheduled amortization from level-pay mortgage formula.
    prepayments : float
        Voluntary principal prepayments beyond scheduled amount.
    defaults : float
        Principal balance lost to default events.
    recoveries : float
        Post-default recoveries (default - loss).
    total_interest_collected : float
        Interest received for waterfall distribution.
    total_principal_collected : float
        Principal received for waterfall distribution.
    """

    period: int
    scheduled_interest: float
    scheduled_principal: float
    prepayments: float
    defaults: float
    recoveries: float
    total_interest_collected: float
    total_principal_collected: float


class CollateralModel:
    """
    Generate simplified collateral cashflows from CPR/CDR/Severity assumptions.

    This model implements a standard RMBS cashflow projection methodology
    using constant prepayment and default rate assumptions. It is used
    when ML models are not enabled or as a fallback when ML fails.

    Parameters
    ----------
    original_balance : float
        Initial pool principal balance at deal closing.
    wac : float
        Weighted-Average Coupon (WAC) - average interest rate across all loans.
        Expressed as a decimal (e.g., 0.06 for 6%).
    wam : int
        Weighted-Average Maturity (WAM) - average remaining term in months.

    Attributes
    ----------
    current_balance : float
        Running pool balance during projection.
    current_period : int
        Current period counter during projection.

    Notes
    -----
    **CPR to SMM Conversion**: The model converts annual CPR to monthly
    Single Monthly Mortality using the standard formula:

        SMM = 1 - (1 - CPR)^(1/12)

    **Default Timing**: Defaults are assumed to occur at the beginning of
    the period on the starting balance, before scheduled principal.

    **Prepayment Timing**: Prepayments occur after scheduled principal
    and defaults, on the remaining balance.

    Example
    -------
    >>> model = CollateralModel(original_balance=100_000_000, wac=0.055, wam=300)
    >>> cfs = model.generate_cashflows(60, cpr_vector=0.12, cdr_vector=0.02, sev_vector=0.35)
    >>> ending_balance = cfs.iloc[-1]["EndBalance"]
    >>> print(f"Balance after 60 months: ${ending_balance:,.0f}")
    """

    def __init__(self, original_balance: float, wac: float, wam: int) -> None:
        """
        Initialize the collateral model with pool-level characteristics.

        Parameters
        ----------
        original_balance : float
            Initial pool principal balance.
        wac : float
            Weighted-average coupon rate (decimal).
        wam : int
            Weighted-average maturity in months.
        """
        self.original_balance = original_balance
        self.wac = wac
        self.wam = wam
        self.current_balance = original_balance
        self.current_period = 0

    def generate_cashflows(
        self,
        periods: int,
        cpr_vector: float,
        cdr_vector: float,
        sev_vector: float,
        start_balance: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Generate collateral cashflows given CPR/CDR/Severity assumptions.

        This method projects monthly cashflows for the specified number of
        periods using constant prepayment, default, and severity rates.
        The projection starts from either the model's internal balance
        or an explicitly provided starting balance.

        Parameters
        ----------
        periods : int
            Number of monthly periods to project.
        cpr_vector : float
            Constant Prepayment Rate (annual), e.g., 0.10 for 10% CPR.
        cdr_vector : float
            Constant Default Rate (annual), e.g., 0.02 for 2% CDR.
        sev_vector : float
            Loss severity on defaults, e.g., 0.40 for 40% loss given default.
        start_balance : float, optional
            Starting pool balance. If None, uses original_balance.

        Returns
        -------
        pd.DataFrame
            Period-by-period cashflow table with columns:

            - ``Period``: Period number (1-indexed)
            - ``BeginBalance``: Pool balance at period start
            - ``EndBalance``: Pool balance at period end
            - ``InterestCollected``: Interest paid to waterfall
            - ``PrincipalCollected``: Total principal (sched + prepay + recovery)
            - ``RealizedLoss``: Loss amount (default * severity)
            - ``DefaultAmount``: Gross default amount
            - ``ScheduledInterest``: Interest accrued on balance
            - ``ScheduledPrincipal``: Scheduled amortization
            - ``Prepayment``: Voluntary prepayments
            - ``Recoveries``: Post-default recoveries
            - ``ServicerAdvances``: Servicer advances for missed interest

        Notes
        -----
        The cashflow waterfall within each period:

        1. Calculate interest due on beginning balance.
        2. Calculate scheduled principal using level-pay formula.
        3. Apply defaults on beginning balance.
        4. Calculate loss and recovery amounts.
        5. Calculate prepayments on post-scheduled balance.
        6. Update ending balance.

        Example
        -------
        >>> model = CollateralModel(1_000_000, 0.05, 360)
        >>> df = model.generate_cashflows(12, 0.08, 0.01, 0.35)
        >>> print(df[["Period", "EndBalance", "RealizedLoss"]].tail(3))
        """
        rows = []
        balance = self.original_balance if start_balance is None else start_balance

        # Monthly interest rate from WAC
        r_gwac = self.wac / 12.0

        for t in range(1, periods + 1):
            if balance <= 0:
                rows.append({
                    "Period": t,
                    "BeginBalance": 0.0,
                    "EndBalance": 0.0,
                    "InterestCollected": 0.0,
                    "PrincipalCollected": 0.0,
                    "RealizedLoss": 0.0,
                    "DefaultAmount": 0.0,
                    "ScheduledInterest": 0.0,
                    "ScheduledPrincipal": 0.0,
                    "Prepayment": 0.0,
                    "Recoveries": 0.0,
                    "ServicerAdvances": 0.0,
                })
                continue

            # 1. Calculate monthly rates from annual rates (SMM conversion)
            smm_prepay = 1 - (1 - cpr_vector) ** (1 / 12)
            mdr_default = 1 - (1 - cdr_vector) ** (1 / 12)

            # 2. Interest due on beginning balance
            interest_due = balance * r_gwac

            # 3. Scheduled principal (level-pay amortization formula)
            remaining_term = max(1, self.wam - t)
            level_pay = (balance * r_gwac) / (1 - (1 + r_gwac) ** (-remaining_term))
            sched_prin = max(0, level_pay - interest_due)

            # 4. Defaults (occur on beginning balance)
            default_amount = balance * mdr_default
            loss_amount = default_amount * sev_vector
            recovery_amount = default_amount - loss_amount

            # 5. Prepayments (on balance after scheduled and defaults)
            bal_post_sched = balance - sched_prin - default_amount
            prepay_amount = max(0, bal_post_sched * smm_prepay)

            # 6. Aggregate cashflows
            total_prin_collected = sched_prin + prepay_amount + recovery_amount
            total_int_collected = interest_due
            servicer_advances = max(0.0, interest_due - total_int_collected)

            # 7. Update ending balance
            balance = balance - sched_prin - default_amount - prepay_amount

            rows.append({
                "Period": t,
                "BeginBalance": balance + sched_prin + default_amount + prepay_amount,
                "EndBalance": balance,
                "InterestCollected": total_int_collected,
                "PrincipalCollected": total_prin_collected,
                "RealizedLoss": loss_amount,
                "DefaultAmount": default_amount,
                "ScheduledInterest": interest_due,
                "ScheduledPrincipal": sched_prin,
                "Prepayment": prepay_amount,
                "Recoveries": recovery_amount,
                "ServicerAdvances": servicer_advances,
            })

        return pd.DataFrame(rows)


@dataclass
class LoanState:
    """
    Track individual loan state during simulation.
    
    Attributes
    ----------
    loan_id : str
        Unique loan identifier.
    original_balance : float
        Balance at origination.
    current_balance : float
        Current outstanding balance.
    note_rate : float
        Contractual interest rate (decimal, e.g., 0.05 for 5%).
    remaining_term : int
        Remaining months to maturity.
    fico : float
        Credit score at origination.
    ltv : float
        Loan-to-value ratio (decimal, e.g., 0.80 for 80%).
    state : str
        Property state (for judicial/non-judicial severity).
    is_active : bool
        Whether loan is still performing (not paid off or defaulted).
    """
    loan_id: str
    original_balance: float
    current_balance: float
    note_rate: float
    remaining_term: int
    fico: float = 700.0
    ltv: float = 0.80
    state: str = "CA"
    is_active: bool = True


class LoanLevelCollateralModel:
    """
    Loan-level (seriatim) collateral model for industry-grade RMBS simulation.
    
    This model iterates through individual loans, calculating loan-specific
    SMM/MDR rates based on loan characteristics. It properly captures:
    
    - **Adverse selection**: High-rate loans prepay first, lowering pool WAC
    - **Credit stratification**: Different default rates by FICO/LTV buckets
    - **Rate sensitivity**: Loan-specific prepayment incentives
    - **WAC drift**: Accurate tracking of pool composition over time
    
    This is required for:
    - Institutional RWA applications
    - Regulatory submissions (CCAR/DFAST)
    - Web3 tokenization (loan-level transparency)
    
    Parameters
    ----------
    loans : pd.DataFrame
        Loan tape with columns: LoanId, OriginalBalance, CurrentBalance,
        NoteRate, RemainingTermMonths, FICO, LTV, State (optional).
    
    Attributes
    ----------
    loans : pd.DataFrame
        Working copy of loan data.
    loan_states : dict
        Mapping of loan_id to LoanState objects.
    wac_history : list
        Period-by-period WAC tracking for adverse selection analysis.
    
    Example
    -------
    >>> model = LoanLevelCollateralModel.from_csv("loan_tape.csv")
    >>> cfs = model.generate_cashflows(
    ...     periods=60, base_cpr=0.10, base_cdr=0.02, base_severity=0.35
    ... )
    >>> # Check WAC drift (adverse selection effect)
    >>> print(f"Initial WAC: {model.wac_history[0]:.3%}")
    >>> print(f"Final WAC: {model.wac_history[-1]:.3%}")
    """
    
    def __init__(self, loans: pd.DataFrame) -> None:
        """
        Initialize with a loan tape DataFrame.
        
        Parameters
        ----------
        loans : pd.DataFrame
            Loan-level data with required columns.
        """
        self.original_loans = loans.copy()
        self.loans = self._normalize_loans(loans)
        self.loan_states: Dict[str, LoanState] = {}
        self.wac_history: List[float] = []
        self._initialize_loan_states()
    
    @classmethod
    def from_csv(cls, filepath: Union[str, Path], **read_kwargs) -> "LoanLevelCollateralModel":
        """
        Create model from a CSV loan tape file.
        
        Parameters
        ----------
        filepath : str or Path
            Path to loan tape CSV.
        **read_kwargs
            Additional arguments passed to pd.read_csv.
        
        Returns
        -------
        LoanLevelCollateralModel
            Initialized model with loaded loan data.
        
        Example
        -------
        >>> model = LoanLevelCollateralModel.from_csv("datasets/DEAL_2024/loan_tape.csv")
        """
        df = pd.read_csv(filepath, **read_kwargs)
        return cls(df)
    
    def _normalize_loans(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to standard schema.
        
        Handles various naming conventions from different data sources.
        """
        df = df.copy()
        
        # Column mapping for common variations
        col_map = {
            "LoanId": "LOAN_ID",
            "LOAN_SEQUENCE_NUMBER": "LOAN_ID",
            "OriginalBalance": "ORIG_BALANCE",
            "ORIGINAL_UPB": "ORIG_BALANCE",
            "CurrentBalance": "CURRENT_BALANCE",
            "CURRENT_ACTUAL_UPB": "CURRENT_BALANCE",
            "NoteRate": "NOTE_RATE",
            "ORIGINAL_INTEREST_RATE": "NOTE_RATE",
            "RemainingTermMonths": "REMAINING_TERM",
            "ORIGINAL_LOAN_TERM": "REMAINING_TERM",
            "TERM": "REMAINING_TERM",
            "FICO": "FICO",
            "CREDIT_SCORE": "FICO",
            "LTV": "LTV",
            "ORIGINAL_LTV": "LTV",
            "State": "STATE",
            "PROPERTY_STATE": "STATE",
        }
        
        for old_col, new_col in col_map.items():
            if old_col in df.columns and new_col not in df.columns:
                df[new_col] = df[old_col]
        
        # Ensure required columns exist with defaults
        if "LOAN_ID" not in df.columns:
            df["LOAN_ID"] = [f"L{i:06d}" for i in range(len(df))]
        if "CURRENT_BALANCE" not in df.columns:
            df["CURRENT_BALANCE"] = df.get("ORIG_BALANCE", 0)
        if "FICO" not in df.columns:
            df["FICO"] = 700.0
        if "LTV" not in df.columns:
            df["LTV"] = 0.80
        if "STATE" not in df.columns:
            df["STATE"] = "CA"
        if "REMAINING_TERM" not in df.columns:
            df["REMAINING_TERM"] = 360
        
        # Normalize rate format (handle percentage vs decimal)
        if "NOTE_RATE" in df.columns:
            df["NOTE_RATE"] = df["NOTE_RATE"].apply(
                lambda x: x / 100 if x > 1 else x
            )
        else:
            df["NOTE_RATE"] = 0.05  # Default 5%
        
        # Convert LTV to decimal if needed
        if df["LTV"].max() > 2:  # Likely percentage format
            df["LTV"] = df["LTV"] / 100
        
        return df
    
    def _initialize_loan_states(self) -> None:
        """Initialize loan state tracking objects."""
        for _, row in self.loans.iterrows():
            loan_id = str(row["LOAN_ID"])
            self.loan_states[loan_id] = LoanState(
                loan_id=loan_id,
                original_balance=float(row.get("ORIG_BALANCE", row.get("CURRENT_BALANCE", 0))),
                current_balance=float(row["CURRENT_BALANCE"]),
                note_rate=float(row["NOTE_RATE"]),
                remaining_term=int(row["REMAINING_TERM"]),
                fico=float(row.get("FICO", 700)),
                ltv=float(row.get("LTV", 0.80)),
                state=str(row.get("STATE", "CA")),
                is_active=float(row["CURRENT_BALANCE"]) > 0,
            )
    
    def _calculate_loan_smm(
        self,
        loan: LoanState,
        base_cpr: float,
        market_rate: Optional[float] = None,
    ) -> float:
        """
        Calculate loan-specific SMM based on characteristics.
        
        Higher rate loans get higher prepayment speeds (refinance incentive).
        """
        # Base SMM from annual CPR
        base_smm = 1 - (1 - base_cpr) ** (1 / 12)
        
        # Rate incentive adjustment
        rate_incentive_mult = 1.0
        if market_rate is not None and loan.note_rate > market_rate:
            # Strong incentive to refinance
            spread = loan.note_rate - market_rate
            rate_incentive_mult = 1.0 + min(spread * 10, 2.0)  # Cap at 3x
        elif market_rate is not None and loan.note_rate < market_rate:
            # Disincentive to refinance (rate locked in)
            spread = market_rate - loan.note_rate
            rate_incentive_mult = max(0.3, 1.0 - spread * 5)  # Floor at 0.3x
        
        # FICO adjustment (higher FICO = slightly more likely to refinance)
        fico_mult = 1.0
        if loan.fico >= 750:
            fico_mult = 1.1
        elif loan.fico >= 700:
            fico_mult = 1.0
        elif loan.fico >= 650:
            fico_mult = 0.9
        else:
            fico_mult = 0.8
        
        # LTV adjustment (higher LTV = harder to refinance)
        ltv_mult = 1.0
        if loan.ltv > 0.80:
            ltv_mult = 0.7  # High LTV loans harder to refi
        elif loan.ltv < 0.60:
            ltv_mult = 1.2  # Low LTV loans easier to refi
        
        # Combined SMM
        loan_smm = base_smm * rate_incentive_mult * fico_mult * ltv_mult
        return min(loan_smm, 1.0)  # Cap at 100%
    
    def _calculate_loan_mdr(
        self,
        loan: LoanState,
        base_cdr: float,
    ) -> float:
        """
        Calculate loan-specific MDR based on credit characteristics.
        
        Lower FICO and higher LTV get higher default rates.
        """
        # Base MDR from annual CDR
        base_mdr = 1 - (1 - base_cdr) ** (1 / 12)
        
        # FICO adjustment (exponential increase for lower scores)
        fico_mult = 1.0
        if loan.fico >= 750:
            fico_mult = 0.3
        elif loan.fico >= 700:
            fico_mult = 0.6
        elif loan.fico >= 650:
            fico_mult = 1.0
        elif loan.fico >= 600:
            fico_mult = 2.0
        else:
            fico_mult = 4.0
        
        # LTV adjustment (higher LTV = more likely to default)
        ltv_mult = 1.0
        if loan.ltv > 0.95:
            ltv_mult = 3.0
        elif loan.ltv > 0.90:
            ltv_mult = 2.0
        elif loan.ltv > 0.80:
            ltv_mult = 1.5
        elif loan.ltv < 0.60:
            ltv_mult = 0.5
        
        # Combined MDR
        loan_mdr = base_mdr * fico_mult * ltv_mult
        return min(loan_mdr, 1.0)
    
    def _calculate_loan_severity(
        self,
        loan: LoanState,
        base_severity: float,
    ) -> float:
        """
        Calculate loan-specific loss severity.
        
        Higher LTV and judicial states get higher severity.
        """
        severity = base_severity
        
        # LTV adjustment
        if loan.ltv > 0.90:
            severity = min(1.0, severity * 1.3)
        elif loan.ltv > 0.80:
            severity = min(1.0, severity * 1.1)
        elif loan.ltv < 0.60:
            severity = severity * 0.7
        
        # Judicial state adjustment (longer foreclosure = higher severity)
        judicial_states = {"NY", "NJ", "FL", "IL", "OH", "PA", "CT", "MA"}
        if loan.state in judicial_states:
            severity = min(1.0, severity * 1.15)
        
        return severity
    
    def calculate_pool_wac(self) -> float:
        """
        Calculate current weighted-average coupon of active loans.
        
        Returns
        -------
        float
            Balance-weighted average note rate.
        """
        total_balance = 0.0
        weighted_rate = 0.0
        
        for loan in self.loan_states.values():
            if loan.is_active and loan.current_balance > 0:
                total_balance += loan.current_balance
                weighted_rate += loan.current_balance * loan.note_rate
        
        if total_balance > 0:
            return weighted_rate / total_balance
        return 0.0
    
    def calculate_pool_balance(self) -> float:
        """Calculate total balance of active loans."""
        return sum(
            loan.current_balance
            for loan in self.loan_states.values()
            if loan.is_active
        )
    
    def get_loan_count(self) -> int:
        """Count active loans."""
        return sum(1 for loan in self.loan_states.values() if loan.is_active)
    
    def get_wac_history(self) -> List[float]:
        """Return WAC tracking history for adverse selection analysis."""
        return self.wac_history
    
    def generate_cashflows(
        self,
        periods: int,
        base_cpr: float,
        base_cdr: float,
        base_severity: float,
        market_rate_path: Optional[List[float]] = None,
    ) -> pd.DataFrame:
        """
        Generate loan-level cashflows with proper adverse selection modeling.
        
        This method iterates through each loan individually, calculating
        loan-specific prepayment and default rates based on characteristics.
        It properly captures WAC drift as high-rate loans prepay first.
        
        Parameters
        ----------
        periods : int
            Number of monthly periods to project.
        base_cpr : float
            Base annual prepayment rate (e.g., 0.10 for 10% CPR).
        base_cdr : float
            Base annual default rate (e.g., 0.02 for 2% CDR).
        base_severity : float
            Base loss severity (e.g., 0.40 for 40% LGD).
        market_rate_path : list of float, optional
            Monthly market rate path for refinance incentive calculation.
            If None, uses 4.5% flat rate.
        
        Returns
        -------
        pd.DataFrame
            Period-by-period cashflow table with columns:
            - Period, BeginBalance, EndBalance
            - InterestCollected, PrincipalCollected
            - RealizedLoss, DefaultAmount
            - ScheduledPrincipal, Prepayment, Recoveries
            - PoolWAC (tracks adverse selection)
            - ActiveLoans (loan count)
        
        Example
        -------
        >>> model = LoanLevelCollateralModel.from_csv("loan_tape.csv")
        >>> cfs = model.generate_cashflows(
        ...     periods=60, base_cpr=0.10, base_cdr=0.02, base_severity=0.35,
        ...     market_rate_path=[0.04] * 60  # 4% flat rate scenario
        ... )
        >>> # Analyze adverse selection
        >>> wac_drift = cfs["PoolWAC"].iloc[-1] - cfs["PoolWAC"].iloc[0]
        >>> print(f"WAC drift due to adverse selection: {wac_drift:.2%}")
        """
        # Reset loan states for fresh projection
        self._initialize_loan_states()
        self.wac_history = []
        
        # Default market rate path
        if market_rate_path is None:
            market_rate_path = [0.045] * periods
        
        rows = []
        
        for t in range(1, periods + 1):
            # Get current pool state
            begin_balance = self.calculate_pool_balance()
            current_wac = self.calculate_pool_wac()
            self.wac_history.append(current_wac)
            
            if begin_balance <= 0:
                # Pool is empty
                rows.append({
                    "Period": t,
                    "BeginBalance": 0.0,
                    "EndBalance": 0.0,
                    "InterestCollected": 0.0,
                    "PrincipalCollected": 0.0,
                    "RealizedLoss": 0.0,
                    "DefaultAmount": 0.0,
                    "ScheduledInterest": 0.0,
                    "ScheduledPrincipal": 0.0,
                    "Prepayment": 0.0,
                    "Recoveries": 0.0,
                    "ServicerAdvances": 0.0,
                    "PoolWAC": 0.0,
                    "ActiveLoans": 0,
                })
                continue
            
            # Get market rate for this period
            market_rate = market_rate_path[min(t - 1, len(market_rate_path) - 1)]
            
            # Aggregate cashflows
            total_interest = 0.0
            total_sched_prin = 0.0
            total_prepay = 0.0
            total_default = 0.0
            total_loss = 0.0
            total_recovery = 0.0
            
            # Process each loan individually (SERIATIM)
            for loan_id, loan in self.loan_states.items():
                if not loan.is_active or loan.current_balance <= 0:
                    continue
                
                # Calculate loan-specific rates
                loan_smm = self._calculate_loan_smm(loan, base_cpr, market_rate)
                loan_mdr = self._calculate_loan_mdr(loan, base_cdr)
                loan_severity = self._calculate_loan_severity(loan, base_severity)
                
                # Monthly interest
                monthly_rate = loan.note_rate / 12
                interest = loan.current_balance * monthly_rate
                total_interest += interest
                
                # Scheduled principal (level-pay amortization)
                remaining = max(1, loan.remaining_term)
                if monthly_rate > 0:
                    denom = 1 - (1 + monthly_rate) ** (-remaining)
                    if denom > 0:
                        level_pay = (loan.current_balance * monthly_rate) / denom
                        sched_prin = max(0, level_pay - interest)
                    else:
                        sched_prin = loan.current_balance / remaining
                else:
                    sched_prin = loan.current_balance / remaining
                
                # Default (on beginning balance)
                default_amt = loan.current_balance * loan_mdr
                loss_amt = default_amt * loan_severity
                recovery_amt = default_amt - loss_amt
                
                # Prepayment (on balance after scheduled and default)
                bal_post = loan.current_balance - sched_prin - default_amt
                prepay_amt = max(0, bal_post * loan_smm)
                
                # Aggregate
                total_sched_prin += sched_prin
                total_default += default_amt
                total_loss += loss_amt
                total_recovery += recovery_amt
                total_prepay += prepay_amt
                
                # Update loan state
                new_balance = loan.current_balance - sched_prin - default_amt - prepay_amt
                loan.current_balance = max(0, new_balance)
                loan.remaining_term = max(0, loan.remaining_term - 1)
                
                # Mark inactive if paid off
                if loan.current_balance < 1.0:
                    loan.is_active = False
            
            # Record period cashflows
            end_balance = self.calculate_pool_balance()
            total_principal = total_sched_prin + total_prepay + total_recovery
            
            rows.append({
                "Period": t,
                "BeginBalance": begin_balance,
                "EndBalance": end_balance,
                "InterestCollected": total_interest,
                "PrincipalCollected": total_principal,
                "RealizedLoss": total_loss,
                "DefaultAmount": total_default,
                "ScheduledInterest": total_interest,
                "ScheduledPrincipal": total_sched_prin,
                "Prepayment": total_prepay,
                "Recoveries": total_recovery,
                "ServicerAdvances": 0.0,
                "PoolWAC": current_wac,
                "ActiveLoans": self.get_loan_count(),
            })
        
        return pd.DataFrame(rows)
    
    def get_loan_level_detail(self) -> pd.DataFrame:
        """
        Export current loan-level state for Web3 transparency.
        
        Returns
        -------
        pd.DataFrame
            Loan-level snapshot with current balances and characteristics.
        
        Notes
        -----
        This method supports Web3 tokenization where investors expect
        to see the specific loans backing a pool (NFT transparency).
        """
        rows = []
        for loan_id, loan in self.loan_states.items():
            rows.append({
                "LoanId": loan.loan_id,
                "OriginalBalance": loan.original_balance,
                "CurrentBalance": loan.current_balance,
                "NoteRate": loan.note_rate,
                "RemainingTerm": loan.remaining_term,
                "FICO": loan.fico,
                "LTV": loan.ltv,
                "State": loan.state,
                "IsActive": loan.is_active,
                "Factor": loan.current_balance / loan.original_balance if loan.original_balance > 0 else 0,
            })
        return pd.DataFrame(rows)
