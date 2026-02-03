# Phase 1 Test Suite - Quick Reference

## Running All Tests

### Individual Tests

```bash
# Test 1: Net WAC Cap Integration
python3 test_net_wac_cap.py

# Test 2: Trigger Cure Logic
python3 test_trigger_cure.py

# Test 3: Caching Infrastructure
python3 test_caching.py

# Test 4: Audit Trail Enhancement
python3 test_audit_trail.py

# Test 5: Canonical Loan Schema
python3 test_loan_schema.py

# Test 6: Phase 1 on Real Deal
python3 test_phase1_on_real_deal.py

# Test 7: Industry Grade Fixes (Loan-Level + Iterative Solver)
python3 test_industry_grade_fixes.py
```

### Run All Phase 1 Tests

```bash
# Run all Phase 1 tests sequentially
python3 test_net_wac_cap.py && \
python3 test_trigger_cure.py && \
python3 test_caching.py && \
python3 test_audit_trail.py && \
python3 test_loan_schema.py && \
python3 test_phase1_on_real_deal.py && \
python3 test_industry_grade_fixes.py && \
echo "✅ All Phase 1 tests passed!"
```

### Quick Smoke Test

```bash
# Fast validation of core features
python3 test_net_wac_cap.py 2>&1 | tail -5 && \
python3 test_trigger_cure.py 2>&1 | tail -5 && \
python3 test_phase1_on_real_deal.py 2>&1 | tail -10
```

## Expected Outputs

### Test 1: Net WAC Cap
- **Duration:** ~1 second
- **Expected:** Solver converges in 3-5 iterations
- **Output:** Net WAC calculation and bond balance updates

### Test 2: Trigger Cure Logic
- **Duration:** <1 second
- **Expected:** Trigger requires 3 consecutive passing periods to cure
- **Output:** Detailed trigger state transitions

### Test 3: Caching
- **Duration:** ~2 seconds
- **Expected:** 1000x+ speedup on cached calculations
- **Output:** Cache hit rate statistics

### Test 4: Audit Trail
- **Duration:** ~1 second
- **Expected:** Complete execution log exported to JSON
- **Output:** Audit trail summary and JSON files in `results/`

### Test 5: Loan Schema
- **Duration:** <1 second
- **Expected:** Successfully map loans from 3 different sources
- **Output:** Normalized loan data from Freddie Mac, Fannie Mae, generic servicer

### Test 6: Phase 1 on Real Deal
- **Duration:** ~2 seconds
- **Expected:** All Phase 1 features work on complex Freddie Mac deal
- **Output:** Net WAC cap, trigger cure, and caching validation

### Test 7: Industry Grade Fixes
- **Duration:** ~3 seconds
- **Expected:** Loan-level model outperforms rep-line, solver handles circularity
- **Output:** WAC drift comparison, solver convergence demonstration

## Troubleshooting

### Test Fails with Import Error
```bash
# Ensure you're in the correct directory
cd /path/to/rmbs_platform
python3 test_name.py
```

### Test Fails with Missing Data
```bash
# Check that datasets exist
ls datasets/FREDDIE_SAMPLE_2017_2020/
```

### View Detailed Logs
```bash
# Run with full logging
python3 test_name.py 2>&1 | grep -v "RMBS\."  # Hide debug logs
python3 test_name.py 2>&1                     # Show all logs
```

## Test Coverage Summary

| Test | Feature | Status | Critical |
|------|---------|--------|----------|
| `test_net_wac_cap.py` | Net WAC Cap | ✅ Pass | Yes |
| `test_trigger_cure.py` | Trigger Cure | ✅ Pass | Yes |
| `test_caching.py` | Performance | ✅ Pass | No |
| `test_audit_trail.py` | Compliance | ✅ Pass | No |
| `test_loan_schema.py` | Data Quality | ✅ Pass | Yes |
| `test_phase1_on_real_deal.py` | Integration | ✅ Pass | Yes |
| `test_industry_grade_fixes.py` | Core Gaps | ✅ Pass | Yes |

**Total:** 7 tests, all passing

## Golden File Testing (Future)

The golden file test framework is ready but requires external data:

```bash
# Run golden file tests (when golden files are available)
python3 tests/test_golden_files.py

# Add your own golden files
mkdir tests/golden_files/YOUR_DEAL_NAME
# Add input_spec.json, expected_cashflows.csv, expected_balances.csv
# See tests/golden_files/README.md for details
```

## Continuous Integration

For CI/CD pipelines:

```bash
# Exit on first failure
set -e

# Run all critical tests
python3 test_net_wac_cap.py
python3 test_trigger_cure.py
python3 test_loan_schema.py
python3 test_phase1_on_real_deal.py
python3 test_industry_grade_fixes.py

echo "✅ All critical tests passed - ready for deployment"
```

## Performance Benchmarks

### Baseline System
- **CPU:** Modern x86_64
- **Python:** 3.10+
- **Pool Size:** 1000 loans

### Expected Runtimes
- Caching (cold): ~2000ms per calculation
- Caching (warm): ~1ms per calculation
- Iterative Solver: 3-5 iterations, <100ms per period
- Loan-Level Model: ~200ms per period (1000 loans)
- Rep-Line Model: ~5ms per period

---

*Last Updated: January 29, 2026*  
*Phase 1 Version: 1.0*
