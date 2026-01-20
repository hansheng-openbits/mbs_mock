"""
Credit Enhancement Tracking Module for RMBS Engine.
====================================================

This module provides comprehensive tracking and analysis of credit
enhancement levels in structured finance transactions, including:

- Overcollateralization (OC) ratio calculation and triggers
- Interest Coverage (IC) ratio monitoring
- Subordination level tracking
- Reserve account analysis
- Excess spread capture mechanisms
- Credit enhancement waterfall modeling

Industry Context
----------------
Credit enhancement is the cornerstone of structured finance credit quality.
It provides protection to senior bondholders against collateral losses:

1. **Subordination**: Junior tranches absorb losses first
2. **Overcollateralization**: Collateral value exceeds bond par value
3. **Excess Spread**: Interest income exceeds bond coupon payments
4. **Reserve Accounts**: Cash buffers for shortfalls
5. **Guarantees**: External credit support (monoline wraps, etc.)

Key metrics follow rating agency methodologies:
- Moody's: OC and IC tests with trigger levels
- S&P: Credit enhancement floors and target levels
- Fitch: Loss coverage multiples

References
----------
- Moody's Global Structured Finance Operational Risk Guidelines
- S&P Structured Finance Criteria
- Fitch RMBS Rating Criteria

Examples
--------
>>> from rmbs_platform.engine.credit_enhancement import (
...     CreditEnhancementTracker, OCTest, ICTest
... )
>>> 
>>> # Initialize tracker
>>> tracker = CreditEnhancementTracker(deal_definition)
>>> 
>>> # Calculate current OC ratio
>>> oc_result = tracker.calculate_oc_ratio('ClassA')
>>> print(f"Class A OC: {oc_result.current_ratio:.2%}")
>>> 
>>> # Check all triggers
>>> trigger_status = tracker.check_all_triggers(current_state)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


# =============================================================================
# Enums and Constants
# =============================================================================

class TriggerType(str, Enum):
    """
    Types of credit enhancement triggers.
    
    Triggers determine when deal mechanics change based on performance.
    """
    
    OC_TEST = "OC_TEST"
    IC_TEST = "IC_TEST"
    DELINQUENCY = "DELINQUENCY"
    CUMULATIVE_LOSS = "CUMULATIVE_LOSS"
    CREDIT_EVENT = "CREDIT_EVENT"
    STEP_DOWN = "STEP_DOWN"
    STEP_UP = "STEP_UP"


class TriggerStatus(str, Enum):
    """
    Status of a trigger test.
    """
    
    PASSING = "PASSING"
    FAILING = "FAILING"
    CURED = "CURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EnhancementType(str, Enum):
    """
    Types of credit enhancement mechanisms.
    """
    
    SUBORDINATION = "SUBORDINATION"
    OVERCOLLATERALIZATION = "OVERCOLLATERALIZATION"
    EXCESS_SPREAD = "EXCESS_SPREAD"
    RESERVE_ACCOUNT = "RESERVE_ACCOUNT"
    LETTER_OF_CREDIT = "LETTER_OF_CREDIT"
    SURETY_BOND = "SURETY_BOND"
    GUARANTEE = "GUARANTEE"
    CASH_COLLATERAL = "CASH_COLLATERAL"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TriggerDefinition:
    """
    Definition of a credit enhancement trigger.
    
    Parameters
    ----------
    trigger_id : str
        Unique identifier for the trigger
    trigger_type : TriggerType
        Type of trigger test
    target_classes : List[str]
        Bond classes affected by this trigger
    threshold : float
        Trigger threshold value
    comparison : str
        Comparison operator ('>=', '<=', '>', '<', '==')
    cure_threshold : Optional[float]
        Threshold for curing the trigger (if different from trigger)
    cure_periods : int
        Number of consecutive passing periods to cure
    breach_action : str
        Action when trigger breaches ('divert', 'accelerate', 'turbo')
    description : str
        Human-readable description
    
    Examples
    --------
    >>> oc_trigger = TriggerDefinition(
    ...     trigger_id='ClassA_OC',
    ...     trigger_type=TriggerType.OC_TEST,
    ...     target_classes=['ClassA'],
    ...     threshold=1.25,
    ...     comparison='>=',
    ...     breach_action='divert',
    ...     description='Class A OC Test - 125%'
    ... )
    """
    
    trigger_id: str
    trigger_type: TriggerType
    target_classes: List[str]
    threshold: float
    comparison: str = ">="
    cure_threshold: Optional[float] = None
    cure_periods: int = 3
    breach_action: str = "divert"
    description: str = ""
    priority: int = 1
    is_structural: bool = True  # Built into deal docs vs. monitoring only
    
    def evaluate(self, current_value: float) -> bool:
        """
        Evaluate if trigger test passes.
        
        Parameters
        ----------
        current_value : float
            Current value to test
            
        Returns
        -------
        bool
            True if test passes, False if breached
        """
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: abs(a - b) < 1e-10,
        }
        
        op = ops.get(self.comparison, ops[">="])
        return op(current_value, self.threshold)


@dataclass
class TriggerResult:
    """
    Result of a trigger evaluation.
    
    Parameters
    ----------
    trigger : TriggerDefinition
        The trigger being evaluated
    status : TriggerStatus
        Current status
    current_value : float
        Current metric value
    threshold : float
        Trigger threshold
    margin : float
        Cushion above/below threshold
    breach_date : Optional[date]
        Date trigger was first breached
    consecutive_pass : int
        Consecutive passing periods (for cure tracking)
    consecutive_fail : int
        Consecutive failing periods
    """
    
    trigger: TriggerDefinition
    status: TriggerStatus
    current_value: float
    threshold: float
    margin: float
    breach_date: Optional[date] = None
    consecutive_pass: int = 0
    consecutive_fail: int = 0
    evaluation_date: date = field(default_factory=date.today)
    
    @property
    def margin_percentage(self) -> float:
        """Return margin as percentage of threshold."""
        if self.threshold == 0:
            return 0.0
        return self.margin / self.threshold * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "trigger_id": self.trigger.trigger_id,
            "type": self.trigger.trigger_type.value,
            "status": self.status.value,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "margin": self.margin,
            "margin_pct": self.margin_percentage,
            "evaluation_date": self.evaluation_date.isoformat(),
            "breach_date": self.breach_date.isoformat() if self.breach_date else None,
            "consecutive_pass": self.consecutive_pass,
            "consecutive_fail": self.consecutive_fail,
        }


@dataclass
class OCTestResult:
    """
    Overcollateralization test result with detailed breakdown.
    
    Parameters
    ----------
    test_id : str
        Identifier for this OC test
    target_class : str
        Bond class being tested
    collateral_balance : float
        Current collateral balance (numerator)
    bond_balance : float
        Bond balance at or above target class (denominator)
    current_ratio : float
        Current OC ratio
    required_ratio : float
        Minimum required OC ratio
    is_passing : bool
        Whether test passes
    par_oc : float
        OC based on par value
    market_oc : Optional[float]
        OC based on market value (if available)
    """
    
    test_id: str
    target_class: str
    collateral_balance: float
    bond_balance: float
    current_ratio: float
    required_ratio: float
    is_passing: bool
    par_oc: float
    market_oc: Optional[float] = None
    evaluation_date: date = field(default_factory=date.today)
    
    @property
    def cushion(self) -> float:
        """Dollar cushion before trigger breach."""
        return self.collateral_balance - (self.bond_balance * self.required_ratio)
    
    @property
    def cushion_percentage(self) -> float:
        """Cushion as percentage of collateral."""
        if self.collateral_balance == 0:
            return 0.0
        return self.cushion / self.collateral_balance * 100


@dataclass
class ICTestResult:
    """
    Interest Coverage test result with detailed breakdown.
    
    Parameters
    ----------
    test_id : str
        Identifier for this IC test
    target_class : str
        Bond class being tested
    interest_collections : float
        Available interest collections
    interest_required : float
        Required interest payments
    current_ratio : float
        Current IC ratio
    required_ratio : float
        Minimum required IC ratio
    is_passing : bool
        Whether test passes
    excess_interest : float
        Interest collections above required
    """
    
    test_id: str
    target_class: str
    interest_collections: float
    interest_required: float
    current_ratio: float
    required_ratio: float
    is_passing: bool
    excess_interest: float
    evaluation_date: date = field(default_factory=date.today)


@dataclass
class SubordinationLevel:
    """
    Subordination level for a bond class.
    
    Parameters
    ----------
    bond_class : str
        Bond class identifier
    subordination_amount : float
        Dollar amount of subordination
    subordination_pct : float
        Subordination as percentage of total
    original_subordination_pct : float
        Original subordination at closing
    floor_subordination_pct : float
        Minimum subordination floor (step-down limit)
    """
    
    bond_class: str
    subordination_amount: float
    subordination_pct: float
    original_subordination_pct: float
    floor_subordination_pct: float = 0.0
    evaluation_date: date = field(default_factory=date.today)
    
    @property
    def subordination_erosion(self) -> float:
        """Percentage points of subordination eroded."""
        return self.original_subordination_pct - self.subordination_pct
    
    @property
    def at_floor(self) -> bool:
        """Whether subordination is at its floor."""
        return self.subordination_pct <= self.floor_subordination_pct


# =============================================================================
# Credit Enhancement Tracker
# =============================================================================

class CreditEnhancementTracker:
    """
    Comprehensive credit enhancement monitoring engine.
    
    Tracks OC, IC, subordination, and other credit enhancement metrics
    throughout the life of a structured deal, maintaining history and
    evaluating triggers.
    
    Parameters
    ----------
    deal_bonds : Dict[str, Dict]
        Bond definitions with class, balance, and seniority
    collateral_balance : float
        Current collateral balance
    triggers : List[TriggerDefinition]
        Trigger definitions for the deal
    reserve_accounts : Dict[str, float]
        Reserve account balances by name
    
    Attributes
    ----------
    history : pd.DataFrame
        Historical credit enhancement metrics
    trigger_history : Dict[str, List[TriggerResult]]
        History of trigger evaluations
    
    Examples
    --------
    >>> tracker = CreditEnhancementTracker(
    ...     deal_bonds=deal.bonds,
    ...     collateral_balance=100_000_000,
    ...     triggers=deal.triggers
    ... )
    >>> 
    >>> # Update and evaluate
    >>> tracker.update_balances(new_collateral, new_bond_balances)
    >>> results = tracker.evaluate_all_triggers()
    >>> 
    >>> # Get enhancement levels
    >>> ce_summary = tracker.get_enhancement_summary()
    """
    
    def __init__(
        self,
        deal_bonds: Dict[str, Dict[str, Any]],
        collateral_balance: float,
        triggers: Optional[List[TriggerDefinition]] = None,
        reserve_accounts: Optional[Dict[str, float]] = None,
        original_collateral: Optional[float] = None,
        evaluation_date: Optional[date] = None,
    ) -> None:
        self.deal_bonds = deal_bonds
        self.collateral_balance = collateral_balance
        self.original_collateral = original_collateral or collateral_balance
        self.triggers = triggers or []
        self.reserve_accounts = reserve_accounts or {}
        self.evaluation_date = evaluation_date or date.today()
        
        # Derived data
        self._bond_priority = self._establish_priority()
        
        # History tracking
        self._history: List[Dict[str, Any]] = []
        self._trigger_history: Dict[str, List[TriggerResult]] = {
            t.trigger_id: [] for t in self.triggers
        }
        
        # Current period collections (for IC tests)
        self._interest_collections = 0.0
        self._principal_collections = 0.0
    
    def _establish_priority(self) -> Dict[str, int]:
        """Establish bond payment priority from deal structure."""
        priority = {}
        
        # Sort by seniority or explicit priority
        sorted_bonds = sorted(
            self.deal_bonds.items(),
            key=lambda x: x[1].get('priority', x[1].get('seniority', 999))
        )
        
        for i, (bond_id, _) in enumerate(sorted_bonds):
            priority[bond_id] = i + 1
        
        return priority
    
    def update_balances(
        self,
        collateral_balance: float,
        bond_balances: Dict[str, float],
        interest_collections: float = 0.0,
        principal_collections: float = 0.0,
        reserve_balances: Optional[Dict[str, float]] = None,
        evaluation_date: Optional[date] = None,
    ) -> None:
        """
        Update current balances for credit enhancement calculation.
        
        Parameters
        ----------
        collateral_balance : float
            Current collateral balance
        bond_balances : Dict[str, float]
            Current bond balances by class
        interest_collections : float
            Interest collected this period
        principal_collections : float
            Principal collected this period
        reserve_balances : Optional[Dict[str, float]]
            Updated reserve account balances
        evaluation_date : Optional[date]
            Date of evaluation
        """
        self.collateral_balance = collateral_balance
        self._interest_collections = interest_collections
        self._principal_collections = principal_collections
        
        if evaluation_date:
            self.evaluation_date = evaluation_date
        
        # Update bond balances in deal structure
        for bond_id, balance in bond_balances.items():
            if bond_id in self.deal_bonds:
                self.deal_bonds[bond_id]['current_balance'] = balance
        
        if reserve_balances:
            self.reserve_accounts.update(reserve_balances)
    
    def get_bond_balance(self, bond_id: str) -> float:
        """Get current balance for a bond class."""
        bond = self.deal_bonds.get(bond_id, {})
        return bond.get('current_balance', bond.get('original_balance', 0.0))
    
    def get_bonds_at_or_above(self, target_bond: str) -> List[str]:
        """
        Get all bonds at or senior to target.
        
        Parameters
        ----------
        target_bond : str
            Target bond class
            
        Returns
        -------
        List[str]
            Bond classes at or above target in priority
        """
        target_priority = self._bond_priority.get(target_bond, 999)
        
        return [
            bond_id for bond_id, priority 
            in self._bond_priority.items()
            if priority <= target_priority
        ]
    
    def get_bonds_below(self, target_bond: str) -> List[str]:
        """
        Get all bonds junior to target.
        
        Parameters
        ----------
        target_bond : str
            Target bond class
            
        Returns
        -------
        List[str]
            Bond classes below target in priority
        """
        target_priority = self._bond_priority.get(target_bond, 999)
        
        return [
            bond_id for bond_id, priority 
            in self._bond_priority.items()
            if priority > target_priority
        ]
    
    def calculate_oc_ratio(
        self,
        target_class: str,
        include_reserves: bool = True,
    ) -> OCTestResult:
        """
        Calculate OC ratio for a bond class.
        
        The OC ratio measures the cushion of collateral supporting
        bonds at and above the target class level.
        
        OC Ratio = (Collateral + Reserves) / (Bonds at or above target class)
        
        Parameters
        ----------
        target_class : str
            Bond class to calculate OC for
        include_reserves : bool
            Include reserve accounts in numerator
            
        Returns
        -------
        OCTestResult
            Detailed OC test result
            
        Examples
        --------
        >>> result = tracker.calculate_oc_ratio('ClassA')
        >>> print(f"OC Ratio: {result.current_ratio:.2%}")
        >>> print(f"Cushion: ${result.cushion:,.0f}")
        """
        # Numerator: collateral + reserves
        numerator = self.collateral_balance
        if include_reserves:
            numerator += sum(self.reserve_accounts.values())
        
        # Denominator: bonds at or above target class
        senior_bonds = self.get_bonds_at_or_above(target_class)
        denominator = sum(self.get_bond_balance(b) for b in senior_bonds)
        
        # Calculate ratio
        if denominator == 0:
            current_ratio = float('inf')
        else:
            current_ratio = numerator / denominator
        
        # Find applicable trigger
        required_ratio = 1.0  # Default
        for trigger in self.triggers:
            if (trigger.trigger_type == TriggerType.OC_TEST and 
                target_class in trigger.target_classes):
                required_ratio = trigger.threshold
                break
        
        # Par-based OC (original collateral basis)
        if self.original_collateral > 0:
            original_bond_balance = sum(
                self.deal_bonds[b].get('original_balance', 0)
                for b in senior_bonds
            )
            par_oc = self.original_collateral / original_bond_balance if original_bond_balance > 0 else 0
        else:
            par_oc = current_ratio
        
        return OCTestResult(
            test_id=f"OC_{target_class}",
            target_class=target_class,
            collateral_balance=numerator,
            bond_balance=denominator,
            current_ratio=current_ratio,
            required_ratio=required_ratio,
            is_passing=current_ratio >= required_ratio,
            par_oc=par_oc,
            evaluation_date=self.evaluation_date,
        )
    
    def calculate_ic_ratio(
        self,
        target_class: str,
    ) -> ICTestResult:
        """
        Calculate Interest Coverage ratio for a bond class.
        
        The IC ratio measures whether interest collections are
        sufficient to cover bond interest payments.
        
        IC Ratio = Interest Collections / Interest Due (at or above target)
        
        Parameters
        ----------
        target_class : str
            Bond class to calculate IC for
            
        Returns
        -------
        ICTestResult
            Detailed IC test result
        """
        # Interest collections (numerator)
        interest_collections = self._interest_collections
        
        # Interest required for bonds at or above target
        senior_bonds = self.get_bonds_at_or_above(target_class)
        interest_required = 0.0
        
        for bond_id in senior_bonds:
            bond = self.deal_bonds.get(bond_id, {})
            balance = self.get_bond_balance(bond_id)
            coupon = bond.get('coupon_rate', bond.get('rate', 0.0))
            # Assume monthly accrual
            interest_required += balance * coupon / 12
        
        # Calculate ratio
        if interest_required == 0:
            current_ratio = float('inf')
        else:
            current_ratio = interest_collections / interest_required
        
        # Find applicable trigger
        required_ratio = 1.0
        for trigger in self.triggers:
            if (trigger.trigger_type == TriggerType.IC_TEST and 
                target_class in trigger.target_classes):
                required_ratio = trigger.threshold
                break
        
        return ICTestResult(
            test_id=f"IC_{target_class}",
            target_class=target_class,
            interest_collections=interest_collections,
            interest_required=interest_required,
            current_ratio=current_ratio,
            required_ratio=required_ratio,
            is_passing=current_ratio >= required_ratio,
            excess_interest=max(0, interest_collections - interest_required),
            evaluation_date=self.evaluation_date,
        )
    
    def calculate_subordination(
        self,
        target_class: str,
    ) -> SubordinationLevel:
        """
        Calculate subordination level for a bond class.
        
        Subordination represents the percentage of the capital structure
        that is junior to (and absorbs losses before) the target class.
        
        Parameters
        ----------
        target_class : str
            Bond class to calculate subordination for
            
        Returns
        -------
        SubordinationLevel
            Subordination metrics
        """
        # Total bond balance
        total_balance = sum(
            self.get_bond_balance(b) 
            for b in self.deal_bonds
        )
        
        # Junior bond balance
        junior_bonds = self.get_bonds_below(target_class)
        junior_balance = sum(
            self.get_bond_balance(b) 
            for b in junior_bonds
        )
        
        # Calculate percentages
        current_pct = junior_balance / total_balance * 100 if total_balance > 0 else 0
        
        # Original subordination
        original_total = sum(
            self.deal_bonds[b].get('original_balance', 0)
            for b in self.deal_bonds
        )
        original_junior = sum(
            self.deal_bonds[b].get('original_balance', 0)
            for b in junior_bonds
        )
        original_pct = original_junior / original_total * 100 if original_total > 0 else 0
        
        # Floor (from deal docs, default to 50% of original)
        floor_pct = original_pct * 0.5  # Typical step-down floor
        
        return SubordinationLevel(
            bond_class=target_class,
            subordination_amount=junior_balance,
            subordination_pct=current_pct,
            original_subordination_pct=original_pct,
            floor_subordination_pct=floor_pct,
            evaluation_date=self.evaluation_date,
        )
    
    def evaluate_trigger(
        self,
        trigger: TriggerDefinition,
    ) -> TriggerResult:
        """
        Evaluate a single trigger.
        
        Parameters
        ----------
        trigger : TriggerDefinition
            Trigger to evaluate
            
        Returns
        -------
        TriggerResult
            Evaluation result
        """
        # Get previous result for cure tracking
        prev_results = self._trigger_history.get(trigger.trigger_id, [])
        prev_result = prev_results[-1] if prev_results else None
        
        # Calculate current value based on trigger type
        current_value = 0.0
        
        if trigger.trigger_type == TriggerType.OC_TEST:
            if trigger.target_classes:
                oc_result = self.calculate_oc_ratio(trigger.target_classes[0])
                current_value = oc_result.current_ratio
        
        elif trigger.trigger_type == TriggerType.IC_TEST:
            if trigger.target_classes:
                ic_result = self.calculate_ic_ratio(trigger.target_classes[0])
                current_value = ic_result.current_ratio
        
        elif trigger.trigger_type == TriggerType.CUMULATIVE_LOSS:
            # Loss as percentage of original collateral
            losses = self.original_collateral - self.collateral_balance
            current_value = losses / self.original_collateral * 100 if self.original_collateral > 0 else 0
        
        elif trigger.trigger_type == TriggerType.DELINQUENCY:
            # Would need delinquency data from collateral
            current_value = 0.0  # Placeholder
        
        # Evaluate test
        is_passing = trigger.evaluate(current_value)
        margin = current_value - trigger.threshold
        
        # Determine status
        if is_passing:
            consecutive_pass = (prev_result.consecutive_pass + 1) if prev_result else 1
            consecutive_fail = 0
            
            if prev_result and prev_result.status == TriggerStatus.FAILING:
                if consecutive_pass >= trigger.cure_periods:
                    status = TriggerStatus.CURED
                else:
                    status = TriggerStatus.FAILING  # Still failing until cured
            else:
                status = TriggerStatus.PASSING
        else:
            consecutive_pass = 0
            consecutive_fail = (prev_result.consecutive_fail + 1) if prev_result else 1
            status = TriggerStatus.FAILING
        
        # Breach date tracking
        breach_date = None
        if status == TriggerStatus.FAILING:
            if prev_result and prev_result.breach_date:
                breach_date = prev_result.breach_date
            else:
                breach_date = self.evaluation_date
        
        result = TriggerResult(
            trigger=trigger,
            status=status,
            current_value=current_value,
            threshold=trigger.threshold,
            margin=margin,
            breach_date=breach_date,
            consecutive_pass=consecutive_pass,
            consecutive_fail=consecutive_fail,
            evaluation_date=self.evaluation_date,
        )
        
        # Store in history
        self._trigger_history[trigger.trigger_id].append(result)
        
        return result
    
    def evaluate_all_triggers(self) -> List[TriggerResult]:
        """
        Evaluate all triggers and return results.
        
        Returns
        -------
        List[TriggerResult]
            Results for all triggers
        """
        return [self.evaluate_trigger(t) for t in self.triggers]
    
    def get_failing_triggers(self) -> List[TriggerResult]:
        """
        Get currently failing triggers.
        
        Returns
        -------
        List[TriggerResult]
            Failing trigger results
        """
        results = self.evaluate_all_triggers()
        return [r for r in results if r.status == TriggerStatus.FAILING]
    
    def get_enhancement_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive credit enhancement summary.
        
        Returns
        -------
        Dict[str, Any]
            Summary including OC, IC, subordination for all classes
        """
        summary = {
            "evaluation_date": self.evaluation_date.isoformat(),
            "collateral_balance": self.collateral_balance,
            "original_collateral": self.original_collateral,
            "pool_factor": self.collateral_balance / self.original_collateral if self.original_collateral > 0 else 0,
            "reserve_accounts": dict(self.reserve_accounts),
            "total_reserves": sum(self.reserve_accounts.values()),
            "oc_tests": {},
            "ic_tests": {},
            "subordination": {},
            "triggers": {},
        }
        
        # Calculate metrics for each bond class
        for bond_id in self.deal_bonds:
            # OC
            oc_result = self.calculate_oc_ratio(bond_id)
            summary["oc_tests"][bond_id] = {
                "ratio": oc_result.current_ratio,
                "required": oc_result.required_ratio,
                "passing": oc_result.is_passing,
                "cushion": oc_result.cushion,
            }
            
            # IC
            ic_result = self.calculate_ic_ratio(bond_id)
            summary["ic_tests"][bond_id] = {
                "ratio": ic_result.current_ratio,
                "required": ic_result.required_ratio,
                "passing": ic_result.is_passing,
                "excess": ic_result.excess_interest,
            }
            
            # Subordination
            sub_level = self.calculate_subordination(bond_id)
            summary["subordination"][bond_id] = {
                "current_pct": sub_level.subordination_pct,
                "original_pct": sub_level.original_subordination_pct,
                "floor_pct": sub_level.floor_subordination_pct,
                "at_floor": sub_level.at_floor,
            }
        
        # Trigger status
        for result in self.evaluate_all_triggers():
            summary["triggers"][result.trigger.trigger_id] = result.to_dict()
        
        return summary
    
    def record_period(self) -> None:
        """Record current state to history."""
        self._history.append(self.get_enhancement_summary())
    
    def get_history_dataframe(self) -> pd.DataFrame:
        """
        Get credit enhancement history as DataFrame.
        
        Returns
        -------
        pd.DataFrame
            Time series of credit enhancement metrics
        """
        if not self._history:
            return pd.DataFrame()
        
        records = []
        for snapshot in self._history:
            record = {
                "date": snapshot["evaluation_date"],
                "collateral_balance": snapshot["collateral_balance"],
                "pool_factor": snapshot["pool_factor"],
                "total_reserves": snapshot["total_reserves"],
            }
            
            # Flatten OC and subordination
            for bond_id, oc_data in snapshot["oc_tests"].items():
                record[f"OC_{bond_id}"] = oc_data["ratio"]
                record[f"OC_{bond_id}_passing"] = oc_data["passing"]
            
            for bond_id, sub_data in snapshot["subordination"].items():
                record[f"Sub_{bond_id}"] = sub_data["current_pct"]
            
            records.append(record)
        
        return pd.DataFrame(records)


# =============================================================================
# Excess Spread Calculator
# =============================================================================

class ExcessSpreadCalculator:
    """
    Calculate and allocate excess spread.
    
    Excess spread is the difference between collateral yield and
    bond coupon rates, providing a first line of defense against losses.
    
    Parameters
    ----------
    collateral_yield : float
        Weighted average coupon of collateral (annual)
    servicing_fee : float
        Annual servicing fee rate
    trust_expenses : float
        Annual trust expense rate
    
    Examples
    --------
    >>> calculator = ExcessSpreadCalculator(
    ...     collateral_yield=0.065,
    ...     servicing_fee=0.0025,
    ...     trust_expenses=0.0005
    ... )
    >>> excess = calculator.calculate_excess_spread(
    ...     collateral_balance=100_000_000,
    ...     bond_coupons={'A': (80_000_000, 0.045), 'B': (15_000_000, 0.06)}
    ... )
    """
    
    def __init__(
        self,
        collateral_yield: float,
        servicing_fee: float = 0.0025,
        trust_expenses: float = 0.0005,
        target_oc_builds: Optional[Dict[str, float]] = None,
    ) -> None:
        self.collateral_yield = collateral_yield
        self.servicing_fee = servicing_fee
        self.trust_expenses = trust_expenses
        self.target_oc_builds = target_oc_builds or {}
    
    def calculate_excess_spread(
        self,
        collateral_balance: float,
        bond_coupons: Dict[str, Tuple[float, float]],  # bond_id -> (balance, coupon)
        period_months: int = 1,
    ) -> Dict[str, float]:
        """
        Calculate excess spread for a period.
        
        Parameters
        ----------
        collateral_balance : float
            Current collateral balance
        bond_coupons : Dict[str, Tuple[float, float]]
            Bond balances and coupon rates
        period_months : int
            Number of months in period
            
        Returns
        -------
        Dict[str, float]
            Excess spread breakdown
        """
        period_factor = period_months / 12
        
        # Gross interest collections
        gross_interest = collateral_balance * self.collateral_yield * period_factor
        
        # Deductions
        servicing = collateral_balance * self.servicing_fee * period_factor
        expenses = collateral_balance * self.trust_expenses * period_factor
        
        # Net interest available
        net_interest = gross_interest - servicing - expenses
        
        # Bond coupon payments
        total_bond_interest = 0.0
        bond_interest_detail = {}
        
        for bond_id, (balance, coupon) in bond_coupons.items():
            interest = balance * coupon * period_factor
            bond_interest_detail[bond_id] = interest
            total_bond_interest += interest
        
        # Excess spread
        excess = net_interest - total_bond_interest
        
        # As percentage of collateral (annualized)
        excess_spread_pct = (excess / collateral_balance) / period_factor if collateral_balance > 0 else 0
        
        return {
            "gross_interest": gross_interest,
            "servicing_fee": servicing,
            "trust_expenses": expenses,
            "net_interest_available": net_interest,
            "total_bond_interest": total_bond_interest,
            "bond_interest_detail": bond_interest_detail,
            "excess_spread_dollars": excess,
            "excess_spread_annualized_pct": excess_spread_pct,
            "period_months": period_months,
        }
    
    def allocate_excess_spread(
        self,
        excess_dollars: float,
        ce_tracker: CreditEnhancementTracker,
        allocation_priority: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Allocate excess spread based on trigger status.
        
        Parameters
        ----------
        excess_dollars : float
            Excess spread available
        ce_tracker : CreditEnhancementTracker
            Credit enhancement tracker for trigger evaluation
        allocation_priority : Optional[List[str]]
            Priority of allocation targets
            
        Returns
        -------
        Dict[str, float]
            Allocation breakdown
        """
        allocation = {
            "to_reserve_account": 0.0,
            "to_oc_build": 0.0,
            "to_principal_paydown": 0.0,
            "to_residual": 0.0,
            "total_allocated": 0.0,
        }
        
        remaining = excess_dollars
        
        # Check for failing triggers
        failing_triggers = ce_tracker.get_failing_triggers()
        
        if failing_triggers:
            # Divert to OC build or principal paydown based on trigger type
            for trigger_result in failing_triggers:
                if remaining <= 0:
                    break
                
                action = trigger_result.trigger.breach_action
                
                if action == "divert":
                    # Divert to reserve or principal
                    divert_amount = min(remaining, remaining)  # Could be capped
                    allocation["to_reserve_account"] += divert_amount
                    remaining -= divert_amount
                
                elif action == "turbo":
                    # Accelerate principal paydown
                    allocation["to_principal_paydown"] += remaining
                    remaining = 0
        
        # Build OC if targets not met
        for bond_id, target_oc in self.target_oc_builds.items():
            if remaining <= 0:
                break
            
            oc_result = ce_tracker.calculate_oc_ratio(bond_id)
            if oc_result.current_ratio < target_oc:
                # Build needed
                build_needed = (target_oc - oc_result.current_ratio) * oc_result.bond_balance
                build_amount = min(remaining, build_needed)
                allocation["to_oc_build"] += build_amount
                remaining -= build_amount
        
        # Remaining to residual holders
        allocation["to_residual"] = remaining
        allocation["total_allocated"] = excess_dollars
        
        return allocation


# =============================================================================
# Loss Allocation Engine
# =============================================================================

class LossAllocationEngine:
    """
    Allocate realized losses through the capital structure.
    
    Losses flow in reverse seniority (junior tranches first),
    respecting subordination and OC constraints.
    
    Parameters
    ----------
    deal_bonds : Dict[str, Dict]
        Bond definitions with priority
    ce_tracker : CreditEnhancementTracker
        Credit enhancement tracker
    write_down_rules : Dict[str, str]
        Rules for write-down vs. write-off by class
    
    Examples
    --------
    >>> engine = LossAllocationEngine(
    ...     deal_bonds=deal.bonds,
    ...     ce_tracker=tracker
    ... )
    >>> allocation = engine.allocate_loss(1_000_000)
    """
    
    def __init__(
        self,
        deal_bonds: Dict[str, Dict[str, Any]],
        ce_tracker: CreditEnhancementTracker,
        write_down_rules: Optional[Dict[str, str]] = None,
    ) -> None:
        self.deal_bonds = deal_bonds
        self.ce_tracker = ce_tracker
        self.write_down_rules = write_down_rules or {}
        
        # Establish loss allocation priority (reverse of payment priority)
        self._loss_priority = self._establish_loss_priority()
    
    def _establish_loss_priority(self) -> List[str]:
        """Get bonds in loss allocation order (junior to senior)."""
        priority_map = self.ce_tracker._bond_priority
        return sorted(priority_map.keys(), key=lambda x: priority_map[x], reverse=True)
    
    def allocate_loss(
        self,
        loss_amount: float,
        loss_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Allocate a realized loss through the structure.
        
        Parameters
        ----------
        loss_amount : float
            Total loss to allocate
        loss_date : Optional[date]
            Date of loss recognition
            
        Returns
        -------
        Dict[str, Any]
            Loss allocation breakdown by class
        """
        allocation = {
            "total_loss": loss_amount,
            "loss_date": (loss_date or date.today()).isoformat(),
            "by_class": {},
            "remaining_loss": 0.0,
        }
        
        remaining = loss_amount
        
        for bond_id in self._loss_priority:
            if remaining <= 0:
                break
            
            bond = self.deal_bonds.get(bond_id, {})
            current_balance = self.ce_tracker.get_bond_balance(bond_id)
            
            # Allocate up to bond balance
            loss_to_bond = min(remaining, current_balance)
            
            if loss_to_bond > 0:
                # Determine write-down treatment
                treatment = self.write_down_rules.get(bond_id, "write_down")
                
                allocation["by_class"][bond_id] = {
                    "loss_allocated": loss_to_bond,
                    "balance_before": current_balance,
                    "balance_after": current_balance - loss_to_bond,
                    "treatment": treatment,
                }
                
                remaining -= loss_to_bond
        
        allocation["remaining_loss"] = remaining  # Unallocated loss (should be 0)
        
        return allocation


# =============================================================================
# Credit Enhancement Builder
# =============================================================================

def create_standard_triggers(
    deal_bonds: Dict[str, Dict],
    oc_threshold: float = 1.25,
    ic_threshold: float = 1.10,
) -> List[TriggerDefinition]:
    """
    Create standard OC and IC triggers for all bond classes.
    
    Parameters
    ----------
    deal_bonds : Dict[str, Dict]
        Bond definitions
    oc_threshold : float
        Default OC test threshold
    ic_threshold : float
        Default IC test threshold
        
    Returns
    -------
    List[TriggerDefinition]
        Standard trigger definitions
    """
    triggers = []
    
    # Sort bonds by priority
    sorted_bonds = sorted(
        deal_bonds.items(),
        key=lambda x: x[1].get('priority', x[1].get('seniority', 999))
    )
    
    for i, (bond_id, bond_spec) in enumerate(sorted_bonds):
        # Skip equity/residual
        if bond_spec.get('is_residual', False):
            continue
        
        # Adjust thresholds by seniority (more senior = lower threshold)
        oc_adj = oc_threshold - (i * 0.05)  # e.g., 1.25, 1.20, 1.15
        ic_adj = ic_threshold - (i * 0.03)
        
        # OC trigger
        triggers.append(TriggerDefinition(
            trigger_id=f"{bond_id}_OC",
            trigger_type=TriggerType.OC_TEST,
            target_classes=[bond_id],
            threshold=max(1.0, oc_adj),
            comparison=">=",
            breach_action="divert",
            description=f"{bond_id} Overcollateralization Test",
            priority=i + 1,
        ))
        
        # IC trigger
        triggers.append(TriggerDefinition(
            trigger_id=f"{bond_id}_IC",
            trigger_type=TriggerType.IC_TEST,
            target_classes=[bond_id],
            threshold=max(1.0, ic_adj),
            comparison=">=",
            breach_action="divert",
            description=f"{bond_id} Interest Coverage Test",
            priority=i + 1,
        ))
    
    return triggers
