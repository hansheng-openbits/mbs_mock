#!/usr/bin/env python3
"""
Debug waterfall execution step by step
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.loader import DealLoader
from engine.state import DealState
from engine.waterfall import WaterfallRunner
from engine.compute import ExpressionEngine
import json

# Load deal
with open('deals/PRIME_2024_1.json', 'r') as f:
    deal_spec = json.load(f)

loader = DealLoader()
definition = loader.load_from_json(deal_spec)

# Create state with some cash in IAF
state = DealState(definition)
state.cash_balances['IAF'] = 2_500_000  # $2.5M interest collected

print("Initial state:")
print(f"IAF: ${state.cash_balances['IAF']:,.0f}")
print(f"RESERVE: ${state.cash_balances['RESERVE']:,.0f}")

# Create waterfall runner
runner = WaterfallRunner(ExpressionEngine())

# Manually execute each interest waterfall step
print("\nExecuting interest waterfall steps:")

interest_waterfall = definition.waterfalls['interest']['steps']

for step in interest_waterfall:
    step_id = step.get('id', 'unknown')
    action = step.get('action', 'unknown')
    amount_rule = step.get('amount_rule', '')
    condition = step.get('condition', '')

    print(f"\nStep {step_id}: {action}")
    print(f"  Rule: {amount_rule}")

    # Evaluate the amount
    if amount_rule:
        try:
            amount = runner.expr.evaluate(amount_rule, state)
            print(f"  Amount: ${amount:,.0f}")
        except Exception as e:
            print(f"  Amount evaluation failed: {e}")
            amount = 0
    else:
        amount = 0

    # Check condition if present
    if condition:
        try:
            condition_met = runner.expr.evaluate_condition(condition, state)
            print(f"  Condition '{condition}': {condition_met}")
            if not condition_met:
                print("  Step skipped")
                continue
        except Exception as e:
            print(f"  Condition evaluation failed: {e}")
            continue

    # Execute the action
    if action == "PAY_FEE":
        state.cash_balances['IAF'] -= amount
        print(f"  Paid fee: -${amount:,.0f}")
    elif action == "PAY_BOND_INTEREST":
        state.cash_balances['IAF'] -= amount
        print(f"  Paid interest: -${amount:,.0f}")
    elif action == "TRANSFER_FUND":
        transfer_amount = min(state.cash_balances['IAF'], amount)
        state.cash_balances['IAF'] -= transfer_amount
        state.cash_balances['RESERVE'] += transfer_amount
        print(f"  Transferred to reserve: -${transfer_amount:,.0f}")

    print(f"  IAF balance: ${state.cash_balances['IAF']:,.0f}")
    print(f"  RESERVE balance: ${state.cash_balances['RESERVE']:,.0f}")

print("\nFinal state:")
print(f"IAF: ${state.cash_balances['IAF']:,.0f}")
print(f"RESERVE: ${state.cash_balances['RESERVE']:,.0f}")