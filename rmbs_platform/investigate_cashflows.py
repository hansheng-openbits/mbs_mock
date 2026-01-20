#!/usr/bin/env python3
"""
Detailed investigation of cash flow calculations
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import run_simulation
from engine.loader import DealLoader
from engine.state import DealState
from engine.collateral import CollateralModel
from engine.compute import ExpressionEngine
import json

def investigate_collateral_cashflows():
    """Investigate what cash flows the collateral model generates"""
    print("🔍 Investigating Collateral Cash Flows")
    print("=" * 60)

    # Test collateral model
    collateral_spec = {
        'original_balance': 500_000_000.0,
        'current_balance': 115_071_000.0,  # From user's CSV period 0
        'wac': 0.055,  # From CSV
        'wam': 348
    }

    model = CollateralModel(
        original_balance=collateral_spec['original_balance'],
        wac=collateral_spec['wac'],
        wam=collateral_spec['wam']
    )

    # Generate cash flows like the simulation does
    cashflows = model.generate_cashflows(
        periods=3,
        cpr_vector=0.05,  # 5% CPR
        cdr_vector=0.01,  # 1% CDR
        sev_vector=0.35,  # 35% severity
        start_balance=115_071_000.0
    )

    print("Collateral Cash Flow Generation:")
    print(f"Starting balance: ${115_071_000.0:,.0f}")
    print(f"CPR: 5.0%, CDR: 1.0%, Severity: 35.0%")
    print()

    for i, cf in enumerate(cashflows):
        print(f"Period {i+1}:")
        print(".2f")
        print(".2f")
        print(".2f")
        print()

def investigate_simulation_cashflows():
    """Run simulation and analyze detailed cash flows"""
    print("🔍 Investigating Simulation Cash Flows")
    print("=" * 60)

    # Load the deal
    with open('deals/PRIME_2024_1.json', 'r') as f:
        deal_spec = json.load(f)

    # Run simulation with same parameters as user's data
    df, _ = run_simulation(
        deal_json=deal_spec,
        collateral_json={
            'original_balance': 500_000_000.0,
            'current_balance': 115_071_000.0  # From user's CSV
        },
        performance_rows=[],  # No actual performance data
        cpr=0.05,
        cdr=0.01,
        severity=0.35,
        horizon_periods=3,
    )

    print("Simulation Results Analysis:")
    print(f"Generated {len(df)} periods")
    print()

    # Analyze key columns
    cash_columns = [col for col in df.columns if 'Fund' in col or 'Var.Input' in col or 'Var.' in col]
    print("Cash Flow Related Columns:")
    for col in sorted(cash_columns):
        if col in df.columns:
            val = df[col].iloc[0] if len(df) > 0 else 'N/A'
            print(f"  {col}: {val}")
    print()

    # Check first period in detail
    if len(df) > 0:
        row = df.iloc[0]
        print("Period 1 Detailed Analysis:")

        # Interest flows
        interest_collected = row.get('Var.InputInterestCollected', 0)
        print(".2f")

        # Principal flows
        principal_collected = row.get('Var.InputPrincipalCollected', 0)
        print(".2f")

        # Fund balances
        iaf_balance = row.get('Fund.IAF.Balance', 0)
        paf_balance = row.get('Fund.PAF.Balance', 0)
        reserve_balance = row.get('Fund.RESERVE.Balance', 0)

        print("\nFund Balances:")
        print(".2f")
        print(".2f")
        print(".2f")

        # Check if funds are being deposited
        expected_iaf = interest_collected
        expected_paf = principal_collected

        print("\nExpected vs Actual:")
        print(".2f")
        print(".2f")

        if abs(iaf_balance - expected_iaf) > 0.01:
            print("❌ IAF balance doesn't match interest collected!")
        if abs(paf_balance - expected_paf) > 0.01:
            print("❌ PAF balance doesn't match principal collected!")

def investigate_waterfall_execution():
    """Investigate how the waterfall processes cash flows"""
    print("🔍 Investigating Waterfall Execution")
    print("=" * 60)

    # Load deal
    with open('deals/PRIME_2024_1.json', 'r') as f:
        deal_spec = json.load(f)

    loader = DealLoader()
    definition = loader.load_from_json(deal_spec)
    state = DealState(definition)

    # Manually set up cash flows like the simulation would
    # Based on collateral model output
    interest_collection = 399612.0  # From user's CSV
    principal_collection = 0  # Period 0 has no principal

    state.cash_balances['IAF'] = interest_collection
    state.cash_balances['PAF'] = principal_collection

    print("Manual Waterfall Test:")
    print(".2f")
    print(".2f")
    print()

    # Create waterfall runner
    from engine.waterfall import WaterfallRunner
    runner = WaterfallRunner(ExpressionEngine())

    # Execute interest waterfall
    print("Executing interest waterfall...")
    runner.run_period(state)

    print("\nAfter waterfall:")
    print(".2f")
    print(".2f")
    print(".2f")

def main():
    investigate_collateral_cashflows()
    print()
    investigate_simulation_cashflows()
    print()
    investigate_waterfall_execution()

if __name__ == '__main__':
    main()