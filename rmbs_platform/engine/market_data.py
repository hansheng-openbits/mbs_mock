"""
Market Data Integration Module
===============================

This module provides infrastructure for:
1. Real-time and historical market data access
2. Yield curve construction from market quotes
3. RMBS spread data and pricing benchmarks
4. Economic indicators (HPI, unemployment, etc.)
5. Data validation and anomaly detection

Supported Data Sources:
- Treasury yield curves
- Swap rates
- RMBS spreads (Agency, Prime, Subprime)
- House Price Index (FHFA, Case-Shiller)
- Unemployment rates
- Mortgage rates (Freddie Mac PMMS)

Author: RMBS Platform Development Team
Date: January 29, 2026
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import warnings

from engine.market_risk import YieldCurve, YieldCurveBuilder, InstrumentType


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TreasurySnapshot:
    """Treasury yield curve snapshot."""
    date: str  # YYYY-MM-DD
    tenors: List[float]  # Years
    par_yields: List[float]  # Annual rates (e.g., 0.045 for 4.5%)
    source: str = "US Treasury"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TreasurySnapshot':
        return cls(**data)


@dataclass
class SwapSnapshot:
    """Swap rate snapshot."""
    date: str
    tenors: List[float]  # Years
    swap_rates: List[float]  # Annual rates
    currency: str = "USD"
    source: str = "Market"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SwapSnapshot':
        return cls(**data)


@dataclass
class RMBSSpreadSnapshot:
    """RMBS spread levels by credit tier."""
    date: str
    agency_oas: float  # OAS for Agency RMBS (bps)
    prime_oas: float  # OAS for Prime Non-Agency (bps)
    subprime_oas: float  # OAS for Subprime (bps)
    alt_a_oas: float  # OAS for Alt-A (bps)
    source: str = "Market Survey"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RMBSSpreadSnapshot':
        return cls(**data)


@dataclass
class HPISnapshot:
    """House Price Index snapshot."""
    date: str
    national_index: float  # Index value (base = 100)
    yoy_change: float  # Year-over-year % change (e.g., 0.05 for 5%)
    source: str = "FHFA"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HPISnapshot':
        return cls(**data)


@dataclass
class UnemploymentSnapshot:
    """Unemployment rate snapshot."""
    date: str
    rate: float  # Unemployment rate (e.g., 0.04 for 4%)
    source: str = "BLS"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'UnemploymentSnapshot':
        return cls(**data)


@dataclass
class MortgageRateSnapshot:
    """Mortgage rate snapshot (30-year fixed, conforming)."""
    date: str
    rate_30y: float  # 30-year fixed rate (e.g., 0.065 for 6.5%)
    rate_15y: float  # 15-year fixed rate
    source: str = "Freddie Mac PMMS"
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MortgageRateSnapshot':
        return cls(**data)


@dataclass
class MarketDataSnapshot:
    """Complete market data snapshot for a given date."""
    date: str
    treasury: Optional[TreasurySnapshot] = None
    swaps: Optional[SwapSnapshot] = None
    rmbs_spreads: Optional[RMBSSpreadSnapshot] = None
    hpi: Optional[HPISnapshot] = None
    unemployment: Optional[UnemploymentSnapshot] = None
    mortgage_rates: Optional[MortgageRateSnapshot] = None
    
    def to_dict(self) -> Dict:
        result = {"date": self.date}
        if self.treasury:
            result["treasury"] = self.treasury.to_dict()
        if self.swaps:
            result["swaps"] = self.swaps.to_dict()
        if self.rmbs_spreads:
            result["rmbs_spreads"] = self.rmbs_spreads.to_dict()
        if self.hpi:
            result["hpi"] = self.hpi.to_dict()
        if self.unemployment:
            result["unemployment"] = self.unemployment.to_dict()
        if self.mortgage_rates:
            result["mortgage_rates"] = self.mortgage_rates.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MarketDataSnapshot':
        return cls(
            date=data["date"],
            treasury=TreasurySnapshot.from_dict(data["treasury"]) if "treasury" in data else None,
            swaps=SwapSnapshot.from_dict(data["swaps"]) if "swaps" in data else None,
            rmbs_spreads=RMBSSpreadSnapshot.from_dict(data["rmbs_spreads"]) if "rmbs_spreads" in data else None,
            hpi=HPISnapshot.from_dict(data["hpi"]) if "hpi" in data else None,
            unemployment=UnemploymentSnapshot.from_dict(data["unemployment"]) if "unemployment" in data else None,
            mortgage_rates=MortgageRateSnapshot.from_dict(data["mortgage_rates"]) if "mortgage_rates" in data else None
        )


# ============================================================================
# Market Data Provider
# ============================================================================

class MarketDataProvider:
    """
    Provider for market data with historical storage and retrieval.
    
    Features:
    - Store and retrieve market data snapshots
    - Build yield curves from market data
    - Validate data for anomalies
    - Support multiple data sources
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize market data provider.
        
        Args:
            data_dir: Directory for storing market data snapshots.
                     Defaults to ./market_data/
        """
        if data_dir is None:
            # Use package root / market_data
            package_root = Path(__file__).parent.parent
            self.data_dir = package_root / "market_data"
        else:
            self.data_dir = Path(data_dir)
        
        # Create directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.data_dir / "snapshots").mkdir(exist_ok=True)
        (self.data_dir / "curves").mkdir(exist_ok=True)
    
    # ========================================================================
    # Snapshot Management
    # ========================================================================
    
    def save_snapshot(self, snapshot: MarketDataSnapshot) -> None:
        """Save a market data snapshot to disk."""
        filename = f"{snapshot.date}.json"
        filepath = self.data_dir / "snapshots" / filename
        
        with open(filepath, 'w') as f:
            json.dump(snapshot.to_dict(), f, indent=2)
    
    def load_snapshot(self, date: str) -> Optional[MarketDataSnapshot]:
        """
        Load a market data snapshot for a given date.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            MarketDataSnapshot if found, None otherwise
        """
        filename = f"{date}.json"
        filepath = self.data_dir / "snapshots" / filename
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return MarketDataSnapshot.from_dict(data)
    
    def get_latest_snapshot(self) -> Optional[MarketDataSnapshot]:
        """Get the most recent market data snapshot."""
        snapshots_dir = self.data_dir / "snapshots"
        snapshot_files = sorted(snapshots_dir.glob("*.json"), reverse=True)
        
        if not snapshot_files:
            return None
        
        with open(snapshot_files[0], 'r') as f:
            data = json.load(f)
        
        return MarketDataSnapshot.from_dict(data)
    
    def get_snapshot_range(self, start_date: str, end_date: str) -> List[MarketDataSnapshot]:
        """
        Get all snapshots in a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of snapshots, sorted by date
        """
        snapshots = []
        snapshots_dir = self.data_dir / "snapshots"
        
        for filepath in sorted(snapshots_dir.glob("*.json")):
            date = filepath.stem
            if start_date <= date <= end_date:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                snapshots.append(MarketDataSnapshot.from_dict(data))
        
        return snapshots
    
    # ========================================================================
    # Yield Curve Construction
    # ========================================================================
    
    def build_treasury_curve(self, date: str) -> Optional[YieldCurve]:
        """
        Build a YieldCurve from Treasury data.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            YieldCurve if data available, None otherwise
        """
        snapshot = self.load_snapshot(date)
        if not snapshot or not snapshot.treasury:
            return None
        
        treasury = snapshot.treasury
        
        # Bootstrap zero curve from par yields using YieldCurveBuilder
        builder = YieldCurveBuilder(curve_date=date)
        
        for tenor, par_yield in zip(treasury.tenors, treasury.par_yields):
            builder.add_instrument(
                instrument_id=f"UST_{tenor}Y",
                maturity=tenor,
                rate=par_yield,
                instrument_type=InstrumentType.TREASURY_PAR
            )
        
        curve = builder.build()
        
        return curve
    
    def build_swap_curve(self, date: str) -> Optional[YieldCurve]:
        """Build a YieldCurve from swap rates."""
        snapshot = self.load_snapshot(date)
        if not snapshot or not snapshot.swaps:
            return None
        
        swaps = snapshot.swaps
        
        # For swaps, rates are approximately equal to zero rates
        # (slight approximation, but acceptable for most use cases)
        curve = YieldCurve(
            curve_date=date,
            tenors=swaps.tenors,
            zero_rates=swaps.swap_rates
        )
        
        return curve
    
    # ========================================================================
    # RMBS Spread Retrieval
    # ========================================================================
    
    def get_rmbs_spread(self, date: str, credit_tier: str) -> Optional[float]:
        """
        Get RMBS OAS for a given credit tier.
        
        Args:
            date: Date in YYYY-MM-DD format
            credit_tier: One of 'agency', 'prime', 'subprime', 'alt_a'
            
        Returns:
            OAS in basis points, or None if not available
        """
        snapshot = self.load_snapshot(date)
        if not snapshot or not snapshot.rmbs_spreads:
            return None
        
        spreads = snapshot.rmbs_spreads
        
        tier_map = {
            'agency': spreads.agency_oas,
            'prime': spreads.prime_oas,
            'subprime': spreads.subprime_oas,
            'alt_a': spreads.alt_a_oas
        }
        
        return tier_map.get(credit_tier.lower())
    
    # ========================================================================
    # Economic Indicators
    # ========================================================================
    
    def get_hpi(self, date: str) -> Optional[HPISnapshot]:
        """Get House Price Index for a date."""
        snapshot = self.load_snapshot(date)
        return snapshot.hpi if snapshot else None
    
    def get_unemployment(self, date: str) -> Optional[UnemploymentSnapshot]:
        """Get unemployment rate for a date."""
        snapshot = self.load_snapshot(date)
        return snapshot.unemployment if snapshot else None
    
    def get_mortgage_rates(self, date: str) -> Optional[MortgageRateSnapshot]:
        """Get mortgage rates for a date."""
        snapshot = self.load_snapshot(date)
        return snapshot.mortgage_rates if snapshot else None
    
    # ========================================================================
    # Data Validation
    # ========================================================================
    
    def validate_snapshot(self, snapshot: MarketDataSnapshot) -> List[str]:
        """
        Validate a market data snapshot for anomalies.
        
        Returns:
            List of warning messages (empty if no issues)
        """
        warnings = []
        
        # Validate Treasury rates
        if snapshot.treasury:
            rates = snapshot.treasury.par_yields
            
            # Check for negative rates (unusual but possible)
            if any(r < 0 for r in rates):
                warnings.append("Treasury: Negative rates detected")
            
            # Check for inverted curve (short > long)
            if len(rates) >= 2:
                if rates[0] > rates[-1]:
                    warnings.append("Treasury: Inverted yield curve detected")
            
            # Check for unrealistic levels
            if any(r > 0.20 for r in rates):
                warnings.append("Treasury: Rates above 20% (check data)")
        
        # Validate RMBS spreads
        if snapshot.rmbs_spreads:
            spreads = snapshot.rmbs_spreads
            
            # Check spread ordering (agency < prime < subprime)
            if not (spreads.agency_oas < spreads.prime_oas < spreads.subprime_oas):
                warnings.append("RMBS: Spread ordering violation (expected: agency < prime < subprime)")
            
            # Check for negative spreads
            if any(s < 0 for s in [spreads.agency_oas, spreads.prime_oas, spreads.subprime_oas]):
                warnings.append("RMBS: Negative spreads detected")
            
            # Check for unrealistic spreads
            if spreads.subprime_oas > 1000:
                warnings.append("RMBS: Subprime spread > 1000 bps (check data)")
        
        # Validate HPI
        if snapshot.hpi:
            hpi = snapshot.hpi
            
            # Check for extreme YoY changes
            if abs(hpi.yoy_change) > 0.30:
                warnings.append(f"HPI: Extreme YoY change: {hpi.yoy_change:.1%}")
        
        # Validate unemployment
        if snapshot.unemployment:
            unemp = snapshot.unemployment
            
            # Check for unrealistic levels
            if unemp.rate < 0 or unemp.rate > 0.25:
                warnings.append(f"Unemployment: Unusual rate: {unemp.rate:.1%}")
        
        return warnings
    
    # ========================================================================
    # Time Series Utilities
    # ========================================================================
    
    def get_rate_history(self, start_date: str, end_date: str, tenor: float) -> List[Tuple[str, float]]:
        """
        Get historical Treasury rates for a specific tenor.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            tenor: Tenor in years (e.g., 10.0 for 10Y)
            
        Returns:
            List of (date, rate) tuples
        """
        snapshots = self.get_snapshot_range(start_date, end_date)
        history = []
        
        for snapshot in snapshots:
            if snapshot.treasury:
                # Find closest tenor
                tenors = snapshot.treasury.tenors
                rates = snapshot.treasury.par_yields
                
                if tenor in tenors:
                    idx = tenors.index(tenor)
                    history.append((snapshot.date, rates[idx]))
                else:
                    # Interpolate if needed
                    # Simple linear interpolation
                    for i in range(len(tenors) - 1):
                        if tenors[i] <= tenor <= tenors[i+1]:
                            # Linear interpolation
                            t1, t2 = tenors[i], tenors[i+1]
                            r1, r2 = rates[i], rates[i+1]
                            interpolated_rate = r1 + (r2 - r1) * (tenor - t1) / (t2 - t1)
                            history.append((snapshot.date, interpolated_rate))
                            break
        
        return history
    
    def get_spread_history(self, start_date: str, end_date: str, credit_tier: str) -> List[Tuple[str, float]]:
        """
        Get historical RMBS spread levels.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            credit_tier: 'agency', 'prime', 'subprime', or 'alt_a'
            
        Returns:
            List of (date, spread_bps) tuples
        """
        snapshots = self.get_snapshot_range(start_date, end_date)
        history = []
        
        for snapshot in snapshots:
            spread = self.get_rmbs_spread(snapshot.date, credit_tier)
            if spread is not None:
                history.append((snapshot.date, spread))
        
        return history


# ============================================================================
# Sample Data Generator (for testing and demos)
# ============================================================================

class SampleDataGenerator:
    """Generate realistic sample market data for testing."""
    
    @staticmethod
    def generate_sample_snapshot(date: str) -> MarketDataSnapshot:
        """Generate a realistic market data snapshot."""
        
        # Parse date to adjust for realistic trends
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        
        # Treasury curve (slightly upward sloping)
        treasury = TreasurySnapshot(
            date=date,
            tenors=[0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0],
            par_yields=[
                0.0420, 0.0430, 0.0440, 0.0450, 0.0455,
                0.0460, 0.0465, 0.0470, 0.0475, 0.0480
            ],
            source="US Treasury"
        )
        
        # Swap rates (slightly above Treasuries)
        swaps = SwapSnapshot(
            date=date,
            tenors=[1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0],
            swap_rates=[
                0.0445, 0.0455, 0.0460, 0.0465, 0.0470,
                0.0475, 0.0480, 0.0485, 0.0490
            ],
            currency="USD"
        )
        
        # RMBS spreads (typical mid-2020s levels)
        rmbs_spreads = RMBSSpreadSnapshot(
            date=date,
            agency_oas=25.0,
            prime_oas=150.0,
            subprime_oas=400.0,
            alt_a_oas=250.0,
            source="Market Survey"
        )
        
        # House Price Index
        hpi = HPISnapshot(
            date=date,
            national_index=350.0,
            yoy_change=0.05,  # 5% YoY growth
            source="FHFA"
        )
        
        # Unemployment
        unemployment = UnemploymentSnapshot(
            date=date,
            rate=0.04,  # 4%
            source="BLS"
        )
        
        # Mortgage rates
        mortgage_rates = MortgageRateSnapshot(
            date=date,
            rate_30y=0.0675,  # 6.75%
            rate_15y=0.0600,  # 6.00%
            source="Freddie Mac PMMS"
        )
        
        return MarketDataSnapshot(
            date=date,
            treasury=treasury,
            swaps=swaps,
            rmbs_spreads=rmbs_spreads,
            hpi=hpi,
            unemployment=unemployment,
            mortgage_rates=mortgage_rates
        )
    
    @staticmethod
    def generate_sample_history(
        start_date: str,
        end_date: str,
        frequency_days: int = 7
    ) -> List[MarketDataSnapshot]:
        """
        Generate a history of sample market data.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            frequency_days: Days between snapshots (default: weekly)
            
        Returns:
            List of market data snapshots
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        snapshots = []
        current = start
        
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            snapshot = SampleDataGenerator.generate_sample_snapshot(date_str)
            snapshots.append(snapshot)
            
            current += timedelta(days=frequency_days)
        
        return snapshots
