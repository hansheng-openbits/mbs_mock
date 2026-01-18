import pandas as pd
import pytest
import os
from rmbs_etl_industry import TapeProcessor, ETLConfig

# Ensure test dir exists
os.makedirs("test_data", exist_ok=True)

def create_dirty_tape():
    """Generates a messy CSV file mimicking a real Servicer Tape."""
    data = [
        # Loan 1: Standard Current Loan
        {
            "LnID": "1001", "RptDate": "2024-02-25", "Bal": "500000.00", 
            "IntPd": "2000.00", "PrinPd": "1000.00", "DQ": "0",
            "LiqProc": "", "LiqExp": "", "LossAmt": "0"
        },
        # Loan 2: 60 Days Delinquent (Trigger Testing)
        {
            "LnID": "1002", "RptDate": "02/25/2024", "Bal": "$300,000.00", # Dirty formatting
            "IntPd": "0.00", "PrinPd": "0.00", "DQ": "65",
            "LiqProc": "0", "LiqExp": "0", "LossAmt": "0"
        },
        # Loan 3: Liquidated (Loss Testing)
        # Note: Bal is 0, but we have proceeds and loss
        {
            "LnID": "1003", "RptDate": "2024-02-25", "Bal": "0.00", 
            "IntPd": "0", "PrinPd": "0", "DQ": "0",
            "LiqProc": "150000.00", "LiqExp": "10000.00", "LossAmt": "50000.00"
        },
        # Loan 4: Negative Balance (Should Fail Validation)
        # We will add this in a separate test to check failure
    ]
    df = pd.DataFrame(data)
    path = "test_data/dirty_tape_v1.csv"
    df.to_csv(path, index=False)
    return path

def test_etl_happy_path():
    """Tests the Mapper, Cleaner, and Aggregator."""
    csv_path = create_dirty_tape()
    
    # 1. Define Config (Mapping Dirty Headers -> Canonical)
    config = ETLConfig(
        field_map={
            "LnID": "loan_id",
            "RptDate": "period_date",
            "Bal": "ending_balance",
            "IntPd": "interest_paid",
            "PrinPd": "principal_paid",
            "DQ": "days_past_due",
            "LiqProc": "liquidation_proceeds",
            "LiqExp": "liquidation_expenses",
            "LossAmt": "principal_loss" # We map explicit loss column
        }
    )
    
    processor = TapeProcessor(config)
    
    # 2. Run Pipeline
    df_clean = processor.ingest_tape(csv_path)
    
    # 3. Assertions on Cleaning
    print("\n--- Test 1: Data Cleaning ---")
    
    # Check Currency Cleaning (Loan 2 had "$300,000.00")
    loan_2_bal = df_clean.loc[df_clean['loan_id'] == 1002, 'ending_balance'].values[0]
    assert loan_2_bal == 300000.0
    print(f"✅ Currency Stripping Worked: Mapped '$300,000.00' -> {loan_2_bal}")
    
    # Check Date Parsing (Mixed formats handled?)
    assert pd.api.types.is_datetime64_any_dtype(df_clean['period_date'])
    print("✅ Date Parsing Worked.")

    # 4. Assertions on Aggregation
    print("\n--- Test 2: Pool Aggregation ---")
    aggs = processor.aggregate_pool_stats(df_clean)
    
    # Interest: Loan 1 (2000) + Others (0) = 2000
    assert aggs['TotalInterest'] == 2000.0
    
    # Principal: Loan 1 Prin (1000) + Loan 3 Liq Proceeds (150,000) = 151,000
    # Note: Our Aggregator adds Prin + LiqProceeds
    assert aggs['TotalPrincipal'] == 151000.0
    
    # Loss: Loan 3 (50,000)
    assert aggs['RealizedLoss'] == 50000.0
    
    # Delinquency Trigger: Loan 2 (300k) is > 60 days
    assert aggs['Delinq60_Amount'] == 300000.0
    
    print(f"✅ Aggregates Verified: {aggs}")

def test_etl_validation_failure():
    """Tests that the pipeline throws errors on garbage data."""
    print("\n--- Test 3: Validation Failure ---")
    
    df = pd.DataFrame([
        {"LnID": "99", "Bal": "-500.00", "IntPd": "0", "PrinPd": "0"}
    ])
    path = "test_data/fail_tape.csv"
    df.to_csv(path, index=False)
    
    config = ETLConfig(field_map={"LnID": "loan_id", "Bal": "ending_balance", "IntPd": "interest_paid", "PrinPd": "principal_paid"})
    processor = TapeProcessor(config)
    
    try:
        processor.ingest_tape(path)
        assert False, "Should have raised ValueError for negative balance"
    except ValueError as e:
        print(f"✅ Caught Expected Error: {e}")

if __name__ == "__main__":
    test_etl_happy_path()
    test_etl_validation_failure()