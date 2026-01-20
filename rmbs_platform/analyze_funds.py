#!/usr/bin/env python3
"""
Analyze why IAF/PAF funds are always zero
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import run_simulation

# Test with PRIME_2024_1 deal
deal_spec = {}
with open('deals/PRIME_2024_1.json', 'r') as f:
    deal_spec = json.load(f)

# Use collateral that generates more interest
collateral = {'original_balance': 500_000_000.0, 'current_balance': 500_000_000.0}

# Run simulation with higher WAC to generate more interest
df, _ = run_simulation(
    deal_json=deal_spec,
    collateral_json=collateral,
    performance_rows=[],
    cpr=0.01,  # Very low prepay to keep balance high
    cdr=0.001,  # Very low default
    severity=0.30,
    horizon_periods=1,  # Just one period
)

print('Detailed Analysis for Period 1:')
if len(df) > 0:
    row = df.iloc[0]

    # Interest collections and payments
    interest_collected = row.get('Var.InputInterestCollected', 0)
    servicing_fee = row.get('Var.ServicingFeeAmount', 0)
    trustee_fee = row.get('Var.TrusteeFeeAmount', 0)
    classA_int = row.get('Var.ClassA_IntDue', 0)
    classM1_int = row.get('Var.ClassM1_IntDue', 0)
    classM2_int = row.get('Var.ClassM2_IntDue', 0)
    classB_int = row.get('Var.ClassB_IntDue', 0)

    print(f'Interest Collected: ${interest_collected:,.0f}')
    print(f'Servicing Fee: ${servicing_fee:,.0f}')
    print(f'Trustee Fee: ${trustee_fee:,.0f}')
    print(f'Class A Interest Due: ${classA_int:,.0f}')
    print(f'Class M1 Interest Due: ${classM1_int:,.0f}')
    print(f'Class M2 Interest Due: ${classM2_int:,.0f}')
    print(f'Class B Interest Due: ${classB_int:,.0f}')

    total_fees = servicing_fee + trustee_fee
    total_interest_due = classA_int + classM1_int + classM2_int + classB_int

    print(f'\nTotal Fees: ${total_fees:,.0f}')
    print(f'Total Interest Due: ${total_interest_due:,.0f}')
    print(f'Available after fees: ${interest_collected - total_fees:,.0f}')

    iaf_balance = row.get('Fund.IAF.Balance', 0)
    print(f'Final IAF Balance: ${iaf_balance:,.0f}')

    if interest_collected - total_fees - total_interest_due > 0:
        print('✅ Sufficient funds: Should have positive IAF balance')
    else:
        shortfall = total_fees + total_interest_due - interest_collected
        print(f'❌ Shortfall of ${shortfall:,.0f}: IAF will be depleted')

    # Check fees
    servicing_fee = row.get('Var.ServicingFeeAmount', 0)
    trustee_fee = row.get('Var.TrusteeFeeAmount', 0)
    total_fees = servicing_fee + trustee_fee
    print(f'\nActual Servicing Fee: ${servicing_fee:,.0f}')
    print(f'Actual Trustee Fee: ${trustee_fee:,.0f}')
    print(f'Total Fees Paid: ${total_fees:,.0f}')

    # Check reserve funding
    reserve_target = row.get('Var.ReserveTarget', 0)
    reserve_deficit = row.get('Var.ReserveDeficit', 0)
    reserve_balance = row.get('Fund.RESERVE.Balance', 0)
    print(f'Reserve Target: ${reserve_target:,.0f}')
    print(f'Reserve Deficit: ${reserve_deficit:,.0f}')
    print(f'Reserve Balance: ${reserve_balance:,.0f}')

    # Calculate expected remaining
    expected_after_fees = interest_collected - total_fees
    expected_after_interest = expected_after_fees - total_interest_due
    print(f'\nExpected after fees: ${expected_after_fees:,.0f}')
    print(f'Expected after interest: ${expected_after_interest:,.0f}')
    print(f'Actual IAF balance: ${iaf_balance:,.0f}')
    print(f'Difference: ${expected_after_interest - iaf_balance:,.0f}')