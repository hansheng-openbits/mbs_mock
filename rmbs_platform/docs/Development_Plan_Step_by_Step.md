# RMBS Platform: Step-by-Step Development Plan

## Executive Summary

This document provides a **practical, sequenced development plan** to transform the RMBS platform from its current state to an industry-grade pricing and risk analytics engine. The plan is based on a detailed evaluation of the existing codebase against the requirements in `Industry_Grade_Build_Plan.md`.

**Timeline**: 24-26 weeks (6 months)  
**Recommended Team**: 2-3 developers  
**Approach**: Iterative delivery with working software every 2 weeks

---

## Current State Evaluation

### ✅ Strengths (What's Working Well)

| Component | Assessment | Evidence |
|-----------|------------|----------|
| **Core Architecture** | Strong | Well-structured modular design |
| **Deal Loader** | Production-ready | Full validation, error handling in `loader.py` |
| **Collateral Models** | Just upgraded | Rep-line + **NEW** loan-level seriatim |
| **Waterfall Engine** | Just upgraded | Sequential + **NEW** iterative solver |
| **ML Integration** | Production-ready | CPR/CDR models, severity, feature engineering |
| **Stress Testing** | Feature-complete | CCAR scenarios, Monte Carlo, reverse stress |
| **Credit Enhancement** | Feature-complete | OC/IC tracking, trigger evaluation |
| **API Layer** | Functional | FastAPI with RBAC, versioning |
| **UI Layer** | Functional | Streamlit with role-based pages |

### ❌ Critical Gaps (Blocking Industry Grade)

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| **Loan state machine** | Can't model realistic DQ timelines | 3 weeks | 🔴 P0 |
| **Servicer normalization** | Can't ingest real data | 2 weeks | 🔴 P0 |
| **Net WAC cap integration** | Wrong interest for capped deals | 1 week | 🔴 P0 |
| **Validation framework** | No confidence in accuracy | 3 weeks | 🟡 P1 |
| **Pricing metrics** | Can't price bonds | 2 weeks | 🟡 P1 |
| **ARM/IO support** | Limited to fixed-rate | 2 weeks | 🟠 P2 |
| **Performance tuning** | Slow for large pools | 2 weeks | 🟠 P2 |

---

## Development Plan Overview

### Phase Structure

```
Sprint 1-2   (Weeks 1-4):   Quick Wins + Foundation
Sprint 3-4   (Weeks 5-8):   Data Ingestion Infrastructure  
Sprint 5-6   (Weeks 9-12):  Loan State Machine
Sprint 7-8   (Weeks 13-16): Pricing & Risk Analytics
Sprint 9-10  (Weeks 17-20): Validation & Calibration
Sprint 11-12 (Weeks 21-24): Performance & Polish
Sprint 13    (Weeks 25-26): Final Integration & Release
```

---

## Sprint 1-2: Quick Wins + Foundation (Weeks 1-4)

**Goal**: Deliver immediate value and set up infrastructure for larger work.

### Week 1: Quick Wins

#### Day 1-2: Net WAC Cap Integration
**Status**: 🔴 Critical Path  
**Effort**: 2 days  
**Files**: `engine/waterfall.py`

**Tasks**:
1. Enhance `_apply_net_wac_cap()` method (already exists, needs wiring)
2. Calculate senior fees in waterfall
3. Compute effective rate: `min(coupon, net_interest / balance × 12)`
4. Add deal spec flag: `"net_wac_cap": {"enabled": true}`

**Acceptance Criteria**:
- [ ] Net WAC cap correctly limits bond coupon
- [ ] Iterative solver converges with cap applied
- [ ] Test case: cap reduces Class B coupon from 6% to 5.2%

**Code Snippet**:
```python
def _apply_net_wac_cap(self, state: DealState) -> None:
    """Apply Net WAC cap to variable-rate bonds."""
    # Get net interest available
    gross_interest = state.cash_balances.get("IAF", 0.0)
    senior_fees = sum([
        state.get_variable("ServicingFee") or 0,
        state.get_variable("TrusteeFee") or 0,
    ])
    net_interest = gross_interest - senior_fees
    
    # Cap each bond's effective rate
    for bond_id, bond in state.bonds.items():
        bond_def = state.def_.bonds.get(bond_id)
        if bond_def and bond_def.coupon_type == "VARIABLE":
            cap = bond_def.variable_cap_ref
            if cap == "NetWAC":
                max_rate = (net_interest / bond.current_balance) * 12 \
                           if bond.current_balance > 0 else 0
                # Store for waterfall steps
                state.set_variable(f"{bond_id}_EffectiveRate", 
                                   min(bond_def.fixed_rate or 0.06, max_rate))
```

**Verification**: Run `FREDDIE_SAMPLE_2017_2020` with Net WAC cap enabled, compare Class B interest to uncapped version.

---

#### Day 3-4: Trigger Cure Logic
**Status**: 🟡 High Priority  
**Effort**: 2 days  
**Files**: `engine/waterfall.py`, `engine/state.py`

**Tasks**:
1. Add `TriggerState` dataclass to `state.py`
2. Track `months_breached`, `months_cured`, `cure_threshold`
3. Update `_run_tests()` to use cure logic
4. Store trigger history in snapshots

**Acceptance Criteria**:
- [ ] Trigger doesn't "flicker" on/off each period
- [ ] Trigger requires 3 consecutive passing periods to cure
- [ ] Trigger history exported in audit trail

**Code Snippet**:
```python
# In engine/state.py
@dataclass
class TriggerState:
    """Track trigger with cure logic."""
    trigger_id: str
    is_breached: bool = False
    months_breached: int = 0
    months_cured: int = 0
    cure_threshold: int = 3
    
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

# In DealState.__init__
self.trigger_states: Dict[str, TriggerState] = {}
```

---

#### Day 5: Caching Infrastructure
**Status**: 🟠 Medium Priority  
**Effort**: 1 day  
**Files**: `engine/collateral.py`, `engine/pricing.py` (new)

**Tasks**:
1. Add `@lru_cache` to amortization factor calculation
2. Add `@lru_cache` to discount factor calculation
3. Benchmark performance improvement

**Code Snippet**:
```python
from functools import lru_cache

@lru_cache(maxsize=10000)
def _amortization_factor(rate: float, term: int) -> float:
    """Cached level-pay amortization factor."""
    if rate <= 0:
        return 1.0 / max(term, 1)
    return rate / (1 - (1 + rate) ** (-term))
```

---

### Week 2: Testing & Documentation Infrastructure

#### Day 1-3: Golden File Test Framework
**Status**: 🟡 High Priority  
**Effort**: 3 days  
**Files**: `tests/golden_files/` (new), `tests/test_golden_files.py` (new)

**Tasks**:
1. Create golden file structure:
   ```
   tests/golden_files/
   ├── DEAL_001/
   │   ├── input_spec.json
   │   ├── input_tape.csv
   │   ├── expected_cashflows.csv
   │   ├── expected_balances.csv
   │   └── tolerance.json
   ```
2. Implement comparator with tolerance thresholds
3. Create 2 golden test cases
4. Add to CI pipeline

**Acceptance Criteria**:
- [ ] Golden test runs in CI
- [ ] Tolerance file allows ±1% for cashflows, ±$100 for balances
- [ ] Deviation report shows which periods failed

---

#### Day 4-5: Audit Trail Enhancement
**Status**: 🟠 Medium Priority  
**Effort**: 2 days  
**Files**: `engine/reporting.py`

**Tasks**:
1. Add waterfall step-level trace
2. Export detailed payment allocation
3. Add deterministic run IDs

**Deliverable**: JSON audit bundle with:
- Run metadata (timestamp, inputs, seed)
- Period-by-period waterfall trace
- Bond payment details
- Trigger status history

---

### Week 3-4: Foundation for Phase 2

#### Canonical Loan Schema Design
**Status**: 🔴 Critical Path  
**Effort**: 1 week  
**Files**: `engine/loan_schema.py` (new)

**Tasks**:
1. Design `LoanRecord` dataclass (50+ fields)
2. Add validation rules
3. Add unit tests
4. Document field mappings

**Deliverable**: Complete loan schema with examples:

```python
# engine/loan_schema.py
@dataclass
class LoanRecord:
    """Canonical loan record for RMBS platform."""
    # Identification
    loan_id: str
    pool_id: Optional[str] = None
    original_loan_id: Optional[str] = None
    
    # Balances
    original_upb: float = 0.0
    current_upb: float = 0.0
    scheduled_upb: float = 0.0
    
    # Rates (ARM support)
    note_rate: float = 0.0
    margin: Optional[float] = None
    index_name: Optional[str] = None
    periodic_cap: Optional[float] = None
    periodic_floor: Optional[float] = None
    lifetime_cap: Optional[float] = None
    lifetime_floor: Optional[float] = None
    
    # Terms
    original_term: int = 360
    remaining_term: int = 360
    amortization_type: str = "LEVEL_PAY"  # LEVEL_PAY, IO, BALLOON
    io_period_months: int = 0
    
    # Credit
    fico: float = 700.0
    dti: float = 0.36
    ltv: float = 0.80
    cltv: float = 0.80
    
    # Property
    state: str = "CA"
    zip_code: Optional[str] = None
    property_type: str = "SFR"  # SFR, CONDO, CO_OP, 2_4_UNIT
    occupancy: str = "OWNER"  # OWNER, INVESTOR, SECOND_HOME
    
    # Status
    current_status: str = "CURRENT"
    days_delinquent: int = 0
    foreclosure_date: Optional[date] = None
    reo_date: Optional[date] = None
    liquidation_date: Optional[date] = None
    
    # Modification
    modification_flag: bool = False
    modification_date: Optional[date] = None
    pre_mod_rate: Optional[float] = None
    
    # Derived (calculated)
    seasoning_months: int = 0
    rate_incentive: float = 0.0
    burnout_proxy: float = 0.0
    
    def validate(self) -> List[str]:
        """Validate field values and return errors."""
        errors = []
        
        if self.current_upb < 0:
            errors.append("current_upb cannot be negative")
        if not (0 < self.note_rate < 0.20):
            errors.append("note_rate must be between 0% and 20%")
        if not (300 <= self.fico <= 850):
            errors.append("fico must be between 300 and 850")
        if not (0 <= self.ltv <= 1.5):
            errors.append("ltv must be between 0 and 150%")
        
        return errors
```

---

## Sprint 3-4: Data Ingestion Infrastructure (Weeks 5-8)

**Goal**: Build production-grade data ingestion for real servicer tapes.

### Week 5: Servicer Normalization Layer

#### Servicer Tape Parser
**Status**: 🔴 Critical Path  
**Effort**: 1 week  
**Files**: `engine/servicer_normalization.py` (new)

**Tasks**:
1. Build format detector (csv vs pipe-delimited)
2. Implement Freddie parser (reuse `ml/etl_freddie.py` mappings)
3. Implement Fannie parser
4. Build generic parser with mapping config

**Code Structure**:
```python
# engine/servicer_normalization.py

class ServicerFormat(Enum):
    FREDDIE_MAC = "freddie"
    FANNIE_MAE = "fannie"
    GENERIC = "generic"

class ServicerTapeParser:
    """Parse servicer tapes to canonical LoanRecord format."""
    
    def detect_format(self, filepath: Path) -> ServicerFormat:
        """Auto-detect tape format."""
        with open(filepath, 'r') as f:
            first_line = f.readline()
            if '|' in first_line:
                # Check for Freddie column names
                if 'LOAN_SEQUENCE_NUMBER' in first_line:
                    return ServicerFormat.FREDDIE_MAC
            # Check for Fannie patterns
            # ...
        return ServicerFormat.GENERIC
    
    def parse(self, filepath: Path, 
              format_type: Optional[ServicerFormat] = None,
              mapping: Optional[Dict] = None) -> List[LoanRecord]:
        """Parse tape and return LoanRecord list."""
        if format_type is None:
            format_type = self.detect_format(filepath)
        
        if format_type == ServicerFormat.FREDDIE_MAC:
            return self._parse_freddie(filepath)
        elif format_type == ServicerFormat.FANNIE_MAE:
            return self._parse_fannie(filepath)
        else:
            return self._parse_generic(filepath, mapping)
    
    def _parse_freddie(self, filepath: Path) -> List[LoanRecord]:
        """Parse Freddie Mac format."""
        df = pd.read_csv(filepath, sep='|')
        records = []
        
        for _, row in df.iterrows():
            record = LoanRecord(
                loan_id=row['LOAN_SEQUENCE_NUMBER'],
                original_upb=row.get('ORIGINAL_UPB', 0),
                current_upb=row.get('CURRENT_ACTUAL_UPB', 0),
                note_rate=row.get('ORIGINAL_INTEREST_RATE', 0) / 100,
                # ... map all fields
            )
            records.append(record)
        
        return records
    
    def validate_tape(self, records: List[LoanRecord]) -> ValidationReport:
        """Validate all records and return report."""
        report = ValidationReport()
        
        for i, record in enumerate(records):
            errors = record.validate()
            if errors:
                report.add_errors(i, record.loan_id, errors)
        
        return report
```

**Acceptance Criteria**:
- [ ] Correctly parse Freddie Mac performance tape
- [ ] Correctly parse Fannie Mae loan tape
- [ ] Validation report shows all errors
- [ ] Handle malformed files gracefully

---

### Week 6: Reconciliation & Validation

#### Tape Reconciliation Logic
**Status**: 🟡 High Priority  
**Effort**: 1 week  
**Files**: `engine/servicer_normalization.py`

**Tasks**:
1. Add balance reconciliation checks
2. Add cashflow consistency checks
3. Generate detailed validation report

**Reconciliation Rules**:
```python
def reconcile_period(prev_record: LoanRecord, 
                     curr_record: LoanRecord) -> List[str]:
    """Reconcile consecutive period records."""
    errors = []
    
    # Rule 1: Balance reconciliation
    # Begin - Scheduled - Prepay - Default = End
    expected_end = (prev_record.current_upb 
                    - curr_record.scheduled_principal
                    - curr_record.prepayment
                    - curr_record.default_amount)
    
    if abs(expected_end - curr_record.current_upb) > 1.0:
        errors.append(f"Balance mismatch: expected {expected_end:.2f}, "
                     f"got {curr_record.current_upb:.2f}")
    
    # Rule 2: Interest due calculation
    expected_interest = prev_record.current_upb * prev_record.note_rate / 12
    if abs(expected_interest - curr_record.interest_due) > 0.01:
        errors.append(f"Interest calculation off: expected {expected_interest:.2f}")
    
    # Rule 3: Status consistency
    if prev_record.current_status == "FORECLOSURE" and \
       curr_record.current_status == "CURRENT":
        errors.append("Invalid status transition: FORECLOSURE → CURRENT")
    
    return errors
```

**Acceptance Criteria**:
- [ ] Detects balance mismatches
- [ ] Detects invalid status transitions
- [ ] Generates CSV reconciliation report

---

### Week 7-8: Integration Testing

#### End-to-End Ingestion Test
**Status**: 🟡 High Priority  
**Effort**: 2 weeks  
**Files**: `tests/test_servicer_integration.py`

**Tasks**:
1. Create test fixtures (sample Freddie/Fannie tapes)
2. Test full ingestion pipeline
3. Test error handling (bad files, missing columns)
4. Document data quality requirements

**Test Cases**:
- Valid Freddie tape with 1000 loans
- Freddie tape with missing columns
- Freddie tape with invalid values (negative balances)
- Fannie tape with different delimiter
- Generic tape with custom mapping

---

## Sprint 5-6: Loan State Machine (Weeks 9-12)

**Goal**: Model realistic loan lifecycle with DQ/FC/REO timelines.

### Week 9-10: State Machine Core

#### Loan Status Engine
**Status**: 🔴 Critical Path  
**Effort**: 2 weeks  
**Files**: `engine/loan_state_machine.py` (new)

**Tasks**:
1. Implement `LoanStatus` enum with all states
2. Build transition matrix
3. Add cure probability logic
4. Test state transitions

**Code Structure**:
```python
# engine/loan_state_machine.py

class LoanStatus(Enum):
    """Comprehensive loan status."""
    CURRENT = "CURRENT"
    DQ_30 = "DQ_30"
    DQ_60 = "DQ_60"
    DQ_90 = "DQ_90"
    DQ_120_PLUS = "DQ_120_PLUS"
    FORECLOSURE = "FORECLOSURE"
    REO = "REO"
    LIQUIDATED = "LIQUIDATED"
    PREPAID_FULL = "PREPAID_FULL"
    PREPAID_PARTIAL = "PREPAID_PARTIAL"
    MODIFIED = "MODIFIED"
    BANKRUPTCY = "BANKRUPTCY"

class TransitionMatrix:
    """State transition probabilities."""
    
    def __init__(self):
        # Base transition probabilities
        self.transitions = {
            (LoanStatus.CURRENT, LoanStatus.DQ_30): 0.03,
            (LoanStatus.CURRENT, LoanStatus.PREPAID_FULL): 0.01,
            (LoanStatus.DQ_30, LoanStatus.CURRENT): 0.80,  # Cure
            (LoanStatus.DQ_30, LoanStatus.DQ_60): 0.18,
            (LoanStatus.DQ_60, LoanStatus.CURRENT): 0.60,  # Cure
            (LoanStatus.DQ_60, LoanStatus.DQ_90): 0.35,
            (LoanStatus.DQ_90, LoanStatus.CURRENT): 0.30,  # Cure
            (LoanStatus.DQ_90, LoanStatus.DQ_120_PLUS): 0.60,
            (LoanStatus.DQ_120_PLUS, LoanStatus.FORECLOSURE): 0.70,
            (LoanStatus.FORECLOSURE, LoanStatus.REO): 0.50,  # 6 months avg
            (LoanStatus.REO, LoanStatus.LIQUIDATED): 0.40,  # 12 months avg
        }
    
    def get_probability(self, from_status: LoanStatus, 
                       to_status: LoanStatus,
                       loan_features: Dict) -> float:
        """Get transition probability adjusted for loan features."""
        base_prob = self.transitions.get((from_status, to_status), 0.0)
        
        # Adjust for FICO
        if loan_features.get('fico', 700) < 620:
            # Lower FICO = lower cure rate
            if to_status == LoanStatus.CURRENT:
                base_prob *= 0.7
        
        # Adjust for LTV
        if loan_features.get('ltv', 0.8) > 0.95:
            # High LTV = harder to cure via refi
            if to_status == LoanStatus.CURRENT:
                base_prob *= 0.8
        
        return base_prob

class LoanStateMachine:
    """Manage loan lifecycle."""
    
    def __init__(self, transition_matrix: Optional[TransitionMatrix] = None):
        self.transitions = transition_matrix or TransitionMatrix()
        self.loan_histories: Dict[str, List[StatusChange]] = {}
    
    def apply_month(self, loan: LoanRecord, 
                   scenario: Optional[Dict] = None) -> LoanRecord:
        """Update loan for one month."""
        new_loan = copy(loan)
        
        # Determine next status based on probabilities
        current_status = LoanStatus(loan.current_status)
        possible_transitions = self._get_possible_transitions(current_status)
        
        # Sample next status
        next_status = self._sample_transition(
            current_status, 
            possible_transitions,
            loan.__dict__
        )
        
        new_loan.current_status = next_status.value
        new_loan.seasoning_months += 1
        
        # Calculate cashflows based on status
        cashflows = self.calculate_cashflows(new_loan)
        new_loan.interest_paid = cashflows['interest']
        new_loan.principal_paid = cashflows['principal']
        new_loan.current_upb -= cashflows['principal']
        
        # Track timeline
        self._record_status_change(loan.loan_id, current_status, next_status)
        
        return new_loan
    
    def calculate_cashflows(self, loan: LoanRecord) -> Dict[str, float]:
        """Calculate cashflows based on loan status."""
        if loan.current_status == "CURRENT":
            # Full P&I payment
            monthly_rate = loan.note_rate / 12
            payment = loan.current_upb * \
                     _amortization_factor(monthly_rate, loan.remaining_term)
            interest = loan.current_upb * monthly_rate
            principal = payment - interest
            
            return {
                'interest': interest,
                'principal': principal,
                'prepayment': 0,
                'default': 0,
            }
        
        elif loan.current_status.startswith("DQ_"):
            # Delinquent - no payments, servicer advances
            return {
                'interest': 0,
                'principal': 0,
                'advance_interest': loan.current_upb * loan.note_rate / 12,
                'advance_principal': 0,
            }
        
        elif loan.current_status == "LIQUIDATED":
            # Loss realization
            severity = 0.40  # Could be model-driven
            loss = loan.current_upb * severity
            recovery = loan.current_upb - loss
            
            return {
                'interest': 0,
                'principal': 0,
                'loss': loss,
                'recovery': recovery,
            }
        
        # ... other statuses
        return {}
```

**Acceptance Criteria**:
- [ ] Loan transitions through DQ buckets correctly
- [ ] Cure probabilities applied correctly
- [ ] Timeline audit trail generated
- [ ] Cashflows calculated per status

---

### Week 11-12: Integration with Collateral Engine

#### Loan-Level Projection with State Machine
**Status**: 🔴 Critical Path  
**Effort**: 2 weeks  
**Files**: `engine/collateral.py` (enhance)

**Tasks**:
1. Integrate state machine into `LoanLevelCollateralModel`
2. Replace simple SMM/MDR with state-driven cashflows
3. Test against current implementation

**Enhancement**:
```python
# In engine/collateral.py - LoanLevelCollateralModel

def generate_cashflows(
    self,
    periods: int,
    base_cpr: float,
    base_cdr: float,
    base_severity: float,
    use_state_machine: bool = True,  # NEW
    market_rate_path: Optional[List[float]] = None,
) -> pd.DataFrame:
    """Generate cashflows with optional state machine."""
    
    if use_state_machine:
        from .loan_state_machine import LoanStateMachine
        state_machine = LoanStateMachine()
    
    # Reset loan states
    self._initialize_loan_states()
    
    rows = []
    for t in range(1, periods + 1):
        # Aggregate cashflows
        total_interest = 0.0
        total_principal = 0.0
        total_loss = 0.0
        
        for loan_id, loan in self.loan_states.items():
            if not loan.is_active:
                continue
            
            if use_state_machine:
                # Use state machine for realistic timeline
                loan_record = self._to_loan_record(loan)
                updated_record = state_machine.apply_month(loan_record)
                cashflows = state_machine.calculate_cashflows(updated_record)
                
                total_interest += cashflows.get('interest', 0)
                total_principal += cashflows.get('principal', 0)
                total_loss += cashflows.get('loss', 0)
                
                # Update loan state
                loan.current_balance = updated_record.current_upb
                loan.is_active = updated_record.current_upb > 0
            else:
                # Use original SMM/MDR logic (backwards compatible)
                # ... existing code ...
```

**Acceptance Criteria**:
- [ ] State machine mode produces realistic DQ ramps
- [ ] Backwards compatible with simple mode
- [ ] Performance acceptable (< 10 sec for 10k loans)

---

## Sprint 7-8: Pricing & Risk Analytics (Weeks 13-16)

**Goal**: Add bond pricing and core risk metrics.

### Week 13-14: Pricing Engine

#### Discount Curve & PV Pricing
**Status**: 🟡 High Priority  
**Effort**: 2 weeks  
**Files**: `engine/pricing.py` (new)

**Tasks**:
1. Build `DiscountCurve` class
2. Implement PV pricing
3. Add yield (IRR) calculation
4. Add discount margin for floaters

**Code Structure**:
```python
# engine/pricing.py

class DiscountCurve:
    """Interest rate curve for discounting."""
    
    def __init__(self, curve_type: str = "treasury"):
        self.curve_type = curve_type
        self.rates = {}  # tenor -> rate
    
    @classmethod
    def from_treasury_rates(cls, rates: Dict[int, float]) -> "DiscountCurve":
        """Build curve from treasury spot rates."""
        curve = cls("treasury")
        curve.rates = rates
        return curve
    
    def get_discount_factor(self, months: int) -> float:
        """Get discount factor for given tenor."""
        # Interpolate if needed
        if months in self.rates:
            rate = self.rates[months]
        else:
            rate = self._interpolate(months)
        
        return (1 + rate) ** (-months / 12)
    
    def shift(self, parallel_bps: int) -> "DiscountCurve":
        """Return parallel-shifted curve."""
        shifted = DiscountCurve(self.curve_type)
        shifted.rates = {
            tenor: rate + (parallel_bps / 10000)
            for tenor, rate in self.rates.items()
        }
        return shifted

def price_cashflows(
    cashflows: pd.DataFrame,
    curve: DiscountCurve,
    spread_bps: float = 0.0,
) -> float:
    """Price cashflows using discount curve."""
    pv = 0.0
    spread = spread_bps / 10000
    
    for _, row in cashflows.iterrows():
        period = row['Period']
        cashflow = row['Principal'] + row['Interest']
        
        # Discount with curve + spread
        df = curve.get_discount_factor(period) / \
             ((1 + spread) ** (period / 12))
        
        pv += cashflow * df
    
    return pv

def calculate_yield(price: float, 
                   cashflows: pd.DataFrame,
                   guess: float = 0.05) -> float:
    """Calculate yield (IRR) given price."""
    from scipy.optimize import newton
    
    def npv(y):
        pv = sum(
            (row['Principal'] + row['Interest']) / ((1 + y) ** (row['Period'] / 12))
            for _, row in cashflows.iterrows()
        )
        return pv - price
    
    return newton(npv, guess)
```

**Acceptance Criteria**:
- [ ] Correctly prices fixed-rate cashflows
- [ ] Yield calculation matches Excel IRR
- [ ] DM calculation for floaters

---

### Week 15-16: Risk Metrics

#### Duration & Convexity
**Status**: 🟡 High Priority  
**Effort**: 2 weeks  
**Files**: `engine/pricing.py`

**Tasks**:
1. Implement modified duration
2. Implement convexity
3. Add effective duration (for MBS)
4. Add API endpoints

**Code**:
```python
def calculate_duration_convexity(
    cashflows: pd.DataFrame,
    curve: DiscountCurve,
    spread_bps: float = 0.0,
    shock_bps: int = 10,
) -> Dict[str, float]:
    """Calculate modified duration and convexity."""
    
    # Base price
    P = price_cashflows(cashflows, curve, spread_bps)
    
    # Shocked prices
    P_up = price_cashflows(cashflows, curve.shift(shock_bps), spread_bps)
    P_down = price_cashflows(cashflows, curve.shift(-shock_bps), spread_bps)
    
    # Calculate metrics
    dy = shock_bps / 10000
    mod_duration = -(P_up - P_down) / (2 * P * dy)
    convexity = (P_up + P_down - 2 * P) / (P * dy ** 2)
    dv01 = mod_duration * P / 10000
    
    return {
        "price": P,
        "modified_duration": mod_duration,
        "convexity": convexity,
        "dv01": dv01,
    }
```

**Acceptance Criteria**:
- [ ] Duration matches bond math formulas
- [ ] Convexity correct for mortgage bonds
- [ ] API returns risk metrics

---

## Sprint 9-10: Validation & Calibration (Weeks 17-20)

**Goal**: Build confidence in model accuracy.

### Week 17-18: Backtesting Framework

#### Backtest Engine
**Status**: 🟡 High Priority  
**Effort**: 2 weeks  
**Files**: `engine/validation.py` (new)

**Tasks**:
1. Build backtest runner
2. Add error metrics (MAPE, RMSE)
3. Generate validation reports

**Code Structure**:
```python
# engine/validation.py

class BacktestEngine:
    """Compare projected vs actual performance."""
    
    def run_backtest(
        self,
        deal_id: str,
        start_period: int,
        end_period: int,
    ) -> BacktestReport:
        """Run backtest for historical periods."""
        
        # Load historical actuals
        actuals = self._load_actuals(deal_id, start_period, end_period)
        
        # Run projection
        projected = self._run_projection(deal_id, start_period, end_period)
        
        # Compare
        return self.compare(projected, actuals)
    
    def compare(
        self,
        projected: pd.DataFrame,
        actual: pd.DataFrame,
    ) -> BacktestReport:
        """Calculate error metrics."""
        
        report = BacktestReport()
        
        # CPR error
        report.cpr_mape = self._mape(actual['CPR'], projected['CPR'])
        report.cpr_rmse = self._rmse(actual['CPR'], projected['CPR'])
        
        # Loss error
        report.loss_mape = self._mape(actual['Loss'], projected['Loss'])
        report.loss_bias = (projected['Loss'].sum() - actual['Loss'].sum()) / \
                          actual['Loss'].sum()
        
        return report
    
    @staticmethod
    def _mape(actual, predicted) -> float:
        """Mean Absolute Percentage Error."""
        return (abs(actual - predicted) / actual).mean()
    
    @staticmethod
    def _rmse(actual, predicted) -> float:
        """Root Mean Square Error."""
        return ((actual - predicted) ** 2).mean() ** 0.5
```

**Acceptance Criteria**:
- [ ] Backtest runs on historical data
- [ ] Error metrics calculated
- [ ] Report generated with charts

---

### Week 19-20: Calibration Tools

#### Model Calibration
**Status**: 🟠 Medium Priority  
**Effort**: 2 weeks  
**Files**: `ml/calibration.py` (new)

**Tasks**:
1. Build CPR calibration
2. Build CDR calibration
3. Add cohort-based fitting

**Code Structure**:
```python
# ml/calibration.py

class HazardCalibrator:
    """Calibrate CPR/CDR models to historical data."""
    
    def fit_cpr_model(
        self,
        historical_data: pd.DataFrame,
        features: List[str],
    ) -> Dict[str, float]:
        """Fit CPR model parameters."""
        
        # Use survival model
        from lifelines import CoxPHFitter
        
        cph = CoxPHFitter()
        cph.fit(historical_data, 
                duration_col='months_to_prepay',
                event_col='prepaid',
                formula=' + '.join(features))
        
        return {
            'coefficients': cph.params_.to_dict(),
            'concordance': cph.concordance_index_,
        }
    
    def cross_validate(
        self,
        data: pd.DataFrame,
        n_folds: int = 5,
    ) -> Dict[str, float]:
        """K-fold cross-validation."""
        from sklearn.model_selection import KFold
        
        scores = []
        kf = KFold(n_splits=n_folds)
        
        for train_idx, test_idx in kf.split(data):
            train = data.iloc[train_idx]
            test = data.iloc[test_idx]
            
            params = self.fit_cpr_model(train, features)
            score = self.evaluate(params, test)
            scores.append(score)
        
        return {
            'mean_score': np.mean(scores),
            'std_score': np.std(scores),
        }
```

**Acceptance Criteria**:
- [ ] Calibration improves fit vs defaults
- [ ] Cross-validation prevents overfitting
- [ ] Cohort-based models available

---

## Sprint 11-12: Performance & Polish (Weeks 21-24)

### Week 21-22: Performance Optimization

#### Vectorization
**Status**: 🟠 Medium Priority  
**Effort**: 2 weeks  
**Files**: `engine/collateral.py`

**Tasks**:
1. Profile performance bottlenecks
2. Vectorize hot loops
3. Add chunked processing for large pools
4. Benchmark improvements

**Target**: 100k loans in < 10 seconds

---

#### Parallel Monte Carlo
**Status**: 🟠 Medium Priority  
**Effort**: 1 week  
**Files**: `engine/stress_testing.py`

**Tasks**:
1. Add parallel execution
2. Add progress tracking
3. Test with 10k simulations

---

### Week 23-24: Integration & Documentation

#### Final Integration
**Tasks**:
1. Integration testing across all modules
2. Fix any remaining issues
3. Update API documentation
4. Update UI help text
5. Create user guides

---

## Sprint 13: Release Preparation (Weeks 25-26)

### Week 25: Testing & QA

**Tasks**:
1. Full regression test suite
2. Performance benchmarks
3. Security review
4. Accessibility audit

---

### Week 26: Release & Training

**Tasks**:
1. Production deployment
2. User training sessions
3. Documentation handoff
4. Support runbook

---

## Success Metrics & Acceptance Criteria

### Technical Metrics

| Metric | Current | Target | Validation |
|--------|---------|--------|------------|
| **Loan types supported** | Fixed only | Fixed, ARM, IO | Test with ARM tape |
| **Max pool size** | ~10k loans | 100k+ loans | Benchmark test |
| **Simulation speed** | ~30 sec | < 5 sec | Performance test |
| **Backtest MAPE (CPR)** | Unknown | < 5% | Historical validation |
| **Backtest MAPE (CDR)** | Unknown | < 10% | Historical validation |
| **Golden file pass rate** | 0% | 95%+ | Automated tests |
| **API response time** | Varies | < 2 sec (p95) | Load test |

### Business Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| **Model accuracy** | MAPE on 12-month forecasts | < 5% |
| **Deal coverage** | % of deals that can be modeled | > 90% |
| **User adoption** | Active users per week | Baseline + 50% |
| **Time to value** | Upload to first simulation | < 5 minutes |

---

## Risk Management

### High-Risk Items

| Risk | Mitigation |
|------|------------|
| **State machine complexity** | Build incrementally, extensive testing |
| **Performance degradation** | Continuous benchmarking, optimization sprints |
| **Data quality issues** | Robust validation, clear error messages |
| **Breaking changes** | Maintain backwards compatibility, deprecation warnings |

### Contingency Plans

- If state machine takes longer: Ship without it, use simpler status model
- If performance targets missed: Reduce max pool size, add chunking
- If validation framework delayed: Manual testing, defer to later phase

---

## Appendix: Quick Reference

### Priority Legend
- 🔴 P0 (Critical): Blocks industry grade, must have
- 🟡 P1 (High): Important for completeness
- 🟠 P2 (Medium): Nice to have, deferred if needed

### File Locations
- **New files**: See each sprint's "Files:" section
- **Enhanced files**: Marked with "(enhance)" in file lists

### Dependencies
- Sprint 3-4 depends on Sprint 1-2 (schema design)
- Sprint 5-6 depends on Sprint 3-4 (data ingestion)
- Sprint 7-8 can run parallel to Sprint 5-6
- Sprint 9-10 depends on Sprint 5-6 (need state machine for validation)

---

*Document Version: 1.0*  
*Created: January 2026*  
*Next Review: End of Sprint 2*
