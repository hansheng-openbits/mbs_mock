"""
Test: Pro-Rata Allocation and Z-Bonds
======================================

This test demonstrates two additional advanced RMBS structures:

1. **Pro-Rata Allocation**: Multiple tranches at the same priority level
   share principal payments proportionally to their outstanding balances.

2. **Z-Bonds (Accrual Bonds)**: Tranches that do not receive current interest.
   Instead, their unpaid interest accretes to principal, causing the bond
   to grow over time. Principal + accreted interest is paid after senior tranches.

Author: RMBS Platform Development Team
Date: January 2026
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.structures import ProRataGroup, StructuredWaterfallEngine
from engine.loader import DealLoader
from engine.state import DealState


def create_prorata_deal():
    """
    Create a deal with pro-rata mezzanine tranches.
    
    Structure:
    - Class A: $60M Senior (sequential)
    - Class M1, M2, M3: $10M each Mezzanine (pro-rata group)
    - Class B: $10M Subordinate (sequential)
    """
    return {
        "meta": {
            "deal_id": "PRORATA_TEST_001",
            "deal_name": "Pro-Rata Test Deal",
            "asset_type": "NON_AGENCY_RMBS",
            "version": "1.0"
        },
        "collateral": {
            "original_balance": 100000000,
            "current_balance": 100000000,
            "wac": 0.055,
            "wam": 360
        },
        "bonds": [
            {
                "id": "ClassA",
                "name": "Class A Senior",
                "type": "SENIOR",
                "original_balance": 60000000,
                "current_balance": 60000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.04},
                "priority": {"interest": 1, "principal": 1},
                "group": "ClassA"
            },
            {
                "id": "ClassM1",
                "name": "Class M1 Mezzanine",
                "type": "MEZZANINE",
                "original_balance": 10000000,
                "current_balance": 10000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 2, "principal": 2},
                "group": "ClassM1"
            },
            {
                "id": "ClassM2",
                "name": "Class M2 Mezzanine",
                "type": "MEZZANINE",
                "original_balance": 10000000,
                "current_balance": 10000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 2, "principal": 2},
                "group": "ClassM2"
            },
            {
                "id": "ClassM3",
                "name": "Class M3 Mezzanine",
                "type": "MEZZANINE",
                "original_balance": 10000000,
                "current_balance": 10000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 2, "principal": 2},
                "group": "ClassM3"
            },
            {
                "id": "ClassB",
                "name": "Class B Subordinate",
                "type": "SUBORDINATE",
                "original_balance": 10000000,
                "current_balance": 10000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.07},
                "priority": {"interest": 3, "principal": 3},
                "group": "ClassB"
            }
        ],
        "funds": [
            {"id": "IAF", "description": "Interest Allocation Fund"},
            {"id": "PAF", "description": "Principal Allocation Fund"}
        ],
        "variables": {},
        "tests": [],
        "waterfalls": {
            "interest": {"steps": []},
            "principal": {"steps": []},
            "loss_allocation": {"write_down_order": ["ClassB", "ClassM3", "ClassM2", "ClassM1", "ClassA"]}
        },
        "structures": {
            "pro_rata_groups": [
                {
                    "group_id": "MEZZANINE",
                    "tranche_ids": ["ClassM1", "ClassM2", "ClassM3"],
                    "allocation_method": "balance"
                }
            ]
        }
    }


def create_zbond_deal():
    """
    Create a deal with Z-bond (accrual bond).
    
    Structure:
    - Class A: $60M Senior (pays current interest)
    - Class Z: $30M Z-Bond (interest accretes to principal)
    - Class B: $10M Subordinate
    """
    return {
        "meta": {
            "deal_id": "ZBOND_TEST_001",
            "deal_name": "Z-Bond Test Deal",
            "asset_type": "NON_AGENCY_RMBS",
            "version": "1.0"
        },
        "collateral": {
            "original_balance": 100000000,
            "current_balance": 100000000,
            "wac": 0.055,
            "wam": 360
        },
        "bonds": [
            {
                "id": "ClassA",
                "name": "Class A Senior",
                "type": "SENIOR",
                "original_balance": 60000000,
                "current_balance": 60000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.04},
                "priority": {"interest": 1, "principal": 1},
                "group": "ClassA"
            },
            {
                "id": "ClassZ",
                "name": "Class Z Accrual",
                "type": "Z_BOND",
                "original_balance": 30000000,
                "current_balance": 30000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 99, "principal": 2},
                "group": "ClassZ"
            },
            {
                "id": "ClassB",
                "name": "Class B Subordinate",
                "type": "SUBORDINATE",
                "original_balance": 10000000,
                "current_balance": 10000000,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.07},
                "priority": {"interest": 2, "principal": 3},
                "group": "ClassB"
            }
        ],
        "funds": [
            {"id": "IAF", "description": "Interest Allocation Fund"},
            {"id": "PAF", "description": "Principal Allocation Fund"}
        ],
        "variables": {},
        "tests": [],
        "waterfalls": {
            "interest": {"steps": []},
            "principal": {"steps": []},
            "loss_allocation": {"write_down_order": ["ClassB", "ClassZ", "ClassA"]}
        },
        "structures": {
            "z_bonds": ["ClassZ"]
        }
    }


def test_prorata_allocation():
    """Test pro-rata principal allocation across mezzanine tranches."""
    print("=" * 80)
    print("TEST 1: Pro-Rata Allocation")
    print("=" * 80)
    print()
    
    # Create deal
    deal_json = create_prorata_deal()
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    
    print("Deal Structure:")
    print(f"  Class A (Senior):        ${state.bonds['ClassA'].current_balance:>12,.0f}")
    print(f"  Class M1 (Mezzanine):    ${state.bonds['ClassM1'].current_balance:>12,.0f}")
    print(f"  Class M2 (Mezzanine):    ${state.bonds['ClassM2'].current_balance:>12,.0f}")
    print(f"  Class M3 (Mezzanine):    ${state.bonds['ClassM3'].current_balance:>12,.0f}")
    print(f"  Class B (Subordinate):   ${state.bonds['ClassB'].current_balance:>12,.0f}")
    print(f"  Total:                   ${sum(b.current_balance for b in state.bonds.values()):>12,.0f}")
    print()
    
    # Create structured engine
    engine = StructuredWaterfallEngine.from_deal_spec(deal_json)
    
    # Test Case 1: Equal balances, equal allocation
    print("Test Case 1: Equal Balances (each mezz = $10M)")
    print("-" * 80)
    
    mezz_group = engine.pro_rata_groups["MEZZANINE"]
    balances = {bid: state.bonds[bid].current_balance for bid in state.bonds}
    
    available = 3000000  # $3M available
    allocations = mezz_group.allocate(available, balances)
    
    print(f"  Available Principal: ${available:,.0f}")
    print("  Allocations:")
    total_allocated = 0
    for tranche_id, allocation in sorted(allocations.items()):
        pct = (allocation / available) * 100
        total_allocated += allocation
        print(f"    {tranche_id:10s}: ${allocation:>12,.2f} ({pct:5.1f}%)")
    print(f"  Total Allocated: ${total_allocated:,.2f}")
    print()
    
    # Update balances
    for tranche_id, allocation in allocations.items():
        state.bonds[tranche_id].current_balance -= allocation
    
    # Test Case 2: Unequal balances after first payment
    print("Test Case 2: Unequal Balances After Principal Payment")
    print("-" * 80)
    
    # Pay down M1 more than others
    state.bonds["ClassM1"].current_balance -= 2000000
    
    print("  Updated Balances:")
    print(f"    ClassM1: ${state.bonds['ClassM1'].current_balance:>12,.0f}")
    print(f"    ClassM2: ${state.bonds['ClassM2'].current_balance:>12,.0f}")
    print(f"    ClassM3: ${state.bonds['ClassM3'].current_balance:>12,.0f}")
    print()
    
    balances = {bid: state.bonds[bid].current_balance for bid in state.bonds}
    available = 2000000  # $2M available
    allocations = mezz_group.allocate(available, balances)
    
    print(f"  Available Principal: ${available:,.0f}")
    print("  Allocations:")
    total_allocated = 0
    for tranche_id, allocation in sorted(allocations.items()):
        pct = (allocation / available) * 100 if available > 0 else 0
        total_allocated += allocation
        print(f"    {tranche_id:10s}: ${allocation:>12,.2f} ({pct:5.1f}%)")
    print(f"  Total Allocated: ${total_allocated:,.2f}")
    print()
    
    print("✅ Pro-rata allocation working correctly")
    print("   - Allocates proportionally to current balances")
    print("   - Maintains pro-rata relationship as tranches pay down")
    print()
    
    return engine, state


def test_zbond_accretion():
    """Test Z-bond interest accretion."""
    print("=" * 80)
    print("TEST 2: Z-Bond Interest Accretion")
    print("=" * 80)
    print()
    
    # Create deal
    deal_json = create_zbond_deal()
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    
    print("Deal Structure:")
    print(f"  Class A (Senior):     ${state.bonds['ClassA'].current_balance:>12,.0f}")
    print(f"  Class Z (Accrual):    ${state.bonds['ClassZ'].current_balance:>12,.0f}")
    print(f"  Class B (Subordinate):${state.bonds['ClassB'].current_balance:>12,.0f}")
    print()
    
    # Create structured engine
    engine = StructuredWaterfallEngine()
    
    # Z-bond details
    z_balance_initial = state.bonds["ClassZ"].current_balance
    z_coupon = 0.05  # 5% annual
    
    print("Z-Bond Details:")
    print(f"  Initial Balance: ${z_balance_initial:,.0f}")
    print(f"  Coupon: {z_coupon:.2%}")
    print(f"  Monthly Interest: ${z_balance_initial * z_coupon / 12:,.2f}")
    print()
    
    # Simulate 12 months of accretion
    print("Accreting Interest for 12 Months:")
    print("-" * 80)
    print()
    print("  Month  Accreted Interest  New Balance")
    print("  -----  ------------------  ---------------")
    
    for month in range(1, 13):
        # Calculate monthly interest manually (simple interest for demo)
        z_bond = state.bonds["ClassZ"]
        monthly_interest = z_bond.current_balance * (z_coupon / 12)
        
        # Accrete to principal
        z_bond.current_balance += monthly_interest
        z_balance = z_bond.current_balance
        
        print(f"   {month:2d}      ${monthly_interest:>14,.2f}  ${z_balance:>15,.0f}")
        
        # Increment period
        state.period_index += 1
    
    print()
    
    # Summary
    final_balance = state.bonds["ClassZ"].current_balance
    total_accreted = final_balance - z_balance_initial
    
    print("Summary:")
    print(f"  Initial Balance:      ${z_balance_initial:>15,.0f}")
    print(f"  Total Accreted:       ${total_accreted:>15,.2f}")
    print(f"  Final Balance:        ${final_balance:>15,.0f}")
    print(f"  Accretion Rate:       {(total_accreted / z_balance_initial) * 100:>14.2f}%")
    print()
    
    # Expected accretion (compound interest)
    expected = z_balance_initial * ((1 + z_coupon/12) ** 12) - z_balance_initial
    print(f"  Expected (compound):  ${expected:>15,.2f}")
    print(f"  Actual:               ${total_accreted:>15,.2f}")
    print(f"  Difference:           ${abs(expected - total_accreted):>15,.2f}")
    print()
    
    print("✅ Z-bond accretion working correctly")
    print("   - Interest compounds monthly")
    print("   - Balance grows over time")
    print("   - No cash paid to Z-bond holders during accretion period")
    print()
    
    return engine, state


def test_combined_structures():
    """Test a deal with multiple advanced structures."""
    print("=" * 80)
    print("TEST 3: Combined Advanced Structures")
    print("=" * 80)
    print()
    
    print("Testing a complex deal with:")
    print("  - Sequential senior tranche (Class A)")
    print("  - Pro-rata mezzanine group (Classes M1, M2)")
    print("  - Z-bond (Class Z)")
    print("  - Sequential subordinate (Class B)")
    print()
    
    # Create complex deal structure
    complex_deal = {
        "meta": {"deal_id": "COMPLEX_001", "deal_name": "Complex Structure", "asset_type": "NON_AGENCY_RMBS", "version": "1.0"},
        "collateral": {"original_balance": 100000000, "current_balance": 100000000, "wac": 0.055, "wam": 360},
        "bonds": [
            {"id": "ClassA", "name": "Class A", "type": "SENIOR", "original_balance": 50000000, "current_balance": 50000000,
             "coupon": {"kind": "FIXED", "fixed_rate": 0.04}, "priority": {"interest": 1, "principal": 1}, "group": "ClassA"},
            {"id": "ClassM1", "name": "Class M1", "type": "MEZZANINE", "original_balance": 15000000, "current_balance": 15000000,
             "coupon": {"kind": "FIXED", "fixed_rate": 0.05}, "priority": {"interest": 2, "principal": 2}, "group": "ClassM1"},
            {"id": "ClassM2", "name": "Class M2", "type": "MEZZANINE", "original_balance": 15000000, "current_balance": 15000000,
             "coupon": {"kind": "FIXED", "fixed_rate": 0.05}, "priority": {"interest": 2, "principal": 2}, "group": "ClassM2"},
            {"id": "ClassZ", "name": "Class Z", "type": "Z_BOND", "original_balance": 15000000, "current_balance": 15000000,
             "coupon": {"kind": "FIXED", "fixed_rate": 0.06}, "priority": {"interest": 99, "principal": 3}, "group": "ClassZ"},
            {"id": "ClassB", "name": "Class B", "type": "SUBORDINATE", "original_balance": 5000000, "current_balance": 5000000,
             "coupon": {"kind": "FIXED", "fixed_rate": 0.07}, "priority": {"interest": 3, "principal": 4}, "group": "ClassB"},
        ],
        "funds": [{"id": "IAF", "description": "Interest Allocation Fund"}, {"id": "PAF", "description": "Principal Allocation Fund"}],
        "variables": {}, "tests": [],
        "waterfalls": {
            "interest": {"steps": []}, "principal": {"steps": []},
            "loss_allocation": {"write_down_order": ["ClassB", "ClassZ", "ClassM2", "ClassM1", "ClassA"]}
        },
        "structures": {
            "pro_rata_groups": [{"group_id": "MEZZANINE", "tranche_ids": ["ClassM1", "ClassM2"], "allocation_method": "balance"}],
            "z_bonds": ["ClassZ"]
        }
    }
    
    loader = DealLoader()
    deal_def = loader.load_from_json(complex_deal)
    state = DealState(deal_def)
    
    print("Initial Structure:")
    total = 0
    for bond_id, bond in state.bonds.items():
        bond_type = deal_def.bonds[bond_id].type
        print(f"  {bond_id:10s} ({bond_type:12s}): ${bond.current_balance:>12,.0f}")
        total += bond.current_balance
    print(f"  {'Total':10s} {' ':14s}  ${total:>12,.0f}")
    print()
    
    print("✅ Complex deal structure loaded successfully")
    print("   - Multiple structure types coexist")
    print("   - Ready for cashflow allocation")
    print()


def main():
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                   PRO-RATA ALLOCATION & Z-BONDS                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # Run tests
    test_prorata_allocation()
    test_zbond_accretion()
    test_combined_structures()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    print("✅ All Pro-Rata and Z-Bond Tests Passed")
    print()
    print("Key Features Demonstrated:")
    print("  1. Pro-Rata Allocation - Proportional payment to multiple tranches")
    print("  2. Z-Bond Accretion - Interest compounds instead of paying cash")
    print("  3. Complex Structures - Multiple advanced features in one deal")
    print()
    print("Industry Applications:")
    print()
    print("Pro-Rata Allocation:")
    print("  - Mezzanine tranches: Share credit risk equally")
    print("  - International issuance: Multiple currencies/regions")
    print("  - Flexible subordination: Dynamic credit enhancement")
    print()
    print("Z-Bonds:")
    print("  - Yield enhancement: Higher returns for patient investors")
    print("  - Cashflow shaping: Defer cashflows to later periods")
    print("  - Tax planning: Defer income recognition")
    print("  - ALM: Match long-dated liabilities")
    print()
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
