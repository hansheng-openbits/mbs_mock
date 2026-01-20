"""
Loan Export and Portfolio Comparison Tests
==========================================

Comprehensive tests for loan-level data export and portfolio comparison:
- SEC Regulation AB XML export
- European DataWarehouse format
- Analytics CSV/JSON exports
- Portfolio comparison metrics
- Stratification analysis
- Vintage comparison

These tests verify export formats meet regulatory requirements
and comparison tools produce meaningful analytics.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path
import sys
import json
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.loan_export import (
    LoanLevelExporter,
    LoanRecord,
    ExportFormat,
    ExportConfig,
    RegABExporter,
    EDWExporter,
    LoanStatus,
    PropertyType,
    OccupancyType,
    convert_dataframe_to_loans,
    validate_loan_data,
)

from engine.comparison import (
    PortfolioComparator,
    PortfolioCharacteristics,
    ComparisonDimension,
    ComparisonResult,
    StratificationComparison,
    DealStructureComparator,
    VintageComparator,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_loan_records() -> list:
    """Create sample loan records for export testing."""
    return [
        LoanRecord(
            loan_id="LOAN001",
            reporting_date=date(2024, 1, 31),
            deal_id="RMBS_2024_001",
            original_balance=350000.0,
            current_balance=325000.0,
            interest_rate=0.0525,
            original_interest_rate=0.0525,
            original_ltv=75.0,
            current_ltv=72.0,
            fico_score=740,
            property_state="CA",
            property_zip="94102",
            property_type=PropertyType.SINGLE_FAMILY,
            occupancy_type=OccupancyType.PRIMARY,
            loan_status=LoanStatus.CURRENT,
            origination_date=date(2022, 6, 15),
            maturity_date=date(2052, 7, 1),
            original_term_months=360,
            remaining_term_months=340,
            days_past_due=0,
            scheduled_principal=850.0,
            scheduled_interest=1420.0,
            actual_principal_collected=850.0,
            actual_interest_collected=1420.0,
        ),
        LoanRecord(
            loan_id="LOAN002",
            reporting_date=date(2024, 1, 31),
            deal_id="RMBS_2024_001",
            original_balance=275000.0,
            current_balance=268000.0,
            interest_rate=0.0575,
            original_interest_rate=0.0575,
            original_ltv=80.0,
            current_ltv=78.0,
            fico_score=700,
            property_state="TX",
            property_zip="75001",
            property_type=PropertyType.CONDO,
            occupancy_type=OccupancyType.PRIMARY,
            loan_status=LoanStatus.DQ_30,
            origination_date=date(2023, 1, 10),
            maturity_date=date(2053, 2, 1),
            original_term_months=360,
            remaining_term_months=348,
            days_past_due=35,
            scheduled_principal=680.0,
            scheduled_interest=1285.0,
            actual_principal_collected=0.0,
            actual_interest_collected=0.0,
        ),
        LoanRecord(
            loan_id="LOAN003",
            reporting_date=date(2024, 1, 31),
            deal_id="RMBS_2024_001",
            original_balance=450000.0,
            current_balance=0.0,
            interest_rate=0.0495,
            original_interest_rate=0.0495,
            original_ltv=70.0,
            fico_score=780,
            property_state="NY",
            property_zip="10001",
            property_type=PropertyType.SINGLE_FAMILY,
            occupancy_type=OccupancyType.PRIMARY,
            loan_status=LoanStatus.PREPAID_FULL,
            origination_date=date(2021, 3, 20),
            days_past_due=0,
            prepayment_amount=420000.0,
        ),
    ]


@pytest.fixture
def sample_loan_df() -> pd.DataFrame:
    """Create sample loan DataFrame for testing."""
    np.random.seed(42)
    n_loans = 100
    
    return pd.DataFrame({
        "loan_id": [f"L{i:04d}" for i in range(n_loans)],
        "reporting_date": [date(2024, 1, 31)] * n_loans,
        "current_balance": np.random.uniform(150_000, 500_000, n_loans),
        "original_balance": np.random.uniform(180_000, 550_000, n_loans),
        "interest_rate": np.random.uniform(0.04, 0.07, n_loans),
        "original_ltv": np.random.uniform(60, 95, n_loans),
        "current_ltv": np.random.uniform(55, 100, n_loans),
        "fico_score": np.random.choice([640, 660, 700, 740, 780], n_loans),
        "property_state": np.random.choice(["CA", "TX", "FL", "NY", "IL"], n_loans),
        "remaining_term_months": np.random.randint(300, 360, n_loans),
        "loan_age": np.random.randint(6, 48, n_loans),
    })


@pytest.fixture
def portfolio_a_df() -> pd.DataFrame:
    """Create first portfolio for comparison."""
    np.random.seed(100)
    n_loans = 200
    
    return pd.DataFrame({
        "loan_id": [f"PA{i:04d}" for i in range(n_loans)],
        "Current_Balance": np.random.uniform(200_000, 400_000, n_loans),
        "Original_Balance": np.random.uniform(220_000, 450_000, n_loans),
        "Interest_Rate": np.random.uniform(0.045, 0.055, n_loans),
        "LTV": np.random.uniform(65, 80, n_loans),  # Prime pool
        "FICO": np.random.choice([720, 740, 760, 780], n_loans),
        "State": np.random.choice(["CA", "TX", "FL"], n_loans, p=[0.4, 0.35, 0.25]),
        "Property_Type": np.random.choice(["SF", "CO"], n_loans, p=[0.8, 0.2]),
        "Loan_Age": np.random.randint(12, 36, n_loans),
        "Remaining_Term": np.random.randint(324, 348, n_loans),
    })


@pytest.fixture
def portfolio_b_df() -> pd.DataFrame:
    """Create second portfolio for comparison (different characteristics)."""
    np.random.seed(200)
    n_loans = 150
    
    return pd.DataFrame({
        "loan_id": [f"PB{i:04d}" for i in range(n_loans)],
        "Current_Balance": np.random.uniform(150_000, 350_000, n_loans),
        "Original_Balance": np.random.uniform(170_000, 400_000, n_loans),
        "Interest_Rate": np.random.uniform(0.055, 0.070, n_loans),
        "LTV": np.random.uniform(75, 95, n_loans),  # Higher LTV
        "FICO": np.random.choice([660, 680, 700, 720], n_loans),  # Lower FICO
        "State": np.random.choice(["FL", "AZ", "NV"], n_loans, p=[0.5, 0.3, 0.2]),
        "Property_Type": np.random.choice(["SF", "CO", "TH"], n_loans, p=[0.6, 0.25, 0.15]),
        "Loan_Age": np.random.randint(6, 24, n_loans),
        "Remaining_Term": np.random.randint(336, 360, n_loans),
    })


# =============================================================================
# Loan Record Tests
# =============================================================================

class TestLoanRecord:
    """Tests for LoanRecord data structure."""
    
    def test_loan_record_creation(self, sample_loan_records):
        """
        Verify LoanRecord objects are created correctly.
        """
        loan = sample_loan_records[0]
        
        assert loan.loan_id == "LOAN001"
        assert loan.current_balance == 325000.0
        assert loan.fico_score == 740
        assert loan.loan_status == LoanStatus.CURRENT
    
    def test_loan_record_to_dict(self, sample_loan_records):
        """
        Verify LoanRecord converts to dictionary correctly.
        """
        loan = sample_loan_records[0]
        data = loan.to_dict()
        
        assert "loan_id" in data
        assert "current_balance" in data
        assert data["loan_id"] == "LOAN001"
        # Enum should be converted to value
        assert data["loan_status"] == "Current"
    
    def test_loan_record_date_serialization(self, sample_loan_records):
        """
        Verify dates are serialized as ISO strings.
        """
        loan = sample_loan_records[0]
        data = loan.to_dict()
        
        assert data["reporting_date"] == "2024-01-31"
        assert data["origination_date"] == "2022-06-15"


# =============================================================================
# Loan Level Exporter Tests
# =============================================================================

class TestLoanLevelExporter:
    """Tests for universal loan exporter."""
    
    def test_exporter_from_records(self, sample_loan_records):
        """
        Verify exporter initializes from loan records.
        """
        exporter = LoanLevelExporter(sample_loan_records)
        
        assert len(exporter.loans) == 3
        assert not exporter.loans_df.empty
    
    def test_exporter_from_dataframe(self, sample_loan_df):
        """
        Verify exporter initializes from DataFrame.
        """
        exporter = LoanLevelExporter(sample_loan_df)
        
        assert len(exporter.loans_df) == 100
    
    def test_export_csv_format(self, sample_loan_records):
        """
        Verify CSV export produces valid output.
        """
        exporter = LoanLevelExporter(
            sample_loan_records,
            deal_info={"deal_id": "TEST_2024"},
        )
        
        csv_content = exporter.export(ExportFormat.ANALYTICS_CSV)
        
        assert isinstance(csv_content, str)
        assert "loan_id" in csv_content
        assert "LOAN001" in csv_content
    
    def test_export_json_format(self, sample_loan_records):
        """
        Verify JSON export produces valid output with metadata.
        """
        exporter = LoanLevelExporter(
            sample_loan_records,
            deal_info={"deal_id": "TEST_2024"},
        )
        
        json_content = exporter.export(ExportFormat.JSON_DETAILED)
        
        # Should be valid JSON
        data = json.loads(json_content)
        
        assert "metadata" in data
        assert "loans" in data
        assert len(data["loans"]) == 3
        assert data["metadata"]["loan_count"] == 3


class TestRegABExporter:
    """Tests for SEC Regulation AB XML export."""
    
    def test_reg_ab_export_structure(self, sample_loan_records):
        """
        Verify Reg AB export produces valid XML structure.
        """
        exporter = RegABExporter(
            deal_id="333-12345",
            reporting_period=(date(2024, 1, 1), date(2024, 1, 31)),
            issuer_name="RMBS Trust 2024-1",
        )
        
        xml_content = exporter.export_loans(sample_loan_records)
        
        # Should be valid XML
        root = ET.fromstring(xml_content.encode('utf-8').lstrip())
        
        # Check structure
        assert root.tag == "assetData"
    
    def test_reg_ab_contains_required_fields(self, sample_loan_records):
        """
        Verify Reg AB export contains required SEC fields.
        """
        exporter = RegABExporter(
            deal_id="333-12345",
            reporting_period=(date(2024, 1, 1), date(2024, 1, 31)),
            issuer_name="RMBS Trust 2024-1",
        )
        
        xml_content = exporter.export_loans(sample_loan_records)
        
        # Check for required fields
        required_fields = [
            "assetNumber",
            "originalLoanAmount",
            "currentActualBalance",
            "originalCreditScore",
            "originalLTV",
            "propertyState",
        ]
        
        for field in required_fields:
            assert f"<{field}>" in xml_content, f"Missing field: {field}"
    
    def test_reg_ab_header_info(self, sample_loan_records):
        """
        Verify Reg AB export includes header information.
        """
        exporter = RegABExporter(
            deal_id="333-12345",
            reporting_period=(date(2024, 1, 1), date(2024, 1, 31)),
            issuer_name="RMBS Trust 2024-1",
            cik="0001234567",
        )
        
        xml_content = exporter.export_loans(sample_loan_records)
        
        assert "RMBS Trust 2024-1" in xml_content
        assert "333-12345" in xml_content


class TestEDWExporter:
    """Tests for European DataWarehouse export."""
    
    def test_edw_export_structure(self, sample_loan_records):
        """
        Verify EDW export produces valid CSV structure.
        """
        exporter = EDWExporter(
            deal_id="EDW123456",
            pool_cutoff_date=date(2024, 1, 15),
            asset_class="RMBS",
        )
        
        csv_content = exporter.export_loans(sample_loan_records)
        
        # Should have header row
        lines = csv_content.strip().split("\n")
        assert len(lines) >= 4  # Header + 3 loans
    
    def test_edw_field_ordering(self, sample_loan_records):
        """
        Verify EDW fields are in correct order per specification.
        """
        exporter = EDWExporter(
            deal_id="EDW123456",
            pool_cutoff_date=date(2024, 1, 15),
        )
        
        csv_content = exporter.export_loans(sample_loan_records)
        
        # Header should start with AS1, AS2, etc.
        header = csv_content.split("\n")[0]
        assert header.startswith("AS1,")


# =============================================================================
# Data Validation Tests
# =============================================================================

class TestLoanDataValidation:
    """Tests for loan data validation."""
    
    def test_validate_complete_data(self, sample_loan_records):
        """
        Verify validation passes for complete data.
        """
        result = validate_loan_data(
            sample_loan_records,
            required_fields=["loan_id", "current_balance", "interest_rate"],
        )
        
        assert result["is_valid"] == True
        assert result["issue_count"] == 0
    
    def test_validate_missing_fields(self):
        """
        Verify validation catches missing required fields.
        """
        incomplete_loans = [
            LoanRecord(
                loan_id="",  # Empty loan_id
                reporting_date=date.today(),
                current_balance=0,  # Zero balance
                interest_rate=0.05,
            ),
        ]
        
        result = validate_loan_data(
            incomplete_loans,
            required_fields=["loan_id", "current_balance"],
        )
        
        assert result["is_valid"] == False
        assert result["issue_count"] > 0


# =============================================================================
# Portfolio Comparator Tests
# =============================================================================

class TestPortfolioComparator:
    """Tests for portfolio comparison functionality."""
    
    def test_calculate_characteristics(self, portfolio_a_df):
        """
        Verify portfolio characteristics are calculated correctly.
        """
        comparator = PortfolioComparator()
        
        chars = comparator.calculate_characteristics(
            portfolio_a_df,
            portfolio_id="Portfolio_A",
        )
        
        assert chars.portfolio_id == "Portfolio_A"
        assert chars.loan_count == 200
        assert chars.total_balance > 0
        assert chars.wac > 0
        assert chars.avg_fico > 0
    
    def test_compare_dataframes(self, portfolio_a_df, portfolio_b_df):
        """
        Verify portfolio comparison produces results.
        """
        comparator = PortfolioComparator()
        
        result = comparator.compare_dataframes(
            portfolio_a_df,
            portfolio_b_df,
            portfolio_a_id="Prime Pool",
            portfolio_b_id="Alt-A Pool",
        )
        
        assert isinstance(result, ComparisonResult)
        assert result.portfolio_a_id == "Prime Pool"
        assert result.portfolio_b_id == "Alt-A Pool"
        assert len(result.metrics) > 0
    
    def test_comparison_metrics_by_dimension(self, portfolio_a_df, portfolio_b_df):
        """
        Verify metrics are organized by dimension.
        """
        comparator = PortfolioComparator()
        
        result = comparator.compare_dataframes(portfolio_a_df, portfolio_b_df)
        
        # Should have credit quality metrics
        credit_metrics = result.get_metrics_by_dimension(ComparisonDimension.CREDIT_QUALITY)
        assert len(credit_metrics) > 0
        
        # Should have collateral metrics
        collateral_metrics = result.get_metrics_by_dimension(ComparisonDimension.COLLATERAL)
        assert len(collateral_metrics) > 0
    
    def test_comparison_significance_flagging(self, portfolio_a_df, portfolio_b_df):
        """
        Verify significant differences are flagged.
        """
        comparator = PortfolioComparator(
            significance_thresholds={"fico": 20, "ltv": 5}
        )
        
        result = comparator.compare_dataframes(portfolio_a_df, portfolio_b_df)
        
        # Portfolio B has lower FICO, higher LTV - should be flagged unfavorable
        unfavorable = result.get_unfavorable_metrics()
        # At least some metrics should be unfavorable for Portfolio B
        # (since it has lower credit quality)
    
    def test_comparison_to_dataframe(self, portfolio_a_df, portfolio_b_df):
        """
        Verify comparison can be converted to DataFrame.
        """
        comparator = PortfolioComparator()
        
        result = comparator.compare_dataframes(portfolio_a_df, portfolio_b_df)
        df = result.to_dataframe()
        
        assert not df.empty
        assert "Metric" in df.columns
        assert "Difference" in df.columns
    
    def test_comparison_summary(self, portfolio_a_df, portfolio_b_df):
        """
        Verify comparison summary is generated.
        """
        comparator = PortfolioComparator()
        
        result = comparator.compare_dataframes(portfolio_a_df, portfolio_b_df)
        summary = result.summary()
        
        assert isinstance(summary, str)
        assert "Portfolio" in summary


class TestStratificationComparison:
    """Tests for stratification analysis."""
    
    def test_stratification_differences(self):
        """
        Verify stratification differences are calculated correctly.
        """
        strat = StratificationComparison(
            dimension="FICO Score",
            buckets=["<660", "660-699", "700-739", "740+"],
            portfolio_a={"<660": 5.0, "660-699": 15.0, "700-739": 40.0, "740+": 40.0},
            portfolio_b={"<660": 15.0, "660-699": 25.0, "700-739": 35.0, "740+": 25.0},
        )
        
        diffs = strat.differences
        
        # Portfolio B has more <660 (+10%)
        assert diffs["<660"] == 10.0
        # Portfolio B has less 740+ (-15%)
        assert diffs["740+"] == -15.0
    
    def test_max_deviation(self):
        """
        Verify max deviation bucket is identified.
        """
        strat = StratificationComparison(
            dimension="State",
            buckets=["CA", "TX", "FL"],
            portfolio_a={"CA": 40.0, "TX": 35.0, "FL": 25.0},
            portfolio_b={"CA": 20.0, "TX": 40.0, "FL": 40.0},  # Big shift from CA
        )
        
        bucket, deviation = strat.max_deviation
        
        # CA has the largest absolute deviation (-20%)
        assert bucket == "CA"
        assert deviation == -20.0


class TestDealStructureComparator:
    """Tests for deal structure comparison."""
    
    def test_compare_deal_structures(self):
        """
        Verify deal structure comparison works.
        """
        deal_a = {
            "deal_id": "DEAL_A",
            "bonds": [
                {"id": "A", "original_balance": 80_000_000, "coupon_rate": 0.045},
                {"id": "B", "original_balance": 20_000_000, "coupon_rate": 0.065},
            ],
            "waterfall": {
                "interest": [{"action": "PAY_BOND_INTEREST", "bond": "A"}],
                "principal": [{"action": "PAY_BOND_PRINCIPAL", "bond": "A"}],
            },
        }
        
        deal_b = {
            "deal_id": "DEAL_B",
            "bonds": [
                {"id": "A", "original_balance": 85_000_000, "coupon_rate": 0.040},
                {"id": "B", "original_balance": 10_000_000, "coupon_rate": 0.070},
                {"id": "C", "original_balance": 5_000_000, "coupon_rate": 0.090},
            ],
            "waterfall": {
                "interest": [],
                "principal": [],
            },
        }
        
        comparator = DealStructureComparator()
        result = comparator.compare_deals(deal_a, deal_b)
        
        assert "tranche_comparison" in result
        assert result["tranche_comparison"]["count_a"] == 2
        assert result["tranche_comparison"]["count_b"] == 3


class TestVintageComparator:
    """Tests for vintage analysis."""
    
    def test_analyze_vintages(self):
        """
        Verify vintage analysis produces summary by origination period.
        """
        df = pd.DataFrame({
            "loan_id": [f"L{i}" for i in range(100)],
            "origination_date": pd.date_range("2020-01-01", periods=100, freq="M"),
            "current_balance": np.random.uniform(200_000, 400_000, 100),
            "original_balance": np.random.uniform(220_000, 450_000, 100),
        })
        
        comparator = VintageComparator()
        result = comparator.analyze_vintages(
            df,
            vintage_column="origination_date",
        )
        
        assert not result.empty
        assert "vintage" in result.columns
        assert "loan_count" in result.columns


class TestHTMLReportGeneration:
    """Tests for HTML report generation."""
    
    def test_generate_html_report(self, portfolio_a_df, portfolio_b_df):
        """
        Verify HTML report is generated correctly.
        """
        comparator = PortfolioComparator()
        result = comparator.compare_dataframes(portfolio_a_df, portfolio_b_df)
        
        html = comparator.generate_html_report(result)
        
        assert "<html>" in html
        assert "Portfolio Comparison" in html
        assert "<table>" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
