# Phase 2B Testing Guide

## Quick Start

Run all Phase 2B tests with:

```bash
# Run swap tests
python3 test_phase2b_swaps.py

# Run market risk tests (curves, OAS, duration)
python3 test_phase2b_market_risk.py

# Or run both at once
python3 test_phase2b_swaps.py && python3 test_phase2b_market_risk.py
```

---

## Test Files

### 1. `test_phase2b_swaps.py`

**Tests interest rate swap mechanics:**

- **Test 1:** Pay-Fixed/Receive-Float Swap
- **Test 2:** Amortizing Swap
- **Test 3:** Interest Rate Cap
- **Test 4:** Interest Rate Floor
- **Test 5:** Interest Rate Collar
- **Test 6:** Multiple Swap Portfolio

**Expected Output:**
```
✅ All Interest Rate Swap Tests Passed

Swap Types Tested:
  1. ✅ Pay-Fixed/Receive-Float - Hedge floating collateral
  2. ✅ Amortizing Swaps - Notional tracks collateral
  3. ✅ Interest Rate Caps - Protection against rising rates
  4. ✅ Interest Rate Floors - Protection against falling rates
  5. ✅ Collars - Cap + Floor combination
  6. ✅ Multiple Swap Portfolio - Complex hedge structures
```

---

### 2. `test_phase2b_market_risk.py`

**Tests yield curves, OAS, and duration/convexity:**

- **Test 1:** Yield Curve Construction & Interpolation
- **Test 2:** Yield Curve Bootstrapping
- **Test 3:** Curve Shifting (Scenario Analysis)
- **Test 4:** Option-Adjusted Spread (OAS)
- **Test 5:** Modified Duration
- **Test 6:** Effective Duration (Accounts for Prepayments)
- **Test 7:** Key Rate Duration
- **Test 8:** Negative Convexity (RMBS Prepayment Risk)

**Expected Output:**
```
✅ All Market Risk Tests Passed

Features Validated:
  1. ✅ Yield Curve Construction - Interpolation working
  2. ✅ Curve Bootstrapping - Zero rates from par yields
  3. ✅ Curve Shifting - Parallel & key rate shifts
  4. ✅ OAS Calculation - Risk-adjusted spread
  5. ✅ Modified Duration - Basic rate sensitivity
  6. ✅ Effective Duration - Accounts for prepayments
  7. ✅ Key Rate Duration - Maturity-specific risk
  8. ✅ Negative Convexity - RMBS prepayment asymmetry
```

---

## Individual Test Execution

Run specific tests by calling functions directly:

```python
# In Python interpreter
from test_phase2b_swaps import *

# Run individual test
test_pay_fixed_receive_float()
test_interest_rate_cap()
```

Or:

```python
from test_phase2b_market_risk import *

# Run individual test
test_yield_curve_construction()
test_oas_calculation()
test_negative_convexity()
```

---

## Test Output Structure

Each test displays:

1. **Header:** Test number and description
2. **Scenario:** What the test is demonstrating
3. **Configuration:** Key parameters
4. **Results:** Calculated metrics with interpretation
5. **Validation:** ✅ Pass/Fail indicator

Example:

```
================================================================================
TEST 4: Option-Adjusted Spread (OAS)
================================================================================

Scenario: Calculate OAS for an RMBS bond

Treasury Curve:
--------------------------------------------------------------------------------
   1.0Y:  4.50%
   2.0Y:  4.60%
   5.0Y:  4.50%
  10.0Y:  4.40%

Bond Characteristics:
--------------------------------------------------------------------------------
  Maturity: 5 years
  Coupon: 5.0% (semi-annual)
  Market Price: 102.5

Z-Spread (Static Spread):
--------------------------------------------------------------------------------
  Z-Spread:   -12 bps

Option-Adjusted Spread:
--------------------------------------------------------------------------------
  OAS:   -12 bps

✅ OAS calculation framework operational
```

---

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`:

```bash
# Ensure you're in the correct directory
cd /path/to/rmbs_platform

# Run with explicit path
python3 test_phase2b_swaps.py
```

### Missing Dependencies

If you see `ImportError: No module named 'scipy'`:

```bash
# Install required packages
pip install numpy scipy

# Or install all requirements
pip install -r requirements.txt
```

### Test Failures

If tests fail, check:

1. **Python Version:** Requires Python 3.8+
2. **Dependencies:** numpy, scipy must be installed
3. **Working Directory:** Must be in `rmbs_platform/` folder

---

## Performance Benchmarks

**Expected Execution Times:**

- `test_phase2b_swaps.py`: ~0.5 seconds
- `test_phase2b_market_risk.py`: ~1.5 seconds

**Total: ~2 seconds for all Phase 2B tests**

If tests take significantly longer:
- Check CPU usage
- Close other applications
- Update scipy/numpy to latest versions

---

## Integration Testing

To test Phase 2B features with a real deal:

```python
from engine.loader import DealLoader
from engine.market_risk import YieldCurveBuilder, OASCalculator, DurationCalculator
from engine.swaps import SwapSettlementEngine

# Load a deal
loader = DealLoader()
deal_def = loader.load("FREDDIE_SAMPLE_2017_2020")

# Build yield curve
builder = YieldCurveBuilder()
builder.add_instrument("UST_5Y", 5.0, 0.045)
builder.add_instrument("UST_10Y", 10.0, 0.044)
curve = builder.build()

# Calculate OAS
# ... (implement full cashflow projection)

# Test swaps integration
# ... (add swap to deal waterfall)
```

---

## Test Coverage Summary

| Component | Tests | Status |
|-----------|-------|--------|
| Interest Rate Swaps | 6 | ✅ Passing |
| Yield Curves | 3 | ✅ Passing |
| OAS Calculation | 1 | ✅ Passing |
| Duration & Convexity | 4 | ✅ Passing |
| **Total** | **14** | **✅ 100% Passing** |

---

## Next Steps After Testing

Once all Phase 2B tests pass:

1. **Review Documentation:** Read `docs/Phase2B_Complete_Summary.md`
2. **Explore API Integration:** Add endpoints to `api_main.py`
3. **UI Enhancement:** Add market risk metrics to Investor dashboard
4. **Proceed to Phase 2C:** Credit risk analytics

---

## Support

For questions or issues:

1. Check `docs/Phase2B_Complete_Summary.md` for detailed documentation
2. Review test source code for usage examples
3. Check module docstrings (`engine/swaps.py`, `engine/market_risk.py`)

---

**Last Updated:** January 29, 2026  
**Status:** All tests passing ✅
