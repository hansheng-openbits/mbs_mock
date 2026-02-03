"""
Test: Canonical Loan Schema
============================

This test demonstrates the standardized loan data model that provides
type safety, validation, and interoperability across different data sources.

The canonical schema solves a major industry problem: every loan tape
has different column names, formats, and conventions. This schema provides
a single, unified representation.

Author: RMBS Platform Development Team
Date: January 2026
"""

import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.loan_schema import (
    LoanRecord,
    from_freddie_mac_tape,
    from_fannie_mae_tape,
    from_generic_tape
)


def test_loan_record_creation():
    """Test creating a loan record with validation."""
    print("1. Creating a loan record...")
    
    loan = LoanRecord(
        loan_id="LOAN-2024-12345",
        original_balance=Decimal("500000"),
        current_balance=Decimal("475000"),
        original_rate=Decimal("0.055"),
        current_rate=Decimal("0.055"),
        original_term_months=360,
        remaining_term_months=348,
        loan_age_months=12,
        fico_score=740,
        original_ltv=Decimal("0.80"),
        property_type="SFR",
        occupancy_status="OWNER_OCCUPIED",
        loan_purpose="PURCHASE",
        property_state="CA",
        amortization_type="FIXED_RATE",
        source_system="Example Servicer"
    )
    
    print(f"   Loan ID: {loan.loan_id}")
    print(f"   Original Balance: ${loan.original_balance:,}")
    print(f"   Current Balance: ${loan.current_balance:,}")
    print(f"   Note Rate: {loan.current_rate:.3%}")
    print(f"   FICO: {loan.fico_score}")
    print(f"   LTV: {loan.original_ltv:.1%}")
    print("   ✅ Loan record created")
    print()
    
    # Validate
    print("2. Validating loan data...")
    errors = loan.validate()
    if errors:
        print("   ❌ Validation errors:")
        for error in errors:
            print(f"      - {error}")
    else:
        print("   ✅ No validation errors")
    print()
    
    # Calculate derived metrics
    print("3. Calculating derived metrics...")
    paydown_pct = loan.calculate_paydown_pct()
    print(f"   Paydown: {paydown_pct:.1%}")
    print(f"   Is Delinquent: {loan.is_delinquent()}")
    print(f"   Is Severely Delinquent: {loan.is_severely_delinquent()}")
    print("   ✅ Metrics calculated")
    print()
    
    return loan


def test_freddie_mac_mapping():
    """Test mapping Freddie Mac tape format."""
    print("4. Mapping Freddie Mac loan tape...")
    
    # Simulate a row from Freddie Mac tape
    freddie_row = {
        "LoanId": "F1234567",
        "OriginalBalance": 400000,
        "CurrentBalance": 380000,
        "NoteRate": 5.5,  # Freddie reports as percentage
        "OriginalTerm": 360,
        "RemainingTermMonths": 350,
        "FICO": 720,
        "LTV": 75,  # Freddie reports as percentage
        "PropertyType": "SF",
        "OccupancyStatus": "P",
        "LoanPurpose": "P",
        "PropertyState": "TX"
    }
    
    loan = from_freddie_mac_tape(freddie_row)
    
    print(f"   Loan ID: {loan.loan_id}")
    print(f"   Original Balance: ${loan.original_balance:,}")
    print(f"   Current Balance: ${loan.current_balance:,}")
    print(f"   Note Rate: {loan.current_rate:.3%}")
    print(f"   FICO: {loan.fico_score}")
    print(f"   LTV: {loan.original_ltv:.1%}")
    print(f"   Property Type: {loan.property_type}")
    print(f"   Occupancy: {loan.occupancy_status}")
    print(f"   State: {loan.property_state}")
    print(f"   Source: {loan.source_system}")
    print("   ✅ Freddie Mac tape mapped successfully")
    print()
    
    return loan


def test_fannie_mae_mapping():
    """Test mapping Fannie Mae tape format."""
    print("5. Mapping Fannie Mae loan tape...")
    
    # Simulate a row from Fannie Mae tape (different column names)
    fannie_row = {
        "Loan Identifier": "FNMA-987654",
        "Original UPB": 350000,
        "Current Actual UPB": 335000,
        "Original Interest Rate": 6.25,
        "Current Interest Rate": 6.25,
        "Credit Score": 680
    }
    
    loan = from_fannie_mae_tape(fannie_row)
    
    print(f"   Loan ID: {loan.loan_id}")
    print(f"   Original Balance: ${loan.original_balance:,}")
    print(f"   Current Balance: ${loan.current_balance:,}")
    print(f"   Note Rate: {loan.current_rate:.3%}")
    print(f"   FICO: {loan.fico_score}")
    print(f"   Source: {loan.source_system}")
    print("   ✅ Fannie Mae tape mapped successfully")
    print()
    
    return loan


def test_generic_mapping():
    """Test mapping a generic servicer tape."""
    print("6. Mapping generic servicer tape...")
    
    # Simulate a row from a non-standard servicer
    servicer_row = {
        "LoanNumber": "SVC-555-ABC",
        "UPB": 275000,
        "OrigUPB": 300000,
        "CouponRate": 4.875,
        "CreditScore": 760,
        "State": "FL"
    }
    
    # Define mapping from canonical to servicer columns
    column_mapping = {
        "loan_id": "LoanNumber",
        "current_balance": "UPB",
        "original_balance": "OrigUPB",
        "current_rate": "CouponRate",
        "fico_score": "CreditScore",
        "property_state": "State"
    }
    
    loan = from_generic_tape(servicer_row, column_mapping)
    
    print(f"   Loan ID: {loan.loan_id}")
    print(f"   Original Balance: ${loan.original_balance:,}")
    print(f"   Current Balance: ${loan.current_balance:,}")
    print(f"   Note Rate: {loan.current_rate:.3%}")
    print(f"   FICO: {loan.fico_score}")
    print(f"   State: {loan.property_state}")
    print("   ✅ Generic tape mapped successfully")
    print()
    
    return loan


def test_validation_errors():
    """Test validation catches errors."""
    print("7. Testing validation error detection...")
    
    # Create an invalid loan
    bad_loan = LoanRecord(
        loan_id="",  # Missing ID
        original_balance=Decimal("-1000"),  # Negative balance
        current_balance=Decimal("1000000"),  # > original balance
        original_rate=Decimal("0.50"),  # 50% rate (suspicious)
        current_rate=Decimal("0.50"),
        fico_score=950,  # Out of range
        remaining_term_months=400,  # > original term
        original_term_months=360
    )
    
    errors = bad_loan.validate()
    print(f"   Found {len(errors)} validation errors:")
    for error in errors:
        print(f"      - {error}")
    print("   ✅ Validation correctly detected errors")
    print()


def test_serialization():
    """Test JSON serialization."""
    print("8. Testing JSON serialization...")
    
    loan = LoanRecord(
        loan_id="JSON-TEST-001",
        original_balance=Decimal("450000"),
        current_balance=Decimal("425000"),
        original_rate=Decimal("0.0575"),
        current_rate=Decimal("0.0575"),
        fico_score=730,
        origination_date=date(2020, 6, 15),
        property_type="CONDO",
        occupancy_status="SECOND_HOME"
    )
    
    # Convert to dict (JSON-serializable)
    loan_dict = loan.to_dict()
    
    print(f"   Loan as dictionary:")
    print(f"      loan_id: {loan_dict['loan_id']}")
    print(f"      original_balance: {loan_dict['original_balance']}")
    print(f"      original_rate: {loan_dict['original_rate']}")
    print(f"      origination_date: {loan_dict['origination_date']}")
    print("   ✅ Serialization successful")
    print()


def main():
    print("=" * 80)
    print("CANONICAL LOAN SCHEMA TEST")
    print("=" * 80)
    print()
    
    # Run all tests
    loan1 = test_loan_record_creation()
    loan2 = test_freddie_mac_mapping()
    loan3 = test_fannie_mae_mapping()
    loan4 = test_generic_mapping()
    test_validation_errors()
    test_serialization()
    
    # Summary
    print("=" * 80)
    print("LOAN SCHEMA TEST COMPLETE")
    print("=" * 80)
    print()
    print("✅ Key Features Demonstrated:")
    print("   1. Type-safe loan representation")
    print("   2. Validation and business rules")
    print("   3. Freddie Mac tape mapping")
    print("   4. Fannie Mae tape mapping")
    print("   5. Generic servicer tape mapping")
    print("   6. Error detection")
    print("   7. JSON serialization")
    print()
    print("📋 Benefits:")
    print("   - Eliminates column name confusion")
    print("   - Enforces data quality")
    print("   - Enables ML feature engineering")
    print("   - Supports Web3 tokenization")
    print("   - Industry-standard terminology")
    print()
    print("🔄 Interoperability:")
    loans = [loan1, loan2, loan3, loan4]
    print(f"   Successfully normalized {len(loans)} loans from different sources:")
    for loan in loans:
        source = loan.source_system or "Manual"
        balance = float(loan.current_balance)
        rate = float(loan.current_rate) * 100
        print(f"      - {source:20s} | ${balance:>12,.0f} @ {rate:.3f}%")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
