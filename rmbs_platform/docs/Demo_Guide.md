# RMBS Platform Demo Guide

This guide provides step-by-step demonstrations of the platform's key capabilities using realistic test data.

---

## Quick Start

### 1. Start the Backend API
```bash
cd rmbs_platform
uvicorn api_main:app --reload --port 8000
```

### 2. Start the UI
```bash
streamlit run ui_app.py
```

### 3. Access the Platform
- **UI**: http://localhost:8501 (Modern modular interface)
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 4. UI Features
The new modular UI provides:
- **Loading States**: Progress indicators for long operations
- **Interactive Charts**: Plotly-based visualizations with hover details
- **KPI Dashboards**: Key metrics displayed prominently
- **Responsive Design**: Adaptive layouts for different screen sizes
- **Error Recovery**: Contextual error messages with retry options

---

## Demo Case Details

---

## Demo Case 1: Prime RMBS Deal Analysis

### Summary
**Use Case**: Investor analyzing a new prime RMBS investment opportunity  
**Persona**: Investor (Analytics)  
**Complexity**: Basic  
**Duration**: 10-15 minutes

### Deal Information
| Field | Value |
|-------|-------|
| Deal ID | `PRIME_2024_1` |
| Deal Name | Prime Residential Trust 2024-1 |
| Issuer | ABC Mortgage Capital |
| Original Balance | $500,000,000 |
| Current Balance | $454,349,983 (after 12 months) |
| Loan Count | 1,847 loans |
| Avg Loan Size | $270,709 |

### Collateral Characteristics
| Metric | Value | Industry Benchmark |
|--------|-------|-------------------|
| WAC | 6.75% | 6.5% - 7.0% |
| WAM | 354 months | 350-358 |
| Avg FICO | 748 | >740 for prime |
| Avg LTV | 72.5% | <80% for prime |
| Avg DTI | 34.2% | <43% |

### Capital Structure
| Tranche | Original | Rating | Coupon | CE Level |
|---------|----------|--------|--------|----------|
| Class A | $425,000,000 | AAA | 4.50% | 15.0% |
| Class M1 | $37,500,000 | AA | 5.50% | 7.5% |
| Class M2 | $25,000,000 | A | 6.50% | 2.5% |
| Class B | $12,500,000 | BBB | 8.50% | 0.0% |

### Input Parameters

**Base Case Scenario**:
```json
{
  "scenario_id": "BASE_CASE_2024",
  "cpr": 0.08,
  "cdr": 0.008,
  "severity": 0.32,
  "horizon_periods": 60,
  "rate_scenario": "base",
  "start_rate": 0.045
}
```

**Rate Rally Scenario**:
```json
{
  "scenario_id": "RATE_RALLY_2024",
  "cpr": 0.18,
  "cdr": 0.006,
  "severity": 0.30,
  "horizon_periods": 60,
  "rate_scenario": "rally",
  "start_rate": 0.045
}
```

### Expected Results

#### Base Case (60-month projection)
| Metric | Class A | Class M1 | Class M2 | Class B |
|--------|---------|----------|----------|---------|
| Ending Balance | $178.5M | $37.5M | $25.0M | $12.5M |
| WAL (years) | 4.2 | 7.5 | 8.8 | 9.2 |
| Cum Principal | $246.5M | $0 | $0 | $0 |
| Total Interest | $52.8M | $12.4M | $9.8M | $6.4M |
| Writedowns | $0 | $0 | $0 | $0 |

#### Rate Rally (60-month projection)
| Metric | Class A | Class M1 | Class M2 | Class B |
|--------|---------|----------|----------|---------|
| Ending Balance | $52.1M | $37.5M | $25.0M | $12.5M |
| WAL (years) | 2.8 | 5.2 | 6.5 | 7.1 |
| Cum Principal | $372.9M | $0 | $0 | $0 |
| Total Interest | $38.2M | $10.8M | $8.5M | $5.5M |
| Writedowns | $0 | $0 | $0 | $0 |

#### Key Observations
- ✅ All tranches pay full principal in both scenarios
- ✅ No credit losses reach bondholder
- 📊 Rate rally shortens Class A WAL by 1.4 years
- 📊 Interest income reduced by $14.6M in rally scenario (extension risk)

---

## Demo Case 2: Non-QM Deal with Elevated Credit Risk

### Summary
**Use Case**: Risk analyst evaluating credit performance of non-QM pool  
**Persona**: Investor (Analytics) + Servicer (Operations)  
**Complexity**: Intermediate  
**Duration**: 15-20 minutes

### Deal Information
| Field | Value |
|-------|-------|
| Deal ID | `NONQM_2023_1` |
| Deal Name | Non-QM Residential Trust 2023-1 |
| Issuer | XYZ Capital Partners |
| Original Balance | $300,000,000 |
| Current Balance | $261,203,156 (after 18 months) |
| Factor | 87.07% |
| Loan Count | 892 loans |

### Collateral Characteristics
| Metric | Value | Risk Assessment |
|--------|-------|-----------------|
| WAC | 7.85% | Higher spread for risk |
| WAM | 342 months | Standard |
| Avg FICO | 712 | Below prime threshold |
| Avg LTV | 75.8% | Moderate |
| Self-Employed | 68.5% | ⚠️ Income volatility |
| Bank Statement | 55% | ⚠️ Non-standard doc |
| Interest Only | 32.5% | ⚠️ Payment shock risk |

### Capital Structure
| Tranche | Original | Rating | Coupon | CE Level |
|---------|----------|--------|--------|----------|
| Class A1 | $210,000,000 | AAA | 5.75% | 30.0% |
| Class A2 | $45,000,000 | AA | 6.25% | 15.0% |
| Class M1 | $30,000,000 | A | 7.25% | 5.0% |
| Class B | $15,000,000 | BBB- | 9.50% | 0.0% |

### Input Parameters

**Mild Recession Scenario**:
```json
{
  "scenario_id": "MILD_RECESSION_2024",
  "cpr": 0.05,
  "cdr": 0.025,
  "severity": 0.40,
  "horizon_periods": 60,
  "rate_scenario": "selloff",
  "start_rate": 0.055,
  "economic_assumptions": {
    "gdp_growth": -0.015,
    "unemployment_rate": 0.065,
    "hpi_growth": -0.08
  }
}
```

### Expected Results

#### Base Case vs Mild Recession (36-month projection)
| Metric | Base Case | Mild Recession | Delta |
|--------|-----------|----------------|-------|
| Cumulative Default | $14.2M | $23.8M | +$9.6M |
| Cumulative Loss | $5.4M | $9.5M | +$4.1M |
| 60+ Delinquency | 4.5% | 7.8% | +3.3% |
| Class B Balance | $15.0M | $9.2M | -$5.8M |
| Class M1 Balance | $30.0M | $30.0M | $0 |
| Delinq Trigger | ⚠️ Near | ❌ Breached | - |

#### Trigger Analysis
| Trigger | Threshold | Base Case | Recession |
|---------|-----------|-----------|-----------|
| Delinquency Test | 4.0% | 4.5% ⚠️ | 7.8% ❌ |
| Cum Loss Test | N/A | N/A | N/A |

#### Key Observations
- ⚠️ Deal approaching delinquency trigger in base case
- ❌ Trigger breached under mild recession
- 📊 Class B absorbs all losses, Class M1 protected
- 📊 30% CE on A1 provides substantial protection

---

## Demo Case 3: Stressed Deal with Active Triggers

### Summary
**Use Case**: Servicer managing workout, demonstrating trigger mechanics  
**Persona**: Servicer (Operations) + Auditor (Review)  
**Complexity**: Advanced  
**Duration**: 20-25 minutes

### Deal Information
| Field | Value |
|-------|-------|
| Deal ID | `STRESSED_2022_1` |
| Deal Name | Legacy Residential Trust 2022-1 |
| Asset Type | Subprime RMBS |
| Original Balance | $250,000,000 |
| Current Balance | $145,000,000 (after 34 months) |
| Factor | 58.0% |
| Original Loan Count | 1,250 |
| Current Loan Count | 892 |

### Collateral Characteristics (Current State)
| Metric | Value | Status |
|--------|-------|--------|
| WAC | 8.25% | High spread |
| Avg FICO | 665 | ❌ Subprime |
| Avg LTV | 88.5% | ⚠️ High |
| 60+ Delinquency | 15.5% | ❌ Severely elevated |
| Cumulative Loss | 8.5% | ❌ Above threshold |
| REO Inventory | 2.0% | ⚠️ Workout |

### Geographic Risk Concentration
| State | Balance % | Avg LTV | Risk Level |
|-------|-----------|---------|------------|
| FL | 32.5% | 92.5% | ❌ High |
| CA | 22.0% | 85.0% | ⚠️ Medium |
| AZ | 12.5% | 95.0% | ❌ High |
| NV | 8.5% | 98.0% | ❌ High |

### Capital Structure (Current State)
| Tranche | Original | Current | Rating | Status |
|---------|----------|---------|--------|--------|
| Class A | $212.5M | $125.5M | BBB (was AAA) | Interest Current |
| Class M | $25.0M | $18.5M | CCC (was A) | $125K Shortfall |
| Class B | $12.5M | $1.0M | D (was BBB) | $850K Shortfall, 92% Written Down |

### Trigger Status
| Trigger | Type | Threshold | Current | Status | Breach Date |
|---------|------|-----------|---------|--------|-------------|
| Delinquency Test | 60+ DQ | 8.0% | 15.5% | ❌ FAILING | 2023-06-25 |
| Cum Loss Test | Cum Loss | 5.0% | 8.5% | ❌ FAILING | 2023-09-25 |

### Input Parameters

**Continued Stress Projection**:
```json
{
  "cpr": 0.04,
  "cdr": 0.035,
  "severity": 0.55,
  "horizon_periods": 36,
  "current_delinq_60plus": 0.155,
  "trigger_status": {
    "delinquency": "FAILING",
    "cumulative_loss": "FAILING"
  }
}
```

### Expected Results (36-month forward projection)

#### Bond Cashflows Under Trigger Events
| Metric | Class A | Class M | Class B |
|--------|---------|---------|---------|
| Beginning Balance | $125.5M | $18.5M | $1.0M |
| Scheduled Interest | $19.8M | $4.0M | $0.3M |
| **Interest Received** | **$19.8M** | **$2.8M** ⚠️ | **$0** ❌ |
| Interest Shortfall | $0 | $1.2M | $0.3M |
| Principal Received | $68.2M | $0 | $0 |
| Ending Balance | $57.3M | $18.5M | $1.0M |
| Additional Writedown | $0 | $0 | $0 |

#### Waterfall Impact Under Active Triggers
```
Interest Waterfall (Trigger Active):
1. Servicing Fee:        $0.60M ✓ Paid
2. Trustee Fee:          $0.02M ✓ Paid
3. Class A Interest:     $0.55M ✓ Paid in Full
4. Reserve Replenish:    $0.65M ✓ Partial Fill
5. Class M Interest:     BLOCKED ❌ (Trigger Active)
6. Class B Interest:     BLOCKED ❌ (Trigger Active)

Principal Waterfall (Trigger Active):
1. Class A Principal:    $1.9M ✓ Paid (All Available)
2. Class M Principal:    BLOCKED ❌ (Trigger Active)
3. Class B Principal:    BLOCKED ❌ (Trigger Active)
```

#### Key Observations
- 🔴 Both triggers remain in FAILING status
- 🔴 Class B has accumulated $11.5M in writedowns (92%)
- ⚠️ Class M interest shortfall growing
- ✅ Class A remains current (protected by trigger mechanism)
- 📊 Subordination redirecting all principal to senior

---

## Demo Case 4: Scenario Comparison Analysis

### Summary
**Use Case**: Investment committee comparing scenario outcomes  
**Persona**: Investor (Analytics)  
**Complexity**: Intermediate  
**Duration**: 15-20 minutes

### Scenarios Overview
| Scenario | CPR | CDR | Severity | Description |
|----------|-----|-----|----------|-------------|
| Base Case | 8% | 0.8% | 32% | Current conditions |
| Rate Rally | 18% | 0.6% | 30% | Fed easing cycle |
| Mild Recession | 5% | 2.5% | 40% | Moderate downturn |
| Severe Stress | 3% | 6.0% | 50% | CCAR severely adverse |
| High Prepay | 25% | 0.5% | 30% | Extreme refi |
| Low Prepay | 4% | 1.2% | 35% | Lock-in effect |

### Input: PRIME_2024_1 Deal

### Expected Results (60-month WAL Comparison)

| Scenario | Class A | Class M1 | Class M2 | Class B |
|----------|---------|----------|----------|---------|
| Base Case | 4.2 yrs | 7.5 yrs | 8.8 yrs | 9.2 yrs |
| Rate Rally | 2.8 yrs | 5.2 yrs | 6.5 yrs | 7.1 yrs |
| Mild Recession | 5.1 yrs | 8.2 yrs | 9.5 yrs | 10.0 yrs |
| Severe Stress | 5.8 yrs | 9.0 yrs | 10.2 yrs | 10.5 yrs |
| High Prepay | 2.1 yrs | 4.5 yrs | 5.8 yrs | 6.4 yrs |
| Low Prepay | 5.5 yrs | 8.8 yrs | 9.8 yrs | 10.2 yrs |

### Expected Results (60-month Cumulative Loss)

| Scenario | Cum Default | Cum Loss | Loss % | Class B Impact |
|----------|-------------|----------|--------|----------------|
| Base Case | $2.4M | $0.8M | 0.16% | 6.4% |
| Rate Rally | $1.8M | $0.5M | 0.10% | 4.0% |
| Mild Recession | $7.5M | $3.0M | 0.60% | 24.0% |
| **Severe Stress** | **$18.0M** | **$9.0M** | **1.80%** | **72.0%** ⚠️ |
| High Prepay | $1.5M | $0.5M | 0.10% | 4.0% |
| Low Prepay | $3.6M | $1.3M | 0.26% | 10.4% |

#### Key Observations
- 📊 WAL varies by 3.7 years for Class A across scenarios
- ⚠️ Severe Stress impacts Class B significantly (72% writedown)
- ✅ Class A protected in all scenarios
- 📊 Extension risk (Low Prepay) adds 1.3 years to Class A WAL

---

## Demo Case 5: CCAR Regulatory Stress Testing

### Summary
**Use Case**: Risk management team performing regulatory stress test  
**Persona**: Investor (Analytics)  
**Complexity**: Advanced  
**Duration**: 20-25 minutes

### Regulatory Framework
- **Standard**: Federal Reserve CCAR Severely Adverse
- **Horizon**: 9 quarters (Q1 2024 - Q1 2026)
- **Variables**: GDP, Unemployment, HPI, Interest Rates

### Macroeconomic Scenario Path

| Quarter | GDP Growth | Unemployment | HPI Δ | 10Y Treasury |
|---------|------------|--------------|-------|--------------|
| Q1 2024 | +0.5% | 5.5% | -2% | 4.2% |
| Q2 2024 | -2.0% | 7.0% | -5% | 3.8% |
| Q3 2024 | -3.5% | 8.5% | -8% | 3.5% |
| Q4 2024 | -2.5% | 9.5% | -8% | 3.3% |
| Q1 2025 | -1.0% | 10.0% | -5% | 3.2% |
| Q2 2025 | +0.5% | 9.8% | -3% | 3.4% |
| Q3 2025 | +1.5% | 9.2% | -1% | 3.6% |
| Q4 2025 | +2.0% | 8.5% | +1% | 3.8% |
| Q1 2026 | +2.5% | 8.0% | +2% | 4.0% |

### Input Parameters

```json
{
  "scenario_id": "SEVERE_STRESS_2024",
  "scenario_type": "severely_adverse",
  "horizon_periods": 27,
  "parameters": {
    "cpr": 0.03,
    "cdr": 0.06,
    "severity": 0.50
  },
  "quarterly_factors": {
    "Q1": {"unemployment": 0.055, "hpi_change": -0.02, "cdr_mult": 1.5},
    "Q2": {"unemployment": 0.070, "hpi_change": -0.05, "cdr_mult": 2.5},
    "Q3": {"unemployment": 0.085, "hpi_change": -0.08, "cdr_mult": 3.5},
    "Q4": {"unemployment": 0.095, "hpi_change": -0.08, "cdr_mult": 4.0},
    "Q5": {"unemployment": 0.100, "hpi_change": -0.05, "cdr_mult": 4.0},
    "Q6": {"unemployment": 0.098, "hpi_change": -0.03, "cdr_mult": 3.5},
    "Q7": {"unemployment": 0.092, "hpi_change": -0.01, "cdr_mult": 3.0},
    "Q8": {"unemployment": 0.085, "hpi_change": 0.01, "cdr_mult": 2.5},
    "Q9": {"unemployment": 0.080, "hpi_change": 0.02, "cdr_mult": 2.0}
  }
}
```

### Expected Results: PRIME_2024_1 Under CCAR Severely Adverse

#### Quarterly Loss Projection
| Quarter | Defaults | Loss | Cum Loss | Class B Impact |
|---------|----------|------|----------|----------------|
| Q1 2024 | $0.75M | $0.38M | 0.08% | 3.0% |
| Q2 2024 | $1.25M | $0.63M | 0.20% | 5.0% |
| Q3 2024 | $1.75M | $0.88M | 0.38% | 7.0% |
| Q4 2024 | $2.00M | $1.00M | 0.58% | 8.0% |
| Q5 2025 | $2.00M | $1.00M | 0.78% | 8.0% |
| Q6 2025 | $1.75M | $0.88M | 0.95% | 7.0% |
| Q7 2025 | $1.50M | $0.75M | 1.10% | 6.0% |
| Q8 2025 | $1.25M | $0.63M | 1.23% | 5.0% |
| Q9 2026 | $1.00M | $0.50M | 1.33% | 4.0% |
| **Total** | **$13.25M** | **$6.65M** | **1.33%** | **53.2%** |

#### Tranche Impact Summary
| Tranche | Beginning | Losses | Ending | Impaired? |
|---------|-----------|--------|--------|-----------|
| Class A | $425.0M | $0 | $345.2M | ✅ No |
| Class M1 | $37.5M | $0 | $37.5M | ✅ No |
| Class M2 | $25.0M | $0 | $25.0M | ✅ No |
| Class B | $12.5M | $6.65M | $5.85M | ⚠️ Partial |

#### Credit Enhancement Analysis
| Metric | Initial | Stressed | Status |
|--------|---------|----------|--------|
| Class A CE | 15.0% | 12.8% | ✅ Adequate |
| Class M1 CE | 7.5% | 5.3% | ⚠️ Eroded |
| Class M2 CE | 2.5% | 0.3% | ⚠️ Near breach |
| OC Ratio | 100% | 97.2% | ⚠️ Below par |

#### Key Findings
- 🔴 53% of Class B principal impaired
- ⚠️ Class M2 CE eroded to 0.3%
- ✅ Class A maintains investment grade protection
- 📊 Peak losses occur Q4-Q5 (aligned with unemployment peak)
- 📊 Recovery begins Q7 as economy stabilizes

---

## Sample Data Summary

### Deals Available
| Deal ID | Type | Size | Tranches | Status |
|---------|------|------|----------|--------|
| PRIME_2024_1 | Prime RMBS | $500M | 4 | New issuance |
| NONQM_2023_1 | Non-QM | $300M | 4 | Seasoned (18mo) |
| STRESSED_2022_1 | Subprime | $250M | 3 | Stressed/Triggers |
| SAMPLE_RMBS_2024 | Demo | $10M | 2 | Basic example |
| FREDDIE_SAMPLE_2017_2020 | Agency | Various | 2 | Freddie Mac data |

### Scenarios Available
| Scenario ID | Type | CPR | CDR | Use Case |
|-------------|------|-----|-----|----------|
| BASE_CASE_2024 | Baseline | 8% | 0.8% | Standard projection |
| RATE_RALLY_2024 | Custom | 18% | 0.6% | Prepay acceleration |
| MILD_RECESSION_2024 | Adverse | 5% | 2.5% | Moderate stress |
| SEVERE_STRESS_2024 | Severely Adverse | 3% | 6% | CCAR stress test |
| HIGH_PREPAY_2024 | Sensitivity | 25% | 0.5% | Extension risk |
| LOW_PREPAY_2024 | Sensitivity | 4% | 1.2% | Contraction risk |

### Collateral Files
| File | Loans | Balance | Avg FICO | Avg LTV |
|------|-------|---------|----------|---------|
| PRIME_2024_1.json | 1,847 | $500M | 748 | 72.5% |
| NONQM_2023_1.json | 892 | $285M | 712 | 75.8% |
| demo_loan_tape.csv | 30 | ~$10M | 735 | 76% |

### Performance Data
| File | Periods | Status |
|------|---------|--------|
| PRIME_2024_1.csv | 12 months | Performing |
| NONQM_2023_1.csv | 18 months | Elevated DQ |

---

## Persona-Specific Demos

### Arranger (Structurer) Demo
1. Upload new deal specification
2. Validate waterfall logic
3. Review credit enhancement levels
4. Check trigger definitions

### Servicer (Operations) Demo
1. Upload monthly performance tape
2. Track delinquency trends
3. Monitor trigger status
4. Review loss allocation

### Investor (Analytics) Demo
1. Run cashflow simulations
2. Compare multiple scenarios
3. Analyze yield and WAL
4. Stress test the structure

### Auditor (Review) Demo
1. Review audit trail
2. Download evidence bundle
3. Verify calculation accuracy
4. Track version history

---

## UI Features Overview

### Modern Interface Components
- **🎯 Simulation Controls**: Sliders and inputs with real-time validation
- **📊 KPI Dashboards**: Key metrics (WAL, losses, balances) prominently displayed
- **📈 Interactive Charts**: Bond balance evolution, prepayment curves, loss distribution
- **🔄 Scenario Comparison**: Side-by-side analysis of different assumptions
- **💾 Export Capabilities**: CSV downloads with formatted data
- **⚡ Loading States**: Progress bars and status indicators during computations

### Persona-Specific Workflows
- **🏗️ Arranger**: Deal structuring with validation feedback
- **📊 Servicer**: Performance upload with reconciliation summaries
- **📈 Investor**: Advanced analytics with ML diagnostics
- **🔍 Auditor**: Evidence packages and audit trails

## Tips for Effective Demos

1. **Start Simple**: Begin with PRIME_2024_1 and Base Case scenario
2. **Show Contrast**: Compare healthy deal vs. stressed deal (STRESSED_2022_1)
3. **Highlight Triggers**: Demonstrate how triggers redirect cashflows
4. **Use Realistic Numbers**: All data reflects actual RMBS market conventions
5. **Show Modern UX**: Demonstrate loading states, interactive charts, and responsive design
6. **Export Results**: Show formatted CSV exports for further analysis

---

## Troubleshooting

**API Not Responding**:
```bash
# Check if API is running
curl http://localhost:8000/health
```

**UI Can't Connect**:
- Verify API is running on port 8000
- Check CORS settings in config.py
- Ensure using the new modular UI (`ui_app.py`)

**UI Loading Issues**:
- Clear browser cache and reload
- Check that all UI modules are properly installed
- Verify Python path includes the rmbs_platform directory

**Missing Data**:
- Ensure all JSON files are in correct directories
- Check file permissions
- Verify deal and collateral files match expected schema

**New UI Features Not Working**:
- Confirm using `streamlit run ui_app.py` (not legacy version)
- Check browser console for JavaScript errors
- Verify Plotly and other dependencies are installed

---

## Appendix A: API Examples

### Running a Simulation via API

**Request:**
```bash
curl -X POST "http://localhost:8000/simulate" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: investor" \
  -d '{
    "deal_id": "PRIME_2024_1",
    "cpr": 0.08,
    "cdr": 0.008,
    "severity": 0.32,
    "horizon_periods": 60,
    "use_ml_models": true
  }'
```

**Response:**
```json
{
  "job_id": "sim_20240115_143022_abc123",
  "status": "completed",
  "deal_id": "PRIME_2024_1",
  "scenario": {
    "cpr": 0.08,
    "cdr": 0.008,
    "severity": 0.32
  },
  "summary": {
    "total_periods": 60,
    "ending_collateral": 178532450.25,
    "cumulative_loss": 796823.45,
    "class_a_wal": 4.21,
    "class_b_writedown": 0.0
  }
}
```

### Uploading Performance Data

**Request:**
```bash
curl -X POST "http://localhost:8000/performance/PRIME_2024_1" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: servicer" \
  -d '[
    {
      "Period": 13,
      "Date": "2025-02-25",
      "BeginningBalance": 454349983.08,
      "InterestCollected": 2555847.00,
      "PrincipalCollected": 3245678.00,
      "Defaults": 182500.00,
      "Recovery": 58000.00,
      "RealizedLoss": 124500.00
    }
  ]'
```

### Creating a Scenario

**Request:**
```bash
curl -X POST "http://localhost:8000/scenarios" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: investor" \
  -d '{
    "name": "Custom Stress Test Q1 2024",
    "description": "Custom scenario for quarterly risk review",
    "parameters": {
      "cpr": 0.06,
      "cdr": 0.03,
      "severity": 0.45,
      "horizon_periods": 48
    }
  }'
```

---

## Appendix B: Calculation Methodologies

### CPR to SMM Conversion
```
SMM = 1 - (1 - CPR)^(1/12)

Example: 8% CPR
SMM = 1 - (1 - 0.08)^(1/12)
SMM = 1 - 0.9931
SMM = 0.69% (monthly)
```

### CDR to MDR Conversion
```
MDR = 1 - (1 - CDR)^(1/12)

Example: 2% CDR
MDR = 1 - (1 - 0.02)^(1/12)
MDR = 0.168% (monthly)
```

### Weighted Average Life (WAL)
```
WAL = Σ(t × Principal_t) / Total_Principal

Where:
- t = time in years
- Principal_t = principal received in period t
```

### Overcollateralization Ratio
```
OC Ratio = (Collateral Balance + Reserve) / Bonds Outstanding at Target Level

Example (Class A):
OC = ($454M + $2.5M) / $425M = 107.4%
```

### Interest Coverage Ratio
```
IC Ratio = Interest Available / Interest Due at Target Level

Example (Class A):
IC = $2.56M / ($425M × 4.5% / 12) = 1.60x
```

### Loss Severity Calculation
```
Severity = Realized Loss / Default Balance

Example:
Severity = $124,500 / $182,500 = 68.2%

Note: Platform uses dynamic model:
Severity = Base + LTV_adj + FICO_adj + State_adj + HPI_adj
```

---

## Appendix C: Trigger Definitions

### Delinquency Trigger
```
Condition: 60+ Day Delinquency > Threshold
Threshold: 4% - 8% (deal dependent)
Cure: 3-6 consecutive periods below threshold
Effect: Redirect subordinate interest/principal to senior
```

### OC Trigger
```
Condition: OC Ratio < Required Level
Threshold: 105% - 125% (tranche dependent)
Cure: 3 consecutive periods above threshold
Effect: Turbo principal to senior, block subordinate interest
```

### Cumulative Loss Trigger
```
Condition: Cumulative Losses > Threshold
Threshold: 2% - 10% of original balance
Cure: Non-curable (loss is permanent)
Effect: Permanent lock-out of subordinate payments
```

---

## Appendix D: Glossary

| Term | Definition |
|------|------------|
| **CPR** | Conditional Prepayment Rate - annualized prepayment speed |
| **CDR** | Conditional Default Rate - annualized default rate |
| **SMM** | Single Monthly Mortality - monthly prepayment rate |
| **MDR** | Monthly Default Rate |
| **WAC** | Weighted Average Coupon |
| **WAM** | Weighted Average Maturity |
| **WALA** | Weighted Average Loan Age |
| **WAL** | Weighted Average Life |
| **CE** | Credit Enhancement |
| **OC** | Overcollateralization |
| **IC** | Interest Coverage |
| **LTV** | Loan-to-Value Ratio |
| **FICO** | Credit score (Fair Isaac Corporation) |
| **DTI** | Debt-to-Income Ratio |
| **DQ** | Delinquency |
| **REO** | Real Estate Owned (foreclosed property) |
| **Non-QM** | Non-Qualified Mortgage |
| **CCAR** | Comprehensive Capital Analysis and Review |

---

*Demo data last updated: January 2026*
