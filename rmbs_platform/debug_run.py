"""
Debug Harness for Rule Evaluation
=================================

Standalone script for testing the expression engine and deal loading
without running a full simulation. Useful for debugging waterfall
rules and trigger conditions.

Usage
-----
Run from the rmbs_platform parent directory::

    python rmbs_platform/debug_run.py

The script:
1. Loads a minimal test deal specification
2. Initializes deal state
3. Tests the expression engine with a sample rule
4. Reports success or failure with traceback
"""

from __future__ import annotations

import traceback
from typing import Any, Dict

from engine.loader import DealLoader
from engine.state import DealState
from engine.compute import ExpressionEngine

# Minimal test deal specification
json_spec: Dict[str, Any] = {
    "meta": {
        "deal_id": "DEBUG_TEST",
        "deal_name": "Debug",
        "asset_type": "RMBS",
        "version": "1.0",
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
        "original_balance": 1000.0,
        "loan_data": {},
        "model_interface": {"kind": "LOAN_LEVEL_SIM", "inputs_required": []},
    },
    "funds": [{"id": "IAF", "description": "Interest"}],
    "accounts": [],
    "variables": {
        "DelinqTrigger": "tests.DelinqTest.failed"  # Test the proxy pattern
    },
    "tests": [
        {
            "id": "DelinqTest",
            "kind": "DELINQ",
            "calc": {"value_rule": "0"},
            "threshold": {"rule": "0"},
            "pass_if": "VALUE_LT_THRESHOLD",
            "effects": [],
        }
    ],
    "bonds": [
        {
            "id": "A",
            "type": "NOTE",
            "original_balance": 1000,
            "priority": {"interest": 1, "principal": 1},
            "coupon": {"kind": "FIXED"},
        }
    ],
    "waterfalls": {
        "interest": {"steps": []},
        "principal": {"steps": []},
        "loss_allocation": {"loss_source_rule": "0", "write_down_order": []},
    },
}


def main() -> None:
    """
    Run the debug test sequence.

    Tests:
    1. Deal loading and validation
    2. State initialization
    3. Expression engine evaluation
    """
    print("--- STARTING DEBUG RUN ---")
    try:
        # 1. Load deal
        print("1. Loading Deal...")
        loader = DealLoader("rmbs_platform/deal_spec.json")
        deal_def = loader.load_from_json(json_spec)

        # 2. Initialize state
        print("2. Initializing State...")
        state = DealState(deal_def)

        # 3. Check flags
        print(f"   State Flags initialized as: {state.flags}")

        # 4. Test expression engine
        print("3. Testing Compute Engine...")
        engine = ExpressionEngine()
        rule = "tests.DelinqTest.failed"
        result = engine.evaluate(rule, state)

        print(f"✅ SUCCESS! Rule '{rule}' evaluated to: {result}")

    except Exception as e:
        print("\n❌ CRASH DETECTED!")
        traceback.print_exc()


if __name__ == "__main__":
    main()
