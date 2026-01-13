import sys
import logging
import pytest
from rmbs_loader import DealDefinition, Bond, Fund, Account, CouponType
from rmbs_state import DealState
from rmbs_compute import ExpressionEngine, EvaluationError

# Setup Logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s', stream=sys.stdout)

# --- MOCK SETUP ---
def create_mock_state():
    # 1. Create Definition
    defn = DealDefinition(
        meta={"id": "TEST"}, dates={}, waterfalls={}, variables={},
        funds={"IAF": Fund("IAF", ""), "PAF": Fund("PAF", "")},
        accounts={"RES": Account("RES", "Reserve")},
        bonds={"A1": Bond("A1", "NOTE", 1000.0, CouponType.FIXED, 1, 1)}
    )
    
    # 2. Create State
    state = DealState(defn)
    
    # 3. Hydrate with data for testing
    state.deposit_funds("IAF", 500.0)   # IAF has 500
    state.deposit_funds("PAF", 0.0)     # PAF is empty
    state.cash_balances["RES"] = 100.0  # Reserve has 100
    state.set_variable("NetWAC", 0.055) # Variable set
    state.ledgers["Losses"] = 50.0      # Ledger set
    
    return state

# --- TEST SUITE ---

def run_tests():
    print("=========================================")
    print("   MODULE 3: COMPUTE CORE TEST SUITE")
    print("=========================================\n")

    engine = ExpressionEngine()
    state = create_mock_state()

    # 1. Basic Arithmetic
    print("Test 1: Basic Arithmetic")
    res = engine.evaluate("100 + 50 * 2", state)
    assert res == 200.0
    print("✅ Math Correct: 100 + 50 * 2 = 200.0")

    # 2. Fund Access
    print("\nTest 2: Context Resolution (Funds)")
    # Test accessing via direct ID and funds.ID
    res1 = engine.evaluate("IAF", state)
    res2 = engine.evaluate("funds.IAF", state)
    assert res1 == 500.0
    assert res2 == 500.0
    print(f"✅ Fund Access Correct: IAF = {res1}")

    # 3. Variable Access
    print("\nTest 3: Context Resolution (Variables)")
    res = engine.evaluate("NetWAC * 100", state)
    assert res == 5.5
    print(f"✅ Variable Access Correct: NetWAC * 100 = {res}")

    # 4. Bond Object Access
    print("\nTest 4: Complex Object Access (Bonds)")
    # Logic: "The lesser of IAF (500) and Bond Balance (1000)"
    rule = "MIN(IAF, bonds.A1.balance)"
    res = engine.evaluate(rule, state)
    assert res == 500.0
    print(f"✅ Logic Rule '{rule}' -> Result: {res}")

    # 5. Condition Evaluation
    print("\nTest 5: Boolean Conditions")
    # Case A: True Condition
    cond_pass = engine.evaluate_condition("IAF > RES", state) # 500 > 100
    assert cond_pass is True
    print("✅ Condition 'IAF > RES' passed (True)")
    
    # Case B: False Condition
    cond_fail = engine.evaluate_condition("IAF < 10", state)
    assert cond_fail is False
    print("✅ Condition 'IAF < 10' passed (False)")

    # 6. Safety / Error Handling
    print("\nTest 6: Safety & Error Handling")
    try:
        # Try to access a variable that doesn't exist
        engine.evaluate("funds.GHOST_FUND + 10", state)
        # Note: Our proxy returns 0.0 for missing funds, which is standard in Excel/Intex logic.
        # Let's try a strict NameError
        engine.evaluate("UNKNOWN_VAR + 50", state)
    except EvaluationError as e:
        print(f"✅ Caught Expected Error: {e}")

    try:
        # Try to import os (Dangerous)
        engine.evaluate("__import__('os').getcwd()", state)
    except Exception as e:
        print(f"✅ Security Check Passed (Import blocked): {e}")

if __name__ == "__main__":
    run_tests()