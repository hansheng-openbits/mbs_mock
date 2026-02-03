# RMBS Platform: Industry-Grade Build Plan

## Executive Summary

This document provides a detailed, phased roadmap to transform the current RMBS platform from a **prototype simulator** into an **industry-grade pricing and risk analytics engine** suitable for institutional RWA applications and Web3 tokenization.

---

## Current State Assessment

### ✅ What's Already Built (Strong Foundation)

| Component | Status | Location |
|-----------|--------|----------|
| Deal loader with validation | ✅ Complete | `engine/loader.py` |
| Sequential waterfall execution | ✅ Complete | `engine/waterfall.py` |
| **Iterative waterfall solver** | ✅ Just Added | `engine/waterfall.py` |
| **Loan-level collateral model** | ✅ Just Added | `engine/collateral.py` |
| Rep-line collateral model | ✅ Complete | `engine/collateral.py` |
| ML prepay/default models | ✅ Complete | `ml/models.py`, `ml/portfolio.py` |
| Stochastic rate generator | ✅ Complete | `ml/models.py` |
| Stress testing framework | ✅ Complete | `engine/stress_testing.py` |
| Credit enhancement tracker | ✅ Complete | `engine/credit_enhancement.py` |
| Advanced structures (PAC/TAC/IO/PO) | ✅ Complete | `engine/structures.py` |
| Expression engine for rules | ✅ Complete | `engine/compute.py` |
| REST API | ✅ Complete | `api_main.py` |
| Streamlit UI | ✅ Complete | `ui/` |
| Severity model | ✅ Complete | `ml/severity.py` |
| Freddie Mac ETL | ✅ Complete | `ml/etl_freddie.py` |

### ❌ Gaps for Industry Grade

| Gap | Severity | Impact |
|-----|----------|--------|
| Loan state machine (DQ buckets, FC, REO) | 🔴 Critical | Can't model delinquency cure logic |
| Net WAC cap waterfall integration | 🔴 Critical | Overestimates interest for capped deals |
| Servicer data normalization layer | 🔴 Critical | Can't ingest real servicer tapes |
| ARM/IO/hybrid loan support | 🟡 High | Limited to fixed-rate loans |
| Pricing metrics (OAS, duration, convexity) | 🟡 High | Can't price bonds properly |
| Trigger cure logic with counters | 🟡 High | Triggers "flicker" incorrectly |
| Validation/backtesting framework | 🟡 High | No confidence in accuracy |
| Performance optimization | 🟠 Medium | Slow for large pools |
| Monte Carlo cashflow distribution | 🟠 Medium | Limited risk metrics |

---

## Phase 1: Data Ingestion & Loan State Machine (Weeks 1-6)

**Objective**: Build the canonical loan schema and state machine that underpins all downstream calculations.

### 1.1 Canonical Loan Schema

Create a comprehensive loan data model that handles all loan types and statuses.

```
engine/loan_schema.py (NEW)
├── LoanRecord (dataclass)
│   ├── Identification: loan_id, pool_id, original_loan_id
│   ├── Balances: original_upb, current_upb, scheduled_upb
│   ├── Rates: note_rate, margin, index, caps/floors
│   ├── Terms: original_term, remaining_term, amortization_type
│   ├── Credit: fico, dti, ltv, cltv
│   ├── Property: state, zip, property_type, occupancy
│   ├── Status: current_status, days_delinquent, fc_flag, reo_flag
│   ├── Modification: mod_flag, mod_rate, mod_term
│   └── Derived: rate_incentive, burnout, seasoning
```

**Deliverables**:
- [ ] `LoanRecord` dataclass with 50+ fields
- [ ] Validation rules for each field
- [ ] Column mapping for Freddie, Fannie, and private-label formats
- [ ] Unit tests with edge cases

### 1.2 Servicer Data Normalization Layer

Build an ingestion layer that converts raw servicer tapes to canonical format.

```
engine/servicer_normalization.py (NEW)
├── ServicerTapeParser
│   ├── detect_format(file) → FormatType
│   ├── parse_freddie(file) → List[LoanRecord]
│   ├── parse_fannie(file) → List[LoanRecord]
│   ├── parse_generic(file, mapping) → List[LoanRecord]
│   └── validate_tape(records) → ValidationReport
```

**Key Features**:
- Auto-detect separator (pipe, comma, tab)
- Map raw status codes to canonical (Current → 0, 30-Days → 1, etc.)
- Derive calculated fields (interest_due = balance × rate / 12)
- Reconciliation checks (begin_balance - end_balance = principal + chargeoffs)

**Deliverables**:
- [ ] Parser for Freddie Mac format
- [ ] Parser for Fannie Mae format
- [ ] Generic parser with configurable mapping
- [ ] Validation report with error details

### 1.3 Loan State Machine

Implement a proper state machine for loan lifecycle.

```
engine/loan_state_machine.py (NEW)
├── LoanStatus (Enum)
│   ├── CURRENT, DQ_30, DQ_60, DQ_90, DQ_120_PLUS
│   ├── FORECLOSURE, REO, LIQUIDATED
│   ├── PREPAID_FULL, PREPAID_PARTIAL
│   ├── MODIFIED, BANKRUPTCY
│   └── TERMINATED
├── TransitionMatrix
│   └── get_transition_prob(from_status, to_status, loan_features)
├── LoanStateMachine
│   ├── apply_month(loan, collections, scenario)
│   ├── calculate_cashflows(loan, status)
│   └── track_timeline(loan) → List[StatusChange]
```

**State Transitions**:
```
CURRENT → DQ_30 → DQ_60 → DQ_90 → DQ_120+ → FORECLOSURE → REO → LIQUIDATED
    ↓         ↓        ↓        ↓
 PREPAID   CURRENT  CURRENT  CURRENT  (cure events)
```

**Deliverables**:
- [ ] State machine with all transitions
- [ ] Configurable transition probabilities
- [ ] Cure logic with counter tracking
- [ ] Timeline tracking for audit

---

## Phase 2: Waterfall Feature Completion (Weeks 4-10)

**Objective**: Complete the waterfall engine to handle all industry-standard deal features.

### 2.1 Net WAC Cap Integration

Integrate the Net WAC cap calculation into the main waterfall.

```python
# In engine/waterfall.py - enhance _apply_net_wac_cap()

def _apply_net_wac_cap(self, state: DealState) -> None:
    """
    Apply Net WAC cap with proper iteration.
    
    Net WAC Formula:
        Effective_Rate = min(Coupon, 
            (Interest_Collections - Senior_Fees) / Bond_Balance × 12)
    
    This caps the bond coupon at the available interest after fees.
    """
    # 1. Calculate total interest available
    gross_interest = state.cash_balances.get("IAF", 0.0)
    
    # 2. Calculate senior fees (servicing, trustee, etc.)
    senior_fees = self._calculate_senior_fees(state)
    
    # 3. Net interest available for bonds
    net_interest = gross_interest - senior_fees
    
    # 4. For each Net WAC capped bond, calculate effective rate
    for bond_id, bond in state.bonds.items():
        if self._has_net_wac_cap(bond_id, state):
            max_rate = (net_interest / bond.current_balance) * 12 \
                       if bond.current_balance > 0 else 0
            bond.effective_rate = min(bond.coupon_rate, max_rate)
```

**Deliverables**:
- [ ] Net WAC cap calculation in waterfall
- [ ] Fee circularity resolution
- [ ] Test cases comparing to Intex outputs
- [ ] Configuration via deal spec JSON

### 2.2 Trigger Cure Logic

Implement proper trigger cure logic with counters.

```python
# In engine/waterfall.py - enhance TriggerState

@dataclass
class TriggerState:
    """Track trigger status with cure logic."""
    trigger_id: str
    is_breached: bool = False
    months_breached: int = 0
    months_cured: int = 0
    cure_threshold: int = 3  # Must pass for N months to cure
    
    def update(self, test_passed: bool) -> None:
        if test_passed:
            self.months_cured += 1
            if self.is_breached and self.months_cured >= self.cure_threshold:
                self.is_breached = False
                self.months_breached = 0
        else:
            self.is_breached = True
            self.months_breached += 1
            self.months_cured = 0
```

**Deliverables**:
- [ ] TriggerState with cure counters
- [ ] Configurable cure periods per trigger
- [ ] Audit trail of trigger history
- [ ] Test cases for flickering prevention

### 2.3 ARM & Hybrid Loan Support

Add support for adjustable-rate and interest-only loans.

```
engine/arm_calculator.py (NEW)
├── ARMParameters
│   ├── index: str (SOFR_1M, CMT_1Y, LIBOR_1M)
│   ├── margin: float
│   ├── initial_rate: float
│   ├── first_reset_month: int
│   ├── reset_frequency: int
│   ├── periodic_cap: float
│   ├── periodic_floor: float
│   ├── lifetime_cap: float
│   ├── lifetime_floor: float
├── ARMCalculator
│   ├── get_current_rate(loan, index_path, month)
│   ├── calculate_payment(loan, rate)
│   └── project_rate_path(loan, scenario)
```

**Deliverables**:
- [ ] ARM rate calculation with caps/floors
- [ ] IO period handling
- [ ] Payment shock calculations
- [ ] Integration with loan state machine

### 2.4 Advancing & Reimbursement

Model servicer advancing and recovery.

```
engine/advancing.py (NEW)
├── AdvanceTracker
│   ├── record_advance(loan_id, advance_type, amount)
│   ├── record_reimbursement(loan_id, amount)
│   ├── get_outstanding_advances(loan_id)
│   └── allocate_reimbursement(available_funds)
```

**Deliverables**:
- [ ] P&I advance tracking
- [ ] T&I advance tracking
- [ ] Reimbursement waterfall
- [ ] Stop-advance logic

---

## Phase 3: Pricing & Risk Analytics (Weeks 8-16)

**Objective**: Add pricing capabilities and comprehensive risk metrics.

### 3.1 Discounting & Present Value

Implement proper cashflow discounting.

```
engine/pricing.py (NEW)
├── DiscountCurve
│   ├── from_treasury_rates(rates)
│   ├── from_swap_rates(rates)
│   ├── get_discount_factor(tenor)
│   └── shift(parallel_shift_bps)
├── CashflowPricer
│   ├── price_tranche(cashflows, curve, spread)
│   ├── calculate_yield(price, cashflows)
│   ├── calculate_dm(price, cashflows, index_curve)
│   └── calculate_oas(price, cashflows, vol_model)
```

**Deliverables**:
- [ ] Discount curve construction
- [ ] Tranche pricing
- [ ] Yield calculation (IRR)
- [ ] Discount margin for floaters

### 3.2 Duration & Convexity

Implement key interest rate risk metrics.

```python
# In engine/pricing.py

def calculate_duration_convexity(
    cashflows: pd.DataFrame,
    curve: DiscountCurve,
    spread: float = 0.0,
    shock_bps: int = 10,
) -> Dict[str, float]:
    """
    Calculate modified duration and convexity.
    
    Duration = -(P+ - P-) / (2 × P × Δy)
    Convexity = (P+ + P- - 2P) / (P × Δy²)
    """
    base_price = price_cashflows(cashflows, curve, spread)
    up_price = price_cashflows(cashflows, curve.shift(shock_bps), spread)
    down_price = price_cashflows(cashflows, curve.shift(-shock_bps), spread)
    
    dy = shock_bps / 10000
    
    mod_duration = -(up_price - down_price) / (2 * base_price * dy)
    convexity = (up_price + down_price - 2 * base_price) / (base_price * dy ** 2)
    
    return {
        "modified_duration": mod_duration,
        "convexity": convexity,
        "dv01": mod_duration * base_price / 10000,
    }
```

**Deliverables**:
- [ ] Modified duration calculation
- [ ] Convexity calculation
- [ ] DV01 (dollar duration)
- [ ] Effective duration (for MBS with prepayment)

### 3.3 OAS Framework (Optional Advanced)

Implement Option-Adjusted Spread for callable/prepayable securities.

```
engine/oas.py (NEW)
├── OASEngine
│   ├── calibrate_vol_model(market_vols)
│   ├── generate_rate_paths(n_paths, n_months)
│   ├── calculate_oas(price, cashflow_model, rate_paths)
│   └── calculate_oad(oas, rate_paths)  # OA Duration
```

**Deliverables**:
- [ ] Rate lattice generation
- [ ] OAS calculation
- [ ] OA Duration
- [ ] Benchmark to Bloomberg/Intex

### 3.4 Loss Distribution Analysis

Generate tranche loss distributions for VaR/ES.

```python
# In engine/stress_testing.py - enhance Monte Carlo

def calculate_loss_distribution(
    loan_data: pd.DataFrame,
    deal_structure: Dict,
    n_simulations: int = 10000,
) -> Dict[str, Any]:
    """
    Generate loss distribution for each tranche.
    
    Returns VaR, ES, EL, UL metrics.
    """
    tranche_losses = {t: [] for t in deal_structure["bonds"]}
    
    for sim in range(n_simulations):
        scenario = generate_random_scenario()
        results = run_projection(loan_data, deal_structure, scenario)
        
        # Allocate losses to tranches
        for tranche_id, loss in allocate_losses(results, deal_structure):
            tranche_losses[tranche_id].append(loss)
    
    # Calculate risk metrics
    return {
        tranche_id: {
            "expected_loss": np.mean(losses),
            "unexpected_loss": np.std(losses),
            "var_95": np.percentile(losses, 95),
            "var_99": np.percentile(losses, 99),
            "expected_shortfall_95": np.mean([l for l in losses if l >= np.percentile(losses, 95)]),
        }
        for tranche_id, losses in tranche_losses.items()
    }
```

**Deliverables**:
- [ ] Monte Carlo loss simulation
- [ ] Tranche-level VaR/ES
- [ ] Correlation stress
- [ ] Loss surface visualization

---

## Phase 4: Validation & Calibration (Weeks 12-20)

**Objective**: Build confidence in model accuracy through validation and calibration.

### 4.1 Backtesting Framework

Compare projected vs actual performance.

```
engine/validation.py (NEW)
├── BacktestEngine
│   ├── run_backtest(deal_id, historical_periods)
│   ├── compare_projected_vs_actual(projected, actual)
│   ├── calculate_error_metrics()
│   └── generate_backtest_report()
├── ErrorMetrics
│   ├── mape (Mean Absolute Percentage Error)
│   ├── rmse (Root Mean Square Error)
│   ├── bias (Systematic over/under prediction)
│   └── hit_rate (Direction accuracy)
```

**Deliverables**:
- [ ] Backtest engine
- [ ] Error decomposition (collateral vs waterfall vs assumptions)
- [ ] Report generation
- [ ] Confidence intervals

### 4.2 Model Calibration

Fit model parameters to historical data.

```
ml/calibration.py (NEW)
├── HazardCalibrator
│   ├── fit_cpr_model(historical_data)
│   ├── fit_cdr_model(historical_data)
│   ├── fit_severity_model(liquidation_data)
│   └── cross_validate(data, n_folds)
├── CalibrationReport
│   ├── parameter_values
│   ├── confidence_intervals
│   ├── goodness_of_fit
│   └── out_of_sample_performance
```

**Deliverables**:
- [ ] CPR model calibration
- [ ] CDR model calibration
- [ ] Severity model calibration
- [ ] Cohort-based calibration

### 4.3 Golden File Testing

Create benchmark tests against known Intex/Moody's outputs.

```
tests/golden_files/ (NEW)
├── DEAL_001/
│   ├── input_spec.json
│   ├── input_tape.csv
│   ├── expected_cashflows.csv
│   ├── expected_balances.csv
│   └── tolerance.json
├── test_golden_files.py
```

**Deliverables**:
- [ ] 5+ golden file test cases
- [ ] Automated comparison with tolerances
- [ ] CI/CD integration
- [ ] Deviation reports

---

## Phase 5: Performance & Scalability (Weeks 16-22)

**Objective**: Optimize for production workloads.

### 5.1 Vectorization

Convert loan-level loops to vectorized operations where possible.

```python
# Before (slow)
for loan in loans:
    loan.interest = loan.balance * loan.rate / 12

# After (fast)
loans_df["interest"] = loans_df["balance"] * loans_df["rate"] / 12
```

**Deliverables**:
- [ ] Vectorized collateral projections
- [ ] Benchmark: 100k loans in < 5 seconds
- [ ] Memory-efficient chunking for large pools

### 5.2 Caching & Memoization

Cache expensive calculations.

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def calculate_amortization_factor(rate: float, term: int) -> float:
    """Cached amortization factor calculation."""
    if rate == 0:
        return 1 / term
    return rate / (1 - (1 + rate) ** (-term))
```

**Deliverables**:
- [ ] Cached amortization calculations
- [ ] Cached discount factors
- [ ] Session-level result caching

### 5.3 Parallel Execution

Add parallel processing for Monte Carlo.

```python
from concurrent.futures import ProcessPoolExecutor

def run_monte_carlo_parallel(
    loan_data: pd.DataFrame,
    deal_structure: Dict,
    n_simulations: int = 10000,
    n_workers: int = 4,
) -> List[Dict]:
    """Run Monte Carlo simulations in parallel."""
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [
            executor.submit(run_single_simulation, loan_data, deal_structure, seed)
            for seed in range(n_simulations)
        ]
        return [f.result() for f in futures]
```

**Deliverables**:
- [ ] Parallel Monte Carlo
- [ ] Configurable worker count
- [ ] Progress tracking

---

## Phase 6: API & UI Enhancements (Weeks 20-26)

**Objective**: Productize the platform for end users.

### 6.1 Enhanced API Endpoints

Add pricing and risk endpoints.

```
POST /price/{deal_id}
  → Returns: price, yield, duration, convexity, OAS

POST /risk/{deal_id}
  → Returns: VaR, ES, loss distribution, scenario impacts

POST /sensitivity/{deal_id}
  → Returns: DV01, CS01, CPR sensitivity, CDR sensitivity

GET /validation/{deal_id}
  → Returns: backtest results, error metrics
```

**Deliverables**:
- [ ] Pricing endpoint
- [ ] Risk metrics endpoint
- [ ] Sensitivity endpoint
- [ ] Validation endpoint

### 6.2 Investor Dashboard Enhancements

Add pricing and risk views.

```
ui/pages/investor.py (ENHANCE)
├── Tab: Pricing
│   ├── Price/yield calculator
│   ├── Duration/convexity display
│   ├── Spread analysis
├── Tab: Risk
│   ├── VaR/ES display
│   ├── Loss distribution chart
│   ├── Scenario comparison table
├── Tab: Validation
│   ├── Backtest results
│   ├── Projected vs actual chart
│   ├── Error metrics
```

**Deliverables**:
- [ ] Pricing calculator UI
- [ ] Risk metrics dashboard
- [ ] Interactive scenario comparison
- [ ] Validation reports

### 6.3 Arranger Workflow Enhancements

Improve deal structuring tools.

```
ui/pages/arranger.py (ENHANCE)
├── Deal Builder
│   ├── Tranche sizing tool
│   ├── CE level calculator
│   ├── Rating agency CE requirements
├── Stress Testing
│   ├── Break-even analysis
│   ├── What-if scenarios
│   ├── Sensitivity tables
```

**Deliverables**:
- [ ] Tranche sizing calculator
- [ ] CE requirements lookup
- [ ] Integrated stress testing

---

## Implementation Priority Matrix

| Phase | Priority | Effort | Dependencies |
|-------|----------|--------|--------------|
| 1.1 Loan Schema | 🔴 Critical | 2 weeks | None |
| 1.2 Servicer Normalization | 🔴 Critical | 2 weeks | 1.1 |
| 1.3 Loan State Machine | 🔴 Critical | 2 weeks | 1.1 |
| 2.1 Net WAC Cap | 🔴 Critical | 1 week | None |
| 2.2 Trigger Cure Logic | 🟡 High | 1 week | None |
| 2.3 ARM Support | 🟡 High | 2 weeks | 1.3 |
| 2.4 Advancing | 🟠 Medium | 1 week | 1.3 |
| 3.1 Discounting | 🟡 High | 1 week | None |
| 3.2 Duration/Convexity | 🟡 High | 1 week | 3.1 |
| 3.3 OAS | 🟠 Medium | 2 weeks | 3.1, 3.2 |
| 3.4 Loss Distribution | 🟡 High | 2 weeks | None |
| 4.1 Backtesting | 🟡 High | 2 weeks | 1.x complete |
| 4.2 Calibration | 🟠 Medium | 2 weeks | 4.1 |
| 4.3 Golden Files | 🟡 High | 2 weeks | 1.x, 2.x complete |
| 5.1 Vectorization | 🟠 Medium | 2 weeks | 1.3 |
| 5.2 Caching | 🟠 Medium | 1 week | None |
| 5.3 Parallel Execution | 🟠 Medium | 1 week | None |
| 6.1 API Enhancements | 🟠 Medium | 2 weeks | 3.x complete |
| 6.2 Investor UI | 🟠 Medium | 2 weeks | 6.1 |
| 6.3 Arranger UI | 🟠 Medium | 2 weeks | 6.1 |

---

## Quick Wins (Can Start Immediately)

1. **Net WAC Cap Integration** (1 week)
   - Already have iterative solver
   - Just need to wire up the calculation

2. **Trigger Cure Logic** (1 week)
   - Extend existing TriggerState
   - Add counter tracking

3. **Golden File Tests** (1 week)
   - Create test fixtures
   - Automate comparison

4. **Caching** (1 week)
   - Add lru_cache to hot paths
   - Immediate performance gain

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Loan types supported | Fixed only | Fixed, ARM, IO, Hybrid |
| Max pool size | ~10k loans | 100k+ loans |
| Simulation speed | ~30 sec/deal | < 5 sec/deal |
| Backtest MAPE | Unknown | < 5% for CPR/CDR |
| Golden file pass rate | 0% | 95%+ |
| API response time (pricing) | N/A | < 2 sec |

---

## Recommended Staffing

| Role | FTE | Focus |
|------|-----|-------|
| Senior Quant Developer | 1.0 | Waterfall, pricing, risk |
| Data Engineer | 0.5 | Ingestion, normalization |
| ML Engineer | 0.5 | Calibration, validation |
| Frontend Developer | 0.5 | UI enhancements |
| QA Engineer | 0.5 | Testing, golden files |

**Total: ~3 FTE for 6 months**

---

## Appendix: File Structure After Completion

```
rmbs_platform/
├── engine/
│   ├── __init__.py
│   ├── advancing.py          (NEW)
│   ├── arm_calculator.py     (NEW)
│   ├── collateral.py         (enhanced)
│   ├── comparison.py
│   ├── compute.py
│   ├── credit_enhancement.py
│   ├── currency.py
│   ├── loader.py             (enhanced)
│   ├── loan_schema.py        (NEW)
│   ├── loan_state_machine.py (NEW)
│   ├── oas.py                (NEW)
│   ├── pricing.py            (NEW)
│   ├── reporting.py
│   ├── servicer.py
│   ├── servicer_normalization.py (NEW)
│   ├── state.py              (enhanced)
│   ├── stress_testing.py     (enhanced)
│   ├── structures.py
│   ├── swaps.py
│   ├── validation.py         (NEW)
│   └── waterfall.py          (enhanced)
├── ml/
│   ├── calibration.py        (NEW)
│   ├── config.py
│   ├── etl_freddie.py
│   ├── features.py
│   ├── models.py
│   ├── portfolio.py
│   ├── severity.py
│   └── train_*.py
├── tests/
│   ├── golden_files/         (NEW)
│   ├── test_*.py
│   └── conftest.py
├── ui/
│   └── pages/
│       ├── arranger.py       (enhanced)
│       ├── investor.py       (enhanced)
│       └── ...
└── api_main.py               (enhanced)
```

---

*Document Version: 1.0*
*Created: January 2026*
*Author: RMBS Platform Team*
