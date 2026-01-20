"""
Collateral Cashflow Generation
==============================

This module provides the rule-based collateral cashflow model used when ML models
are not enabled. It implements standard RMBS prepayment and default assumptions
using CPR (Constant Prepayment Rate), CDR (Constant Default Rate), and loss
severity parameters.

The :class:`CollateralModel` generates monthly cashflows based on:

- **Scheduled principal**: Amortization payments from the mortgage pool.
- **Prepayments**: Voluntary principal payoffs above scheduled amounts.
- **Defaults**: Involuntary loss events (foreclosure, charge-off).
- **Recoveries**: Post-default recoveries (REO sales, short sales).
- **Servicer advances**: Interest advances when borrowers are delinquent.

This model uses the Single Monthly Mortality (SMM) methodology to convert
annual CPR/CDR rates to monthly rates.

Example
-------
>>> from rmbs_platform.engine.collateral import CollateralModel
>>> model = CollateralModel(original_balance=1e6, wac=0.05, wam=360)
>>> cashflows = model.generate_cashflows(
...     periods=60, cpr_vector=0.10, cdr_vector=0.01, sev_vector=0.40
... )
>>> print(cashflows[["Period", "InterestCollected", "PrincipalCollected"]].head())

See Also
--------
ml.portfolio.SurveillanceEngine : ML-driven cashflow generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
