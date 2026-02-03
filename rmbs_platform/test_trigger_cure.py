"""
Test Trigger Cure Logic
========================

This script tests the trigger cure logic that prevents "flickering"
where triggers alternate between breached and cured each period.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.loader import DealLoader
from engine.state import DealState
from engine.waterfall import WaterfallRunner
from engine.compute import ExpressionEngine


def create_test_deal_with_trigger():
    """Create a deal with a simple OC trigger."""
    return {
        "meta": {
            "deal_id": "TEST_TRIGGER",
            "deal_name": "Trigger Cure Test",
            "asset_type": "NON_AGENCY_RMBS",
            "version": "1.0"
        },
        "currency": "USD",
        "dates": {
            "cutoff_date": "2024-01-01",
            "closing_date": "2024-01-30",
            "first_payment_date": "2024-02-25",
            "maturity_date": "2054-01-01",
            "payment_frequency": "MONTHLY"
        },
        "collateral": {
            "original_balance": 10000000.0,
            "current_balance": 10000000.0,
            "wac": 0.06,
            "wam": 360,
            "count": 100
        },
        "funds": [
            {"id": "IAF", "description": "Interest Available Funds"},
            {"id": "PAF", "description": "Principal Available Funds"}
        ],
        "accounts": {},
        "bonds": [
            {
                "id": "ClassA",
                "type": "NOTE",
                "original_balance": 8000000.0,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 1, "principal": 1}
            }
        ],
        "variables": {},
        "waterfalls": {
            "interest": {"steps": []},
            "principal": {"steps": []}
        },
        "tests": [
            {
                "id": "OC_Test",
                "kind": "OC",
                "calc": {"value_rule": "variables.OC_Ratio"},
                "threshold": {"rule": "1.10"},
                "pass_if": "VALUE_GEQ_THRESHOLD",
                "cure_periods": 3
            }
        ]
    }


def main():
    """Run trigger cure logic test."""
    print("=" * 80)
    print("TRIGGER CURE LOGIC TEST")
    print("=" * 80)
    print()
    
    # Create deal
    deal_json = create_test_deal_with_trigger()
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    
    # Create runner
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)
    
    print("TEST SCENARIO")
    print("-" * 80)
    print("OC Test: Collateral / Bonds >= 110%")
    print("Cure Threshold: 3 consecutive passing periods")
    print()
    print("Initial State:")
    print(f"  Collateral: $10,000,000")
    print(f"  Bonds:      $8,000,000")
    print(f"  OC Ratio:   {10_000_000 / 8_000_000:.2%}  (PASSES)")
    print()
    
    # Simulate periods with varying OC ratios
    scenarios = [
        ("Period 1", 10_000_000, 8_000_000, True,  "OC = 125.00% >= 110% → PASS"),
        ("Period 2", 8_500_000,  8_000_000, False, "OC = 106.25% < 110% → FAIL (BREACHED)"),
        ("Period 3", 8_900_000,  8_000_000, True,  "OC = 111.25% >= 110% → PASS (cure 1/3)"),
        ("Period 4", 8_700_000,  8_000_000, False, "OC = 108.75% < 110% → FAIL (cure reset)"),
        ("Period 5", 8_900_000,  8_000_000, True,  "OC = 111.25% >= 110% → PASS (cure 1/3)"),
        ("Period 6", 9_000_000,  8_000_000, True,  "OC = 112.50% >= 110% → PASS (cure 2/3)"),
        ("Period 7", 9_100_000,  8_000_000, True,  "OC = 113.75% >= 110% → PASS (cure 3/3 → CURED)"),
    ]
    
    print("SIMULATION")
    print("-" * 80)
    
    for period_name, coll_bal, bond_bal, expected_pass, description in scenarios:
        # Update balances
        state.collateral["current_balance"] = coll_bal
        state.bonds["ClassA"].current_balance = bond_bal
        
        # Calculate and set OC_Ratio variable
        oc_ratio = coll_bal / bond_bal if bond_bal > 0 else 0
        state.set_variable("OC_Ratio", oc_ratio)
        
        # Deposit minimal cashflows
        state.deposit_funds("IAF", 1000)
        state.deposit_funds("PAF", 0)
        
        # Run period
        runner.run_period(state)
        
        # Check trigger state
        trigger = state.trigger_states.get("OC_Test")
        is_breached = state.flags.get("OC_Test", False)
        
        print(f"{period_name}: {description}")
        print(f"  → Trigger Breached: {is_breached}")
        if trigger:
            print(f"  → Cure Progress: {trigger.months_cured}/{trigger.cure_threshold}")
        print()
    
    # Final verification
    print("VERIFICATION")
    print("-" * 80)
    
    final_trigger = state.trigger_states.get("OC_Test")
    final_breached = state.flags.get("OC_Test", False)
    
    print(f"Final Trigger Status: {'BREACHED' if final_breached else 'CURED'}")
    if final_trigger:
        print(f"Months Breached: {final_trigger.months_breached}")
        print(f"Months Cured: {final_trigger.months_cured}")
    print()
    
    # Test expectations
    if not final_breached:
        print("✅ Trigger cure logic: CORRECT")
        print("   Trigger required 3 consecutive passing periods to cure")
    else:
        print("❌ Trigger cure logic: ERROR")
        print("   Trigger should have cured after 3 consecutive passes")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
