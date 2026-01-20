#!/usr/bin/env python3
"""
Test case with positive fund balances
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import run_simulation
import json

def create_positive_funds_scenario():
    """Create a deal scenario designed to have positive fund balances"""

    # Start with the existing deal
    with open('deals/PRIME_2024_1.json', 'r') as f:
        deal_spec = json.load(f)

    # Modify to create positive balances:
    # 1. Lower bond coupon rates (reduce payments due)
    # 2. Keep collateral balance high to generate more interest
    # 3. Lower prepayment rate to maintain higher balance

    # Lower coupon rates
    for bond in deal_spec['bonds']:
        if 'coupon' in bond and 'fixed_rate' in bond['coupon']:
            bond['coupon']['fixed_rate'] *= 0.7  # 30% lower coupons

    # Update the interest due variables to match
    deal_spec['variables']['ClassA_IntDue'] = "bonds.ClassA.balance * 0.0315 / 12"  # 4.5% * 0.7
    deal_spec['variables']['ClassM1_IntDue'] = "bonds.ClassM1.balance * 0.0385 / 12"  # 5.5% * 0.7
    deal_spec['variables']['ClassM2_IntDue'] = "bonds.ClassM2.balance * 0.0455 / 12"  # 6.5% * 0.7
    deal_spec['variables']['ClassB_IntDue'] = "bonds.ClassB.balance * 0.0595 / 12"  # 8.5% * 0.7

    return deal_spec

def test_positive_funds():
    """Test scenario designed to produce positive fund balances"""

    # Create modified deal
    deal_spec = create_positive_funds_scenario()

    # Use high collateral balance with low prepayments to maximize interest
    collateral = {
        'original_balance': 500_000_000.0,
        'current_balance': 480_000_000.0  # High balance = more interest
    }

    # Run simulation with low prepayments to maintain balance
    df, _ = run_simulation(
        deal_json=deal_spec,
        collateral_json=collateral,
        performance_rows=[],
        cpr=0.005,  # Very low prepayments (0.5% CPR)
        cdr=0.001,  # Low defaults
        severity=0.10,  # Low severity
        horizon_periods=1,
    )

    row = df.iloc[0]

    # Get all values
    interest_collected = float(row.get('Var.InputInterestCollected', 0))
    principal_collected = float(row.get('Var.InputPrincipalCollected', 0))

    # Interest payments due (with reduced coupons)
    classA_int = float(row.get('Var.ClassA_IntDue', 0))
    classM1_int = float(row.get('Var.ClassM1_IntDue', 0))
    classM2_int = float(row.get('Var.ClassM2_IntDue', 0))
    classB_int = float(row.get('Var.ClassB_IntDue', 0))
    total_int_due = classA_int + classM1_int + classM2_int + classB_int

    # Fees
    servicing_fee = float(row.get('Var.ServicingFee', 0))
    trustee_fee = float(row.get('Var.TrusteeFee', 0))
    total_fees = servicing_fee + trustee_fee

    # Fund balances
    iaf_balance = float(row.get('Fund.IAF.Balance', 0))
    paf_balance = float(row.get('Fund.PAF.Balance', 0))

    print('🟢 POSITIVE FUND BALANCES TEST')
    print('=' * 50)
    print('Scenario: Lower bond coupons + High collateral balance + Low prepayments')
    print()
    print(f'Interest Collected:      ${interest_collected:>12,.0f}')
    print(f'Servicing Fee:           ${servicing_fee:>12,.0f}')
    print(f'Trustee Fee:             ${trustee_fee:>12,.0f}')
    print(f'Total Fees:              ${total_fees:>12,.0f}')
    print()
    print(f'Available for Interest:  ${interest_collected - total_fees:>12,.0f}')
    print()
    print(f'Class A Interest Due:    ${classA_int:>12,.0f}')
    print(f'Class M1 Interest Due:   ${classM1_int:>12,.0f}')
    print(f'Class M2 Interest Due:   ${classM2_int:>12,.0f}')
    print(f'Class B Interest Due:    ${classB_int:>12,.0f}')
    print(f'Total Interest Due:      ${total_int_due:>12,.0f}')
    print()

    available = interest_collected - total_fees
    surplus = available - total_int_due

    print(f'Interest Surplus:        ${surplus:>12,.0f}')
    print()
    print(f'Final IAF Balance:       ${iaf_balance:>12,.0f}')
    print(f'Final PAF Balance:       ${paf_balance:>12,.0f}')
    print()

    if iaf_balance > 0 and surplus > 0:
        print('✅ SUCCESS: Positive fund balances achieved!')
        print('   This confirms the waterfall correctly handles surplus cash flows.')
        print(f'   IAF retained ${iaf_balance:,.0f} after paying all obligations.')
    elif surplus > 0 and iaf_balance == 0:
        print('❌ ISSUE: Surplus exists but IAF is still $0')
        print('   This would indicate a problem with surplus distribution.')
    else:
        print('📊 NEUTRAL: No surplus, funds depleted as expected.')
        print('   Try adjusting parameters further to create surplus.')

    return iaf_balance > 0

def test_original_vs_modified():
    """Compare original deal (deficit) vs modified deal (surplus)"""

    print('🔄 COMPARISON: Original vs Modified Deal')
    print('=' * 60)

    # Test original deal (should have deficit)
    with open('deals/PRIME_2024_1.json', 'r') as f:
        original_deal = json.load(f)

    df_orig, _ = run_simulation(
        deal_json=original_deal,
        collateral_json={'original_balance': 500_000_000.0, 'current_balance': 115_071_000.0},
        performance_rows=[],
        cpr=0.05, cdr=0.01, severity=0.35, horizon_periods=1
    )

    orig_iaf = float(df_orig.iloc[0].get('Fund.IAF.Balance', 0))
    orig_interest = float(df_orig.iloc[0].get('Var.InputInterestCollected', 0))

    # Test modified deal (should have surplus)
    modified_deal = create_positive_funds_scenario()
    df_mod, _ = run_simulation(
        deal_json=modified_deal,
        collateral_json={'original_balance': 500_000_000.0, 'current_balance': 480_000_000.0},
        performance_rows=[],
        cpr=0.005, cdr=0.001, severity=0.10, horizon_periods=1
    )

    mod_iaf = float(df_mod.iloc[0].get('Fund.IAF.Balance', 0))
    mod_interest = float(df_mod.iloc[0].get('Var.InputInterestCollected', 0))

    print('Original Deal (Stressed):')
    print(f'  Interest Collected: ${orig_interest:,.0f}')
    print(f'  Final IAF Balance:  ${orig_iaf:,.0f} (deficit scenario)')
    print()
    print('Modified Deal (Healthy):')
    print(f'  Interest Collected: ${mod_interest:,.0f}')
    print(f'  Final IAF Balance:  ${mod_iaf:,.0f} (surplus scenario)')
    print()

    if orig_iaf == 0 and mod_iaf > 0:
        print('✅ PERFECT: Platform correctly handles both scenarios!')
        print('   - Deficit scenarios: funds depleted to $0')
        print('   - Surplus scenarios: funds retain positive balances')
    else:
        print('❌ Unexpected results in comparison')

if __name__ == '__main__':
    test_positive_funds()
    print()
    test_original_vs_modified()