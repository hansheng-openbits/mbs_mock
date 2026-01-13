import sys
import logging
import pandas as pd
from datetime import date
from rmbs_state import Snapshot
from rmbs_reporting import ReportGenerator

# Setup Logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s', stream=sys.stdout)

def create_mock_history():
    """
    Creates a fake history of 3 periods:
    T=0: Bond has 1000.
    T=1: Bond pays down to 900.
    T=2: Bond pays down to 800.
    """
    # T=0
    s0 = Snapshot(
        date=date(2024, 1, 1).isoformat(), period=0,
        funds={"IAF": 0.0}, ledgers={}, variables={"NetWAC": 0.05}, flags={},
        bond_balances={"A1": 1000.0}
    )
    
    # T=1 (Paid 100 Principal)
    s1 = Snapshot(
        date=date(2024, 2, 1).isoformat(), period=1,
        funds={"IAF": 5.0}, ledgers={"Losses": 0.0}, variables={"NetWAC": 0.05}, flags={},
        bond_balances={"A1": 900.0}
    )
    
    # T=2 (Paid 100 Principal, Shortfall 10)
    s2 = Snapshot(
        date=date(2024, 3, 1).isoformat(), period=2,
        funds={"IAF": 2.0}, ledgers={"Losses": 0.0, "Shortfall": 10.0}, 
        variables={"NetWAC": 0.06}, flags={},
        bond_balances={"A1": 800.0}
    )
    
    return [s0, s1, s2]

def run_tests():
    print("=========================================")
    print("   MODULE 5: REPORTING LAYER TEST SUITE")
    print("=========================================\n")

    history = create_mock_history()
    reporter = ReportGenerator(history)

    # --- Test 1: DataFrame Creation ---
    print("Test 1: Generating DataFrame")
    df = reporter.generate_cashflow_report()
    
    # Check shape: 3 rows (periods 0,1,2). 
    # Cols: Period, Date, Bond.A1.Balance, Fund.IAF.Balance, Var.NetWAC, Bond.A1.Prin_Paid ...
    print(f"✅ DataFrame Created. Shape: {df.shape}")
    print(df[['Period', 'Bond.A1.Balance', 'Bond.A1.Prin_Paid']].to_string(index=False))

    # --- Test 2: Data Verification ---
    print("\nTest 2: Verifying Values")
    
    # Check T=1 Principal Payment (1000 - 900 = 100)
    p1_payment = df.loc[1, 'Bond.A1.Prin_Paid']
    assert p1_payment == 100.0
    print(f"✅ Period 1 Principal Payment Correct: {p1_payment}")

    # Check T=2 Ledger Population
    p2_shortfall = df.loc[2, 'Ledger.Shortfall']
    assert p2_shortfall == 10.0
    print(f"✅ Period 2 Shortfall Ledger Populated: {p2_shortfall}")
    
    # Check T=2 Variable Update
    p2_wac = df.loc[2, 'Var.NetWAC']
    assert p2_wac == 0.06
    print(f"✅ Period 2 Variable Update (NetWAC): {p2_wac}")

    # --- Test 3: CSV Export (Smoke Test) ---
    print("\nTest 3: CSV Export")
    try:
        filename = "test_output.csv"
        reporter.save_to_csv(df, filename)
        print(f"✅ CSV Saved successfully to {filename}")
    except Exception as e:
        print(f"❌ CSV Save Failed: {e}")

if __name__ == "__main__":
    run_tests()