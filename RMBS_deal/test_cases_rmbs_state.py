import logging
import sys
from datetime import date

# Import our Modules
from rmbs_loader import DealDefinition, Bond, Fund, Account, CouponType
from rmbs_state import DealState

# Configure Logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s', stream=sys.stdout)

def get_mock_deal_def():
    """Creates a static DealDefinition without parsing JSON."""
    return DealDefinition(
        meta={"id": "MOCK_1"},
        dates={},
        waterfalls={},
        variables={},
        funds={
            "IAF": Fund("IAF", "Interest Available Funds"),
            "PAF": Fund("PAF", "Principal Available Funds")
        },
        accounts={
            "RES": Account("RES", "Reserve Account")
        },
        bonds={
            "A1": Bond("A1", "NOTE", 1000.0, CouponType.FIXED, 1, 1),
            "B1": Bond("B1", "NOTE", 500.0,  CouponType.FIXED, 2, 2)
        }
    )

def run_tests():
    print("=========================================")
    print("   MODULE 2: STATE MANAGER TEST SUITE")
    print("=========================================\n")

    # 1. Setup
    definition = get_mock_deal_def()
    state = DealState(definition)
    
    print("Test 1: Initialization")
    assert state.bonds['A1'].current_balance == 1000.0
    assert state.cash_balances['IAF'] == 0.0
    print("✅ T=0 Initialized Correctly.")

    # 2. Deposit Cash
    print("\nTest 2: Cash Ingestion")
    state.deposit_funds("IAF", 500.00)
    assert state.cash_balances['IAF'] == 500.00
    print(f"✅ Deposited $500. IAF Balance: ${state.cash_balances['IAF']}")

    # 3. Transfer Logic
    print("\nTest 3: Fund Transfer (Waterfall Step Simulation)")
    try:
        # Move 100 to Reserve
        state.transfer_cash("IAF", "RES", 100.0)
        assert state.cash_balances['IAF'] == 400.0
        assert state.cash_balances['RES'] == 100.0
        print("✅ Transfer Success: IAF -> RES ($100)")
    except Exception as e:
        print(f"❌ Transfer Failed: {e}")

    # 4. Overdraft Protection
    print("\nTest 4: Overdraft Protection")
    try:
        state.transfer_cash("IAF", "RES", 9999.0) # Should fail
        print("❌ FAILED: System allowed negative balance.")
    except ValueError as e:
        print(f"✅ Success: Caught expected overdraft error: {e}")

    # 5. Bond Principal Payment
    print("\nTest 5: Bond Principal Payment")
    state.deposit_funds("PAF", 200.0)
    state.pay_bond_principal("A1", 150.0, "PAF")
    
    assert state.bonds['A1'].current_balance == 850.0
    assert state.cash_balances['PAF'] == 50.0 # 200 - 150
    print(f"✅ Bond A1 paid down. New Balance: {state.bonds['A1'].current_balance}")

    # 6. Snapshotting
    print("\nTest 6: Snapshotting History")
    state.snapshot(date(2024, 1, 25))
    
    last_snap = state.history[-1]
    print(f"✅ Snapshot recorded Period {last_snap.period} on {last_snap.date}")
    print(f"   Stored Bond Balances: {last_snap.bond_balances}")
    assert last_snap.bond_balances['A1'] == 850.0

if __name__ == "__main__":
    run_tests()