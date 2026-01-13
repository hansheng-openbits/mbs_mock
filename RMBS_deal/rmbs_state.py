import logging
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import date

# Import immutable definitions from Module 1
# (Assuming the previous code is saved as rmbs_loader.py)
from rmbs_loader import DealDefinition, Bond

# --- CONFIGURATION ---
logger = logging.getLogger("RMBS.State")

# --- MUTABLE STATE OBJECTS ---

@dataclass
class BondState:
    """Tracks the dynamic status of a single bond."""
    original_balance: float
    current_balance: float
    deferred_balance: float = 0.0
    interest_shortfall: float = 0.0
    
    @property
    def factor(self) -> float:
        if self.original_balance == 0: return 0.0
        return self.current_balance / self.original_balance

@dataclass
class Snapshot:
    """A frozen record of the deal state at a specific point in time."""
    date: str
    period: int
    funds: Dict[str, float]
    ledgers: Dict[str, float]
    bond_balances: Dict[str, float]
    variables: Dict[str, Any]
    flags: Dict[str, bool]

# --- THE STATE MANAGER ---

class DealState:
    def __init__(self, definition: DealDefinition):
        self.def_ = definition
        self.current_date: Optional[date] = None
        self.period_index: int = 0
        
        # 1. Cash Balances (Funds + Accounts)
        # We treat 'Accounts' (Reserves) and 'Funds' (IAF) as bucketable cash.
        self.cash_balances: Dict[str, float] = {}
        
        # 2. Accounting Ledgers (Non-cash tracking, e.g., PDL, Cumulative Loss)
        self.ledgers: Dict[str, float] = {}
        
        # 3. Bond States (Balances, Factors)
        self.bonds: Dict[str, BondState] = {}
        
        # 4. Variables & Flags (Calculated per period)
        self.variables: Dict[str, Any] = {}
        self.flags: Dict[str, bool] = {}
        
        # 5. History (List of Snapshots)
        self.history: List[Snapshot] = []
        
        self._initialize_t0()

    def _initialize_t0(self):
        """Sets the state to the Closing Date values."""
        logger.info("Initializing State to T=0")
        
        # Init Cash Buckets (Start at 0.0)
        for fund_id in self.def_.funds:
            self.cash_balances[fund_id] = 0.0
        for acc_id in self.def_.accounts:
            self.cash_balances[acc_id] = 0.0
            
        # Init Bonds (Start at Original Balance)
        for b_id, b_def in self.def_.bonds.items():
            self.bonds[b_id] = BondState(
                original_balance=b_def.original_balance,
                current_balance=b_def.original_balance
            )
            
        # Init Generic Ledgers
        self.ledgers['CumulativeLoss'] = 0.0
        self.ledgers['CumulativePrepayment'] = 0.0

    # --- CASH MANAGEMENT METHODS ---

    def deposit_funds(self, fund_id: str, amount: float):
        """Injects cash into the deal (e.g., from Collections)."""
        if amount < 0:
            raise ValueError(f"Cannot deposit negative amount: {amount}")
        self._ensure_bucket(fund_id)
        self.cash_balances[fund_id] += amount
        # logger.debug(f"Deposited ${amount:,.2f} into {fund_id}")

    def transfer_cash(self, from_id: str, to_id: str, amount: float):
        """Moves cash between buckets. Enforces non-negative checks."""
        self._ensure_bucket(from_id)
        self._ensure_bucket(to_id)
        
        if amount < 0:
            raise ValueError("Transfer amount must be positive.")
        
        # Floating point tolerance check
        if self.cash_balances[from_id] < (amount - 0.00001):
            raise ValueError(f"Insufficient funds in {from_id}. Has {self.cash_balances[from_id]}, tried to move {amount}")
            
        self.cash_balances[from_id] -= amount
        self.cash_balances[to_id] += amount
        # logger.debug(f"Transferred ${amount:,.2f} from {from_id} to {to_id}")

    def pay_bond_principal(self, bond_id: str, amount: float, source_fund: str):
        """
        Pays principal to a bond. 
        1. Decreases Source Fund.
        2. Decreases Bond Balance.
        """
        # 1. Move Cash out
        self.withdraw_cash(source_fund, amount)
        
        # 2. Update Bond State
        b_state = self.bonds[bond_id]
        if amount > b_state.current_balance + 0.00001:
             logger.warning(f"Overpaying bond {bond_id}. Bal: {b_state.current_balance}, Pay: {amount}")
        
        b_state.current_balance = max(0.0, b_state.current_balance - amount)
        # logger.info(f"Bond {bond_id} Principal Pay: ${amount:,.2f}. New Factor: {b_state.factor:.4f}")

    def withdraw_cash(self, fund_id: str, amount: float):
        """Removes cash from the system (e.g. paying external fees/coupon)."""
        self._ensure_bucket(fund_id)
        if self.cash_balances[fund_id] < (amount - 0.00001):
            raise ValueError(f"Insufficient funds in {fund_id} to withdraw {amount}")
        self.cash_balances[fund_id] -= amount

    def _ensure_bucket(self, bucket_id: str):
        if bucket_id not in self.cash_balances:
            raise KeyError(f"Cash bucket '{bucket_id}' does not exist.")

    # --- VARIABLE & LOGIC METHODS ---

    def set_variable(self, name: str, value: Any):
        self.variables[name] = value

    def get_variable(self, name: str) -> Any:
        return self.variables.get(name)
        
    def set_ledger(self, ledger_id: str, value: float):
        self.ledgers[ledger_id] = value

    # --- REPORTING ---

    def snapshot(self, current_date: date):
        """Captures the state at the end of a period."""
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