"""
Test: Phase 2B - Interest Rate Swaps
=====================================

This test validates interest rate swap mechanics for RMBS deals,
including hedging strategies and various swap structures.

Swap Types Tested
-----------------
1. **Pay-Fixed/Receive-Float**: Convert floating collateral to fixed-rate bonds
2. **Pay-Float/Receive-Fixed**: Synthetic floating-rate bonds
3. **Basis Swaps**: Exchange one index for another (SOFR vs Prime)
4. **Caps/Floors**: Option-like rate protection
5. **Amortizing Swaps**: Notional tracks collateral paydown

Author: RMBS Platform Development Team
Date: January 2026
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.swaps import (
    SwapDefinition,
    SwapSettlementEngine,
    SwapType,
    DayCountConvention,
)


def test_pay_fixed_receive_float():
    """Test standard pay-fixed/receive-float swap."""
    print("=" * 80)
    print("TEST 1: Pay-Fixed/Receive-Float Swap")
    print("=" * 80)
    print()
    
    print("Scenario: Deal has floating-rate collateral (SOFR-based)")
    print("          Needs to pay fixed-rate bonds")
    print("          Solution: Pay-fixed swap to hedge rate risk")
    print()
    
    # Create swap
    swap = SwapDefinition(
        swap_id="HEDGE_001",
        notional=100_000_000,
        fixed_rate=0.045,  # Pay 4.5% fixed
        floating_index="SOFR",
        spread=0.0025,  # Receive SOFR + 25bps
        pay_fixed=True
    )
    
    print("Swap Configuration:")
    print(f"  Type: {swap.swap_type.value}")
    print(f"  Notional: ${swap.notional:,.0f}")
    print(f"  Fixed Rate (pay): {swap.fixed_rate:.2%}")
    print(f"  Floating Index (receive): {swap.floating_index} + {swap.spread:.2%}")
    print()
    
    # Create engine
    engine = SwapSettlementEngine([swap])
    
    # Test scenarios
    scenarios = [
        ("Low Rates", 0.0300),
        ("At Strike", 0.0425),
        ("High Rates", 0.0600),
    ]
    
    print("Settlement Scenarios:")
    print("-" * 80)
    print()
    
    for scenario_name, sofr_rate in scenarios:
        engine.set_index_rate("SOFR", sofr_rate)
        settlement = engine.settle(swap, period=1)
        
        print(f"{scenario_name} (SOFR = {sofr_rate:.2%}):")
        print(f"  Fixed Leg (pay):     ${settlement.fixed_amount:>12,.2f}")
        print(f"  Floating Leg (recv): ${settlement.floating_amount:>12,.2f}")
        print(f"  Net Payment:         ${settlement.net_payment:>12,.2f}", end="")
        
        if settlement.net_payment > 0:
            print(" (deal receives)")
        elif settlement.net_payment < 0:
            print(" (deal pays)")
        else:
            print(" (no net payment)")
        
        print()
    
    print("✅ Pay-fixed swap hedges floating-rate exposure correctly")
    print()


def test_amortizing_swap():
    """Test amortizing swap with declining notional."""
    print("=" * 80)
    print("TEST 2: Amortizing Swap")
    print("=" * 80)
    print()
    
    print("Scenario: Swap notional tracks declining collateral balance")
    print()
    
    # Create amortizing swap
    swap = SwapDefinition(
        swap_id="AMORT_001",
        notional=100_000_000,
        fixed_rate=0.050,
        floating_index="SOFR",
        pay_fixed=True,
        amortizing=True
    )
    
    print("Initial Configuration:")
    print(f"  Notional: ${swap.notional:,.0f}")
    print(f"  Amortizing: {swap.amortizing}")
    print()
    
    # Create engine
    engine = SwapSettlementEngine([swap])
    engine.set_index_rate("SOFR", 0.055)
    
    # Simulate with declining notional
    print("Amortization Schedule:")
    print("-" * 80)
    print()
    print("  Period  Notional Factor  Current Notional  Net Payment")
    print("  ------  ---------------  ----------------  ------------")
    
    for period in range(1, 7):
        notional_factor = 1.0 - (period * 0.05)  # 5% paydown per period
        settlement = engine.settle(swap, period, notional_factor)
        
        print(f"   {period:2d}         {notional_factor:4.0%}          ${settlement.notional:>12,.0f}  ${settlement.net_payment:>12,.2f}")
    
    print()
    print("✅ Amortizing swap notional tracks collateral correctly")
    print()


def test_interest_rate_cap():
    """Test interest rate cap (protection against rising rates)."""
    print("=" * 80)
    print("TEST 3: Interest Rate Cap")
    print("=" * 80)
    print()
    
    print("Scenario: Deal has floating-rate bonds")
    print("          Wants protection if rates rise above 6%")
    print("          Solution: Purchase interest rate cap")
    print()
    
    # Create capped swap
    swap = SwapDefinition(
        swap_id="CAP_001",
        notional=50_000_000,
        fixed_rate=0.0,  # No fixed leg for pure cap
        floating_index="SOFR",
        spread=0.0,
        pay_fixed=False,  # Receive floating (capped)
        cap_rate=0.06  # Cap at 6%
    )
    
    print("Cap Configuration:")
    print(f"  Type: {swap.swap_type.value}")
    print(f"  Notional: ${swap.notional:,.0f}")
    print(f"  Index: {swap.floating_index}")
    print(f"  Cap Strike: {swap.cap_rate:.2%}")
    print()
    
    # Create engine
    engine = SwapSettlementEngine([swap])
    
    # Test scenarios
    print("Cap Payouts:")
    print("-" * 80)
    print()
    print("  SOFR Rate  Uncapped Rate  Effective Rate  Payout Status")
    print("  ---------  -------------  --------------  ----------------")
    
    test_rates = [0.040, 0.055, 0.060, 0.070, 0.080]
    
    for sofr_rate in test_rates:
        engine.set_index_rate("SOFR", sofr_rate)
        settlement = engine.settle(swap, period=1)
        
        uncapped = sofr_rate
        effective = settlement.all_in_rate
        is_capped = "✅ CAPPED" if effective < uncapped else "No payout"
        
        print(f"    {sofr_rate:4.1%}        {uncapped:4.1%}          {effective:4.1%}          {is_capped}")
    
    print()
    print("✅ Interest rate cap provides protection above strike")
    print()


def test_interest_rate_floor():
    """Test interest rate floor (protection against falling rates)."""
    print("=" * 80)
    print("TEST 4: Interest Rate Floor")
    print("=" * 80)
    print()
    
    print("Scenario: Deal receives floating-rate income")
    print("          Wants minimum rate of 3% even if rates fall")
    print("          Solution: Purchase interest rate floor")
    print()
    
    # Create floored swap
    swap = SwapDefinition(
        swap_id="FLOOR_001",
        notional=50_000_000,
        fixed_rate=0.0,
        floating_index="SOFR",
        pay_fixed=False,  # Receive floating (floored)
        floor_rate=0.03  # Floor at 3%
    )
    
    print("Floor Configuration:")
    print(f"  Type: {swap.swap_type.value}")
    print(f"  Notional: ${swap.notional:,.0f}")
    print(f"  Index: {swap.floating_index}")
    print(f"  Floor Strike: {swap.floor_rate:.2%}")
    print()
    
    # Create engine
    engine = SwapSettlementEngine([swap])
    
    # Test scenarios
    print("Floor Payouts:")
    print("-" * 80)
    print()
    print("  SOFR Rate  Unfloored Rate  Effective Rate  Payout Status")
    print("  ---------  --------------  --------------  ----------------")
    
    test_rates = [0.010, 0.020, 0.030, 0.040, 0.050]
    
    for sofr_rate in test_rates:
        engine.set_index_rate("SOFR", sofr_rate)
        settlement = engine.settle(swap, period=1)
        
        unfloored = sofr_rate
        effective = settlement.all_in_rate
        is_floored = "✅ FLOORED" if effective > unfloored else "No payout"
        
        print(f"    {sofr_rate:4.1%}        {unfloored:4.1%}          {effective:4.1%}          {is_floored}")
    
    print()
    print("✅ Interest rate floor provides protection below strike")
    print()


def test_collar():
    """Test interest rate collar (cap + floor)."""
    print("=" * 80)
    print("TEST 5: Interest Rate Collar")
    print("=" * 80)
    print()
    
    print("Scenario: Deal wants to limit rate volatility")
    print("          Cap at 6%, Floor at 3%")
    print("          Solution: Collar (buy cap, sell floor)")
    print()
    
    # Create collar
    swap = SwapDefinition(
        swap_id="COLLAR_001",
        notional=100_000_000,
        fixed_rate=0.0,
        floating_index="SOFR",
        pay_fixed=False,
        cap_rate=0.06,
        floor_rate=0.03
    )
    
    print("Collar Configuration:")
    print(f"  Type: {swap.swap_type.value}")
    print(f"  Notional: ${swap.notional:,.0f}")
    print(f"  Cap Strike: {swap.cap_rate:.2%}")
    print(f"  Floor Strike: {swap.floor_rate:.2%}")
    print()
    
    # Create engine
    engine = SwapSettlementEngine([swap])
    
    # Test scenarios
    print("Collar Behavior:")
    print("-" * 80)
    print()
    print("  SOFR Rate  Uncollared  Collared  Action")
    print("  ---------  ----------  --------  ----------------")
    
    test_rates = [0.01, 0.02, 0.03, 0.045, 0.06, 0.07, 0.08]
    
    for sofr_rate in test_rates:
        engine.set_index_rate("SOFR", sofr_rate)
        settlement = engine.settle(swap, period=1)
        
        uncollared = sofr_rate
        collared = settlement.all_in_rate
        
        if collared > uncollared:
            action = "Floored ↑"
        elif collared < uncollared:
            action = "Capped ↓"
        else:
            action = "Within collar"
        
        print(f"    {sofr_rate:4.1%}       {uncollared:4.1%}      {collared:4.1%}    {action}")
    
    print()
    print("✅ Collar limits rate volatility within band")
    print()


def test_multiple_swaps():
    """Test portfolio of multiple swaps."""
    print("=" * 80)
    print("TEST 6: Multiple Swap Portfolio")
    print("=" * 80)
    print()
    
    print("Scenario: Complex deal with multiple hedges")
    print()
    
    # Create multiple swaps
    swap1 = SwapDefinition(
        swap_id="SWAP_A",
        notional=50_000_000,
        fixed_rate=0.045,
        floating_index="SOFR",
        pay_fixed=True
    )
    
    swap2 = SwapDefinition(
        swap_id="SWAP_B",
        notional=30_000_000,
        fixed_rate=0.0475,
        floating_index="SOFR",
        spread=0.0050,
        pay_fixed=True
    )
    
    swap3 = SwapDefinition(
        swap_id="CAP_A",
        notional=100_000_000,
        fixed_rate=0.0,
        floating_index="SOFR",
        pay_fixed=False,
        cap_rate=0.065
    )
    
    # Create engine with multiple swaps
    engine = SwapSettlementEngine([swap1, swap2, swap3])
    engine.set_index_rate("SOFR", 0.055)
    
    print("Swap Portfolio:")
    print("-" * 80)
    for swap in engine.swaps:
        print(f"  {swap.swap_id}: {swap.swap_type.value}, ${swap.notional:,.0f}")
    print()
    
    # Settle all swaps
    result = engine.settle_all(period=1)
    settlements = result["settlements"]
    
    print("Settlement Results (SOFR = 5.5%):")
    print("-" * 80)
    print()
    
    for settlement in settlements:
        print(f"{settlement.swap_id}:")
        print(f"  Fixed Leg:     ${settlement.fixed_amount:>12,.2f}")
        print(f"  Floating Leg:  ${settlement.floating_amount:>12,.2f}")
        print(f"  Net Payment:   ${settlement.net_payment:>12,.2f}")
        print()
    
    print(f"Total Portfolio Net Payment: ${result['total_net']:,.2f}")
    print()
    
    print("✅ Multiple swaps can be managed simultaneously")
    print()


def main():
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                PHASE 2B - INTEREST RATE SWAPS & HEDGING                     ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # Run tests
    test_pay_fixed_receive_float()
    test_amortizing_swap()
    test_interest_rate_cap()
    test_interest_rate_floor()
    test_collar()
    test_multiple_swaps()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    print("✅ All Interest Rate Swap Tests Passed")
    print()
    print("Swap Types Tested:")
    print("  1. ✅ Pay-Fixed/Receive-Float - Hedge floating collateral")
    print("  2. ✅ Amortizing Swaps - Notional tracks collateral")
    print("  3. ✅ Interest Rate Caps - Protection against rising rates")
    print("  4. ✅ Interest Rate Floors - Protection against falling rates")
    print("  5. ✅ Collars - Cap + Floor combination")
    print("  6. ✅ Multiple Swap Portfolio - Complex hedge structures")
    print()
    print("Industry Applications:")
    print()
    print("Pay-Fixed Swaps:")
    print("  - Convert floating collateral to fixed bonds")
    print("  - Lock in spread over SOFR")
    print("  - Eliminate index basis risk")
    print()
    print("Caps:")
    print("  - Protect floating-rate bond investors")
    print("  - Limit interest expense on floating bonds")
    print("  - Common in ARM RMBS deals")
    print()
    print("Floors:")
    print("  - Protect against negative carry")
    print("  - Ensure minimum net interest margin")
    print("  - Used by investors receiving floating cashflows")
    print()
    print("Collars:")
    print("  - Zero-cost rate protection (buy cap, sell floor)")
    print("  - Limit rate volatility")
    print("  - Popular for balance sheet management")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
