import sys
import logging
from rmbs_loader import DealDefinition, Bond, Fund, Account, CouponType
from rmbs_state import DealState
from rmbs_compute import ExpressionEngine
from rmbs_waterfall import WaterfallRunner

# Setup Logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s', stream=sys.stdout)

def setup_simulation():
    """Constructs a realistic mini-deal."""
    # Definition
    defn = DealDefinition(
        meta={"id": "SIM_1"}, dates={}, 
        variables={
            # Calculate Interest Due: Rate * Balance
            "SeniorInterestDue": "bonds.Senior.balance * 0.04", 
            "JuniorInterestDue": "bonds.Junior.balance * 0.08",
            "PeriodRealizedLoss": "0.0" # Default 0
        },
        funds={"IAF": Fund("IAF", "Interest Funds")},
        accounts={},
        bonds={
            "Senior": Bond("Senior", "NOTE", 1000.0, CouponType.FIXED, 1, 1),
            "Junior": Bond("Junior", "NOTE", 200.0,  CouponType.FIXED, 2, 2)
        },
        waterfalls={
            "interest": {
                "steps": [
                    {
                        "id": "1", "from_fund": "IAF", "action": "PAY_BOND_INTEREST", 
                        "group": "Senior", "amount_rule": "SeniorInterestDue",
                        "unpaid_ledger_id": "SeniorShortfall"
                    },
                    {
                        "id": "2", "from_fund": "IAF", "action": "PAY_BOND_INTEREST", 
                        "group": "Junior", "amount_rule": "JuniorInterestDue",
                        "unpaid_ledger_id": "JuniorShortfall"
                    }
                ]
            },
            "loss_allocation": {
                "write_down_order": ["Junior", "Senior"]
            }
        }
    )
    
    state = DealState(defn)
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)
    
    return state, runner

def run_tests():
    print("=========================================")
    print("   MODULE 4: WATERFALL RUNNER TEST SUITE")
    print("=========================================\n")

    # --- TEST 1: Full Payment Scenario ---
    print("--- Test 1: Full Payment (Healthy Deal) ---")
    state, runner = setup_simulation()
    
    # Context: Senior Due = 1000 * 0.04 = 40. Junior Due = 200 * 0.08 = 16. Total = 56.
    # Ingest Cash: $60 (Enough to pay everyone)
    state.deposit_funds("IAF", 60.0)
    
    runner.run_period(state)
    
    # Assertions
    assert state.cash_balances['IAF'] == 4.0  # 60 - 40 - 16 = 4 remaining
    assert state.ledgers.get('SeniorShortfall', 0) == 0.0
    print("✅ Logic Correct: All bonds paid. $4.00 excess cash remaining.")


    # --- TEST 2: Shortfall Scenario ---
    print("\n--- Test 2: Shortfall (Distressed Deal) ---")
    state, runner = setup_simulation()
    
    # Context: Needs $56.
    # Ingest Cash: $30 (Not enough even for Senior)
    state.deposit_funds("IAF", 30.0)
    
    runner.run_period(state)
    
    # Assertions
    assert state.cash_balances['IAF'] == 0.0 # Drained
    # Senior wanted 40, got 30. Shortfall = 10.
    senior_short = state.ledgers.get('SeniorShortfall')
    # Junior wanted 16, got 0. Shortfall = 16.
    junior_short = state.ledgers.get('JuniorShortfall')
    
    assert senior_short == 10.0
    assert junior_short == 16.0
    print(f"✅ Logic Correct: Senior Shortfall ${senior_short}, Junior Shortfall ${junior_short}")


    # --- TEST 3: Loss Allocation ---
    print("\n--- Test 3: Loss Writedowns ---")
    state, runner = setup_simulation()
    
    # Trigger a loss via variable
    # We update the variable logic just for this test (simulating external model input)
    state.def_.variables['PeriodRealizedLoss'] = "100.0" 
    
    runner.run_period(state)
    
    # Junior starts at 200. Loss is 100. Junior should drop to 100.
    # Senior should be untouched.
    assert state.bonds['Junior'].current_balance == 100.0
    assert state.bonds['Senior'].current_balance == 1000.0
    print(f"✅ Loss Allocation Correct: Junior wrote down to ${state.bonds['Junior'].current_balance}")

if __name__ == "__main__":
    run_tests()