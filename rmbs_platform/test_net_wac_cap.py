"""
Test Net WAC Cap Implementation
=================================

This script tests the enhanced Net WAC cap functionality in the waterfall engine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.loader import DealLoader
from engine.state import DealState
from engine.waterfall import WaterfallRunner
from engine.compute import ExpressionEngine


def create_simple_test_deal():
    """Create a minimal test deal with Net WAC scenario."""
    return {
        "meta": {
            "deal_id": "TEST_NET_WAC",
            "deal_name": "Net WAC Cap Test",
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
                "original_balance": 7000000.0,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                "priority": {"interest": 1, "principal": 1}
            },
            {
                "id": "ClassB",
                "type": "NOTE",
                "original_balance": 2000000.0,
                "coupon": {"kind": "FIXED", "fixed_rate": 0.06},
                "priority": {"interest": 2, "principal": 2}
            }
        ],
        "variables": {
            "ServicingFeeRate": "0.0025 / 12",
            "ServicingFeeAmount": "collateral.current_balance * ServicingFeeRate",
            "TrusteeFeeAmount": "MAX(7500, collateral.current_balance * 0.0001 / 12)",
            "GrossWAC": "0.06",
            "ClassA_IntDue": "bonds.ClassA.balance * (0.05 / 12)",
            "ClassB_IntDue": "bonds.ClassB.balance * (0.06 / 12)"
        },
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "I-1", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "ServicingFeeAmount"},
                    {"id": "I-2", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "TrusteeFeeAmount"},
                    {"id": "I-3", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "ClassA_IntDue"},
                    {"id": "I-4", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassB", "amount_rule": "ClassB_IntDue"}
                ]
            },
            "principal": {"steps": []
        }
        },
        "tests": []
    }


def main():
    """Run Net WAC cap test."""
    print("=" * 80)
    print("NET WAC CAP IMPLEMENTATION TEST")
    print("=" * 80)
    print()
    
    # Create and load deal
    deal_json = create_simple_test_deal()
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    
    # Create runner with iterative solver
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine, use_iterative_solver=True, max_iterations=15, convergence_tol=0.01)
    
    # Show scenario
    print("TEST SCENARIO")
    print("-" * 80)
    print(f"Collateral: $10M at 6% WAC")
    print(f"Class A: $7M at 5% fixed")
    print(f"Class B: $2M at 6% fixed")
    print(f"Servicing Fee: 25 bps")
    print(f"Trustee Fee: $7.5k + 1 bp")
    print()
    
    # Deposit cashflows
    gross_interest = 10_000_000 * 0.06 / 12
    state.deposit_funds("IAF", gross_interest)
    state.deposit_funds("PAF", 0)
    
    print(f"Gross Interest: ${gross_interest:,.2f}")
    print()
    
    # Run waterfall
    runner.run_period(state)
    
    # Check results
    print("NET WAC CALCULATION")
    print("-" * 80)
    
    servicing_fee = state.get_variable("ServicingFeeAmount")
    trustee_fee = state.get_variable("TrusteeFeeAmount")
    net_wac = state.get_variable("NetWAC")
    
    print(f"Servicing Fee: ${servicing_fee:,.2f}")
    print(f"Trustee Fee: ${trustee_fee:,.2f}")
    print(f"Net Interest: ${gross_interest - servicing_fee - trustee_fee:,.2f}")
    print()
    
    if net_wac:
        print(f"Net WAC: {net_wac:.4%}")
        expected_net_wac = (gross_interest - servicing_fee - trustee_fee) / 9_000_000 * 12
        print(f"Expected Net WAC: {expected_net_wac:.4%}")
        print()
        if abs(net_wac - expected_net_wac) < 0.00001:
            print("✅ Net WAC calculation: CORRECT")
        else:
            print(f"❌ Net WAC calculation: ERROR")
    else:
        print("⚠️  Net WAC not calculated (variable not set)")
    
    print()
    
    if runner.last_solver_result:
        print(f"Solver converged: {runner.last_solver_result.converged}")
        print(f"Iterations: {runner.last_solver_result.iterations}")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
