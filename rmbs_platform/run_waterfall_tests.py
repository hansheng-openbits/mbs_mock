#!/usr/bin/env python3
"""
Waterfall Test Runner
====================

Runs waterfall tests manually to identify issues.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Mock pytest and hypothesis
class MockPytest:
    @staticmethod
    def fixture(func=None):
        if func:
            return func
        return lambda f: f

    class mark:
        @staticmethod
        def skipif(condition, reason=''):
            def decorator(func):
                if condition:
                    return lambda *args, **kwargs: None
                return func
            return decorator

        @staticmethod
        def parametrize(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

sys.modules['pytest'] = MockPytest

# Mock hypothesis
class MockHypothesis:
    def given(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    strategies = type('strategies', (), {})()
    HealthCheck = type('HealthCheck', (), {})()
    settings = lambda *args, **kwargs: lambda func: func

sys.modules['hypothesis'] = MockHypothesis
sys.modules['hypothesis.strategies'] = MockHypothesis.strategies

# Mock tmp_path fixture
def tmp_path():
    return Path('/tmp')

def basic_sequential_deal():
    """Create a basic sequential pay deal for testing."""
    return {
        "meta": {"deal_id": "TEST_SEQ"},
        "bonds": [
            {"id": "A", "type": "NOTE", "original_balance": 60_000_000.0, "priority": {"interest": 1, "principal": 1}, "coupon": {"kind": "FIXED", "fixed_rate": 0.045}},
            {"id": "B", "type": "NOTE", "original_balance": 30_000_000.0, "priority": {"interest": 2, "principal": 2}, "coupon": {"kind": "FIXED", "fixed_rate": 0.060}},
            {"id": "C", "type": "NOTE", "original_balance": 10_000_000.0, "priority": {"interest": 3, "principal": 3}, "coupon": {"kind": "FIXED", "fixed_rate": 0.085}},
        ],
        "funds": [
            {"id": "IAF", "description": "Interest Available Funds"},
            {"id": "PAF", "description": "Principal Available Funds"},
        ],
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "1", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "A", "amount_rule": "bonds.A.balance * 0.045 / 12"},
                    {"id": "2", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "B", "amount_rule": "bonds.B.balance * 0.060 / 12"},
                    {"id": "3", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "C", "amount_rule": "bonds.C.balance * 0.085 / 12"},
                ]
            },
            "principal": {
                "steps": [
                    {"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "A", "amount_rule": "ALL"},
                    {"id": "2", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "B", "amount_rule": "ALL"},
                    {"id": "3", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "C", "amount_rule": "ALL"},
                ]
            }
        },
        "variables": {},
        "dates": {"cutoff_date": "2024-01-01", "first_payment_date": "2024-02-25"},
        "collateral": {"original_balance": 100_000_000.0, "current_balance": 100_000_000.0}
    }

def run_waterfall_tests():
    print("🔍 Running Waterfall Unit Tests")
    print("=" * 50)

    # Import test class
    from unit_tests.test_waterfall import TestWaterfallExecution

    instance = TestWaterfallExecution()

    # Test methods to run (avoiding hypothesis-dependent ones)
    test_methods = [
        'test_mass_conservation',
        'test_priority_order_preserved_under_stress',
        'test_waterfall_idempotent_for_same_inputs',
        'test_waterfall_handles_extreme_edge_cases',
    ]

    passed = 0
    failed = 0

    for method_name in test_methods:
        if hasattr(instance, method_name):
            try:
                print(f"🧪 Running {method_name}...")
                method = getattr(instance, method_name)

                # Pass the fixture manually
                if 'basic_sequential_deal' in method.__code__.co_varnames:
                    method(basic_sequential_deal())
                else:
                    method()

                print(f"✅ {method_name} PASSED")
                passed += 1

            except Exception as e:
                print(f"❌ {method_name} FAILED: {e}")
                failed += 1
        else:
            print(f"⚠️  {method_name} not found")

    print("=" * 50)
    print(f"📊 Waterfall Tests: {passed} passed, {failed} failed")

    return failed == 0

def run_manual_waterfall_test():
    """Run a simple manual waterfall test."""
    print("\n🧪 Running Manual Waterfall Test...")

    from engine.waterfall import WaterfallRunner
    from engine.state import DealState
    from engine.compute import ExpressionEngine

    # Create a simple deal state
    deal_spec = basic_sequential_deal()
    state = DealState()
    state.load_deal(deal_spec)

    # Initialize funds
    state.funds["IAF"] = 1_000_000  # $1M interest available
    state.funds["PAF"] = 2_000_000  # $2M principal available

    # Create waterfall runner
    runner = WaterfallRunner(state)

    # Run interest waterfall
    print("  Running interest waterfall...")
    runner.run_waterfall("interest")

    # Check results
    print(f"  IAF remaining: ${state.funds['IAF']:,.0f}")
    print(f"  Bond A balance: ${state.def_.bonds['A'].balance:,.0f}")

    # Run principal waterfall
    print("  Running principal waterfall...")
    runner.run_waterfall("principal")

    print(f"  PAF remaining: ${state.funds['PAF']:,.0f}")

    print("✅ Manual waterfall test completed")

if __name__ == '__main__':
    success = run_waterfall_tests()
    run_manual_waterfall_test()

    sys.exit(0 if success else 1)