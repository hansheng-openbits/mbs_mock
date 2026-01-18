import os
import glob
import logging
import pandas as pd
from datetime import datetime

# Import Core Modules
from rmbs_loader import DealLoader
from rmbs_state import DealState
from rmbs_compute import ExpressionEngine
from rmbs_waterfall import WaterfallRunner
from rmbs_reporting import ReportGenerator

# Import Industry ETL Module
from rmbs_etl_industry import TapeProcessor, ETLConfig

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("RMBS.Runner")

def main():
    print("==================================================")
    print("   RMBS ENGINE: DATA-DRIVEN EXECUTION")
    print("==================================================\n")

    # 1. SETUP ENGINE
    # --------------------------------------------------------
    logger.info("Initializing Engine Components...")
    
    # Load Deal Rules
    loader = DealLoader('rmbs_schema.json')
    if not os.path.exists('deal_spec.json'):
        logger.error("deal_spec.json not found! Please generate it first.")
        return
        
    deal_def = loader.load_from_json(loader._load_schema('deal_spec.json'))
    
    # Initialize State & Logic
    state = DealState(deal_def)
    engine = ExpressionEngine()
    runner = WaterfallRunner(engine)
    
    # 2. SETUP ETL PIPELINE
    # --------------------------------------------------------
    # Define the mapping for your specific "Dirty" Tapes.
    # Adjust 'field_map' to match the actual headers in your CSV files.
    etl_config = ETLConfig(
        field_map={
            "LnID": "loan_id",
            "RptDate": "period_date",
            "Bal": "ending_balance",
            "IntPd": "interest_paid",
            "PrinPd": "principal_paid",
            "DQ": "days_past_due",
            "LiqProc": "liquidation_proceeds",
            "LiqExp": "liquidation_expenses",
            "LossAmt": "principal_loss" # Explicit loss column if available
        }
    )
    etl_processor = TapeProcessor(etl_config)

    # 3. DISCOVER DATA
    # --------------------------------------------------------
    # Look for files matching pattern in data/ folder
    tape_files = sorted(glob.glob("test_data/*_tape.csv"))
    
    if not tape_files:
        logger.warning("No data files found in 'data/' folder. Please generate mock data first.")
        return

    logger.info(f"Found {len(tape_files)} tape(s) to process.")

    # 4. EXECUTION LOOP (Time Series)
    # --------------------------------------------------------
    for i, tape_path in enumerate(tape_files):
        period_idx = i + 1
        logger.info(f"\n--- Processing Period {period_idx}: {os.path.basename(tape_path)} ---")
        
        # A. ETL: Ingest & Clean
        try:
            df_clean = etl_processor.ingest_tape(tape_path)
            aggs = etl_processor.aggregate_pool_stats(df_clean)
        except Exception as e:
            logger.error(f"ETL Failed for {tape_path}: {e}")
            break # Stop simulation on bad data

        # Log Inputs
        logger.info(f"    [IN] Interest: ${aggs['TotalInterest']:,.2f}")
        logger.info(f"    [IN] Principal: ${aggs['TotalPrincipal']:,.2f}")
        logger.info(f"    [IN] Losses:    ${aggs['RealizedLoss']:,.2f}")

        # B. STATE INJECTION: Feed Data to Engine
        # 1. Deposit Cash
        state.deposit_funds("IAF", aggs['TotalInterest'])
        state.deposit_funds("PAF", aggs['TotalPrincipal'])
        
        # 2. Update Variables
        state.set_variable("RealizedLoss", aggs['RealizedLoss'])
        state.set_variable("CurrentPoolBalance", aggs['EndPoolBalance'])
        
        # 3. Update Triggers (Delinquency Logic)
        # Calculate ratio: 60+ Days Delinq Balance / Total Balance
        delinq_bal = aggs['Delinq60_Amount']
        total_bal = aggs['EndPoolBalance']
        
        delinq_ratio = 0.0
        if total_bal > 0:
            delinq_ratio = delinq_bal / total_bal
            
        # Update the Deal Variable so the JSON rule "DelinqTrigger == False" works
        is_breached = delinq_ratio > 0.05 # 5% Threshold
        state.def_.variables['DelinqTrigger'] = str(is_breached)
        
        if is_breached:
            logger.warning(f"    ⚠️ TRIGGER ACTIVE: Delinq Ratio {delinq_ratio:.2%} > 5.00%")

        # C. WATERFALL EXECUTION
        runner.run_period(state)
        
        # D. SNAPSHOT
        # Try to parse date from filename or tape, else iterate
        current_date_str = df_clean['period_date'].iloc[0] if not df_clean.empty else f"Period-{period_idx}"
        # Simplified date object creation
        try:
            # Assuming pandas converted it to datetime, take the date component
            snap_date = df_clean['period_date'].dt.date.iloc[0]
        except:
            snap_date = f"Period_{period_idx}"
            
        state.snapshot(snap_date)

    # 5. REPORTING
    # --------------------------------------------------------
    logger.info("\n--- Generating Final Report ---")
    reporter = ReportGenerator(state.history)
    df_results = reporter.generate_cashflow_report()
    
    output_path = "rmbs_actuals_output.csv"
    df_results.to_csv(output_path, index=False)
    logger.info(f"✅ Run Complete. Output saved to: {output_path}")
    
    # Optional: Print Summary to Console
    if not df_results.empty:
        print("\nSummary of Results:")
        cols = ['Period', 'Bond.ClassA.Prin_Paid', 'Bond.ClassB.Prin_Paid', 'Ledger.CumulativeLoss']
        # Filter cols that actually exist
        valid_cols = [c for c in cols if c in df_results.columns]
        print(df_results[valid_cols].to_string(index=False))

if __name__ == "__main__":
    main()