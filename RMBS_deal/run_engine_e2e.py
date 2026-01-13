import os
import sys
import logging
import pandas as pd
from datetime import date, timedelta

# Import our Modules
# Ensure these files are in the same directory or Python path
from rmbs_loader import DealLoader
from rmbs_state import DealState
from rmbs_compute import ExpressionEngine
from rmbs_waterfall import WaterfallRunner
from rmbs_reporting import ReportGenerator
from rmbs_collateral import CollateralModel

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(message)s') # Simplified log format
logger = logging.getLogger("RMBS.E2E")

def main():
    print("==================================================")
    print("   RMBS ENGINE: END-TO-END SIMULATION")
    print("==================================================\n")

    # 1. LOAD DEAL SPEC
    # --------------------------------------------------------
    json_path = 'deal_spec.json'
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Please create it using the JSON provided above.")
        return

    loader = DealLoader()
    try:
        deal_def = loader.load_from_json(loader._load_schema(json_path)) # Using simplified load for demo
        logger.info(f"✅ Loaded Deal: {deal_def.meta['deal_name']}")
    except Exception as e:
        logger.error(f"❌ Failed to load deal: {e}")
        return

    # 2. INITIALIZE STATE & MODULES
    # --------------------------------------------------------
    state = DealState(deal_def)
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)
    
    # 3. GENERATE COLLATERAL CASHFLOWS (EXTERNAL MODEL)
    # --------------------------------------------------------
    # Assumption: $10MM Balance, 6.0% WAC, 360 Month Term
    # Scenarios: 10% CPR (Prepay), 1% CDR (Default), 40% Severity
    logger.info("--- Generating Collateral Cashflows ---")
    asset_model = CollateralModel(original_balance=10_000_000.0, wac=0.06, wam=360)
    asset_cfs = asset_model.generate_cashflows(periods=60, cpr_vector=0.10, cdr_vector=0.01, sev_vector=0.40)
    
    print(f"   Generated {len(asset_cfs)} periods of asset data.")
    print(f"   First Period Collections: Int=${asset_cfs.iloc[0]['InterestCollected']:,.2f}, Prin=${asset_cfs.iloc[0]['PrincipalCollected']:,.2f}")

    # 4. EXECUTE TIME LOOP
    # --------------------------------------------------------
    start_date = date(2024, 1, 30)
    
    for idx, row in asset_cfs.iterrows():
        period = int(row['Period'])
        current_date = start_date + timedelta(days=30 * period)
        
        # A. Mapping: Move Cash from Asset Model to Deal Funds
        # In deal.json, IAF gets Interest, PAF gets Principal+Recoveries
        int_cash = row['InterestCollected']
        prin_cash = row['PrincipalCollected'] # Includes Recoveries in our simplified model
        loss_amt = row['RealizedLoss']
        
        state.deposit_funds("IAF", int_cash)
        state.deposit_funds("PAF", prin_cash)
        
        # Set external variables
        state.set_variable("RealizedLoss", loss_amt)
        # Assuming trigger passes for this base case
        state.def_.variables['DelinqTrigger'] = "False" 

        # B. Run Waterfall
        runner.run_period(state)
        
        # C. Snapshot
        state.snapshot(current_date)

    # 5. REPORTING & TEST CASES
    # --------------------------------------------------------
    reporter = ReportGenerator(state.history)
    df_results = reporter.generate_cashflow_report()
    
    # Save results
    df_results.to_csv("rmbs_results.csv", index=False)
    logger.info("\n✅ Simulation Complete. Results saved to rmbs_results.csv")
    
    # --------------------------------------------------------
    # AUTOMATED TEST VERIFICATION
    # --------------------------------------------------------
    verify_results(df_results, deal_def)

def verify_results(df: pd.DataFrame, deal):
    print("\n--- CONDUCTING AUTOMATED CHECKS ---")
    
    # Check 1: Reserve Account Funding
    # It should fill up to 20,000 over time
    max_reserve = df['Fund.RESERVE.Balance'].max()
    print(f"1. Max Reserve Balance: ${max_reserve:,.2f} (Target: $20,000)")
    if max_reserve >= 19999.0:
        print("   ✅ PASS: Reserve Account Funded.")
    else:
        print("   ❌ FAIL: Reserve Account did not reach target.")

    # Check 2: Sequential Principal
    # Class A should pay down significantly before Class B pays $1
    # Check Period 10
    if 10 < len(df):
        a_bal_p10 = df.loc[9, 'Bond.ClassA.Balance']
        b_bal_p10 = df.loc[9, 'Bond.ClassB.Balance']
        
        a_orig = 9_000_000
        b_orig = 1_000_000
        
        print(f"2. Period 10 Balances: Class A=${a_bal_p10:,.0f}, Class B=${b_bal_p10:,.0f}")
        
        if a_bal_p10 < a_orig and b_bal_p10 == b_orig:
            print("   ✅ PASS: Principal is Sequential (Class A paying, Class B locked).")
        else:
            print("   ❌ FAIL: Principal allocation logic seems incorrect.")

    # Check 3: Loss Allocation
    # We had ~1% defaults. Losses should hit the deal.
    total_loss_ledger = df['Ledger.CumulativeLoss'].max()
    print(f"3. Total Realized Losses: ${total_loss_ledger:,.2f}")
    
    # Did Class B take a write down?
    b_end_bal = df.iloc[-1]['Bond.ClassB.Balance']
    b_prin_paid = df['Bond.ClassB.Prin_Paid'].sum()
    
    # Expected: End Balance = Original - Paid - Losses
    # If End Balance < Original - Paid, then a Writedown occurred
    implied_writedown = 1_000_000 - b_end_bal - b_prin_paid
    
    if implied_writedown > 0:
        print(f"   ✅ PASS: Class B took writedowns of ${implied_writedown:,.2f}")
    elif total_loss_ledger > 0:
        print("   ❌ FAIL: Losses occurred but Bond Balance did not decrease.")

if __name__ == "__main__":
    main()