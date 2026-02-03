"""
Canonical Loan Schema
=====================

Standardized data model for residential mortgage loans across all sources.

This module provides a unified schema that maps heterogeneous loan data
from various sources (Freddie Mac, Fannie Mae, Non-QM servicers) to a
canonical representation. This enables:

- **Type Safety**: Strong typing for all loan attributes
- **Validation**: Data quality checks on ingestion
- **Interoperability**: Seamless integration across modules
- **ML Feature Engineering**: Consistent fields for model training
- **Web3 Tokenization**: NFT-ready loan representation

Design Philosophy
-----------------
The schema follows industry standards:
- MBA (Mortgage Bankers Association) terminology
- Freddie Mac's "Gold PC" file format
- Fannie Mae's "MBS Disclosure" schema
- Common servicing tape conventions

Example
-------
>>> from engine.loan_schema import LoanRecord, from_freddie_mac_tape
>>> df = pd.read_csv("freddie_mac_tape.csv")
>>> loans = [from_freddie_mac_tape(row) for _, row in df.iterrows()]
>>> avg_fico = sum(loan.fico_score for loan in loans) / len(loans)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Literal
from datetime import date
from decimal import Decimal


# Type aliases for clarity
LoanPurpose = Literal["PURCHASE", "REFI_CASHOUT", "REFI_NOCASH", "CONSTRUCTION", "OTHER"]
PropertyType = Literal["SFR", "CONDO", "COOP", "PUD", "MANUFACTURED", "MULTIFAMILY", "COMMERCIAL", "LAND"]
OccupancyStatus = Literal["OWNER_OCCUPIED", "SECOND_HOME", "INVESTMENT", "UNKNOWN"]
LoanStatus = Literal["CURRENT", "30_DAY_DLQ", "60_DAY_DLQ", "90_DAY_DLQ", "120_DAY_DLQ", "FC", "REO", "PAID_OFF", "DEFAULT"]
DocumentationType = Literal["FULL_DOC", "ALT_DOC", "STATED_INCOME", "NO_DOC", "UNKNOWN"]
AmortizationType = Literal["FIXED_RATE", "ARM", "IO", "BALLOON", "GPM", "OTHER"]
Channel = Literal["RETAIL", "BROKER", "CORRESPONDENT", "BULK", "UNKNOWN"]


@dataclass
class LoanRecord:
    """
    Canonical representation of a residential mortgage loan.
    
    All monetary values are in USD (Decimal for precision).
    All rates are annualized decimals (e.g., 0.055 = 5.5%).
    All dates are in YYYY-MM-DD format.
    
    Attributes are grouped into logical categories:
    1. Identification
    2. Origination
    3. Current Status
    4. Borrower
    5. Property
    6. Underwriting
    7. Performance
    """
    
    # -------------------------------------------------------------------------
    # 1. IDENTIFICATION
    # -------------------------------------------------------------------------
    loan_id: str
    """Unique loan identifier (primary key)."""
    
    servicer_loan_number: Optional[str] = None
    """Servicer's internal loan tracking number."""
    
    pool_id: Optional[str] = None
    """Pool or deal this loan belongs to."""
    
    seller_name: Optional[str] = None
    """Originating lender or seller name."""
    
    # -------------------------------------------------------------------------
    # 2. ORIGINATION
    # -------------------------------------------------------------------------
    origination_date: Optional[date] = None
    """Date loan was originated."""
    
    first_payment_date: Optional[date] = None
    """Date of first scheduled payment."""
    
    original_balance: Decimal = Decimal("0")
    """Original principal balance at origination (UPB at time 0)."""
    
    original_term_months: int = 360
    """Original term in months (e.g., 360 for 30-year)."""
    
    original_rate: Decimal = Decimal("0")
    """Original note rate at origination (annualized)."""
    
    original_ltv: Optional[Decimal] = None
    """Loan-to-Value ratio at origination (0.80 = 80%)."""
    
    original_cltv: Optional[Decimal] = None
    """Combined Loan-to-Value (includes subordinate liens)."""
    
    original_dti: Optional[Decimal] = None
    """Debt-to-Income ratio at origination (0.43 = 43%)."""
    
    loan_purpose: LoanPurpose = "PURCHASE"
    """Purpose of loan (Purchase, Refi, etc.)."""
    
    channel: Channel = "UNKNOWN"
    """Origination channel (Retail, Broker, etc.)."""
    
    # -------------------------------------------------------------------------
    # 3. CURRENT STATUS
    # -------------------------------------------------------------------------
    as_of_date: Optional[date] = None
    """Date of this snapshot (report date)."""
    
    current_balance: Decimal = Decimal("0")
    """Current unpaid principal balance (UPB)."""
    
    current_rate: Decimal = Decimal("0")
    """Current note rate (for ARMs, updated at reset)."""
    
    remaining_term_months: int = 360
    """Remaining term in months."""
    
    loan_age_months: int = 0
    """Number of months since origination."""
    
    loan_status: LoanStatus = "CURRENT"
    """Current delinquency or default status."""
    
    months_delinquent: int = 0
    """Number of months delinquent (0 = current)."""
    
    scheduled_payment: Optional[Decimal] = None
    """Monthly P&I payment (excluding escrow)."""
    
    # -------------------------------------------------------------------------
    # 4. BORROWER
    # -------------------------------------------------------------------------
    fico_score: Optional[int] = None
    """FICO credit score at origination (or most recent)."""
    
    co_borrower_fico: Optional[int] = None
    """Co-borrower FICO score (if applicable)."""
    
    first_time_buyer: Optional[bool] = None
    """True if borrower is first-time homebuyer."""
    
    num_borrowers: int = 1
    """Number of borrowers on loan."""
    
    documentation_type: DocumentationType = "UNKNOWN"
    """Level of income documentation."""
    
    # -------------------------------------------------------------------------
    # 5. PROPERTY
    # -------------------------------------------------------------------------
    property_type: PropertyType = "SFR"
    """Type of property securing the loan."""
    
    num_units: int = 1
    """Number of units in property (1-4 for residential)."""
    
    occupancy_status: OccupancyStatus = "OWNER_OCCUPIED"
    """How borrower occupies the property."""
    
    property_state: Optional[str] = None
    """Two-letter state code (e.g., "CA", "TX")."""
    
    msa: Optional[str] = None
    """Metropolitan Statistical Area code."""
    
    zip_code: Optional[str] = None
    """Property ZIP code."""
    
    current_appraisal_value: Optional[Decimal] = None
    """Most recent appraised property value."""
    
    # -------------------------------------------------------------------------
    # 6. UNDERWRITING
    # -------------------------------------------------------------------------
    amortization_type: AmortizationType = "FIXED_RATE"
    """Type of amortization (Fixed, ARM, IO, etc.)."""
    
    io_period_months: Optional[int] = None
    """Interest-only period in months (if applicable)."""
    
    arm_margin: Optional[Decimal] = None
    """ARM margin over index (if ARM)."""
    
    arm_index: Optional[str] = None
    """ARM index type (e.g., "LIBOR", "SOFR", "CMT")."""
    
    arm_next_reset_date: Optional[date] = None
    """Next ARM rate reset date."""
    
    rate_cap_initial: Optional[Decimal] = None
    """Initial rate change cap (e.g., 0.02 = 2%)."""
    
    rate_cap_periodic: Optional[Decimal] = None
    """Periodic rate change cap."""
    
    rate_cap_lifetime: Optional[Decimal] = None
    """Lifetime rate change cap."""
    
    prepayment_penalty_flag: bool = False
    """True if loan has prepayment penalty."""
    
    pmi_flag: bool = False
    """True if loan requires private mortgage insurance."""
    
    # -------------------------------------------------------------------------
    # 7. PERFORMANCE
    # -------------------------------------------------------------------------
    total_principal_paid: Decimal = Decimal("0")
    """Cumulative principal paid to date."""
    
    total_interest_paid: Decimal = Decimal("0")
    """Cumulative interest paid to date."""
    
    prepayments_ytd: Decimal = Decimal("0")
    """Year-to-date prepayments (unscheduled principal)."""
    
    modifications_count: int = 0
    """Number of times loan has been modified."""
    
    modification_date: Optional[date] = None
    """Date of most recent modification."""
    
    foreclosure_date: Optional[date] = None
    """Date foreclosure was initiated."""
    
    reo_date: Optional[date] = None
    """Date property became REO (Real Estate Owned)."""
    
    disposition_date: Optional[date] = None
    """Date property was sold or disposed of."""
    
    loss_amount: Optional[Decimal] = None
    """Realized loss on default (if applicable)."""
    
    # -------------------------------------------------------------------------
    # 8. METADATA
    # -------------------------------------------------------------------------
    source_system: Optional[str] = None
    """Source system or tape provider (e.g., "Freddie Mac", "Fannie Mae")."""
    
    data_version: Optional[str] = None
    """Version or period of source data."""
    
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    """Flexible field for non-standard attributes."""
    
    # -------------------------------------------------------------------------
    # METHODS
    # -------------------------------------------------------------------------
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling Decimal serialization."""
        result = asdict(self)
        # Convert Decimals to floats for JSON serialization
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
            elif isinstance(value, date):
                result[key] = value.isoformat()
        return result
    
    def validate(self) -> List[str]:
        """
        Validate loan data for consistency and business rules.
        
        Returns
        -------
        list
            List of validation errors (empty if valid).
        """
        errors = []
        
        # Required fields
        if not self.loan_id:
            errors.append("loan_id is required")
        
        # Balance checks
        if self.current_balance < 0:
            errors.append(f"current_balance cannot be negative: {self.current_balance}")
        
        if self.original_balance <= 0:
            errors.append(f"original_balance must be positive: {self.original_balance}")
        
        if self.current_balance > self.original_balance * Decimal("1.1"):
            warnings.warn(
                f"Loan {self.loan_id}: current_balance ({self.current_balance}) > "
                f"110% of original_balance ({self.original_balance}). Possible error."
            )
        
        # Rate checks
        if self.current_rate < 0 or self.current_rate > 0.25:
            errors.append(f"current_rate looks suspicious: {self.current_rate:.2%}")
        
        if self.original_rate < 0 or self.original_rate > 0.25:
            errors.append(f"original_rate looks suspicious: {self.original_rate:.2%}")
        
        # LTV checks
        if self.original_ltv is not None:
            if self.original_ltv < 0 or self.original_ltv > 1.5:
                errors.append(f"original_ltv looks suspicious: {self.original_ltv:.2%}")
        
        # FICO checks
        if self.fico_score is not None:
            if self.fico_score < 300 or self.fico_score > 850:
                errors.append(f"fico_score out of range: {self.fico_score}")
        
        # Term checks
        if self.remaining_term_months > self.original_term_months:
            errors.append(
                f"remaining_term_months ({self.remaining_term_months}) > "
                f"original_term_months ({self.original_term_months})"
            )
        
        if self.loan_age_months < 0:
            errors.append(f"loan_age_months cannot be negative: {self.loan_age_months}")
        
        # Status checks
        if self.loan_status != "CURRENT" and self.months_delinquent == 0:
            errors.append(f"loan_status is {self.loan_status} but months_delinquent is 0")
        
        return errors
    
    def calculate_current_ltv(self) -> Optional[Decimal]:
        """Calculate current LTV (requires current_appraisal_value)."""
        if self.current_appraisal_value and self.current_appraisal_value > 0:
            return self.current_balance / self.current_appraisal_value
        return None
    
    def calculate_equity(self) -> Optional[Decimal]:
        """Calculate borrower equity (if appraisal available)."""
        if self.current_appraisal_value and self.current_appraisal_value > 0:
            return self.current_appraisal_value - self.current_balance
        return None
    
    def is_delinquent(self) -> bool:
        """Check if loan is currently delinquent."""
        return self.months_delinquent > 0
    
    def is_severely_delinquent(self) -> bool:
        """Check if loan is 90+ days delinquent."""
        return self.months_delinquent >= 3
    
    def calculate_paydown_pct(self) -> Decimal:
        """Calculate percentage of original balance that has been paid down."""
        if self.original_balance == 0:
            return Decimal("0")
        return (self.original_balance - self.current_balance) / self.original_balance


# -----------------------------------------------------------------------------
# MAPPING FUNCTIONS
# -----------------------------------------------------------------------------

def from_freddie_mac_tape(row: Dict[str, Any]) -> LoanRecord:
    """
    Map Freddie Mac loan tape to canonical schema.
    
    Parameters
    ----------
    row : dict
        Row from Freddie Mac CSV (column names as keys).
    
    Returns
    -------
    LoanRecord
        Canonical loan record.
    
    Notes
    -----
    Freddie Mac file format:
    - Reference Guide: www.freddiemac.com/research/data/
    """
    return LoanRecord(
        loan_id=str(row.get("LoanId", row.get("LOAN_ID", ""))),
        original_balance=Decimal(str(row.get("OriginalBalance", row.get("ORIGINAL_UPB", 0)))),
        current_balance=Decimal(str(row.get("CurrentBalance", row.get("CURRENT_UPB", 0)))),
        original_rate=Decimal(str(row.get("NoteRate", row.get("ORIGINAL_INTEREST_RATE", 0)))) / Decimal("100"),
        current_rate=Decimal(str(row.get("CurrentRate", row.get("CURRENT_INTEREST_RATE", 0)))) / Decimal("100"),
        original_term_months=int(row.get("OriginalTerm", row.get("ORIGINAL_LOAN_TERM", 360))),
        remaining_term_months=int(row.get("RemainingTermMonths", row.get("REMAINING_MONTHS_TO_MATURITY", 360))),
        fico_score=int(row.get("FICO", row.get("CREDIT_SCORE", 0))) if row.get("FICO") or row.get("CREDIT_SCORE") else None,
        original_ltv=Decimal(str(row.get("LTV", row.get("ORIGINAL_LTV", 0)))) / Decimal("100") if row.get("LTV") or row.get("ORIGINAL_LTV") else None,
        property_type=_map_freddie_property_type(row.get("PropertyType", row.get("PROPERTY_TYPE", "SFR"))),
        occupancy_status=_map_freddie_occupancy(row.get("OccupancyStatus", row.get("OCCUPANCY_STATUS", "P"))),
        loan_purpose=_map_freddie_purpose(row.get("LoanPurpose", row.get("LOAN_PURPOSE", "P"))),
        property_state=str(row.get("PropertyState", row.get("PROPERTY_STATE", ""))),
        source_system="Freddie Mac",
        custom_fields={k: v for k, v in row.items() if k not in ["LoanId", "OriginalBalance", "CurrentBalance"]}
    )


def from_fannie_mae_tape(row: Dict[str, Any]) -> LoanRecord:
    """Map Fannie Mae loan tape to canonical schema."""
    return LoanRecord(
        loan_id=str(row.get("LoanId", row.get("Loan Identifier", ""))),
        original_balance=Decimal(str(row.get("OriginalBalance", row.get("Original UPB", 0)))),
        current_balance=Decimal(str(row.get("CurrentBalance", row.get("Current Actual UPB", 0)))),
        original_rate=Decimal(str(row.get("NoteRate", row.get("Original Interest Rate", 0)))) / Decimal("100"),
        current_rate=Decimal(str(row.get("CurrentRate", row.get("Current Interest Rate", 0)))) / Decimal("100"),
        fico_score=int(row.get("FICO", row.get("Credit Score", 0))) if row.get("FICO") or row.get("Credit Score") else None,
        source_system="Fannie Mae",
        custom_fields={k: v for k, v in row.items()}
    )


def from_generic_tape(row: Dict[str, Any], column_mapping: Dict[str, str]) -> LoanRecord:
    """
    Map generic servicer tape to canonical schema using custom column mapping.
    
    Parameters
    ----------
    row : dict
        Row from servicer tape.
    column_mapping : dict
        Mapping from canonical field names to servicer column names.
        Example: {"loan_id": "LoanNumber", "current_balance": "UPB"}
    
    Returns
    -------
    LoanRecord
        Canonical loan record.
    """
    kwargs = {}
    
    # Map each canonical field using the provided mapping
    for canon_field, servicer_column in column_mapping.items():
        if servicer_column in row:
            value = row[servicer_column]
            
            # Type conversion based on field type
            if canon_field in ["original_balance", "current_balance", "original_ltv", "original_rate", "current_rate"]:
                kwargs[canon_field] = Decimal(str(value)) if value else Decimal("0")
            elif canon_field in ["original_term_months", "remaining_term_months", "fico_score", "loan_age_months"]:
                kwargs[canon_field] = int(value) if value else 0
            else:
                kwargs[canon_field] = value
    
    # Ensure loan_id is set
    if "loan_id" not in kwargs:
        raise ValueError("loan_id must be mapped in column_mapping")
    
    return LoanRecord(**kwargs)


# Helper mapping functions for Freddie Mac conventions
def _map_freddie_property_type(code: str) -> PropertyType:
    """Map Freddie Mac property type code to canonical."""
    mapping = {
        "SF": "SFR", "PU": "PUD", "CO": "CONDO", "CP": "COOP",
        "MH": "MANUFACTURED", "LH": "SFR"
    }
    return mapping.get(code, "SFR")


def _map_freddie_occupancy(code: str) -> OccupancyStatus:
    """Map Freddie Mac occupancy code to canonical."""
    mapping = {
        "P": "OWNER_OCCUPIED", "S": "SECOND_HOME", "I": "INVESTMENT"
    }
    return mapping.get(code, "OWNER_OCCUPIED")


def _map_freddie_purpose(code: str) -> LoanPurpose:
    """Map Freddie Mac loan purpose code to canonical."""
    mapping = {
        "P": "PURCHASE", "C": "REFI_CASHOUT", "N": "REFI_NOCASH", "R": "REFI_NOCASH"
    }
    return mapping.get(code, "PURCHASE")
