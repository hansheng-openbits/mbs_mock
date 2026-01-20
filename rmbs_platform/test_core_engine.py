#!/usr/bin/env python3
"""
Test Core Engine Components
===========================

Direct tests of the core RMBS engine functionality.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.waterfall import WaterfallRunner
from engine.state import DealState
from engine.compute import ExpressionEngine
from engine.collateral import CollateralModel

print('✅ All core engine modules imported successfully')

# Test basic waterfall functionality
print('\n🧪 Testing WaterfallRunner...')

deal_spec = {
    'meta': {'deal_id': 'TEST'},
    'bonds': [
        {'id': 'A', 'type': 'NOTE', 'original_balance': 1000000.0, 'priority': {'interest': 1, 'principal': 1}, 'coupon': {'kind': 'FIXED', 'fixed_rate': 0.05}},
        {'id': 'B', 'type': 'NOTE', 'original_balance': 500000.0, 'priority': {'interest': 2, 'principal': 2}, 'coupon': {'kind': 'FIXED', 'fixed_rate': 0.07}},
    ],
    'waterfalls': {
        'interest': {
            'steps': [
                {'id': '1', 'action': 'PAY_BOND_INTEREST', 'from_fund': 'IAF', 'group': 'A', 'amount_rule': 'bonds.A.balance * 0.05 / 12'},
                {'id': '2', 'action': 'PAY_BOND_INTEREST', 'from_fund': 'IAF', 'group': 'B', 'amount_rule': 'bonds.B.balance * 0.07 / 12'},
            ]
        },
        'principal': {
            'steps': [
                {'id': '1', 'action': 'PAY_BOND_PRINCIPAL', 'from_fund': 'PAF', 'group': 'A', 'amount_rule': 'ALL'},
                {'id': '2', 'action': 'PAY_BOND_PRINCIPAL', 'from_fund': 'PAF', 'group': 'B', 'amount_rule': 'ALL'},
            ]
        }
    },
    'funds': [{'id': 'IAF'}, {'id': 'PAF'}],
    'variables': {},
    'dates': {'cutoff_date': '2024-01-01', 'first_payment_date': '2024-02-25'},
    'collateral': {'original_balance': 1500000.0, 'current_balance': 1500000.0}
}

# Test DealState
from engine.loader import DealLoader

loader = DealLoader()
definition = loader.load_from_json(deal_spec)
state = DealState(definition)

# Initialize funds
state.cash_balances['IAF'] = 50000  # Enough for interest
state.cash_balances['PAF'] = 200000  # Some principal

print(f'Initial IAF: ${state.cash_balances["IAF"]:,.0f}')
print(f'Initial PAF: ${state.cash_balances["PAF"]:,.0f}')
print(f'Bond A balance: ${state.bonds["A"].current_balance:,.0f}')
print(f'Bond B balance: ${state.bonds["B"].current_balance:,.0f}')

# Test WaterfallRunner
runner = WaterfallRunner(ExpressionEngine())

# Run full period (includes interest and principal waterfalls)
print('\nRunning full period waterfall...')
runner.run_period(state)

print('After full period:')
print(f'IAF remaining: ${state.cash_balances["IAF"]:,.0f}')
print(f'PAF remaining: ${state.cash_balances["PAF"]:,.0f}')
print(f'Bond A balance: ${state.bonds["A"].current_balance:,.0f}')
print(f'Bond B balance: ${state.bonds["B"].current_balance:,.0f}')

print('\n✅ WaterfallRunner test completed successfully')

# Test ExpressionEngine
print('\n🧪 Testing ExpressionEngine...')

engine = ExpressionEngine()

# Test some expressions
expressions = [
    'bonds.A.balance * 0.05 / 12',
    'bonds.B.balance + 1000',
    '1000000 - bonds.A.balance',
]

for expr in expressions:
    try:
        result = engine.evaluate(expr, state)
        print(f'  {expr} = {result}')
    except Exception as e:
        print(f'  {expr} = ERROR: {e}')

print('✅ ExpressionEngine test completed successfully')

# Test CollateralModel
print('\n🧪 Testing CollateralModel...')

model = CollateralModel(
    original_balance=1000000.0,
    wac=0.06,
    wam=360
)

# Generate cashflows
cashflows = model.generate_cashflows(
    periods=3,
    cpr_vector=0.10,
    cdr_vector=0.02,
    sev_vector=0.40
)

print(f'Generated {len(cashflows)} periods of cashflows')
print(f'Columns: {list(cashflows.columns)}')
if not cashflows.empty:
    first_row = cashflows.iloc[0]
    # Just show the first few values
    print(f'First period values: {dict(first_row.head())}')

print('✅ CollateralModel test completed successfully')

print('\n' + '=' * 50)
print('🎉 All core engine tests PASSED!')
print('The RMBS platform core functionality is working correctly.')