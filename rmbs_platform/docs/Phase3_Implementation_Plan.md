# Phase 3: Full Pricing Engine - Implementation Plan

**Start Date:** January 29, 2026  
**Estimated Duration:** 4-6 weeks  
**Status:** 🚀 Starting  

---

## Overview

Phase 3 transforms the RMBS Platform from a simulation engine into a **complete pricing and valuation system** by combining market risk analytics (Phase 2B) and credit risk analytics (Phase 2C) with advanced Monte Carlo simulation capabilities.

**Key Deliverables:**
1. Credit-Adjusted OAS Calculator
2. Monte Carlo Pricing Engine
3. Market Data Integration Layer
4. Historical Database Infrastructure

---

## Architecture

```
                    PHASE 3: FULL PRICING ENGINE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Credit-Adjusted OAS Calculator                │ │
│  │  (Combines Market Risk + Credit Risk)                      │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────▼───────────────┐  ┌─────────────────────┐   │
│  │   Monte Carlo Pricing Engine   │  │  Market Data Layer  │   │
│  │  • Interest rate paths         │◄─┤  • Real-time feeds  │   │
│  │  • Prepayment scenarios        │  │  • Historical DB    │   │
│  │  • Default/severity paths      │  │  • Curve snapshots  │   │
│  │  • Path-dependent cashflows    │  └─────────────────────┘   │
│  └────────────────┬───────────────┘                             │
│                   │                                              │
│  ┌────────────────▼───────────────────────────────────────────┐ │
│  │              Pricing Results & Analytics                    │ │
│  │  • Fair value                  • Greeks                     │ │
│  │  • Credit-adjusted OAS         • Key rate durations         │ │
│  │  • Price/yield relationship    • Convexity profile          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component 1: Credit-Adjusted OAS Calculator

### Objective
Combine risk-free discount rates (Phase 2B) with credit spreads (Phase 2C) to calculate option-adjusted spreads that account for both prepayment risk and credit risk.

### Formula
```
Price = E[ Σ CF_t × DF(r_RF + OAS + Credit_Spread + Liquidity_Spread) ]

Where:
  CF_t            = Cashflow at time t (prepayment/default adjusted)
  r_RF            = Risk-free rate from yield curve
  OAS             = Option-Adjusted Spread (solve for this)
  Credit_Spread   = f(PD, LGD, Recovery_Lag)
  Liquidity_Spread = Market illiquidity premium
```

### Implementation Steps

#### 1.1 Credit Spread Calculation
**File:** `engine/pricing.py`

```python
def calculate_credit_spread(
    pd: float,           # Probability of default
    lgd: float,          # Loss given default
    recovery_lag: float, # Time to recovery (years)
    risk_free_rate: float
) -> float:
    """
    Calculate credit spread from PD and LGD.
    
    Formula: Credit Spread ≈ (PD × LGD) / (1 - PD × LGD)
    
    Adjusted for recovery lag and compounding.
    """
```

#### 1.2 OAS Solver with Credit Adjustment
**File:** `engine/pricing.py`

```python
def solve_credit_adjusted_oas(
    bond: BondState,
    market_price: float,
    yield_curve: YieldCurve,
    pd: float,
    lgd: float,
    prepayment_model: callable,
    target_tol: float = 0.01
) -> dict:
    """
    Solve for OAS that makes PV(cashflows) = market_price.
    
    Incorporates:
    - Risk-free discounting (yield curve)
    - Credit spread (from PD/LGD)
    - Prepayment optionality (from prepayment model)
    
    Returns:
        {
            'oas': float,
            'z_spread': float,
            'credit_spread': float,
            'liquidity_spread': float (implied),
            'iterations': int,
            'converged': bool
        }
    """
```

#### 1.3 Integration with Existing Components
- Use `YieldCurve` from `engine/market_risk.py`
- Use `DefaultModel` and `SeverityModel` from Phase 2C
- Use `OASCalculator` from `engine/market_risk.py` as base

**Status:** Ready to implement

---

## Component 2: Monte Carlo Pricing Engine

### Objective
Simulate thousands of economic scenarios to price RMBS bonds with embedded options (prepayment, default) and path-dependent features.

### Monte Carlo Framework

#### 2.1 Scenario Generator
**File:** `engine/monte_carlo.py`

```python
class ScenarioGenerator:
    """
    Generate correlated economic scenarios for Monte Carlo simulation.
    """
    
    def generate_interest_rate_paths(
        self,
        n_paths: int,
        n_periods: int,
        initial_curve: YieldCurve,
        volatility: float,
        mean_reversion: float
    ) -> np.ndarray:
        """
        Generate interest rate paths using Vasicek or CIR model.
        
        Returns: (n_paths, n_periods, n_tenors) array
        """
    
    def generate_hpi_paths(
        self,
        n_paths: int,
        n_periods: int,
        initial_hpi: float,
        drift: float,
        volatility: float,
        correlation_with_rates: float
    ) -> np.ndarray:
        """
        Generate House Price Index paths correlated with rates.
        
        Returns: (n_paths, n_periods) array
        """
    
    def generate_unemployment_paths(
        self,
        n_paths: int,
        n_periods: int,
        initial_unemployment: float,
        scenarios: dict  # e.g., baseline, adverse, severely adverse
    ) -> np.ndarray:
        """
        Generate unemployment rate paths for stress testing.
        
        Returns: (n_paths, n_periods) array
        """
```

#### 2.2 Path-Dependent Cashflow Engine
**File:** `engine/monte_carlo.py`

```python
class MonteCarloEngine:
    """
    Monte Carlo pricing engine for RMBS.
    """
    
    def __init__(
        self,
        deal_def: DealDefinition,
        n_paths: int = 1000,
        seed: int = 42
    ):
        self.deal_def = deal_def
        self.n_paths = n_paths
        self.scenario_gen = ScenarioGenerator(seed=seed)
    
    def simulate_path(
        self,
        path_id: int,
        rate_path: np.ndarray,
        hpi_path: np.ndarray,
        unemployment_path: np.ndarray
    ) -> dict:
        """
        Simulate a single path through the deal life.
        
        Returns:
            {
                'bond_cashflows': Dict[str, np.ndarray],
                'collateral_balance': np.ndarray,
                'defaults': np.ndarray,
                'prepayments': np.ndarray
            }
        """
    
    def price_bond(
        self,
        bond_id: str,
        discount_curve: YieldCurve,
        oas: float = 0.0
    ) -> dict:
        """
        Price a bond using Monte Carlo simulation.
        
        Returns:
            {
                'fair_value': float,
                'mean_cashflow': np.ndarray,
                'std_cashflow': np.ndarray,
                'paths': Dict[int, np.ndarray],  # Selected paths
                'convergence': dict
            }
        """
    
    def calculate_greeks(
        self,
        bond_id: str,
        base_price: float,
        shift_bps: int = 25
    ) -> dict:
        """
        Calculate option-adjusted Greeks via Monte Carlo.
        
        Returns:
            {
                'delta': float,  # dP/dr
                'gamma': float,  # d²P/dr²
                'vega': float,   # dP/dσ
                'theta': float   # dP/dt
            }
        """
```

#### 2.3 Variance Reduction Techniques
- **Antithetic variates:** For each path, simulate opposite path
- **Control variates:** Use known bond as control
- **Importance sampling:** Oversample tail scenarios

**Status:** Ready to implement

---

## Component 3: Market Data Integration

### Objective
Create a flexible layer for ingesting real-time and historical market data from multiple sources.

### Data Sources

#### 3.1 Yield Curves
- **US Treasury:** Daily par yields (1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y)
- **SOFR:** Overnight, term rates (1M, 3M, 6M, 12M)
- **Swap Curves:** USD interest rate swaps (2Y, 3Y, 5Y, 7Y, 10Y, 30Y)

#### 3.2 Spread Indices
- **RMBS Spreads:** Agency RMBS 30Y spreads (current coupon, specified pools)
- **Credit Spreads:** Investment-grade, high-yield corporate spreads
- **Mortgage Basis:** MBA purchase application index, refinance index

#### 3.3 Economic Indicators
- **HPI:** S&P CoreLogic Case-Shiller Home Price Index
- **Unemployment:** U.S. unemployment rate (monthly)
- **GDP:** Real GDP growth (quarterly)

### Implementation

#### 3.1 Market Data Provider Interface
**File:** `engine/market_data.py`

```python
from abc import ABC, abstractmethod
from datetime import date

class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    def get_yield_curve(self, curve_id: str, as_of_date: date) -> YieldCurve:
        """Fetch yield curve for a given date."""
    
    @abstractmethod
    def get_spread(self, security_id: str, as_of_date: date) -> float:
        """Fetch spread for a security."""
    
    @abstractmethod
    def get_economic_indicator(
        self,
        indicator: str,
        as_of_date: date
    ) -> float:
        """Fetch economic indicator (HPI, unemployment, etc.)."""

class FileBasedProvider(MarketDataProvider):
    """
    File-based market data provider (CSV/JSON).
    For development and backtesting.
    """

class APIBasedProvider(MarketDataProvider):
    """
    API-based market data provider.
    Integrates with Bloomberg, Reuters, FRED, etc.
    """

class DatabaseProvider(MarketDataProvider):
    """
    Database-based market data provider.
    For production with historical database.
    """
```

#### 3.2 Market Data Manager
**File:** `engine/market_data.py`

```python
class MarketDataManager:
    """
    Central manager for market data access.
    Handles caching, fallback providers, and staleness checks.
    """
    
    def __init__(self, providers: list[MarketDataProvider]):
        self.providers = providers
        self.cache = {}
    
    def get_yield_curve(
        self,
        curve_id: str,
        as_of_date: date,
        max_staleness_days: int = 1
    ) -> YieldCurve:
        """
        Get yield curve with fallback and caching.
        
        Tries providers in order until successful.
        Caches results for performance.
        """
    
    def get_market_snapshot(self, as_of_date: date) -> dict:
        """
        Get complete market snapshot for a date.
        
        Returns:
            {
                'treasury_curve': YieldCurve,
                'sofr_curve': YieldCurve,
                'swap_curve': YieldCurve,
                'rmbs_spread': float,
                'hpi': float,
                'unemployment': float
            }
        """
```

**Status:** Ready to implement

---

## Component 4: Historical Database

### Objective
Store and efficiently query historical market data for backtesting, model calibration, and historical analysis.

### Database Schema

#### 4.1 Yield Curves Table
```sql
CREATE TABLE yield_curves (
    id SERIAL PRIMARY KEY,
    curve_id VARCHAR(50) NOT NULL,        -- 'UST', 'SOFR', 'SWAP'
    as_of_date DATE NOT NULL,
    tenor_months INTEGER NOT NULL,        -- 1, 3, 6, 12, 24, 60, 120, 360
    rate DECIMAL(10, 6) NOT NULL,         -- Zero rate (e.g., 0.0450 for 4.50%)
    rate_type VARCHAR(20) NOT NULL,       -- 'ZERO', 'PAR', 'FORWARD'
    source VARCHAR(50),                   -- 'TREASURY', 'FRED', 'BLOOMBERG'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(curve_id, as_of_date, tenor_months, rate_type)
);

CREATE INDEX idx_yield_curves_date ON yield_curves(as_of_date);
CREATE INDEX idx_yield_curves_curve ON yield_curves(curve_id, as_of_date);
```

#### 4.2 Spreads Table
```sql
CREATE TABLE spreads (
    id SERIAL PRIMARY KEY,
    security_id VARCHAR(100) NOT NULL,    -- CUSIP, ISIN, or index ID
    as_of_date DATE NOT NULL,
    spread_bps INTEGER NOT NULL,          -- Spread in basis points
    spread_type VARCHAR(20) NOT NULL,     -- 'Z_SPREAD', 'OAS', 'ASW'
    duration DECIMAL(10, 4),              -- Modified duration
    convexity DECIMAL(10, 4),             -- Convexity
    price DECIMAL(10, 4),                 -- Clean price
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(security_id, as_of_date, spread_type)
);

CREATE INDEX idx_spreads_date ON spreads(as_of_date);
CREATE INDEX idx_spreads_security ON spreads(security_id, as_of_date);
```

#### 4.3 Economic Indicators Table
```sql
CREATE TABLE economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_id VARCHAR(50) NOT NULL,    -- 'HPI', 'UNEMPLOYMENT', 'GDP'
    as_of_date DATE NOT NULL,
    value DECIMAL(12, 4) NOT NULL,
    frequency VARCHAR(20) NOT NULL,       -- 'DAILY', 'MONTHLY', 'QUARTERLY'
    source VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(indicator_id, as_of_date)
);

CREATE INDEX idx_indicators_date ON economic_indicators(as_of_date);
CREATE INDEX idx_indicators_id ON economic_indicators(indicator_id, as_of_date);
```

### Database Implementation Options

#### Option 1: SQLite (Development/Testing)
- **Pros:** Zero setup, file-based, fast for small datasets
- **Cons:** Limited concurrency, not scalable
- **Use case:** Development, testing, single-user

#### Option 2: PostgreSQL (Production)
- **Pros:** Production-grade, scalable, advanced analytics (TimescaleDB)
- **Cons:** Requires server setup
- **Use case:** Production deployment, multi-user

#### Option 3: Hybrid (Recommended for Phase 3)
- **Development:** SQLite with sample data (last 2 years)
- **Production:** PostgreSQL with full history (20+ years)
- **Migration path:** Simple schema compatibility

### Python Database Interface
**File:** `engine/database.py`

```python
class MarketDataDB:
    """
    Historical market data database interface.
    """
    
    def __init__(self, db_path: str = "market_data.db"):
        self.db_path = db_path
        self.conn = None
    
    def store_yield_curve(
        self,
        curve_id: str,
        as_of_date: date,
        curve: YieldCurve
    ) -> None:
        """Store a yield curve snapshot."""
    
    def get_yield_curve(
        self,
        curve_id: str,
        as_of_date: date
    ) -> YieldCurve:
        """Retrieve a yield curve snapshot."""
    
    def get_yield_curve_history(
        self,
        curve_id: str,
        start_date: date,
        end_date: date,
        tenor_months: int
    ) -> pd.DataFrame:
        """Get time series of rates for a specific tenor."""
    
    def store_spread(
        self,
        security_id: str,
        as_of_date: date,
        spread_bps: int,
        spread_type: str = 'OAS',
        **kwargs
    ) -> None:
        """Store a spread observation."""
    
    def get_spread_history(
        self,
        security_id: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Get spread time series."""
    
    def backfill_from_csv(
        self,
        csv_path: str,
        data_type: str  # 'curves', 'spreads', 'indicators'
    ) -> int:
        """Bulk load historical data from CSV."""
```

**Status:** Ready to implement

---

## Implementation Timeline

### Week 1-2: Credit-Adjusted OAS
- [ ] Implement `calculate_credit_spread()` function
- [ ] Build `solve_credit_adjusted_oas()` solver
- [ ] Integrate with Phase 2B (YieldCurve) and Phase 2C (PD/LGD)
- [ ] Create test suite with known examples
- [ ] Validate against industry benchmarks

**Deliverable:** `engine/pricing.py` with credit-adjusted OAS

### Week 2-3: Monte Carlo Engine (Core)
- [ ] Implement `ScenarioGenerator` for interest rate paths
- [ ] Build `MonteCarloEngine.simulate_path()`
- [ ] Create variance reduction techniques
- [ ] Implement convergence diagnostics
- [ ] Build test suite with simple bonds

**Deliverable:** `engine/monte_carlo.py` (core simulation)

### Week 3-4: Monte Carlo Engine (Advanced)
- [ ] Add HPI and unemployment path generation
- [ ] Implement prepayment/default path correlation
- [ ] Build Greeks calculation (delta, gamma, vega)
- [ ] Create comprehensive test suite
- [ ] Performance optimization (parallel paths)

**Deliverable:** Complete Monte Carlo pricing engine

### Week 4-5: Market Data Integration
- [ ] Design provider interface (`MarketDataProvider`)
- [ ] Implement `FileBasedProvider` for development
- [ ] Build `MarketDataManager` with caching
- [ ] Create sample historical data files
- [ ] Test with real FRED data (US Treasury, HPI)

**Deliverable:** `engine/market_data.py` + sample data

### Week 5-6: Historical Database
- [ ] Design database schema (SQLite for Phase 3)
- [ ] Implement `MarketDataDB` interface
- [ ] Backfill 2-year history (Treasury, SOFR, HPI)
- [ ] Build query/analytics functions
- [ ] Create migration script for PostgreSQL

**Deliverable:** `engine/database.py` + historical DB

### Week 6: Integration & Testing
- [ ] End-to-end test: Price RMBS bond with Monte Carlo
- [ ] Validate OAS vs. market benchmarks
- [ ] Performance testing (1000 paths in <60 seconds)
- [ ] Documentation and examples
- [ ] Phase 3 summary document

**Deliverable:** Phase 3 complete and tested

---

## Testing Strategy

### Unit Tests
- `test_credit_adjusted_oas.py` - OAS solver accuracy
- `test_monte_carlo_scenarios.py` - Scenario generation
- `test_monte_carlo_pricing.py` - Path simulation and pricing
- `test_market_data.py` - Data provider interfaces
- `test_database.py` - Database operations

### Integration Tests
- `test_phase3_integration.py` - Full pricing workflow
- `test_phase3_performance.py` - Speed and scalability

### Validation Tests
- Compare to Bloomberg/Intex pricing (if available)
- Compare to analytical approximations for simple bonds
- Stress test with extreme scenarios

---

## Success Criteria

### Functional
- [ ] Credit-adjusted OAS matches industry formulas (±1 bp)
- [ ] Monte Carlo converges to stable price (±0.1% with 1000 paths)
- [ ] Greeks match finite difference calculations (±5%)
- [ ] Market data integration works with real FRED API
- [ ] Database stores/retrieves 2+ years of history

### Performance
- [ ] 1000-path Monte Carlo completes in <60 seconds
- [ ] OAS solver converges in <10 iterations (typical)
- [ ] Database queries return in <100ms (typical)

### Quality
- [ ] >90% code coverage on new modules
- [ ] All tests pass
- [ ] Documentation complete
- [ ] Examples and tutorials provided

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Monte Carlo convergence slow | High | Implement variance reduction (antithetic, control variates) |
| Market data API rate limits | Medium | Cache aggressively, use fallback providers |
| Database schema changes | Low | Version schema, create migration scripts |
| OAS solver non-convergence | Medium | Robust initialization, bracketing methods |

---

## Documentation Deliverables

1. **Technical Documentation**
   - `docs/Phase3_Complete_Summary.md` - Implementation summary
   - `docs/Phase3_Pricing_Theory.md` - Mathematical foundations
   - `docs/Phase3_API_Reference.md` - Function/class reference

2. **User Documentation**
   - `docs/Phase3_User_Guide.md` - How to price bonds
   - `docs/Phase3_Examples.md` - Worked examples

3. **Test Documentation**
   - `RUN_PHASE3_TESTS.md` - Test runner guide
   - `docs/Phase3_Validation_Results.md` - Test results

---

## Next Steps After Phase 3

Once Phase 3 is complete, the platform will have:
- ✅ Full pricing capabilities (fair value, OAS, Greeks)
- ✅ Monte Carlo simulation engine
- ✅ Real-time and historical market data
- ✅ Production-ready pricing API

**This enables:**
- **Phase 4:** Portfolio analytics (multi-deal, VAR, optimization)
- **Phase 5:** Web3 integration (tokenization, smart contracts)
- **Production Deployment:** Real-world pricing and risk management

---

**Status:** Ready to begin implementation  
**Next Action:** Start with `engine/pricing.py` (credit-adjusted OAS)
