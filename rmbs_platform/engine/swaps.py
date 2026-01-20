"""
Interest Rate Swap Settlement
=============================

This module implements interest rate swap mechanics for RMBS deals.
Swaps are commonly used to:

1. **Convert Rate Risk**: Transform floating-rate collateral cashflows to fixed.
2. **Hedge Basis Risk**: Manage mismatch between collateral index and bond index.
3. **Create Inverse Floaters**: Synthetic tranches with inverse rate exposure.

Swap Types
----------
- **Pay-Fixed/Receive-Float**: Deal pays fixed rate, receives floating index.
- **Pay-Float/Receive-Fixed**: Deal pays floating index, receives fixed rate.
- **Basis Swap**: Exchange one floating index for another (e.g., SOFR vs. Prime).

Settlement
----------
Net swap payments are settled each period:

    Net Payment = (Receive Rate - Pay Rate) × Notional × Day Count Factor

If net > 0, swap counterparty pays the deal (deposited to IAF).
If net < 0, deal pays swap counterparty (deducted from IAF).

Classes
-------
SwapType
    Enumeration of swap types.
SwapDefinition
    Configuration for a single swap contract.
SwapSettlementEngine
    Calculates net swap payments.
CappedSwap
    Interest rate cap/floor mechanics.

Example
-------
>>> from rmbs_platform.engine.swaps import SwapSettlementEngine, SwapDefinition
>>> swap = SwapDefinition(
...     swap_id="SWAP_1",
...     notional=10_000_000,
...     fixed_rate=0.045,
...     floating_index="SOFR",
...     pay_fixed=True,
... )
>>> engine = SwapSettlementEngine([swap])
>>> settlement = engine.settle(period=6, current_index_rate=0.0525)

See Also
--------
waterfall.WaterfallRunner : Integrates swap payments into waterfall.
config.settings : Default rate assumptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("RMBS.Swaps")


class SwapType(Enum):
    """
    Types of interest rate swaps.

    Attributes
    ----------
    FIXED_FOR_FLOATING : str
        Pay fixed, receive floating (most common in RMBS).
    FLOATING_FOR_FIXED : str
        Pay floating, receive fixed.
    BASIS : str
        Exchange one floating index for another.
    CAP : str
        Interest rate cap (receive payout when rate exceeds strike).
    FLOOR : str
        Interest rate floor (receive payout when rate below strike).
    COLLAR : str
        Combined cap and floor.
    """

    FIXED_FOR_FLOATING = "fixed_for_floating"
    FLOATING_FOR_FIXED = "floating_for_fixed"
    BASIS = "basis"
    CAP = "cap"
    FLOOR = "floor"
    COLLAR = "collar"


class DayCountConvention(Enum):
    """
    Day count conventions for interest calculation.

    Attributes
    ----------
    ACTUAL_360 : str
        Actual days / 360 (money market convention).
    ACTUAL_365 : str
        Actual days / 365.
    THIRTY_360 : str
        30/360 (bond basis).
    ACTUAL_ACTUAL : str
        Actual/actual (ISDA).
    """

    ACTUAL_360 = "ACT/360"
    ACTUAL_365 = "ACT/365"
    THIRTY_360 = "30/360"
    ACTUAL_ACTUAL = "ACT/ACT"


@dataclass
class SwapDefinition:
    """
    Configuration for an interest rate swap contract.

    Parameters
    ----------
    swap_id : str
        Unique identifier for the swap.
    notional : float
        Notional amount (typically tracks collateral balance).
    fixed_rate : float
        Fixed rate for the swap leg (annual rate as decimal).
    floating_index : str
        Name of the floating rate index (SOFR, LIBOR, Prime, etc.).
    spread : float
        Spread added to floating index (in decimal).
    pay_fixed : bool
        True if deal pays fixed and receives floating.
    day_count : DayCountConvention
        Day count convention for interest calculation.
    start_date : date, optional
        Effective date of swap.
    maturity_date : date, optional
        Termination date of swap.
    amortizing : bool
        Whether notional amortizes with collateral.
    cap_rate : float, optional
        Maximum rate for capped swaps.
    floor_rate : float, optional
        Minimum rate for floored swaps.
    counterparty : str
        Swap counterparty name.
    priority : int
        Payment priority in waterfall (lower = higher priority).

    Example
    -------
    >>> swap = SwapDefinition(
    ...     swap_id="SWAP_A",
    ...     notional=50_000_000,
    ...     fixed_rate=0.0450,
    ...     floating_index="SOFR",
    ...     spread=0.0025,
    ...     pay_fixed=True,
    ... )
    """

    swap_id: str
    notional: float
    fixed_rate: float
    floating_index: str = "SOFR"
    spread: float = 0.0
    pay_fixed: bool = True
    day_count: DayCountConvention = DayCountConvention.THIRTY_360
    start_date: Optional[date] = None
    maturity_date: Optional[date] = None
    amortizing: bool = True
    cap_rate: Optional[float] = None
    floor_rate: Optional[float] = None
    counterparty: str = "SwapCo"
    priority: int = 1

    @property
    def swap_type(self) -> SwapType:
        """Determine swap type from configuration."""
        if self.cap_rate is not None and self.floor_rate is not None:
            return SwapType.COLLAR
        elif self.cap_rate is not None:
            return SwapType.CAP
        elif self.floor_rate is not None:
            return SwapType.FLOOR
        elif self.pay_fixed:
            return SwapType.FIXED_FOR_FLOATING
        else:
            return SwapType.FLOATING_FOR_FIXED


@dataclass
class SwapSettlement:
    """
    Result of a swap settlement calculation.

    Attributes
    ----------
    swap_id : str
        Swap identifier.
    period : int
        Period number.
    notional : float
        Notional amount for period.
    fixed_amount : float
        Fixed leg amount.
    floating_amount : float
        Floating leg amount.
    net_payment : float
        Net payment (positive = deal receives, negative = deal pays).
    index_rate : float
        Floating index rate used.
    all_in_rate : float
        Floating rate including spread.
    """

    swap_id: str
    period: int
    notional: float
    fixed_amount: float
    floating_amount: float
    net_payment: float
    index_rate: float
    all_in_rate: float


class SwapSettlementEngine:
    """
    Calculate net swap payments for RMBS deals.

    This engine processes all swaps in a deal and calculates the net
    payment due each period. Positive payments are deposited to the
    Interest Available Fund; negative payments are deducted.

    Parameters
    ----------
    swaps : list of SwapDefinition
        Swap contracts in the deal.
    index_rates : dict
        Current index rates by name (e.g., {"SOFR": 0.0525}).

    Attributes
    ----------
    swaps : list
        Active swap contracts.
    index_rates : dict
        Current index rate assumptions.
    settlement_history : list
        Historical settlement records.

    Example
    -------
    >>> engine = SwapSettlementEngine([swap1, swap2])
    >>> engine.set_index_rate("SOFR", 0.0525)
    >>> settlements = engine.settle_all(period=6, notional_factor=0.95)
    """

    def __init__(
        self,
        swaps: Optional[List[SwapDefinition]] = None,
        index_rates: Optional[Dict[str, float]] = None,
    ) -> None:
        """Initialize with swap definitions and index rates."""
        self.swaps = swaps or []
        self.index_rates = index_rates or {}
        self.settlement_history: List[SwapSettlement] = []

        # Default index rates (can be overridden)
        self._default_rates = {
            "SOFR": 0.0525,
            "LIBOR_1M": 0.0535,
            "LIBOR_3M": 0.0545,
            "PRIME": 0.0850,
            "TREASURY_1Y": 0.0480,
            "TREASURY_10Y": 0.0430,
        }

    def set_index_rate(self, index_name: str, rate: float) -> None:
        """Set or update an index rate."""
        self.index_rates[index_name] = rate

    def get_index_rate(self, index_name: str) -> float:
        """Get index rate with fallback to defaults."""
        return self.index_rates.get(
            index_name, self._default_rates.get(index_name, 0.05)
        )

    def add_swap(self, swap: SwapDefinition) -> None:
        """Add a swap to the engine."""
        self.swaps.append(swap)

    @classmethod
    def from_deal_spec(cls, deal_spec: Dict[str, Any]) -> "SwapSettlementEngine":
        """
        Create engine from deal specification.

        Parameters
        ----------
        deal_spec : dict
            Deal specification with swaps section.

        Returns
        -------
        SwapSettlementEngine
            Configured engine.
        """
        engine = cls()

        swaps_spec = deal_spec.get("swaps", [])
        for swap_def in swaps_spec:
            swap = SwapDefinition(
                swap_id=swap_def["swap_id"],
                notional=swap_def["notional"],
                fixed_rate=swap_def["fixed_rate"],
                floating_index=swap_def.get("floating_index", "SOFR"),
                spread=swap_def.get("spread", 0.0),
                pay_fixed=swap_def.get("pay_fixed", True),
                amortizing=swap_def.get("amortizing", True),
                cap_rate=swap_def.get("cap_rate"),
                floor_rate=swap_def.get("floor_rate"),
                counterparty=swap_def.get("counterparty", "SwapCo"),
                priority=swap_def.get("priority", 1),
            )
            engine.add_swap(swap)

        return engine

    def settle(
        self,
        swap: SwapDefinition,
        period: int,
        notional_factor: float = 1.0,
        index_rate_override: Optional[float] = None,
    ) -> SwapSettlement:
        """
        Calculate net settlement for a single swap.

        Parameters
        ----------
        swap : SwapDefinition
            Swap to settle.
        period : int
            Period number.
        notional_factor : float
            Factor to apply to notional (for amortizing swaps).
        index_rate_override : float, optional
            Override the floating index rate.

        Returns
        -------
        SwapSettlement
            Settlement calculation result.
        """
        # Determine current notional
        current_notional = swap.notional
        if swap.amortizing:
            current_notional *= notional_factor

        if current_notional <= 0:
            return SwapSettlement(
                swap_id=swap.swap_id,
                period=period,
                notional=0.0,
                fixed_amount=0.0,
                floating_amount=0.0,
                net_payment=0.0,
                index_rate=0.0,
                all_in_rate=0.0,
            )

        # Get floating rate
        index_rate = index_rate_override or self.get_index_rate(swap.floating_index)
        all_in_rate = index_rate + swap.spread

        # Apply cap/floor if defined
        if swap.cap_rate is not None:
            all_in_rate = min(all_in_rate, swap.cap_rate)
        if swap.floor_rate is not None:
            all_in_rate = max(all_in_rate, swap.floor_rate)

        # Calculate day count factor (simplified monthly)
        dcf = self._day_count_factor(swap.day_count)

        # Calculate leg amounts
        fixed_amount = current_notional * swap.fixed_rate * dcf
        floating_amount = current_notional * all_in_rate * dcf

        # Calculate net payment (positive = deal receives)
        if swap.pay_fixed:
            net_payment = floating_amount - fixed_amount
        else:
            net_payment = fixed_amount - floating_amount

        settlement = SwapSettlement(
            swap_id=swap.swap_id,
            period=period,
            notional=current_notional,
            fixed_amount=fixed_amount,
            floating_amount=floating_amount,
            net_payment=net_payment,
            index_rate=index_rate,
            all_in_rate=all_in_rate,
        )

        self.settlement_history.append(settlement)

        logger.debug(
            f"Swap {swap.swap_id} period {period}: "
            f"notional=${current_notional:,.0f}, "
            f"fixed={swap.fixed_rate:.4f}, float={all_in_rate:.4f}, "
            f"net=${net_payment:,.2f}"
        )

        return settlement

    def settle_all(
        self,
        period: int,
        notional_factor: float = 1.0,
        index_rates: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Settle all swaps for a period.

        Parameters
        ----------
        period : int
            Period number.
        notional_factor : float
            Factor for amortizing notionals.
        index_rates : dict, optional
            Override index rates for this period.

        Returns
        -------
        dict
            Summary of all settlements:
            - total_net: Total net payment across all swaps
            - settlements: List of individual SwapSettlement objects
            - by_counterparty: Net by counterparty
        """
        if index_rates:
            for name, rate in index_rates.items():
                self.set_index_rate(name, rate)

        settlements = []
        total_net = 0.0
        by_counterparty: Dict[str, float] = {}

        for swap in self.swaps:
            settlement = self.settle(swap, period, notional_factor)
            settlements.append(settlement)
            total_net += settlement.net_payment

            cp = swap.counterparty
            by_counterparty[cp] = by_counterparty.get(cp, 0.0) + settlement.net_payment

        result = {
            "period": period,
            "total_net": total_net,
            "settlements": settlements,
            "by_counterparty": by_counterparty,
            "deal_receives": total_net > 0,
        }

        logger.info(
            f"Period {period} swap settlement: "
            f"net=${total_net:,.2f} ({'receive' if total_net > 0 else 'pay'})"
        )

        return result

    def _day_count_factor(self, convention: DayCountConvention) -> float:
        """Calculate day count factor for monthly period."""
        if convention == DayCountConvention.ACTUAL_360:
            return 30 / 360
        elif convention == DayCountConvention.ACTUAL_365:
            return 30 / 365
        elif convention == DayCountConvention.THIRTY_360:
            return 1 / 12
        else:  # ACTUAL_ACTUAL
            return 30 / 365

    def get_settlement_history_df(self) -> "pd.DataFrame":
        """
        Get settlement history as a DataFrame.

        Returns
        -------
        pd.DataFrame
            Historical settlements.
        """
        import pandas as pd

        if not self.settlement_history:
            return pd.DataFrame()

        records = []
        for s in self.settlement_history:
            records.append({
                "period": s.period,
                "swap_id": s.swap_id,
                "notional": s.notional,
                "fixed_amount": s.fixed_amount,
                "floating_amount": s.floating_amount,
                "net_payment": s.net_payment,
                "index_rate": s.index_rate,
                "all_in_rate": s.all_in_rate,
            })

        return pd.DataFrame(records)


def integrate_swaps_to_waterfall(
    settlements: Dict[str, Any],
    state: "DealState",
    iaf_fund: str = "IAF",
) -> None:
    """
    Integrate swap settlements into the waterfall funds.

    Parameters
    ----------
    settlements : dict
        Settlement result from SwapSettlementEngine.settle_all().
    state : DealState
        Current deal state.
    iaf_fund : str
        Interest Available Fund identifier.

    Notes
    -----
    - Positive net: Deposit to IAF (deal receives from counterparty).
    - Negative net: Withdraw from IAF (deal pays counterparty).

    The net swap payment is handled before the interest waterfall,
    as swap payments typically have senior priority.
    """
    from .state import DealState

    total_net = settlements.get("total_net", 0.0)

    if total_net > 0:
        # Deal receives - deposit to IAF
        state.deposit_funds(iaf_fund, total_net)
        logger.debug(f"Deposited ${total_net:,.2f} swap receipt to {iaf_fund}")
    elif total_net < 0:
        # Deal pays - withdraw from IAF
        payment = abs(total_net)
        available = state.cash_balances.get(iaf_fund, 0.0)
        actual_payment = min(payment, available)

        if actual_payment > 0:
            state.withdraw_cash(iaf_fund, actual_payment)
            logger.debug(f"Withdrew ${actual_payment:,.2f} for swap payment from {iaf_fund}")

        if actual_payment < payment:
            shortfall = payment - actual_payment
            state.set_variable("SwapPaymentShortfall", shortfall)
            logger.warning(f"Swap payment shortfall: ${shortfall:,.2f}")

    # Track in state variables
    state.set_variable("SwapNetPayment", total_net)
    state.set_variable("SwapSettlementCount", len(settlements.get("settlements", [])))


@dataclass
class InterestRateCap:
    """
    Interest rate cap contract.

    A cap pays the holder when the reference rate exceeds the strike.
    Used to protect against rising rates.

    Parameters
    ----------
    cap_id : str
        Identifier for the cap.
    notional : float
        Notional amount.
    strike_rate : float
        Cap strike rate.
    reference_index : str
        Reference rate index.
    premium : float
        Upfront or periodic premium paid.

    Example
    -------
    >>> cap = InterestRateCap(
    ...     cap_id="CAP_1",
    ...     notional=10_000_000,
    ...     strike_rate=0.06,
    ...     reference_index="SOFR",
    ... )
    >>> payout = cap.calculate_payout(current_rate=0.065, period=6)
    """

    cap_id: str
    notional: float
    strike_rate: float
    reference_index: str = "SOFR"
    premium: float = 0.0
    amortizing: bool = True

    def calculate_payout(
        self, current_rate: float, notional_factor: float = 1.0
    ) -> float:
        """
        Calculate cap payout for current period.

        Parameters
        ----------
        current_rate : float
            Current reference rate.
        notional_factor : float
            Factor for amortizing notional.

        Returns
        -------
        float
            Cap payout amount (>= 0).
        """
        current_notional = self.notional
        if self.amortizing:
            current_notional *= notional_factor

        if current_rate <= self.strike_rate:
            return 0.0

        # Payout = max(0, rate - strike) × notional × dcf
        rate_excess = current_rate - self.strike_rate
        payout = current_notional * rate_excess / 12  # Monthly

        return payout


@dataclass
class InterestRateFloor:
    """
    Interest rate floor contract.

    A floor pays the holder when the reference rate falls below the strike.
    Used to protect against falling rates.

    Parameters
    ----------
    floor_id : str
        Identifier for the floor.
    notional : float
        Notional amount.
    strike_rate : float
        Floor strike rate.
    reference_index : str
        Reference rate index.
    """

    floor_id: str
    notional: float
    strike_rate: float
    reference_index: str = "SOFR"
    amortizing: bool = True

    def calculate_payout(
        self, current_rate: float, notional_factor: float = 1.0
    ) -> float:
        """
        Calculate floor payout for current period.

        Parameters
        ----------
        current_rate : float
            Current reference rate.
        notional_factor : float
            Factor for amortizing notional.

        Returns
        -------
        float
            Floor payout amount (>= 0).
        """
        current_notional = self.notional
        if self.amortizing:
            current_notional *= notional_factor

        if current_rate >= self.strike_rate:
            return 0.0

        # Payout = max(0, strike - rate) × notional × dcf
        rate_deficit = self.strike_rate - current_rate
        payout = current_notional * rate_deficit / 12  # Monthly

        return payout
