"""
Servicer Advance Mechanics
==========================

This module implements servicer advancing functionality, a critical component
of RMBS deal mechanics that ensures bond investors receive timely payments
even when underlying borrowers are delinquent.

Servicer Advancing Overview
---------------------------
When borrowers miss payments, the servicer advances funds to:

1. **P&I Advances**: Cover missed principal and interest payments.
2. **T&I Advances**: Cover tax and insurance escrow shortfalls.
3. **Corporate Advances**: Cover foreclosure and liquidation costs.

Advances are typically reimbursable from future collections or liquidation
proceeds, with priority over other distributions.

Industry Standards
------------------
- **Fannie Mae/Freddie Mac**: Servicers must advance P&I until loan is 120 days delinquent.
- **Private Label**: Varies by PSA, often advances until deemed non-recoverable.
- **Advance Stop**: Servicer stops advancing when deemed unlikely to recover.

Classes
-------
AdvanceType
    Types of servicer advances.
AdvancePolicy
    Configuration for when/how to advance.
ServicerAdvanceEngine
    Calculates and tracks servicer advances.
AdvanceRecoveryEngine
    Manages advance reimbursement.

Example
-------
>>> from rmbs_platform.engine.servicer import ServicerAdvanceEngine, AdvancePolicy
>>> policy = AdvancePolicy(
...     max_delinquency_months=4,
...     advance_pi=True,
...     advance_ti=True,
... )
>>> engine = ServicerAdvanceEngine(policy)
>>> advances = engine.calculate_advances(loan_df, period=6)

See Also
--------
waterfall.WaterfallRunner : Uses advances in waterfall execution.
state.DealState : Tracks advance balances.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("RMBS.Servicer")


class AdvanceType(Enum):
    """
    Types of servicer advances.

    Attributes
    ----------
    PI : str
        Principal and interest advances.
    TI : str
        Tax and insurance escrow advances.
    CORPORATE : str
        Foreclosure, legal, and property preservation costs.
    """

    PI = "principal_interest"
    TI = "tax_insurance"
    CORPORATE = "corporate"


@dataclass
class AdvancePolicy:
    """
    Configuration for servicer advancing behavior.

    This policy defines the rules for when the servicer will advance
    funds and when they will stop (the "advance stop" trigger).

    Parameters
    ----------
    advance_pi : bool
        Whether to advance principal and interest.
    advance_ti : bool
        Whether to advance tax and insurance.
    advance_corporate : bool
        Whether to advance corporate expenses.
    max_delinquency_months : int
        Stop P&I advances after this many months delinquent.
    non_recoverable_threshold : float
        Stop advances if LTV exceeds this threshold.
    max_advance_rate : float
        Maximum advance as percentage of original balance.
    recovery_priority : list
        Order of advance recovery types.

    Example
    -------
    >>> policy = AdvancePolicy(
    ...     advance_pi=True,
    ...     max_delinquency_months=4,
    ...     non_recoverable_threshold=1.20,  # 120% LTV
    ... )
    """

    advance_pi: bool = True
    advance_ti: bool = True
    advance_corporate: bool = True
    max_delinquency_months: int = 4
    non_recoverable_threshold: float = 1.20
    max_advance_rate: float = 0.50
    recovery_priority: List[AdvanceType] = field(
        default_factory=lambda: [
            AdvanceType.PI,
            AdvanceType.TI,
            AdvanceType.CORPORATE,
        ]
    )


@dataclass
class AdvanceRecord:
    """
    Record of a single advance transaction.

    Attributes
    ----------
    loan_id : str
        Identifier of the loan.
    advance_type : AdvanceType
        Type of advance.
    amount : float
        Amount advanced.
    period : int
        Period in which advance was made.
    date : date
        Date of advance.
    recovered : float
        Amount recovered so far.
    is_non_recoverable : bool
        Whether deemed non-recoverable.
    """

    loan_id: str
    advance_type: AdvanceType
    amount: float
    period: int
    date: date
    recovered: float = 0.0
    is_non_recoverable: bool = False

    @property
    def outstanding(self) -> float:
        """Return outstanding (unreimbursed) advance amount."""
        return max(0.0, self.amount - self.recovered)


class ServicerAdvanceEngine:
    """
    Calculate and track servicer advances for delinquent loans.

    This engine implements industry-standard advancing logic:

    1. Identify delinquent loans requiring advances.
    2. Calculate required P&I, T&I, and corporate advances.
    3. Apply advance stop rules (max delinquency, non-recoverable).
    4. Track cumulative advances by loan and type.

    Parameters
    ----------
    policy : AdvancePolicy
        Advancing configuration.

    Attributes
    ----------
    policy : AdvancePolicy
        Active policy.
    advance_history : list of AdvanceRecord
        Historical advance records.
    cumulative_advances : dict
        Cumulative advances by (loan_id, advance_type).

    Example
    -------
    >>> engine = ServicerAdvanceEngine(AdvancePolicy())
    >>> # Calculate advances for period
    >>> advances = engine.calculate_advances(delinquent_loans, period=6)
    >>> print(f"Total P&I advances: ${advances['pi_total']:,.2f}")
    """

    def __init__(self, policy: Optional[AdvancePolicy] = None) -> None:
        """Initialize with advancing policy."""
        self.policy = policy or AdvancePolicy()
        self.advance_history: List[AdvanceRecord] = []
        self.cumulative_advances: Dict[Tuple[str, AdvanceType], float] = {}

    def calculate_advances(
        self,
        loan_df: pd.DataFrame,
        period: int,
        current_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Calculate required advances for delinquent loans.

        Parameters
        ----------
        loan_df : pd.DataFrame
            Loan-level data with columns:
            - LoanId: Loan identifier
            - DelinquencyStatus: Months delinquent (0 = current)
            - ScheduledPrincipal: Scheduled principal payment
            - ScheduledInterest: Scheduled interest payment
            - EscrowShortfall: Tax/insurance escrow shortfall
            - CurrentLTV: Current loan-to-value ratio
            - OriginalBalance: Original loan balance
        period : int
            Current period number.
        current_date : date, optional
            Date of advances.

        Returns
        -------
        dict
            Advance summary:
            - pi_total: Total P&I advances
            - ti_total: Total T&I advances
            - corporate_total: Total corporate advances
            - total: Grand total
            - loan_count: Number of loans with advances
            - details: List of per-loan advance amounts
        """
        if current_date is None:
            current_date = date.today()

        result = {
            "pi_total": 0.0,
            "ti_total": 0.0,
            "corporate_total": 0.0,
            "total": 0.0,
            "loan_count": 0,
            "details": [],
        }

        for _, loan in loan_df.iterrows():
            loan_advances = self._calculate_loan_advances(loan, period, current_date)

            if loan_advances["total"] > 0:
                result["pi_total"] += loan_advances["pi"]
                result["ti_total"] += loan_advances["ti"]
                result["corporate_total"] += loan_advances["corporate"]
                result["total"] += loan_advances["total"]
                result["loan_count"] += 1
                result["details"].append(loan_advances)

        logger.info(
            f"Period {period}: Calculated ${result['total']:,.2f} in advances "
            f"for {result['loan_count']} loans"
        )

        return result

    def _calculate_loan_advances(
        self, loan: pd.Series, period: int, current_date: date
    ) -> Dict[str, Any]:
        """Calculate advances for a single loan."""
        loan_id = str(loan.get("LoanId", loan.name))
        delinquency = int(loan.get("DelinquencyStatus", 0))
        current_ltv = float(loan.get("CurrentLTV", loan.get("LTV", 80.0)))
        orig_balance = float(loan.get("OriginalBalance", loan.get("ORIG_UPB", 0.0)))

        result = {
            "loan_id": loan_id,
            "delinquency_status": delinquency,
            "pi": 0.0,
            "ti": 0.0,
            "corporate": 0.0,
            "total": 0.0,
            "advance_stop": False,
            "stop_reason": None,
        }

        # Check advance stop conditions
        if delinquency == 0:
            return result  # Loan is current, no advance needed

        if delinquency > self.policy.max_delinquency_months:
            result["advance_stop"] = True
            result["stop_reason"] = "max_delinquency_exceeded"
            return result

        if current_ltv > self.policy.non_recoverable_threshold * 100:
            result["advance_stop"] = True
            result["stop_reason"] = "non_recoverable_ltv"
            return result

        # Check cumulative advance limit
        cumulative = self._get_cumulative_advances(loan_id)
        max_advance = orig_balance * self.policy.max_advance_rate
        if cumulative >= max_advance:
            result["advance_stop"] = True
            result["stop_reason"] = "max_advance_exceeded"
            return result

        # Calculate P&I advance
        if self.policy.advance_pi:
            sched_prin = float(loan.get("ScheduledPrincipal", 0.0))
            sched_int = float(loan.get("ScheduledInterest", 0.0))
            pi_advance = sched_prin + sched_int

            # Cap at remaining advance capacity
            pi_advance = min(pi_advance, max_advance - cumulative)

            if pi_advance > 0:
                result["pi"] = pi_advance
                self._record_advance(
                    loan_id, AdvanceType.PI, pi_advance, period, current_date
                )

        # Calculate T&I advance
        if self.policy.advance_ti:
            escrow_shortfall = float(loan.get("EscrowShortfall", 0.0))
            if escrow_shortfall > 0:
                ti_advance = min(
                    escrow_shortfall, max_advance - cumulative - result["pi"]
                )
                if ti_advance > 0:
                    result["ti"] = ti_advance
                    self._record_advance(
                        loan_id, AdvanceType.TI, ti_advance, period, current_date
                    )

        result["total"] = result["pi"] + result["ti"] + result["corporate"]
        return result

    def _record_advance(
        self,
        loan_id: str,
        advance_type: AdvanceType,
        amount: float,
        period: int,
        advance_date: date,
    ) -> None:
        """Record an advance transaction."""
        record = AdvanceRecord(
            loan_id=loan_id,
            advance_type=advance_type,
            amount=amount,
            period=period,
            date=advance_date,
        )
        self.advance_history.append(record)

        key = (loan_id, advance_type)
        self.cumulative_advances[key] = (
            self.cumulative_advances.get(key, 0.0) + amount
        )

    def _get_cumulative_advances(self, loan_id: str) -> float:
        """Get total cumulative advances for a loan."""
        total = 0.0
        for adv_type in AdvanceType:
            total += self.cumulative_advances.get((loan_id, adv_type), 0.0)
        return total

    def get_outstanding_advances(self) -> Dict[AdvanceType, float]:
        """
        Get total outstanding (unreimbursed) advances by type.

        Returns
        -------
        dict
            Outstanding amounts by AdvanceType.
        """
        outstanding: Dict[AdvanceType, float] = {t: 0.0 for t in AdvanceType}

        for record in self.advance_history:
            if record.outstanding > 0 and not record.is_non_recoverable:
                outstanding[record.advance_type] += record.outstanding

        return outstanding

    def get_advance_summary(self) -> pd.DataFrame:
        """
        Generate a summary of all advances.

        Returns
        -------
        pd.DataFrame
            Advance summary with columns: period, type, amount, recovered, outstanding.
        """
        if not self.advance_history:
            return pd.DataFrame()

        records = []
        for adv in self.advance_history:
            records.append({
                "period": adv.period,
                "loan_id": adv.loan_id,
                "type": adv.advance_type.value,
                "amount": adv.amount,
                "recovered": adv.recovered,
                "outstanding": adv.outstanding,
                "non_recoverable": adv.is_non_recoverable,
            })

        return pd.DataFrame(records)


class AdvanceRecoveryEngine:
    """
    Manage recovery and reimbursement of servicer advances.

    Advances are typically recovered from:
    1. Future borrower payments (when loan cures)
    2. Liquidation proceeds (when property is sold)
    3. Loss severity (write-off if non-recoverable)

    Parameters
    ----------
    servicer_engine : ServicerAdvanceEngine
        The advance engine tracking advances.

    Example
    -------
    >>> recovery = AdvanceRecoveryEngine(servicer_engine)
    >>> # Loan cured, recover advances
    >>> recovered = recovery.recover_from_cure(loan_id="LOAN123", payment=5000)
    >>> # Liquidation proceeds
    >>> recovered = recovery.recover_from_liquidation(
    ...     loan_id="LOAN456",
    ...     net_proceeds=150000,
    ... )
    """

    def __init__(self, servicer_engine: ServicerAdvanceEngine) -> None:
        """Initialize with servicer advance engine."""
        self.servicer = servicer_engine

    def recover_from_cure(
        self, loan_id: str, payment: float
    ) -> Dict[str, Any]:
        """
        Recover advances when a loan cures (borrower catches up).

        Parameters
        ----------
        loan_id : str
            Loan identifier.
        payment : float
            Amount received from borrower.

        Returns
        -------
        dict
            Recovery details:
            - total_recovered: Amount applied to advances
            - remaining_payment: Amount left for regular distribution
            - by_type: Recovered amounts by advance type
        """
        result = {
            "loan_id": loan_id,
            "total_recovered": 0.0,
            "remaining_payment": payment,
            "by_type": {t: 0.0 for t in AdvanceType},
        }

        # Apply payment to advances in priority order
        for adv_type in self.servicer.policy.recovery_priority:
            for record in self.servicer.advance_history:
                if (
                    record.loan_id == loan_id
                    and record.advance_type == adv_type
                    and record.outstanding > 0
                    and result["remaining_payment"] > 0
                ):
                    recovery = min(record.outstanding, result["remaining_payment"])
                    record.recovered += recovery
                    result["total_recovered"] += recovery
                    result["remaining_payment"] -= recovery
                    result["by_type"][adv_type] += recovery

        logger.info(
            f"Loan {loan_id} cure: recovered ${result['total_recovered']:,.2f} "
            f"of advances, ${result['remaining_payment']:,.2f} remaining"
        )

        return result

    def recover_from_liquidation(
        self,
        loan_id: str,
        net_proceeds: float,
        liquidation_expenses: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Recover advances from property liquidation proceeds.

        Liquidation waterfall priority:
        1. Liquidation expenses (already deducted in net_proceeds)
        2. Outstanding servicer advances
        3. Principal balance
        4. Any remainder to deal

        Parameters
        ----------
        loan_id : str
            Loan identifier.
        net_proceeds : float
            Net liquidation proceeds after expenses.
        liquidation_expenses : float
            Additional expenses to deduct.

        Returns
        -------
        dict
            Recovery details.
        """
        available = net_proceeds - liquidation_expenses

        result = {
            "loan_id": loan_id,
            "gross_proceeds": net_proceeds,
            "liquidation_expenses": liquidation_expenses,
            "advances_recovered": 0.0,
            "principal_recovered": 0.0,
            "loss_severity": 0.0,
            "by_type": {t: 0.0 for t in AdvanceType},
        }

        # Recover advances first
        for adv_type in self.servicer.policy.recovery_priority:
            for record in self.servicer.advance_history:
                if (
                    record.loan_id == loan_id
                    and record.advance_type == adv_type
                    and record.outstanding > 0
                    and available > 0
                ):
                    recovery = min(record.outstanding, available)
                    record.recovered += recovery
                    result["advances_recovered"] += recovery
                    available -= recovery
                    result["by_type"][adv_type] += recovery

        # Remaining goes to principal recovery
        result["principal_recovered"] = available

        # Mark unrecovered advances as non-recoverable
        for record in self.servicer.advance_history:
            if record.loan_id == loan_id and record.outstanding > 0:
                record.is_non_recoverable = True
                result["loss_severity"] += record.outstanding

        logger.info(
            f"Loan {loan_id} liquidation: "
            f"advances recovered=${result['advances_recovered']:,.2f}, "
            f"principal=${result['principal_recovered']:,.2f}, "
            f"loss=${result['loss_severity']:,.2f}"
        )

        return result

    def write_off_non_recoverable(self, loan_id: str) -> float:
        """
        Write off all advances for a loan as non-recoverable.

        Parameters
        ----------
        loan_id : str
            Loan identifier.

        Returns
        -------
        float
            Total amount written off.
        """
        written_off = 0.0

        for record in self.servicer.advance_history:
            if record.loan_id == loan_id and record.outstanding > 0:
                record.is_non_recoverable = True
                written_off += record.outstanding

        logger.info(f"Loan {loan_id}: wrote off ${written_off:,.2f} in non-recoverable advances")
        return written_off


def integrate_advances_to_waterfall(
    advances: Dict[str, Any],
    state: "DealState",
    fund_id: str = "IAF",
) -> None:
    """
    Add servicer advances to waterfall funds for distribution.

    This function bridges the servicer advance engine with the waterfall,
    depositing advances into the appropriate fund for distribution.

    Parameters
    ----------
    advances : dict
        Advance calculation result from ServicerAdvanceEngine.
    state : DealState
        Current deal state.
    fund_id : str
        Fund to deposit P&I advances (typically IAF or PAF).

    Notes
    -----
    P&I advances go to the Interest Available Fund (IAF) and Principal
    Available Fund (PAF) proportionally. The advances are tracked in
    state variables for reporting.
    """
    pi_total = advances.get("pi_total", 0.0)

    if pi_total > 0:
        state.deposit_funds(fund_id, pi_total)
        state.set_variable("ServicerAdvancesPI", pi_total)
        logger.debug(f"Deposited ${pi_total:,.2f} in P&I advances to {fund_id}")

    # Track in state variables
    state.set_variable("ServicerAdvancesTotal", advances.get("total", 0.0))
    state.set_variable("ServicerAdvancesTI", advances.get("ti_total", 0.0))
    state.set_variable("ServicerAdvancesCorporate", advances.get("corporate_total", 0.0))
    state.set_variable("ServicerAdvancesLoanCount", advances.get("loan_count", 0))
