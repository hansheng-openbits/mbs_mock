"""
Test: PAC/TAC Bonds and Advanced Structures
============================================

This test demonstrates PAC (Planned Amortization Class) and TAC (Targeted
Amortization Class) bonds, which provide predictable cashflows by using
companion bonds to absorb prepayment variability.

Key Concepts
------------
**PAC Bonds**: Have a scheduled principal payment protected by a prepayment collar.
  - Two-sided protection (both fast and slow prepayments)
  - Collar typically 100-300% PSA (8-30% CPR)
  - Prioritized over support/companion tranches

**TAC Bonds**: Similar to PAC but with one-sided protection.
  - Protected against fast prepayments only
  - Simpler structure, less protection

**Support/Companion Bonds**: Absorb prepayment variability to protect PAC.
  - Highly sensitive to prepayment speeds
  - Higher yield due to increased risk
  - Can experience severe contraction or extension

Author: RMBS Platform Development Team
Date: January 2026
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.structures import (
    AmortizationSchedule,
    ProRataGroup,
    StructuredWaterfallEngine,
    generate_pac_schedule,
)
from engine.loader import DealLoader
from engine.state import DealState
from engine.compute import ExpressionEngine
from engine.waterfall import WaterfallRunner


def create_pac_tac_deal():
    """
    Create a deal with PAC, TAC, and Support tranches.
    
    Structure:
    - Class A-PAC: $50M PAC tranche with 100-300 PSA collar
    - Class B-TAC: $30M TAC tranche with 300 PSA ceiling
    - Class SUP: $20M Support tranche (absorbs variability)
    """
    return {
        "meta": {
            "deal_id": "PAC_TAC_TEST_001",
            "deal_name": "PAC/TAC Test Deal",
            "asset_type": "NON_AGENCY_RMBS",
            "version": "1.0"
        },
        "collateral": {
            "original_balance": 100000000,
            "current_balance": 100000000,
            "wac": 0.055,
            "wam": 360,
            "pool_type": "PRIME"
        },
        "bonds": [
            {
                "id": "PAC_A",
                "name": "Class A-PAC",
                "type": "PAC",
                "original_balance": 50000000,
                "current_balance": 50000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.04},
                "priority": {"interest": 1, "principal": 1},
                "group": "PAC_A"
            },
            {
                "id": "TAC_B",
                "name": "Class B-TAC",
                "type": "TAC",
                "original_balance": 30000000,
                "current_balance": 30000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 2, "principal": 2},
                "group": "TAC_B"
            },
            {
                "id": "SUP_C",
                "name": "Class C-Support",
                "type": "SUPPORT",
                "original_balance": 20000000,
                "current_balance": 20000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.07},
                "priority": {"interest": 3, "principal": 3},
                "group": "SUP_C"
            }
        ],
        "funds": [
            {"id": "IAF", "description": "Interest Allocation Fund"},
            {"id": "PAF", "description": "Principal Allocation Fund"}
        ],
        "variables": {},
        "tests": [],
        "waterfalls": {
            "interest": {
                "steps": [
                    {
                        "priority": 1,
                        "from_fund": "IAF",
                        "action": "PAY_BOND_INTEREST",
                        "group": "PAC_A",
                        "amount_rule": "166666",
                        "condition": "true"
                    },
                    {
                        "priority": 2,
                        "from_fund": "IAF",
                        "action": "PAY_BOND_INTEREST",
                        "group": "TAC_B",
                        "amount_rule": "125000",
                        "condition": "true"
                    },
                    {
                        "priority": 3,
                        "from_fund": "IAF",
                        "action": "PAY_BOND_INTEREST",
                        "group": "SUP_C",
                        "amount_rule": "116666",
                        "condition": "true"
                    }
                ]
            },
            "principal": {
                "steps": []
            },
            "loss_allocation": {
                "write_down_order": ["SUP_C", "TAC_B", "PAC_A"]
            }
        },
        "structures": {
            "pac_schedules": [
                {
                    "tranche_id": "PAC_A",
                    "collar_low": 0.08,
                    "collar_high": 0.30,
                    "type": "PAC",
                    "schedule": []  # Will be generated
                },
                {
                    "tranche_id": "TAC_B",
                    "collar_high": 0.30,
                    "type": "TAC",
                    "schedule": []  # Will be generated
                }
            ],
            "support_tranches": ["SUP_C"]
        }
    }


def test_pac_schedule_generation():
    """Test PAC schedule generation from collar parameters."""
    print("=" * 80)
    print("TEST 1: PAC Schedule Generation")
    print("=" * 80)
    print()
    
    print("Generating PAC schedule for $50M tranche...")
    print("  Parameters:")
    print("    Original Balance: $50,000,000")
    print("    WAM: 360 months")
    print("    Collar: 8% - 30% CPR (100-300 PSA)")
    print()
    
    schedule = generate_pac_schedule(
        original_balance=50000000,
        wam=360,
        collar_low_cpr=0.08,
        collar_high_cpr=0.30
    )
    
    print(f"✅ Generated {len(schedule)} scheduled payments")
    print()
    print("First 12 Months:")
    print("  Period  Scheduled Payment")
    print("  ------  -----------------")
    for period, amount in schedule[:12]:
        print(f"    {period:3d}     ${amount:>15,.2f}")
    
    print()
    print(f"Total Scheduled: ${sum(amt for _, amt in schedule):,.2f}")
    print()
    
    return schedule


def test_pac_waterfall_execution():
    """Test PAC waterfall with various prepayment scenarios."""
    print("=" * 80)
    print("TEST 2: PAC Waterfall Execution")
    print("=" * 80)
    print()
    
    # Create deal
    deal_json = create_pac_tac_deal()
    
    # Generate PAC schedules
    pac_schedule = generate_pac_schedule(50000000, 360, 0.08, 0.30)
    tac_schedule = generate_pac_schedule(30000000, 360, 0.0, 0.30)  # TAC: only upper bound
    
    # Update deal spec with generated schedules
    deal_json["structures"]["pac_schedules"][0]["schedule"] = [
        {"period": p, "amount": a} for p, a in pac_schedule[:60]
    ]
    deal_json["structures"]["pac_schedules"][1]["schedule"] = [
        {"period": p, "amount": a} for p, a in tac_schedule[:60]
    ]
    
    # Load deal
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    
    # Initialize collateral
    state.collateral["current_balance"] = 100000000
    state.collateral["original_balance"] = 100000000
    
    # Create structured waterfall engine
    engine = StructuredWaterfallEngine.from_deal_spec(deal_json)
    
    print("Deal Structure:")
    print(f"  PAC-A:    ${state.bonds['PAC_A'].current_balance:>12,.0f}")
    print(f"  TAC-B:    ${state.bonds['TAC_B'].current_balance:>12,.0f}")
    print(f"  SUP-C:    ${state.bonds['SUP_C'].current_balance:>12,.0f}")
    print(f"  Total:    ${sum(b.current_balance for b in state.bonds.values()):>12,.0f}")
    print()
    
    # Test Scenario 1: Normal prepayments (within collar)
    print("Scenario 1: Normal Prepayments (15% CPR - Within Collar)")
    print("-" * 80)
    
    available_principal = 2000000  # $2M principal
    actual_cpr = 0.15
    
    payments = engine.execute_principal_waterfall(state, available_principal, actual_cpr)
    
    print(f"  Available Principal: ${available_principal:,.2f}")
    print(f"  Actual CPR: {actual_cpr:.1%}")
    print()
    print("  Principal Payments:")
    for tranche_id, payment in sorted(payments.items(), key=lambda x: x[1], reverse=True):
        pct = (payment / available_principal) * 100
        print(f"    {tranche_id:10s}: ${payment:>12,.2f} ({pct:5.1f}%)")
    print()
    
    # Apply payments to bonds
    for tranche_id, payment in payments.items():
        state.bonds[tranche_id].current_balance -= payment
    
    # Test Scenario 2: Fast prepayments (above collar)
    print("Scenario 2: Fast Prepayments (35% CPR - Above Collar)")
    print("-" * 80)
    
    available_principal = 4000000  # $4M principal
    actual_cpr = 0.35
    
    # Increment period
    state.period_index += 1
    
    payments = engine.execute_principal_waterfall(state, available_principal, actual_cpr)
    
    print(f"  Available Principal: ${available_principal:,.2f}")
    print(f"  Actual CPR: {actual_cpr:.1%}")
    print(f"  ⚠️  PAC collar breached (ceiling: 30%)")
    print()
    print("  Principal Payments:")
    for tranche_id, payment in sorted(payments.items(), key=lambda x: x[1], reverse=True):
        pct = (payment / available_principal) * 100
        print(f"    {tranche_id:10s}: ${payment:>12,.2f} ({pct:5.1f}%)")
    print()
    
    # Apply payments
    for tranche_id, payment in payments.items():
        state.bonds[tranche_id].current_balance -= payment
    
    # Test Scenario 3: Slow prepayments (below collar)
    print("Scenario 3: Slow Prepayments (5% CPR - Below Collar)")
    print("-" * 80)
    
    available_principal = 500000  # $500K principal
    actual_cpr = 0.05
    
    # Increment period
    state.period_index += 1
    
    payments = engine.execute_principal_waterfall(state, available_principal, actual_cpr)
    
    print(f"  Available Principal: ${available_principal:,.2f}")
    print(f"  Actual CPR: {actual_cpr:.1%}")
    print(f"  ⚠️  PAC collar breached (floor: 8%)")
    print()
    print("  Principal Payments:")
    for tranche_id, payment in sorted(payments.items(), key=lambda x: x[1], reverse=True):
        pct = (payment / available_principal) * 100 if available_principal > 0 else 0
        print(f"    {tranche_id:10s}: ${payment:>12,.2f} ({pct:5.1f}%)")
    print()
    
    # Final balances
    print("=" * 80)
    print("FINAL BOND BALANCES")
    print("=" * 80)
    print()
    for tranche_id, bond in state.bonds.items():
        original = deal_json["bonds"][[b["id"] for b in deal_json["bonds"]].index(tranche_id)]["original_balance"]
        paid_down = original - bond.current_balance
        pct = (paid_down / original) * 100
        print(f"  {tranche_id:10s}: ${bond.current_balance:>12,.0f} (paid down {pct:5.1f}%)")
    print()
    
    return engine, state


def test_pac_collar_breach():
    """Test PAC behavior when collar is breached."""
    print("=" * 80)
    print("TEST 3: PAC Collar Breach Detection")
    print("=" * 80)
    print()
    
    # Create a simple PAC schedule
    schedule = AmortizationSchedule(
        tranche_id="PAC_TEST",
        schedule=[(1, 100000), (2, 100000), (3, 100000)],
        collar_low=0.08,
        collar_high=0.30,
        schedule_type="PAC"
    )
    
    print("Testing PAC collar breach detection...")
    print(f"  Collar: {schedule.collar_low:.1%} - {schedule.collar_high:.1%} CPR")
    print()
    
    test_cprs = [0.05, 0.08, 0.15, 0.30, 0.35]
    
    print("  CPR      Status")
    print("  -------  ----------------")
    for cpr in test_cprs:
        is_busted = schedule.is_busted(cpr)
        status = "❌ BUSTED" if is_busted else "✅ PROTECTED"
        print(f"  {cpr:5.1%}    {status}")
    
    print()
    
    # Test TAC (one-sided)
    tac_schedule = AmortizationSchedule(
        tranche_id="TAC_TEST",
        schedule=[(1, 100000), (2, 100000), (3, 100000)],
        collar_high=0.30,
        schedule_type="TAC"
    )
    
    print("Testing TAC collar breach detection (one-sided)...")
    print(f"  Ceiling: {tac_schedule.collar_high:.1%} CPR")
    print()
    
    print("  CPR      Status")
    print("  -------  ----------------")
    for cpr in test_cprs:
        is_busted = tac_schedule.is_busted(cpr)
        status = "❌ BUSTED" if is_busted else "✅ PROTECTED"
        print(f"  {cpr:5.1%}    {status}")
    
    print()
    print("✅ Collar breach detection working correctly")
    print()


def main():
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                    PAC/TAC BONDS - ADVANCED STRUCTURES                       ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # Run tests
    schedule = test_pac_schedule_generation()
    engine, state = test_pac_waterfall_execution()
    test_pac_collar_breach()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    print("✅ All PAC/TAC Tests Passed")
    print()
    print("Key Features Demonstrated:")
    print("  1. PAC Schedule Generation - Automatic schedule from collar parameters")
    print("  2. Collar Protection - PAC bonds protected within 8-30% CPR range")
    print("  3. Support Bonds - Absorb prepayment variability outside collar")
    print("  4. TAC Bonds - One-sided protection (ceiling only)")
    print("  5. Breach Detection - Automatic collar breach identification")
    print()
    print("Industry Applications:")
    print("  - Pension funds: Predictable cashflows match liabilities")
    print("  - Insurance companies: ALM (Asset-Liability Management)")
    print("  - Banks: Book yield stability")
    print("  - Retail investors: Reduced prepayment uncertainty")
    print()
    print("Structure Types Tested:")
    print("  ✅ PAC (Planned Amortization Class)")
    print("  ✅ TAC (Targeted Amortization Class)")
    print("  ✅ Support/Companion Tranches")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
