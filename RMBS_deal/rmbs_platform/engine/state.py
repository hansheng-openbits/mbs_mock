"""In-memory deal state used to apply waterfalls period by period."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import date
# Adjust import based on your folder structure
# If running as flat files use: from rmbs_loader import DealDefinition
from .loader import DealDefinition

logger = logging.getLogger("RMBS.State")

@dataclass
class BondState:
    """Tracks an individual bond's balances and shortfalls."""
    original_balance: float
    current_balance: float
    deferred_balance: float = 0.0
    interest_shortfall: float = 0.0
    
    @property
    def factor(self) -> float:
        """Return current balance as a fraction of original balance."""
        if self.original_balance == 0: return 0.0
        return self.current_balance / self.original_balance

@dataclass
class Snapshot:
    """Point-in-time record of deal state for reporting."""
    date: str
    period: int
    funds: Dict[str, float]
    ledgers: Dict[str, float]
    bond_balances: Dict[str, float]
    variables: Dict[str, Any]
    flags: Dict[str, bool]

class DealState:
    """Mutable deal state used by the engine to run waterfalls."""

    def __init__(self, definition: DealDefinition) -> None:
        self.def_ = definition
        self.current_date: Optional[date] = None
        self.period_index: int = 0
        self.cash_balances: Dict[str, float] = {}
        self.ledgers: Dict[str, float] = {}
        self.bonds: Dict[str, BondState] = {}
        self.variables: Dict[str, Any] = {}
        self.collateral: Dict[str, Any] = definition.collateral
        
        # --- CRITICAL FIX: Ensure flags is initialized ---
        self.flags: Dict[str, bool] = {} 
        # -------------------------------------------------
        
        self.history: List[Snapshot] = []
        self._initialize_t0()

    def _initialize_t0(self) -> None:
        """Initialize cash buckets, bond balances, and ledgers at period 0."""
        for fund_id in self.def_.funds:
            self.cash_balances[fund_id] = 0.0
        for acc_id in self.def_.accounts:
            self.cash_balances[acc_id] = 0.0
        for b_id, b_def in self.def_.bonds.items():
            self.bonds[b_id] = BondState(b_def.original_balance, b_def.original_balance)
        self.ledgers['CumulativeLoss'] = 0.0

    def deposit_funds(self, fund_id: str, amount: float) -> None:
        """Deposit cash into a waterfall fund or account."""
        if amount < 0: raise ValueError(f"Negative deposit: {amount}")
        self._ensure_bucket(fund_id)
        self.cash_balances[fund_id] += amount

    def transfer_cash(self, from_id: str, to_id: str, amount: float) -> None:
        """Move cash between internal funds/accounts."""
        self._ensure_bucket(from_id)
        self._ensure_bucket(to_id)
        if self.cash_balances[from_id] < (amount - 0.00001):
            raise ValueError(f"Insufficient funds in {from_id}")
        self.cash_balances[from_id] -= amount
        self.cash_balances[to_id] += amount

    def pay_bond_principal(self, bond_id: str, amount: float, source_fund: str) -> None:
        """Apply principal cash to a bond balance, capped at remaining balance."""
        b_state = self.bonds[bond_id]
        if b_state.current_balance <= 0 or amount <= 0:
            return
        pay_amount = min(amount, b_state.current_balance)
        self.withdraw_cash(source_fund, pay_amount)
        b_state.current_balance = max(0.0, b_state.current_balance - pay_amount)

    def withdraw_cash(self, fund_id: str, amount: float) -> None:
        """Withdraw cash from a fund or account."""
        self._ensure_bucket(fund_id)
        if self.cash_balances[fund_id] < (amount - 0.00001):
            raise ValueError(f"Insufficient funds in {fund_id}")
        self.cash_balances[fund_id] -= amount

    def _ensure_bucket(self, bucket_id: str) -> None:
        """Validate that a cash bucket exists in the deal definition."""
        if bucket_id not in self.cash_balances:
            raise KeyError(f"Cash bucket '{bucket_id}' does not exist.")

    def set_variable(self, name: str, value: Any) -> None:
        """Set a deal variable used by tests or waterfall formulas."""
        self.variables[name] = value

    def get_variable(self, name: str) -> Any:
        """Retrieve a computed deal variable."""
        return self.variables.get(name)

    def set_ledger(self, ledger_id: str, value: float) -> None:
        """Set a ledger balance such as cumulative loss or shortfall."""
        self.ledgers[ledger_id] = value

    def snapshot(self, current_date: date) -> None:
        """Record a reporting snapshot after completing a period."""
        self.current_date = current_date
        self.period_index += 1
        snap = Snapshot(
            date=current_date.isoformat(),
            period=self.period_index,
            funds=self.cash_balances.copy(),
            ledgers=self.ledgers.copy(),
            bond_balances={k: v.current_balance for k, v in self.bonds.items()},
            variables=self.variables.copy(),
            flags=self.flags.copy()
        )
        self.history.append(snap)