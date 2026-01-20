#!/usr/bin/env python3
"""
Simple Test Runner for RMBS Platform
====================================

Runs key tests manually to identify and fix issues.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Manual fixture data
PRODUCTION_DEAL_SPEC = {
    "meta": {
        "deal_id": "RMBS_2024_PROD",
        "deal_name": "Production Test Deal 2024-1",
        "asset_type": "PRIME_RMBS",
        "version": "2.0",
    },
    "dates": {
        "cutoff_date": "2024-01-01",
        "closing_date": "2024-01-30",
        "first_payment_date": "2024-02-25",
        "maturity_date": "2054-01-01",
        "payment_frequency": "MONTHLY",
        "day_count": "30_360",
    },
    "collateral": {
        "original_balance": 100_000_000.0,
        "current_balance": 100_000_000.0,
        "wac": 0.0625,
        "wam": 348,
    },
    "funds": [
        {"id": "IAF", "description": "Interest Available Funds"},
        {"id": "PAF", "description": "Principal Available Funds"},
    ],
    "accounts": [
        {"id": "RESERVE", "type": "RESERVE", "target_rule": "500000.0"},
    ],
    "variables": {
        "ServicingFee": "collateral.current_balance * 0.0025 / 12",
        "TrusteeFee": "collateral.current_balance * 0.0002 / 12",
        "ClassA_IntDue": "bonds.ClassA.balance * 0.045 / 12",
        "ClassB_IntDue": "bonds.ClassB.balance * 0.060 / 12",
        "ClassC_IntDue": "bonds.ClassC.balance * 0.085 / 12",
        "DelinqTrigger": "tests.DelinqTest.failed",
        "ReserveTarget": "500000.0",
        "ReserveShortfall": "MAX(0, ReserveTarget - funds.RESERVE)",
    },
    "tests": [
        {
            "id": "DelinqTest",
            "kind": "DELINQ",
            "calc": {
                "value_rule": "variables.DelinquencyRate",
                "numerator_rule": "0",
                "denominator_rule": "1",
            },
            "threshold": {"rule": "0.05"},
            "pass_if": "VALUE_LT_THRESHOLD",
            "effects": [{"set_flag": "TriggerActive"}],
        },
    ],
    "bonds": [
        {
            "id": "ClassA",
            "type": "NOTE",
            "original_balance": 80_000_000.0,
            "priority": {"interest": 1, "principal": 1},
            "coupon": {"kind": "FIXED", "fixed_rate": 0.045},
        },
        {
            "id": "ClassB",
            "type": "NOTE",
            "original_balance": 15_000_000.0,
            "priority": {"interest": 2, "principal": 2},
            "coupon": {"kind": "FIXED", "fixed_rate": 0.060},
        },
        {
            "id": "ClassC",
            "type": "NOTE",
            "original_balance": 5_000_000.0,
            "priority": {"interest": 3, "principal": 3},
            "coupon": {"kind": "FIXED", "fixed_rate": 0.085},
        },
    ],
    "waterfalls": {
        "interest": {
            "steps": [
                {"id": "1", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "ServicingFee"},
                {"id": "2", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "TrusteeFee"},
                {"id": "3", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "ClassA_IntDue"},
                {"id": "4", "action": "TRANSFER_FUND", "from_fund": "IAF", "to": "RESERVE", "amount_rule": "MIN(funds.IAF, ReserveShortfall)"},
                {"id": "5", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassB", "amount_rule": "ClassB_IntDue"},
                {"id": "6", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassC", "amount_rule": "ClassC_IntDue", "condition": "DelinqTrigger == False"},
            ],
        },
        "principal": {
            "steps": [
                {"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"},
                {"id": "2", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassB", "amount_rule": "ALL"},
                {"id": "3", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassC", "amount_rule": "ALL"},
            ],
        },
        "loss_allocation": {
            "loss_source_rule": "variables.RealizedLoss",
            "write_down_order": ["ClassC", "ClassB", "ClassA"],
        },
    },
    "options": {
        "cleanup_call": {
            "enabled": True,
            "threshold_rule": "collateral.current_balance <= 0.10 * collateral.original_balance",
        },
    },
}

def test_zero_collateral_balance():
    """Test zero collateral balance handling."""
    print("🧪 Running test_zero_collateral_balance...")

    from engine import run_simulation

    zero_collateral = {
        "original_balance": 100_000_000.0,
        "current_balance": 0.0,  # Already liquidated
    }

    df, _ = run_simulation(
        deal_json=PRODUCTION_DEAL_SPEC,
        collateral_json=zero_collateral,
        performance_rows=[],
        cpr=0.10,
        cdr=0.02,
        severity=0.40,
        horizon_periods=12,
    )

    # Should still return valid DataFrame
    assert not df.empty
    # With zero collateral, cleanup call triggers and simulation terminates early
    assert len(df) < 12, f"Expected early termination due to cleanup call, got {len(df)} periods"

    # Verify cleanup call was triggered
    if "Var.CleanupCallTriggered" in df.columns:
        cleanup_triggered = df["Var.CleanupCallTriggered"].iloc[-1]
        assert cleanup_triggered == True, "Cleanup call should be triggered with zero collateral"

    # Verify collateral inputs are zero throughout
    if "Var.InputEndBalance" in df.columns:
        end_balances = df["Var.InputEndBalance"].unique()
        assert all(b == 0.0 for b in end_balances), f"Expected all zero end balances, got {end_balances}"

    if "Var.InputInterestCollected" in df.columns:
        interest_vals = df["Var.InputInterestCollected"].unique()
        assert all(i == 0.0 for i in interest_vals), f"Expected all zero interest, got {interest_vals}"

    if "Var.InputPrincipalCollected" in df.columns:
        principal_vals = df["Var.InputPrincipalCollected"].unique()
        assert all(p == 0.0 for p in principal_vals), f"Expected all zero principal, got {principal_vals}"

    print("✅ test_zero_collateral_balance PASSED")

def test_extreme_prepay_scenario():
    """Test extreme prepayment scenario."""
    print("🧪 Running test_extreme_prepay_scenario...")

    from engine import run_simulation

    collateral_spec = {
        "original_balance": 100_000_000.0,
        "current_balance": 100_000_000.0,
    }

    df, _ = run_simulation(
        deal_json=PRODUCTION_DEAL_SPEC,
        collateral_json=collateral_spec,
        performance_rows=[],
        cpr=0.50,  # 50% CPR - extreme prepay
        cdr=0.02,
        severity=0.40,
        horizon_periods=12,
    )

    # Should return valid DataFrame
    assert not df.empty
    assert len(df) == 12

    # Verify high prepayments
    if "Var.InputPrincipalCollected" in df.columns:
        principal_vals = df["Var.InputPrincipalCollected"]
        # Should have significant principal collections
        avg_principal = principal_vals.mean()
        assert avg_principal > 1_000_000, f"Expected high principal payments, got average {avg_principal}"

    print("✅ test_extreme_prepay_scenario PASSED")

def test_basic_simulation():
    """Test basic simulation functionality."""
    print("🧪 Running test_basic_simulation...")

    from engine import run_simulation

    # Simple deal spec
    deal_spec = {
        'meta': {'deal_id': 'TEST'},
        'bonds': [{'id': 'A', 'type': 'NOTE', 'original_balance': 1000000.0, 'priority': {'interest': 1, 'principal': 1}, 'coupon': {'kind': 'FIXED', 'fixed_rate': 0.05}}],
        'waterfalls': {
            'interest': {'steps': [{'id': '1', 'action': 'PAY_BOND_INTEREST', 'from_fund': 'IAF', 'group': 'A', 'amount_rule': 'bonds.A.balance * 0.05 / 12'}]},
            'principal': {'steps': [{'id': '1', 'action': 'PAY_BOND_PRINCIPAL', 'from_fund': 'PAF', 'group': 'A', 'amount_rule': 'ALL'}]}
        },
        'funds': [{'id': 'IAF'}, {'id': 'PAF'}],
        'variables': {},
        'dates': {'cutoff_date': '2024-01-01', 'first_payment_date': '2024-02-25'},
        'collateral': {'original_balance': 1000000.0, 'current_balance': 1000000.0}
    }

    collateral = {'original_balance': 1000000.0, 'current_balance': 1000000.0}

    df, _ = run_simulation(
        deal_json=deal_spec,
        collateral_json=collateral,
        performance_rows=[],
        cpr=0.10,
        cdr=0.02,
        severity=0.40,
        horizon_periods=3,
    )

    assert not df.empty
    assert len(df) == 3
    assert len(df.columns) > 10  # Should have various output columns

    print("✅ test_basic_simulation PASSED")

def main():
    print("🔍 Running RMBS Platform Unit Tests")
    print("=" * 50)

    tests = [
        test_basic_simulation,
        test_zero_collateral_balance,
        test_extreme_prepay_scenario,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"📊 Results: {passed} passed, {failed} failed")

    return 0 if failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())