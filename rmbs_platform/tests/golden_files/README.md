# Golden File Testing Framework

## Overview

Golden file tests validate simulation accuracy by comparing our results against industry-standard tools (Intex, Bloomberg, Moody's CDOROM).

Each test consists of:
- **Input Deal Specification**: JSON file defining the RMBS structure
- **Expected Outputs**: CSV files with benchmark cashflows and balances
- **Tolerance Configuration**: Acceptable deviation thresholds

## Directory Structure

```
tests/golden_files/
├── README.md                    # This file
├── tolerance.json              # Default tolerance configuration
├── test_golden_files.py        # Test runner
├── FREDDIE_SAMPLE_001/         # Example test case
│   ├── input_spec.json         # Deal specification
│   ├── expected_cashflows.csv  # Expected cashflows from Intex
│   ├── expected_balances.csv   # Expected bond balances
│   └── README.md               # Test case notes
└── [YOUR_TEST_NAME]/           # Add your own test cases
    ├── input_spec.json
    ├── expected_cashflows.csv
    ├── expected_balances.csv
    └── README.md               # Document source and assumptions
```

## Creating a Golden File Test

### Step 1: Run Deal in Industry Tool

1. Load your deal in Intex/Bloomberg/Moody's
2. Run cashflow projection (usually 360 periods)
3. Export results to CSV:
   - Bond cashflows by period
   - Bond balances by period
   - Any other metrics you want to validate

### Step 2: Create Test Directory

```bash
mkdir tests/golden_files/YOUR_DEAL_NAME
```

### Step 3: Add Input Specification

Save your deal spec as `input_spec.json`:

```json
{
  "meta": {
    "deal_id": "YOUR_DEAL_NAME",
    "deal_name": "Your Deal Name",
    "asset_type": "NON_AGENCY_RMBS",
    "version": "1.0"
  },
  "bonds": [...],
  "waterfalls": {...},
  ...
}
```

### Step 4: Add Expected Outputs

**expected_cashflows.csv**:
```csv
Period,Interest,Principal,Prepayment,Default,Loss
1,1375000,0,0,0,0
2,1373245,125000,50000,10000,4000
...
```

**expected_balances.csv**:
```csv
Period,ClassA1,ClassA2,ClassB
1,150000000,60000000,25000000
2,149750000,59900000,24990000
...
```

### Step 5: Document Test Case

Create `README.md` in your test directory:

```markdown
# Test Case: YOUR_DEAL_NAME

**Source**: Intex v1.23.4  
**Run Date**: 2026-01-28  
**Assumptions**:
- CPR: 6% (PSA 100)
- CDR: 0.5%
- Loss Severity: 40%
- Rate path: Flat at 5.5%

**Notes**:
- Any special considerations
- Known differences between tools
- Rounding conventions used
```

### Step 6: Run Test

```bash
cd tests
python test_golden_files.py
```

## Tolerance Configuration

Tolerances are defined in `tolerance.json`:

```json
{
  "cashflows": {
    "absolute": 100.0,      // ±$100
    "relative": 0.01,       // ±1%
    "description": "Use larger of absolute or relative"
  },
  "balances": {
    "absolute": 1000.0,     // ±$1,000
    "relative": 0.001       // ±0.1%
  }
}
```

The test uses the **larger** of absolute or relative tolerance, so:
- Small values use absolute tolerance
- Large values use relative tolerance

### Custom Tolerances

To use custom tolerances for a specific test, create `tolerance.json` in the test directory.

## Running Tests

### Run All Tests

```bash
python tests/test_golden_files.py
```

### Run Specific Test

```python
from tests.test_golden_files import GoldenFileTest

test = GoldenFileTest("tests/golden_files/YOUR_DEAL_NAME")
result = test.run()

print(result.summary())

if result.pass_rate >= 0.95:
    print("✅ Test passed")
else:
    print("❌ Test failed")
```

### Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/tests.yml
- name: Run Golden File Tests
  run: |
    python tests/test_golden_files.py
    if [ $? -ne 0 ]; then
      echo "Golden file tests failed"
      exit 1
    fi
```

## Interpreting Results

### Pass Rate

- **≥95%**: Test passes - minor differences within tolerance
- **90-95%**: Review differences - may indicate rounding or assumption differences
- **<90%**: Test fails - significant differences require investigation

### Common Differences

**Rounding Conventions**:
- Our tool: Round to nearest cent
- Intex: May use banker's rounding
- **Solution**: Increase absolute tolerance to $1-10

**Day Count**:
- Our tool: 30/360
- Intex: Actual/360
- **Solution**: Document in test README, adjust tolerances

**Prepayment Models**:
- Our tool: ML-based or PSA
- Intex: May use different CPR curves
- **Solution**: Use same assumptions or document differences

**Floating Rate Fixings**:
- Our tool: Index + margin
- Intex: May use different index fixings
- **Solution**: Use fixed-rate deals for baseline validation

## Best Practices

### 1. Start Simple

Begin with:
- Fixed-rate deals (no index complications)
- Sequential pay (no PAC/TAC structures)
- Short maturities (60-120 periods for faster validation)

### 2. Document Everything

Always include:
- Source tool and version
- All assumptions (CPR, CDR, severity, rates)
- Any known differences
- Date of golden file generation

### 3. Version Control

- Commit golden files to git
- Tag with tool version: `git tag golden-intex-v1.23.4`
- Update when tool changes

### 4. Regular Updates

- Re-run golden files quarterly
- Update when:
  - Industry tools release new versions
  - Our engine adds features
  - Market conventions change

### 5. Multiple Sources

For critical validation:
- Create golden files from 2+ sources (Intex + Bloomberg)
- Compare differences between sources first
- Use consensus values if sources disagree

## Troubleshooting

### Test Fails Due to Rounding

**Problem**: Small differences in every period

**Solution**:
```json
{
  "cashflows": {
    "absolute": 10.0  // Increase from 1.0 to 10.0
  }
}
```

### Test Fails in Later Periods

**Problem**: Differences accumulate over time

**Cause**: Likely due to:
- Balance mismatch causing compounding errors
- Different amortization schedules
- Prepayment timing differences

**Solution**:
- Focus on early periods first (periods 1-12)
- Verify balance matching before cashflows
- Check if both tools use same amortization formula

### Missing Metrics

**Problem**: `Metric 'XXX' not found in simulation results`

**Solution**:
- Add metric to `_extract_cashflows()` or `_extract_balances()`
- Or remove from expected CSV if not critical

## Example Test Cases

### FREDDIE_SAMPLE_001

- **Source**: Manually calculated
- **Structure**: Simple 2-class deal
- **Purpose**: Smoke test for basic functionality
- **Pass Rate Target**: 100%

### Add Your Own

To contribute:
1. Create test case following structure above
2. Document assumptions and source
3. Run test and verify ≥95% pass rate
4. Submit PR with test case

## Support

For questions or issues:
- Review `test_golden_files.py` for implementation details
- Check existing test cases for examples
- Consult Intex/Bloomberg documentation for export formats

---

*Last Updated: January 2026*  
*Framework Version: 1.0*
