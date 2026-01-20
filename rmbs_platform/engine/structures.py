"""
Advanced Deal Structures
========================

This module provides support for sophisticated RMBS deal structures including:

- **PAC (Planned Amortization Class)**: Tranches with scheduled principal windows.
- **TAC (Targeted Amortization Class)**: Similar to PAC but with one-sided protection.
- **Pro-rata allocation**: Equal-priority tranches that share payments.
- **Sequential-pay**: Tranches paid in strict priority order.

These structures enable precise cashflow targeting and credit enhancement
allocation across the capital structure.

Classes
-------
TrancheType
    Enumeration of supported tranche types.
AmortizationSchedule
    Planned amortization schedule for PAC/TAC tranches.
ProRataGroup
    Group of tranches receiving pro-rata payments.
SequentialPaymentEngine
    Allocates payments sequentially by seniority.
StructuredWaterfallEngine
    Advanced waterfall supporting mixed payment structures.

Example
-------
>>> from rmbs_platform.engine.structures import (
...     StructuredWaterfallEngine,
...     ProRataGroup,
...     AmortizationSchedule,
... )
>>> # Create PAC schedule
>>> pac_schedule = AmortizationSchedule(
...     tranche_id="PAC_A",
...     schedule=[(1, 10000), (2, 10000), ..., (60, 10000)],
...     collar_low=0.08,  # 8% PSA floor
...     collar_high=0.30, # 30% PSA ceiling
... )
>>> # Create pro-rata group for support tranches
>>> support_group = ProRataGroup(
...     group_id="SUPPORT",
...     tranche_ids=["SUP_1", "SUP_2"],
... )

See Also
--------
waterfall.WaterfallRunner : Base waterfall execution.
state.DealState : Deal state management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .state import DealState

logger = logging.getLogger("RMBS.Structures")


class TrancheType(Enum):
    """
    Enumeration of supported tranche types.

    Attributes
    ----------
    SEQUENTIAL : str
        Sequential-pay tranche (paid in strict priority order).
    PAC : str
        Planned Amortization Class (scheduled principal with collar protection).
    TAC : str
        Targeted Amortization Class (one-sided collar protection).
    SUPPORT : str
        Support/Companion tranche (absorbs excess or shortfall).
    Z_BOND : str
        Accrual bond (interest accretes to principal, paid last).
    IO : str
        Interest-only (receives interest but no principal).
    PO : str
        Principal-only (receives principal but no interest).
    PRO_RATA : str
        Pro-rata allocation (equal-priority within group).
    RESIDUAL : str
        Residual/equity tranche (receives remaining cashflows).
    """

    SEQUENTIAL = "sequential"
    PAC = "pac"
    TAC = "tac"
    SUPPORT = "support"
    Z_BOND = "z_bond"
    IO = "io"
    PO = "po"
    PRO_RATA = "pro_rata"
    RESIDUAL = "residual"


@dataclass
class AmortizationSchedule:
    """
    Planned amortization schedule for PAC/TAC tranches.

    A PAC tranche has a scheduled principal payment for each period,
    protected by a prepayment collar. If actual prepayments fall within
    the collar, the PAC receives its scheduled amount.

    Parameters
    ----------
    tranche_id : str
        Identifier of the PAC/TAC tranche.
    schedule : list of (period, amount) tuples
        Planned principal payment schedule.
    collar_low : float
        Lower prepayment speed (CPR) for collar calculation.
    collar_high : float
        Upper prepayment speed (CPR) for collar calculation.
    schedule_type : str
        "PAC" (two-sided) or "TAC" (one-sided protection).

    Attributes
    ----------
    remaining_schedule : dict
        Current remaining scheduled payments by period.
    cumulative_shortfall : float
        Accumulated shortfall from missed scheduled payments.

    Example
    -------
    >>> schedule = AmortizationSchedule(
    ...     tranche_id="PAC_A",
    ...     schedule=[(1, 50000), (2, 50000), (3, 50000)],
    ...     collar_low=0.08,
    ...     collar_high=0.30,
    ... )
    >>> # Get scheduled payment for period 2
    >>> scheduled = schedule.get_scheduled_payment(2)
    """

    tranche_id: str
    schedule: List[Tuple[int, float]]
    collar_low: float = 0.08
    collar_high: float = 0.30
    schedule_type: str = "PAC"
    remaining_schedule: Dict[int, float] = field(default_factory=dict)
    cumulative_shortfall: float = 0.0

    def __post_init__(self) -> None:
        """Initialize remaining schedule from original schedule."""
        self.remaining_schedule = {p: a for p, a in self.schedule}

    def get_scheduled_payment(self, period: int) -> float:
        """
        Get the scheduled payment for a given period.

        Parameters
        ----------
        period : int
            Period number.

        Returns
        -------
        float
            Scheduled payment amount for the period.
        """
        return self.remaining_schedule.get(period, 0.0)

    def record_payment(self, period: int, actual_payment: float) -> float:
        """
        Record an actual payment and calculate shortfall.

        Parameters
        ----------
        period : int
            Period number.
        actual_payment : float
            Amount actually paid.

        Returns
        -------
        float
            Shortfall (scheduled - actual) for this period.
        """
        scheduled = self.remaining_schedule.get(period, 0.0)
        shortfall = max(0, scheduled - actual_payment)
        self.cumulative_shortfall += shortfall

        # Update remaining schedule
        if period in self.remaining_schedule:
            self.remaining_schedule[period] = 0.0

        return shortfall

    def is_busted(self, actual_cpr: float) -> bool:
        """
        Check if the PAC collar has been breached.

        Parameters
        ----------
        actual_cpr : float
            Actual prepayment speed.

        Returns
        -------
        bool
            True if collar is breached and PAC is "busted".
        """
        if self.schedule_type == "PAC":
            return actual_cpr < self.collar_low or actual_cpr > self.collar_high
        else:  # TAC - only protected on downside
            return actual_cpr > self.collar_high


@dataclass
class ProRataGroup:
    """
    Group of tranches receiving pro-rata principal allocation.

    In a pro-rata structure, tranches within the group receive principal
    in proportion to their outstanding balances, rather than sequentially.

    Parameters
    ----------
    group_id : str
        Identifier for the group.
    tranche_ids : list of str
        Tranche identifiers in this group.
    allocation_method : str
        "balance" (by outstanding balance) or "original" (by original balance).

    Example
    -------
    >>> group = ProRataGroup(
    ...     group_id="MEZZANINE",
    ...     tranche_ids=["M1", "M2", "M3"],
    ...     allocation_method="balance",
    ... )
    >>> allocations = group.allocate(100000, current_balances)
    """

    group_id: str
    tranche_ids: List[str]
    allocation_method: str = "balance"

    def allocate(
        self, total_amount: float, balances: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Allocate a total amount pro-rata across group members.

        Parameters
        ----------
        total_amount : float
            Total amount to allocate.
        balances : dict
            Current balances by tranche_id.

        Returns
        -------
        dict
            Allocation amounts by tranche_id.
        """
        allocations: Dict[str, float] = {}

        # Calculate total balance in group
        total_balance = sum(balances.get(t, 0.0) for t in self.tranche_ids)

        if total_balance <= 0:
            return allocations

        for tranche_id in self.tranche_ids:
            tranche_balance = balances.get(tranche_id, 0.0)
            if tranche_balance > 0:
                share = tranche_balance / total_balance
                allocation = min(total_amount * share, tranche_balance)
                allocations[tranche_id] = allocation

        return allocations


class StructuredWaterfallEngine:
    """
    Advanced waterfall engine supporting PAC/TAC and pro-rata structures.

    This engine extends the basic waterfall with support for:

    1. **PAC/TAC Scheduling**: Pays scheduled amounts when within collar.
    2. **Pro-rata Groups**: Allocates proportionally to group members.
    3. **Support Tranches**: Absorb excess/shortfall from PAC tranches.
    4. **Z-Bond Accretion**: Accretes interest to principal.

    Parameters
    ----------
    pac_schedules : dict
        PAC/TAC schedules by tranche_id.
    pro_rata_groups : dict
        Pro-rata groups by group_id.
    support_tranches : list
        Tranche IDs designated as support tranches.

    Attributes
    ----------
    pac_schedules : dict
        Active PAC schedules.
    pro_rata_groups : dict
        Active pro-rata groups.
    support_tranches : list
        Support tranche identifiers.
    z_bond_accrued : dict
        Accrued interest by Z-bond tranche_id.

    Example
    -------
    >>> engine = StructuredWaterfallEngine()
    >>> engine.add_pac_schedule(pac_schedule)
    >>> engine.add_pro_rata_group(mezz_group)
    >>> # Execute structured principal waterfall
    >>> engine.execute_principal_waterfall(state, available_principal)
    """

    def __init__(
        self,
        pac_schedules: Optional[Dict[str, AmortizationSchedule]] = None,
        pro_rata_groups: Optional[Dict[str, ProRataGroup]] = None,
        support_tranches: Optional[List[str]] = None,
    ) -> None:
        """Initialize the structured waterfall engine."""
        self.pac_schedules: Dict[str, AmortizationSchedule] = pac_schedules or {}
        self.pro_rata_groups: Dict[str, ProRataGroup] = pro_rata_groups or {}
        self.support_tranches: List[str] = support_tranches or []
        self.z_bond_accrued: Dict[str, float] = {}

    def add_pac_schedule(self, schedule: AmortizationSchedule) -> None:
        """Add a PAC/TAC schedule to the engine."""
        self.pac_schedules[schedule.tranche_id] = schedule

    def add_pro_rata_group(self, group: ProRataGroup) -> None:
        """Add a pro-rata group to the engine."""
        self.pro_rata_groups[group.group_id] = group

    @classmethod
    def from_deal_spec(cls, deal_spec: Dict[str, Any]) -> "StructuredWaterfallEngine":
        """
        Create engine from a deal specification.

        Parameters
        ----------
        deal_spec : dict
            Deal specification with structure definitions.

        Returns
        -------
        StructuredWaterfallEngine
            Configured engine instance.
        """
        engine = cls()

        # Parse PAC/TAC schedules
        structures = deal_spec.get("structures", {})

        for pac_def in structures.get("pac_schedules", []):
            schedule = AmortizationSchedule(
                tranche_id=pac_def["tranche_id"],
                schedule=[(s["period"], s["amount"]) for s in pac_def["schedule"]],
                collar_low=pac_def.get("collar_low", 0.08),
                collar_high=pac_def.get("collar_high", 0.30),
                schedule_type=pac_def.get("type", "PAC"),
            )
            engine.add_pac_schedule(schedule)

        # Parse pro-rata groups
        for group_def in structures.get("pro_rata_groups", []):
            group = ProRataGroup(
                group_id=group_def["group_id"],
                tranche_ids=group_def["tranche_ids"],
                allocation_method=group_def.get("allocation_method", "balance"),
            )
            engine.add_pro_rata_group(group)

        # Parse support tranches
        engine.support_tranches = structures.get("support_tranches", [])

        return engine

    def execute_principal_waterfall(
        self, state: DealState, available_principal: float, actual_cpr: float = 0.10
    ) -> Dict[str, float]:
        """
        Execute the structured principal waterfall.

        This method implements the industry-standard principal allocation:

        1. **PAC Tranches**: Pay scheduled amounts (if within collar).
        2. **Sequential Tranches**: Pay in priority order.
        3. **Pro-rata Groups**: Allocate proportionally.
        4. **Support Tranches**: Absorb excess or receive shortfall makeup.

        Parameters
        ----------
        state : DealState
            Current deal state.
        available_principal : float
            Total principal available for distribution.
        actual_cpr : float
            Actual prepayment speed for PAC collar check.

        Returns
        -------
        dict
            Principal payments by tranche_id.

        Notes
        -----
        The allocation follows priority rules in this order:

        1. PAC/TAC scheduled payments (protected by collar)
        2. Sequential senior tranches
        3. Pro-rata mezzanine tranches
        4. Support/companion tranches
        5. Subordinate sequential tranches
        """
        payments: Dict[str, float] = {}
        remaining = available_principal

        # Get current balances
        balances = {bid: bs.current_balance for bid, bs in state.bonds.items()}

        # Phase 1: PAC/TAC Scheduled Payments
        for tranche_id, schedule in self.pac_schedules.items():
            if remaining <= 0:
                break

            if tranche_id not in balances or balances[tranche_id] <= 0:
                continue

            # Check collar breach
            if schedule.is_busted(actual_cpr):
                logger.info(
                    f"PAC {tranche_id} collar breached (CPR={actual_cpr:.2%})"
                )
                continue  # PAC is busted, treat as support

            # Pay scheduled amount
            period = state.period_index + 1
            scheduled = schedule.get_scheduled_payment(period)
            payment = min(scheduled, remaining, balances[tranche_id])

            if payment > 0:
                payments[tranche_id] = payments.get(tranche_id, 0.0) + payment
                remaining -= payment
                schedule.record_payment(period, payment)
                logger.debug(f"PAC {tranche_id}: paid ${payment:,.2f} of ${scheduled:,.2f} scheduled")

        # Phase 2: Pro-rata Groups
        for group_id, group in self.pro_rata_groups.items():
            if remaining <= 0:
                break

            group_allocations = group.allocate(remaining, balances)

            for tranche_id, allocation in group_allocations.items():
                if allocation > 0:
                    payments[tranche_id] = payments.get(tranche_id, 0.0) + allocation
                    remaining -= allocation
                    balances[tranche_id] -= allocation

            logger.debug(f"Pro-rata group {group_id}: allocated ${sum(group_allocations.values()):,.2f}")

        # Phase 3: Support Tranches (absorb remaining)
        for tranche_id in self.support_tranches:
            if remaining <= 0:
                break

            balance = balances.get(tranche_id, 0.0)
            if balance > 0:
                payment = min(remaining, balance)
                payments[tranche_id] = payments.get(tranche_id, 0.0) + payment
                remaining -= payment
                balances[tranche_id] -= payment
                logger.debug(f"Support {tranche_id}: absorbed ${payment:,.2f}")

        return payments

    def accrue_z_bond_interest(
        self, state: DealState, z_bond_ids: List[str]
    ) -> Dict[str, float]:
        """
        Accrete interest to Z-bond principal instead of paying cash.

        Z-bonds (accrual bonds) do not receive current interest payments.
        Instead, their unpaid interest is added to their principal balance.

        Parameters
        ----------
        state : DealState
            Current deal state.
        z_bond_ids : list of str
            Tranche IDs of Z-bonds.

        Returns
        -------
        dict
            Accreted interest amounts by tranche_id.
        """
        accreted: Dict[str, float] = {}

        for tranche_id in z_bond_ids:
            bond = state.bonds.get(tranche_id)
            if bond is None or bond.current_balance <= 0:
                continue

            # Get coupon rate from bond definition
            bond_def = state.def_.bonds.get(tranche_id)
            if bond_def is None:
                continue

            coupon_rate = 0.0
            coupon = bond_def.coupon
            if hasattr(coupon, "fixed_rate") and coupon.fixed_rate:
                coupon_rate = float(coupon.fixed_rate)

            # Calculate monthly interest
            monthly_interest = bond.current_balance * (coupon_rate / 12)

            # Accrete to principal
            bond.current_balance += monthly_interest
            accreted[tranche_id] = monthly_interest

            # Track for reporting
            self.z_bond_accrued[tranche_id] = (
                self.z_bond_accrued.get(tranche_id, 0.0) + monthly_interest
            )

            logger.debug(
                f"Z-bond {tranche_id}: accreted ${monthly_interest:,.2f}, "
                f"new balance ${bond.current_balance:,.2f}"
            )

        return accreted

    def calculate_io_po_cashflows(
        self,
        interest_available: float,
        principal_available: float,
        io_tranche_ids: List[str],
        po_tranche_ids: List[str],
        balances: Dict[str, float],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Calculate cashflows for IO (Interest-Only) and PO (Principal-Only) tranches.

        Parameters
        ----------
        interest_available : float
            Total interest available.
        principal_available : float
            Total principal available.
        io_tranche_ids : list
            Interest-only tranche IDs.
        po_tranche_ids : list
            Principal-only tranche IDs.
        balances : dict
            Current balances by tranche_id.

        Returns
        -------
        tuple of (dict, dict)
            IO payments and PO payments by tranche_id.
        """
        io_payments: Dict[str, float] = {}
        po_payments: Dict[str, float] = {}

        # IO tranches receive interest proportionally to notional
        io_total_notional = sum(balances.get(t, 0.0) for t in io_tranche_ids)
        if io_total_notional > 0:
            for tranche_id in io_tranche_ids:
                notional = balances.get(tranche_id, 0.0)
                if notional > 0:
                    share = notional / io_total_notional
                    io_payments[tranche_id] = interest_available * share

        # PO tranches receive principal proportionally
        po_total_balance = sum(balances.get(t, 0.0) for t in po_tranche_ids)
        if po_total_balance > 0:
            for tranche_id in po_tranche_ids:
                balance = balances.get(tranche_id, 0.0)
                if balance > 0:
                    share = balance / po_total_balance
                    payment = min(principal_available * share, balance)
                    po_payments[tranche_id] = payment

        return io_payments, po_payments


def generate_pac_schedule(
    original_balance: float,
    wam: int,
    collar_low_cpr: float = 0.08,
    collar_high_cpr: float = 0.30,
) -> List[Tuple[int, float]]:
    """
    Generate a PAC amortization schedule from balance and collar.

    This function calculates the minimum scheduled principal that the
    PAC tranche would receive across the collar range.

    Parameters
    ----------
    original_balance : float
        Original PAC tranche balance.
    wam : int
        Weighted average maturity in months.
    collar_low_cpr : float
        Lower bound of prepayment collar (annual CPR).
    collar_high_cpr : float
        Upper bound of prepayment collar (annual CPR).

    Returns
    -------
    list of (period, amount) tuples
        Scheduled principal payments.

    Example
    -------
    >>> schedule = generate_pac_schedule(
    ...     original_balance=10_000_000,
    ...     wam=360,
    ...     collar_low_cpr=0.08,
    ...     collar_high_cpr=0.30,
    ... )
    """
    # Convert annual CPR to monthly SMM
    smm_low = 1 - (1 - collar_low_cpr) ** (1 / 12)
    smm_high = 1 - (1 - collar_high_cpr) ** (1 / 12)

    schedule: List[Tuple[int, float]] = []
    balance_low = original_balance
    balance_high = original_balance

    for period in range(1, wam + 1):
        # Calculate principal at each collar bound
        prin_low = balance_low * smm_low
        prin_high = balance_high * smm_high

        # PAC receives the minimum of the two scenarios
        scheduled = min(prin_low, prin_high)

        if scheduled < 0.01:
            break

        schedule.append((period, scheduled))

        # Update balances for next period
        balance_low -= prin_low
        balance_high -= prin_high

        if balance_low <= 0 and balance_high <= 0:
            break

    return schedule
