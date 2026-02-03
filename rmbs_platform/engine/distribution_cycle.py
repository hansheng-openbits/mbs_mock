"""
Distribution Cycle Management
=============================

Implements the industry-standard RMBS monthly distribution cycle:

1. SERVICER uploads monthly performance tape (Day 1)
   - Loan-level payments, defaults, prepayments
   - Creates "pending" distribution period

2. TRUSTEE executes waterfall (Day 2-3)
   - Runs waterfall with actual collections
   - Calculates interest/principal for each tranche
   - Allocates losses to appropriate tranches
   - Creates yield distributions for token holders

3. TOKENS are updated (Day 3-4)
   - Principal payments reduce token balances (factor adjustment)
   - Losses reduce subordinate tranche balances
   - Interest becomes claimable yield

4. INVESTORS claim yields (Day 5+)
   - View updated portfolio with new factor
   - Claim pending interest distributions
   - See distribution history

Author: RMBS Platform Development Team
Date: February 2026
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid


class DistributionStatus(str, Enum):
    """Status of a distribution period."""
    PENDING = "pending"           # Servicer uploaded, awaiting trustee
    PROCESSING = "processing"     # Trustee running waterfall
    DISTRIBUTED = "distributed"   # Waterfall complete, yields distributed
    FINALIZED = "finalized"       # All claims processed, period closed


@dataclass
class DistributionPeriod:
    """
    Represents a monthly distribution period.
    
    Attributes
    ----------
    period_id : str
        Unique identifier for this period
    deal_id : str
        Deal this period belongs to
    period_number : int
        Sequential period number (1, 2, 3, ...)
    collection_date : str
        Date collections were received (ISO format)
    distribution_date : str, optional
        Date distributions were made (ISO format)
    status : DistributionStatus
        Current status of the period
    servicer_tape_version : str, optional
        Version ID of the servicer tape used
    
    Collections (from servicer tape):
    ---------------------------------
    total_collections : float
        Total cash collected from pool
    interest_collected : float
        Interest portion of collections
    principal_collected : float
        Principal portion (scheduled + prepay + recovery)
    prepayments : float
        Voluntary prepayments
    defaults : float
        Loan defaults this period
    losses : float
        Realized losses (defaults * severity)
    recoveries : float
        Recovered amounts from defaults
    
    Distributions (from waterfall):
    -------------------------------
    tranche_distributions : Dict
        Per-tranche distribution details
    total_interest_distributed : float
        Total interest paid to tranches
    total_principal_distributed : float
        Total principal paid to tranches
    reserve_deposit : float
        Amount deposited to reserve account
    excess_spread : float
        Residual after all payments
    """
    period_id: str
    deal_id: str
    period_number: int
    collection_date: str
    status: DistributionStatus
    
    # Collections
    total_collections: float = 0.0
    interest_collected: float = 0.0
    principal_collected: float = 0.0
    prepayments: float = 0.0
    defaults: float = 0.0
    losses: float = 0.0
    recoveries: float = 0.0
    beginning_balance: float = 0.0
    ending_balance: float = 0.0
    
    # Distributions (populated after waterfall)
    distribution_date: Optional[str] = None
    tranche_distributions: Optional[Dict[str, Dict[str, float]]] = None
    total_interest_distributed: float = 0.0
    total_principal_distributed: float = 0.0
    reserve_deposit: float = 0.0
    excess_spread: float = 0.0
    
    # Metadata
    servicer_tape_version: Optional[str] = None
    waterfall_tx_hash: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    processed_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DistributionPeriod":
        """Create from dictionary."""
        data = data.copy()
        if "status" in data:
            data["status"] = DistributionStatus(data["status"])
        return cls(**data)


@dataclass
class TrancheDistribution:
    """Distribution details for a single tranche."""
    tranche_id: str
    interest_due: float
    interest_paid: float
    interest_shortfall: float
    principal_due: float
    principal_paid: float
    principal_shortfall: float
    loss_allocation: float
    beginning_balance: float
    ending_balance: float
    factor: float  # ending_balance / original_balance


class DistributionCycleManager:
    """
    Manages the monthly distribution cycle for RMBS deals.
    
    This class coordinates the flow between servicer, trustee, and investors
    following industry best practices.
    """
    
    def __init__(self, storage_path: Path):
        """
        Initialize the distribution cycle manager.
        
        Parameters
        ----------
        storage_path : Path
            Base path for storing distribution data
        """
        self.storage_path = storage_path
        self.distributions_file = storage_path / "distribution_cycles.json"
        self._ensure_storage()
    
    def _ensure_storage(self) -> None:
        """Ensure storage directory and file exist."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        if not self.distributions_file.exists():
            self._save_data({"deals": {}})
    
    def _load_data(self) -> Dict[str, Any]:
        """Load distribution data from disk."""
        try:
            return json.loads(self.distributions_file.read_text())
        except Exception:
            return {"deals": {}}
    
    def _save_data(self, data: Dict[str, Any]) -> None:
        """Save distribution data to disk."""
        self.distributions_file.write_text(
            json.dumps(data, indent=2, default=str)
        )
    
    def _utc_now(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    def _generate_tx_hash(self, data: str) -> str:
        """Generate a mock transaction hash."""
        return "0x" + hashlib.sha256(
            f"{data}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:64]
    
    # ========== SERVICER FUNCTIONS ==========
    
    def create_distribution_period(
        self,
        deal_id: str,
        period_number: int,
        collections: Dict[str, float],
        servicer_tape_version: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> DistributionPeriod:
        """
        Create a new pending distribution period (called by Servicer).
        
        This is step 1 of the distribution cycle - the servicer uploads
        the monthly tape and creates a pending period for trustee review.
        
        Parameters
        ----------
        deal_id : str
            Deal identifier
        period_number : int
            Sequential period number
        collections : Dict[str, float]
            Collection data from servicer tape:
            - interest_collected
            - principal_collected
            - prepayments
            - defaults
            - losses
            - recoveries
            - beginning_balance
            - ending_balance
        servicer_tape_version : str, optional
            Version ID of the servicer tape
        created_by : str, optional
            Servicer identifier
        
        Returns
        -------
        DistributionPeriod
            The created period in PENDING status
        """
        data = self._load_data()
        deals = data.setdefault("deals", {})
        deal_data = deals.setdefault(deal_id, {"periods": []})
        
        # Check for existing period
        existing = [p for p in deal_data["periods"] if p.get("period_number") == period_number]
        if existing:
            # Update existing period - allow re-uploading even if distributed (reset for re-processing)
            period_data = existing[0]
            old_status = period_data.get("status")
            if old_status == DistributionStatus.DISTRIBUTED.value:
                # Allow reset for re-processing with new data
                print(f"Resetting period {period_number} from '{old_status}' to 'pending' for re-processing")
        else:
            period_data = {}
        
        now = self._utc_now()
        
        period = DistributionPeriod(
            period_id=period_data.get("period_id") or str(uuid.uuid4()),
            deal_id=deal_id,
            period_number=period_number,
            collection_date=now,
            status=DistributionStatus.PENDING,
            total_collections=collections.get("interest_collected", 0) + collections.get("principal_collected", 0),
            interest_collected=collections.get("interest_collected", 0),
            principal_collected=collections.get("principal_collected", 0),
            prepayments=collections.get("prepayments", 0),
            defaults=collections.get("defaults", 0),
            losses=collections.get("losses", 0),
            recoveries=collections.get("recoveries", 0),
            beginning_balance=collections.get("beginning_balance", 0),
            ending_balance=collections.get("ending_balance", 0),
            servicer_tape_version=servicer_tape_version,
            created_at=period_data.get("created_at") or now,
            updated_at=now,
            created_by=created_by,
        )
        
        # Update or add period
        if existing:
            idx = deal_data["periods"].index(existing[0])
            deal_data["periods"][idx] = period.to_dict()
        else:
            deal_data["periods"].append(period.to_dict())
        
        self._save_data(data)
        return period
    
    # ========== TRUSTEE FUNCTIONS ==========
    
    def get_pending_periods(self, deal_id: str) -> List[DistributionPeriod]:
        """
        Get all pending periods awaiting trustee action.
        
        Parameters
        ----------
        deal_id : str
            Deal identifier
        
        Returns
        -------
        List[DistributionPeriod]
            Periods in PENDING status
        """
        data = self._load_data()
        deal_data = data.get("deals", {}).get(deal_id, {})
        periods = deal_data.get("periods", [])
        
        return [
            DistributionPeriod.from_dict(p)
            for p in periods
            if p.get("status") == DistributionStatus.PENDING.value
        ]
    
    def execute_waterfall_distribution(
        self,
        deal_id: str,
        period_number: int,
        waterfall_results: Dict[str, Any],
        processed_by: Optional[str] = None,
    ) -> Tuple[DistributionPeriod, Dict[str, TrancheDistribution]]:
        """
        Execute waterfall and distribute to tranches (called by Trustee).
        
        This is step 2 of the distribution cycle - the trustee runs the
        waterfall engine and records the results.
        
        Parameters
        ----------
        deal_id : str
            Deal identifier
        period_number : int
            Period to process
        waterfall_results : Dict[str, Any]
            Results from waterfall engine containing:
            - bond_cashflows: per-tranche interest/principal
            - losses_allocated: per-tranche loss allocation
            - reserve_deposit: amount to reserve
            - excess_spread: residual amount
        processed_by : str, optional
            Trustee identifier
        
        Returns
        -------
        Tuple[DistributionPeriod, Dict[str, TrancheDistribution]]
            Updated period and per-tranche distribution details
        """
        data = self._load_data()
        deal_data = data.get("deals", {}).get(deal_id, {})
        periods = deal_data.get("periods", [])
        
        # Find the period
        period_data = next(
            (p for p in periods if p.get("period_number") == period_number),
            None
        )
        if not period_data:
            raise ValueError(f"Period {period_number} not found for deal {deal_id}")
        
        if period_data.get("status") not in [
            DistributionStatus.PENDING.value,
            DistributionStatus.PROCESSING.value
        ]:
            raise ValueError(f"Period {period_number} is not pending")
        
        now = self._utc_now()
        
        # Process waterfall results
        bond_cashflows = waterfall_results.get("bond_cashflows", {})
        losses_allocated = waterfall_results.get("losses_allocated", {})
        beginning_balances = waterfall_results.get("beginning_balances", {})
        ending_balances = waterfall_results.get("ending_balances", {})
        original_balances = waterfall_results.get("original_balances", {})
        
        tranche_distributions: Dict[str, TrancheDistribution] = {}
        total_interest = 0.0
        total_principal = 0.0
        
        for tranche_id, cf in bond_cashflows.items():
            interest_paid = cf.get("interest_paid", 0)
            principal_paid = cf.get("principal_paid", 0)
            interest_due = cf.get("interest_due", interest_paid)
            principal_due = cf.get("principal_due", principal_paid)
            loss = losses_allocated.get(tranche_id, 0)
            begin_bal = beginning_balances.get(tranche_id, 0)
            end_bal = ending_balances.get(tranche_id, begin_bal - principal_paid - loss)
            orig_bal = original_balances.get(tranche_id, begin_bal)
            factor = end_bal / orig_bal if orig_bal > 0 else 0
            
            tranche_distributions[tranche_id] = TrancheDistribution(
                tranche_id=tranche_id,
                interest_due=interest_due,
                interest_paid=interest_paid,
                interest_shortfall=max(0, interest_due - interest_paid),
                principal_due=principal_due,
                principal_paid=principal_paid,
                principal_shortfall=max(0, principal_due - principal_paid),
                loss_allocation=loss,
                beginning_balance=begin_bal,
                ending_balance=end_bal,
                factor=factor,
            )
            
            total_interest += interest_paid
            total_principal += principal_paid
        
        # Update period
        period_data["status"] = DistributionStatus.DISTRIBUTED.value
        period_data["distribution_date"] = now
        period_data["updated_at"] = now
        period_data["processed_by"] = processed_by
        period_data["waterfall_tx_hash"] = self._generate_tx_hash(f"{deal_id}-{period_number}")
        period_data["total_interest_distributed"] = total_interest
        period_data["total_principal_distributed"] = total_principal
        period_data["reserve_deposit"] = waterfall_results.get("reserve_deposit", 0)
        period_data["excess_spread"] = waterfall_results.get("excess_spread", 0)
        period_data["tranche_distributions"] = {
            tid: asdict(td) for tid, td in tranche_distributions.items()
        }
        
        self._save_data(data)
        
        return DistributionPeriod.from_dict(period_data), tranche_distributions
    
    def get_period(self, deal_id: str, period_number: int) -> Optional[DistributionPeriod]:
        """Get a specific distribution period."""
        data = self._load_data()
        deal_data = data.get("deals", {}).get(deal_id, {})
        periods = deal_data.get("periods", [])
        
        period_data = next(
            (p for p in periods if p.get("period_number") == period_number),
            None
        )
        
        return DistributionPeriod.from_dict(period_data) if period_data else None
    
    def get_all_periods(self, deal_id: str) -> List[DistributionPeriod]:
        """Get all distribution periods for a deal."""
        data = self._load_data()
        deal_data = data.get("deals", {}).get(deal_id, {})
        periods = deal_data.get("periods", [])
        
        return [DistributionPeriod.from_dict(p) for p in periods]
    
    def get_latest_period(self, deal_id: str) -> Optional[DistributionPeriod]:
        """Get the most recent distribution period."""
        periods = self.get_all_periods(deal_id)
        if not periods:
            return None
        return max(periods, key=lambda p: p.period_number)
    
    # ========== TOKEN UPDATE FUNCTIONS ==========
    
    def calculate_token_updates(
        self,
        tranche_distributions: Dict[str, TrancheDistribution],
        token_holdings: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate token balance updates based on waterfall distributions.
        
        Parameters
        ----------
        tranche_distributions : Dict[str, TrancheDistribution]
            Distribution details for each tranche
        token_holdings : Dict[str, Dict[str, Any]]
            Current token holdings by tranche_id
        
        Returns
        -------
        Dict[str, Dict[str, Any]]
            Updated holdings with new balances, factors, and yields
        """
        updates = {}
        
        for tranche_id, dist in tranche_distributions.items():
            holdings = token_holdings.get(tranche_id, {})
            
            # Calculate new balance after principal distribution
            old_balance = holdings.get("balance", dist.beginning_balance)
            
            # Principal reduces balance
            principal_reduction = dist.principal_paid
            
            # Losses reduce balance (for affected tranches)
            loss_reduction = dist.loss_allocation
            
            new_balance = max(0, old_balance - principal_reduction - loss_reduction)
            
            # Interest becomes claimable yield
            interest_yield = dist.interest_paid
            
            # Calculate factor
            original_balance = holdings.get("original_balance", dist.beginning_balance)
            new_factor = new_balance / original_balance if original_balance > 0 else 0
            
            updates[tranche_id] = {
                "old_balance": old_balance,
                "new_balance": new_balance,
                "principal_reduction": principal_reduction,
                "loss_reduction": loss_reduction,
                "interest_yield": interest_yield,
                "old_factor": holdings.get("factor", 1.0),
                "new_factor": new_factor,
            }
        
        return updates


def get_distribution_manager(storage_path: Optional[Path] = None) -> DistributionCycleManager:
    """
    Get the distribution cycle manager singleton.
    
    Parameters
    ----------
    storage_path : Path, optional
        Storage path. If None, uses default.
    
    Returns
    -------
    DistributionCycleManager
        The manager instance
    """
    if storage_path is None:
        from config import settings
        storage_path = settings.package_root
    
    return DistributionCycleManager(storage_path)
