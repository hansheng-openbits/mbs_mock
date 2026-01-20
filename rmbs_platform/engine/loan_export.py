"""
Loan-Level Detail Export Module for RMBS Engine.
=================================================

This module provides comprehensive loan-level data export capabilities
for regulatory reporting, investor transparency, and analytics:

- SEC Regulation AB II compliant exports (Asset-Level Data)
- European Data Warehouse (EDW) format exports
- Bloomberg loan-level templates
- Custom analytical exports
- Performance tracking exports

Industry Context
----------------
Post-2008 regulatory requirements mandate detailed loan-level disclosure:

1. **SEC Regulation AB II**: Asset-level data for registered ABS
2. **ECB Loan-Level Initiative**: European securitization transparency
3. **ESMA STS Requirements**: Simple, Transparent, Standardized criteria
4. **Investor Due Diligence**: Third-party review requirements

Standard data points include:
- Loan characteristics (balance, rate, term, LTV, FICO)
- Borrower attributes (DTI, employment, income)
- Property details (type, location, occupancy)
- Performance history (delinquency, modifications)
- Loss/recovery data (foreclosure, REO, severity)

References
----------
- SEC Regulation AB, Item 1111 and Schedule AL
- European DataWarehouse Templates
- CREFC/CMSA Investor Reporting Package (IRP)

Examples
--------
>>> from rmbs_platform.engine.loan_export import (
...     LoanLevelExporter, ExportFormat, RegABExporter
... )
>>> 
>>> # Create exporter
>>> exporter = LoanLevelExporter(loan_data)
>>> 
>>> # Export to SEC format
>>> reg_ab_file = exporter.export(ExportFormat.SEC_REG_AB, output_path='reg_ab_data.xml')
>>> 
>>> # Export to CSV for analytics
>>> analytics_file = exporter.export(ExportFormat.ANALYTICS_CSV, output_path='loans.csv')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import json
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom

import numpy as np
import pandas as pd


# =============================================================================
# Enums and Constants
# =============================================================================

class ExportFormat(str, Enum):
    """
    Supported export formats for loan-level data.
    """
    
    SEC_REG_AB = "SEC_REG_AB"
    EDW_RMBS = "EDW_RMBS"
    BLOOMBERG = "BLOOMBERG"
    ANALYTICS_CSV = "ANALYTICS_CSV"
    JSON_DETAILED = "JSON_DETAILED"
    EXCEL = "EXCEL"
    PARQUET = "PARQUET"


class LoanStatus(str, Enum):
    """
    Standard loan status codes per industry conventions.
    """
    
    CURRENT = "Current"
    PREPAID_FULL = "Prepaid in Full"
    PREPAID_PARTIAL = "Partial Prepayment"
    DQ_30 = "30 Days Delinquent"
    DQ_60 = "60 Days Delinquent"
    DQ_90 = "90+ Days Delinquent"
    FORECLOSURE = "In Foreclosure"
    REO = "Real Estate Owned"
    BANKRUPT = "Bankruptcy"
    MODIFIED = "Modified"
    LIQUIDATED = "Liquidated"


class PropertyType(str, Enum):
    """
    Standard property type classifications.
    """
    
    SINGLE_FAMILY = "SF"
    CONDO = "CO"
    TOWNHOUSE = "TH"
    MULTI_FAMILY_2_4 = "MF"
    PUD = "PU"
    MANUFACTURED = "MH"
    COOPERATIVE = "CP"


class OccupancyType(str, Enum):
    """
    Property occupancy classifications.
    """
    
    PRIMARY = "Primary Residence"
    SECOND_HOME = "Second Home"
    INVESTMENT = "Investment Property"


# =============================================================================
# SEC Regulation AB Field Mappings
# =============================================================================

# SEC Schedule AL field definitions for RMBS (simplified)
SEC_REG_AB_FIELDS = {
    # Identification
    "assetNumber": {"required": True, "type": "string", "max_length": 32},
    "reportingPeriodBeginDate": {"required": True, "type": "date"},
    "reportingPeriodEndDate": {"required": True, "type": "date"},
    
    # Original Loan Terms
    "originalLoanAmount": {"required": True, "type": "decimal", "precision": 2},
    "originationDate": {"required": True, "type": "date"},
    "originalLoanTerm": {"required": True, "type": "integer"},
    "originalInterestRate": {"required": True, "type": "decimal", "precision": 5},
    "loanMaturityDate": {"required": True, "type": "date"},
    "originalInterestRateType": {"required": True, "type": "code"},
    
    # Current Loan Status
    "currentActualBalance": {"required": True, "type": "decimal", "precision": 2},
    "currentInterestRate": {"required": True, "type": "decimal", "precision": 5},
    "scheduledPrincipal": {"required": True, "type": "decimal", "precision": 2},
    "scheduledInterest": {"required": True, "type": "decimal", "precision": 2},
    "actualPrincipalCollected": {"required": True, "type": "decimal", "precision": 2},
    "actualInterestCollected": {"required": True, "type": "decimal", "precision": 2},
    
    # Credit Metrics
    "originalCreditScore": {"required": True, "type": "integer"},
    "currentCreditScore": {"required": False, "type": "integer"},
    "originalLTV": {"required": True, "type": "decimal", "precision": 2},
    "currentLTV": {"required": False, "type": "decimal", "precision": 2},
    "originalDTI": {"required": True, "type": "decimal", "precision": 2},
    
    # Property Information
    "propertyType": {"required": True, "type": "code"},
    "propertyState": {"required": True, "type": "code"},
    "propertyZIP": {"required": True, "type": "string", "max_length": 5},
    "occupancyStatus": {"required": True, "type": "code"},
    "numberOfUnits": {"required": True, "type": "integer"},
    "originalAppraisedValue": {"required": True, "type": "decimal", "precision": 2},
    
    # Delinquency and Performance
    "paymentStatus": {"required": True, "type": "code"},
    "daysPastDue": {"required": True, "type": "integer"},
    "paidThroughDate": {"required": True, "type": "date"},
    "zeroBalanceCode": {"required": False, "type": "code"},
    "zeroBalanceDate": {"required": False, "type": "date"},
    
    # Modification Information
    "modificationIndicator": {"required": True, "type": "boolean"},
    "modificationDate": {"required": False, "type": "date"},
    "modificationInterestRate": {"required": False, "type": "decimal", "precision": 5},
    "modificationPrincipalForgiven": {"required": False, "type": "decimal", "precision": 2},
    
    # Loss Information
    "totalLossAmount": {"required": False, "type": "decimal", "precision": 2},
    "liquidationProceedsAmount": {"required": False, "type": "decimal", "precision": 2},
    "miClaimAmount": {"required": False, "type": "decimal", "precision": 2},
}


# =============================================================================
# European DataWarehouse Field Mappings
# =============================================================================

EDW_RMBS_FIELDS = {
    # Pool Cut-off Date Info
    "AS1": "Pool Identifier",
    "AS2": "Loan Identifier",
    "AS3": "Originator",
    "AS4": "Servicer Identifier",
    
    # Loan Terms
    "AS5": "Interest Rate",
    "AS6": "Current Balance",
    "AS7": "Original Balance",
    "AS8": "Origination Date",
    "AS9": "Maturity Date",
    "AS10": "Original Term",
    "AS11": "Remaining Term",
    
    # Credit Data
    "AS20": "LTV at Origination",
    "AS21": "Current LTV",
    "AS22": "DTI at Origination",
    "AS23": "Borrower Income",
    
    # Property
    "AS30": "Property Type",
    "AS31": "Occupancy Type",
    "AS32": "Geographic Region",
    "AS33": "Property Value at Origination",
    
    # Performance
    "AS40": "Payment Status",
    "AS41": "Days Past Due",
    "AS42": "Number of Payments Due",
    "AS43": "Arrears Balance",
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LoanRecord:
    """
    Comprehensive loan-level record for export.
    
    Parameters
    ----------
    loan_id : str
        Unique loan identifier
    reporting_date : date
        As-of date for the data
    original_balance : float
        Original loan balance
    current_balance : float
        Current unpaid principal balance
    interest_rate : float
        Current note rate
    original_ltv : float
        Original loan-to-value ratio
    fico_score : int
        Credit score at origination
    property_state : str
        Two-letter state code
    property_type : PropertyType
        Property type classification
    loan_status : LoanStatus
        Current loan status
    """
    
    # Identification
    loan_id: str
    reporting_date: date
    deal_id: Optional[str] = None
    pool_id: Optional[str] = None
    
    # Original Terms
    original_balance: float = 0.0
    origination_date: Optional[date] = None
    original_term_months: int = 360
    original_interest_rate: float = 0.0
    maturity_date: Optional[date] = None
    loan_purpose: str = "Purchase"
    loan_type: str = "Fixed"
    
    # Current Status
    current_balance: float = 0.0
    interest_rate: float = 0.0
    remaining_term_months: int = 0
    next_payment_date: Optional[date] = None
    paid_through_date: Optional[date] = None
    loan_status: LoanStatus = LoanStatus.CURRENT
    days_past_due: int = 0
    
    # Credit Metrics
    fico_score: int = 0
    current_fico: Optional[int] = None
    original_ltv: float = 0.0
    current_ltv: Optional[float] = None
    combined_ltv: Optional[float] = None
    dti_ratio: float = 0.0
    
    # Property Information
    property_type: PropertyType = PropertyType.SINGLE_FAMILY
    property_state: str = ""
    property_zip: str = ""
    property_value: float = 0.0
    current_property_value: Optional[float] = None
    occupancy_type: OccupancyType = OccupancyType.PRIMARY
    number_of_units: int = 1
    
    # Borrower Information
    borrower_count: int = 1
    employment_status: str = ""
    documentation_type: str = "Full"
    
    # Collections
    scheduled_principal: float = 0.0
    scheduled_interest: float = 0.0
    actual_principal_collected: float = 0.0
    actual_interest_collected: float = 0.0
    prepayment_amount: float = 0.0
    
    # Modification
    is_modified: bool = False
    modification_date: Optional[date] = None
    modification_type: Optional[str] = None
    principal_forgiven: float = 0.0
    rate_reduction: float = 0.0
    
    # Loss/Liquidation
    is_liquidated: bool = False
    liquidation_date: Optional[date] = None
    liquidation_proceeds: float = 0.0
    loss_amount: float = 0.0
    loss_severity: float = 0.0
    mi_claim_amount: float = 0.0
    
    # Servicer Advances
    servicer_advance_balance: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with string date formatting."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, Enum):
                result[key] = value.value
            else:
                result[key] = value
        return result


@dataclass
class ExportConfig:
    """
    Configuration for loan-level export.
    
    Parameters
    ----------
    format : ExportFormat
        Target export format
    include_header : bool
        Include header row/elements
    date_format : str
        Date formatting string
    decimal_places : int
        Decimal precision for amounts
    include_metadata : bool
        Include file metadata
    compress : bool
        Compress output file
    """
    
    format: ExportFormat = ExportFormat.ANALYTICS_CSV
    include_header: bool = True
    date_format: str = "%Y-%m-%d"
    decimal_places: int = 2
    include_metadata: bool = True
    compress: bool = False
    chunk_size: int = 10000
    encoding: str = "utf-8"
    null_representation: str = ""


# =============================================================================
# SEC Regulation AB Exporter
# =============================================================================

class RegABExporter:
    """
    SEC Regulation AB compliant loan-level data exporter.
    
    Generates XML files conforming to SEC Schedule AL requirements
    for asset-backed securities registration statements.
    
    Parameters
    ----------
    deal_id : str
        SEC file number or deal identifier
    reporting_period : Tuple[date, date]
        Start and end of reporting period
    issuer_name : str
        Name of the issuing entity
    
    Examples
    --------
    >>> exporter = RegABExporter(
    ...     deal_id='333-12345',
    ...     reporting_period=(date(2024, 1, 1), date(2024, 1, 31)),
    ...     issuer_name='RMBS Trust 2024-1'
    ... )
    >>> xml_content = exporter.export_loans(loan_records)
    """
    
    def __init__(
        self,
        deal_id: str,
        reporting_period: Tuple[date, date],
        issuer_name: str,
        cik: Optional[str] = None,
    ) -> None:
        self.deal_id = deal_id
        self.reporting_period = reporting_period
        self.issuer_name = issuer_name
        self.cik = cik
    
    def export_loans(
        self,
        loans: List[LoanRecord],
        output_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """
        Export loans to SEC Regulation AB XML format.
        
        Parameters
        ----------
        loans : List[LoanRecord]
            Loan records to export
        output_path : Optional[Union[str, Path]]
            Output file path (returns string if None)
            
        Returns
        -------
        str
            XML content
        """
        # Create root element
        root = ET.Element("assetData")
        root.set("xmlns", "http://www.sec.gov/edgar/document/abs")
        
        # Add header
        header = ET.SubElement(root, "headerData")
        ET.SubElement(header, "issuerName").text = self.issuer_name
        ET.SubElement(header, "dealId").text = self.deal_id
        ET.SubElement(header, "reportingPeriodBeginDate").text = self.reporting_period[0].isoformat()
        ET.SubElement(header, "reportingPeriodEndDate").text = self.reporting_period[1].isoformat()
        if self.cik:
            ET.SubElement(header, "cik").text = self.cik
        ET.SubElement(header, "assetCount").text = str(len(loans))
        ET.SubElement(header, "generationTimestamp").text = datetime.now().isoformat()
        
        # Add loans
        assets = ET.SubElement(root, "assets")
        
        for loan in loans:
            asset_elem = ET.SubElement(assets, "asset")
            self._add_loan_elements(asset_elem, loan)
        
        # Format XML
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        
        # Write to file if path provided
        if output_path:
            path = Path(output_path)
            path.write_text(xml_str, encoding="utf-8")
        
        return xml_str
    
    def _add_loan_elements(self, parent: ET.Element, loan: LoanRecord) -> None:
        """Add loan data elements to XML."""
        # Identification
        ET.SubElement(parent, "assetNumber").text = loan.loan_id
        ET.SubElement(parent, "reportingPeriodBeginDate").text = self.reporting_period[0].isoformat()
        ET.SubElement(parent, "reportingPeriodEndDate").text = self.reporting_period[1].isoformat()
        
        # Original Terms
        ET.SubElement(parent, "originalLoanAmount").text = f"{loan.original_balance:.2f}"
        if loan.origination_date:
            ET.SubElement(parent, "originationDate").text = loan.origination_date.isoformat()
        ET.SubElement(parent, "originalLoanTerm").text = str(loan.original_term_months)
        ET.SubElement(parent, "originalInterestRate").text = f"{loan.original_interest_rate:.5f}"
        if loan.maturity_date:
            ET.SubElement(parent, "loanMaturityDate").text = loan.maturity_date.isoformat()
        ET.SubElement(parent, "originalInterestRateType").text = loan.loan_type
        
        # Current Status
        ET.SubElement(parent, "currentActualBalance").text = f"{loan.current_balance:.2f}"
        ET.SubElement(parent, "currentInterestRate").text = f"{loan.interest_rate:.5f}"
        ET.SubElement(parent, "scheduledPrincipal").text = f"{loan.scheduled_principal:.2f}"
        ET.SubElement(parent, "scheduledInterest").text = f"{loan.scheduled_interest:.2f}"
        ET.SubElement(parent, "actualPrincipalCollected").text = f"{loan.actual_principal_collected:.2f}"
        ET.SubElement(parent, "actualInterestCollected").text = f"{loan.actual_interest_collected:.2f}"
        
        # Credit Metrics
        if loan.fico_score > 0:
            ET.SubElement(parent, "originalCreditScore").text = str(loan.fico_score)
        if loan.current_fico:
            ET.SubElement(parent, "currentCreditScore").text = str(loan.current_fico)
        ET.SubElement(parent, "originalLTV").text = f"{loan.original_ltv:.2f}"
        if loan.current_ltv:
            ET.SubElement(parent, "currentLTV").text = f"{loan.current_ltv:.2f}"
        ET.SubElement(parent, "originalDTI").text = f"{loan.dti_ratio:.2f}"
        
        # Property
        ET.SubElement(parent, "propertyType").text = loan.property_type.value
        ET.SubElement(parent, "propertyState").text = loan.property_state
        ET.SubElement(parent, "propertyZIP").text = loan.property_zip[:5] if loan.property_zip else ""
        ET.SubElement(parent, "occupancyStatus").text = loan.occupancy_type.value
        ET.SubElement(parent, "numberOfUnits").text = str(loan.number_of_units)
        ET.SubElement(parent, "originalAppraisedValue").text = f"{loan.property_value:.2f}"
        
        # Delinquency
        ET.SubElement(parent, "paymentStatus").text = loan.loan_status.value
        ET.SubElement(parent, "daysPastDue").text = str(loan.days_past_due)
        if loan.paid_through_date:
            ET.SubElement(parent, "paidThroughDate").text = loan.paid_through_date.isoformat()
        
        # Modification
        ET.SubElement(parent, "modificationIndicator").text = "Y" if loan.is_modified else "N"
        if loan.is_modified and loan.modification_date:
            ET.SubElement(parent, "modificationDate").text = loan.modification_date.isoformat()
            ET.SubElement(parent, "modificationPrincipalForgiven").text = f"{loan.principal_forgiven:.2f}"
        
        # Loss (if liquidated)
        if loan.is_liquidated:
            ET.SubElement(parent, "zeroBalanceCode").text = "Liquidated"
            if loan.liquidation_date:
                ET.SubElement(parent, "zeroBalanceDate").text = loan.liquidation_date.isoformat()
            ET.SubElement(parent, "totalLossAmount").text = f"{loan.loss_amount:.2f}"
            ET.SubElement(parent, "liquidationProceedsAmount").text = f"{loan.liquidation_proceeds:.2f}"
            ET.SubElement(parent, "miClaimAmount").text = f"{loan.mi_claim_amount:.2f}"


# =============================================================================
# European DataWarehouse Exporter
# =============================================================================

class EDWExporter:
    """
    European DataWarehouse (EDW) format exporter.
    
    Generates loan-level data files compliant with ECB loan-level
    initiative requirements for European securitizations.
    
    Parameters
    ----------
    deal_id : str
        EDW deal identifier
    pool_cutoff_date : date
        Pool cut-off date
    asset_class : str
        Asset class code ('RMBS', 'CMBS', 'ABS')
    
    Examples
    --------
    >>> exporter = EDWExporter(
    ...     deal_id='EDW123456',
    ...     pool_cutoff_date=date(2024, 1, 15),
    ...     asset_class='RMBS'
    ... )
    >>> csv_content = exporter.export_loans(loan_records)
    """
    
    def __init__(
        self,
        deal_id: str,
        pool_cutoff_date: date,
        asset_class: str = "RMBS",
        originator: str = "",
        servicer: str = "",
    ) -> None:
        self.deal_id = deal_id
        self.pool_cutoff_date = pool_cutoff_date
        self.asset_class = asset_class
        self.originator = originator
        self.servicer = servicer
    
    def export_loans(
        self,
        loans: List[LoanRecord],
        output_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """
        Export loans to EDW CSV format.
        
        Parameters
        ----------
        loans : List[LoanRecord]
            Loan records to export
        output_path : Optional[Union[str, Path]]
            Output file path
            
        Returns
        -------
        str
            CSV content
        """
        output = StringIO()
        writer = csv.writer(output)
        
        # Header row (EDW field codes)
        header = list(EDW_RMBS_FIELDS.keys())
        writer.writerow(header)
        
        # Data rows
        for loan in loans:
            row = self._map_loan_to_edw(loan)
            writer.writerow(row)
        
        content = output.getvalue()
        
        if output_path:
            Path(output_path).write_text(content, encoding="utf-8")
        
        return content
    
    def _map_loan_to_edw(self, loan: LoanRecord) -> List[str]:
        """Map loan record to EDW field order."""
        return [
            self.deal_id,  # AS1: Pool Identifier
            loan.loan_id,  # AS2: Loan Identifier
            self.originator,  # AS3: Originator
            self.servicer,  # AS4: Servicer
            f"{loan.interest_rate:.5f}",  # AS5: Interest Rate
            f"{loan.current_balance:.2f}",  # AS6: Current Balance
            f"{loan.original_balance:.2f}",  # AS7: Original Balance
            loan.origination_date.isoformat() if loan.origination_date else "",  # AS8
            loan.maturity_date.isoformat() if loan.maturity_date else "",  # AS9
            str(loan.original_term_months),  # AS10
            str(loan.remaining_term_months),  # AS11
            f"{loan.original_ltv:.2f}",  # AS20
            f"{loan.current_ltv:.2f}" if loan.current_ltv else "",  # AS21
            f"{loan.dti_ratio:.2f}",  # AS22
            "",  # AS23: Borrower Income (not in LoanRecord)
            loan.property_type.value,  # AS30
            loan.occupancy_type.value,  # AS31
            loan.property_state,  # AS32
            f"{loan.property_value:.2f}",  # AS33
            loan.loan_status.value,  # AS40
            str(loan.days_past_due),  # AS41
            "",  # AS42: Number of payments due
            "",  # AS43: Arrears balance
        ]


# =============================================================================
# Main Loan-Level Exporter
# =============================================================================

class LoanLevelExporter:
    """
    Universal loan-level data exporter supporting multiple formats.
    
    Provides a unified interface for exporting loan data to various
    industry-standard and analytical formats.
    
    Parameters
    ----------
    loans : Union[List[LoanRecord], pd.DataFrame]
        Loan data to export
    deal_info : Optional[Dict[str, Any]]
        Deal metadata for headers
    
    Attributes
    ----------
    loans : pd.DataFrame
        Loan data as DataFrame
    deal_info : Dict[str, Any]
        Deal metadata
    
    Examples
    --------
    >>> exporter = LoanLevelExporter(loan_records, deal_info={'id': 'DEAL_2024_001'})
    >>> 
    >>> # Export to various formats
    >>> csv_file = exporter.export(ExportFormat.ANALYTICS_CSV, 'loans.csv')
    >>> json_file = exporter.export(ExportFormat.JSON_DETAILED, 'loans.json')
    >>> excel_file = exporter.export(ExportFormat.EXCEL, 'loans.xlsx')
    """
    
    def __init__(
        self,
        loans: Union[List[LoanRecord], pd.DataFrame],
        deal_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        if isinstance(loans, pd.DataFrame):
            self.loans_df = loans
            self.loans = self._df_to_records(loans)
        else:
            self.loans = loans
            self.loans_df = self._records_to_df(loans)
        
        self.deal_info = deal_info or {}
    
    def _records_to_df(self, records: List[LoanRecord]) -> pd.DataFrame:
        """Convert loan records to DataFrame."""
        if not records:
            return pd.DataFrame()
        return pd.DataFrame([r.to_dict() for r in records])
    
    def _df_to_records(self, df: pd.DataFrame) -> List[LoanRecord]:
        """Convert DataFrame to loan records."""
        records = []
        for _, row in df.iterrows():
            record = LoanRecord(
                loan_id=str(row.get('loan_id', '')),
                reporting_date=pd.to_datetime(row.get('reporting_date', date.today())).date(),
                original_balance=float(row.get('original_balance', 0)),
                current_balance=float(row.get('current_balance', 0)),
                interest_rate=float(row.get('interest_rate', 0)),
                original_ltv=float(row.get('original_ltv', 0)),
                fico_score=int(row.get('fico_score', 0)),
                property_state=str(row.get('property_state', '')),
            )
            records.append(record)
        return records
    
    def export(
        self,
        format: ExportFormat,
        output_path: Optional[Union[str, Path]] = None,
        config: Optional[ExportConfig] = None,
    ) -> Union[str, bytes, pd.DataFrame]:
        """
        Export loan data to specified format.
        
        Parameters
        ----------
        format : ExportFormat
            Target export format
        output_path : Optional[Union[str, Path]]
            Output file path
        config : Optional[ExportConfig]
            Export configuration
            
        Returns
        -------
        Union[str, bytes, pd.DataFrame]
            Exported content
        """
        config = config or ExportConfig(format=format)
        
        exporters = {
            ExportFormat.SEC_REG_AB: self._export_sec_reg_ab,
            ExportFormat.EDW_RMBS: self._export_edw,
            ExportFormat.BLOOMBERG: self._export_bloomberg,
            ExportFormat.ANALYTICS_CSV: self._export_csv,
            ExportFormat.JSON_DETAILED: self._export_json,
            ExportFormat.EXCEL: self._export_excel,
            ExportFormat.PARQUET: self._export_parquet,
        }
        
        export_func = exporters.get(format)
        if not export_func:
            raise ValueError(f"Unsupported format: {format}")
        
        return export_func(output_path, config)
    
    def _export_sec_reg_ab(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> str:
        """Export to SEC Regulation AB XML."""
        reporting_period = (
            date.today().replace(day=1),
            date.today(),
        )
        
        exporter = RegABExporter(
            deal_id=self.deal_info.get('deal_id', 'UNKNOWN'),
            reporting_period=reporting_period,
            issuer_name=self.deal_info.get('issuer_name', 'RMBS Trust'),
        )
        
        return exporter.export_loans(self.loans, output_path)
    
    def _export_edw(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> str:
        """Export to European DataWarehouse format."""
        exporter = EDWExporter(
            deal_id=self.deal_info.get('deal_id', 'UNKNOWN'),
            pool_cutoff_date=self.deal_info.get('cutoff_date', date.today()),
        )
        
        return exporter.export_loans(self.loans, output_path)
    
    def _export_bloomberg(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> str:
        """Export to Bloomberg loan-level format."""
        # Bloomberg format is similar to CSV with specific columns
        columns = [
            'loan_id', 'current_balance', 'interest_rate', 'original_balance',
            'origination_date', 'maturity_date', 'original_ltv', 'current_ltv',
            'fico_score', 'property_state', 'property_type', 'loan_status',
            'days_past_due', 'prepayment_amount', 'loss_amount',
        ]
        
        df = self.loans_df[
            [c for c in columns if c in self.loans_df.columns]
        ].copy()
        
        content = df.to_csv(index=False)
        
        if output_path:
            Path(output_path).write_text(content)
        
        return content
    
    def _export_csv(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> str:
        """Export to analytics CSV format."""
        content = self.loans_df.to_csv(index=False)
        
        if output_path:
            Path(output_path).write_text(content, encoding=config.encoding)
        
        return content
    
    def _export_json(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> str:
        """Export to detailed JSON format."""
        data = {
            "metadata": {
                "deal_info": self.deal_info,
                "export_timestamp": datetime.now().isoformat(),
                "loan_count": len(self.loans),
            },
            "loans": [loan.to_dict() for loan in self.loans],
        }
        
        content = json.dumps(data, indent=2, default=str)
        
        if output_path:
            Path(output_path).write_text(content, encoding=config.encoding)
        
        return content
    
    def _export_excel(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> pd.DataFrame:
        """Export to Excel format."""
        if output_path:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Main loan data
                self.loans_df.to_excel(writer, sheet_name='Loan Data', index=False)
                
                # Summary statistics
                summary = self._generate_summary()
                summary.to_excel(writer, sheet_name='Summary', index=True)
                
                # Metadata
                meta_df = pd.DataFrame([self.deal_info])
                meta_df.to_excel(writer, sheet_name='Metadata', index=False)
        
        return self.loans_df
    
    def _export_parquet(
        self,
        output_path: Optional[Union[str, Path]],
        config: ExportConfig,
    ) -> pd.DataFrame:
        """Export to Parquet format for big data analytics."""
        if output_path:
            self.loans_df.to_parquet(output_path, index=False)
        
        return self.loans_df
    
    def _generate_summary(self) -> pd.DataFrame:
        """Generate summary statistics for the loan pool."""
        df = self.loans_df
        
        summary = {
            "Total Loan Count": len(df),
            "Total Current Balance": df['current_balance'].sum() if 'current_balance' in df else 0,
            "Total Original Balance": df['original_balance'].sum() if 'original_balance' in df else 0,
            "WAC (Weighted Avg Coupon)": self._calculate_wac(),
            "WAM (Weighted Avg Maturity)": self._calculate_wam(),
            "Avg LTV": df['original_ltv'].mean() if 'original_ltv' in df else 0,
            "Avg FICO": df['fico_score'].mean() if 'fico_score' in df else 0,
        }
        
        return pd.Series(summary).to_frame(name='Value')
    
    def _calculate_wac(self) -> float:
        """Calculate weighted average coupon."""
        df = self.loans_df
        if 'current_balance' not in df or 'interest_rate' not in df:
            return 0.0
        
        total_balance = df['current_balance'].sum()
        if total_balance == 0:
            return 0.0
        
        return (df['current_balance'] * df['interest_rate']).sum() / total_balance
    
    def _calculate_wam(self) -> float:
        """Calculate weighted average maturity (in months)."""
        df = self.loans_df
        if 'current_balance' not in df or 'remaining_term_months' not in df:
            return 0.0
        
        total_balance = df['current_balance'].sum()
        if total_balance == 0:
            return 0.0
        
        return (df['current_balance'] * df['remaining_term_months']).sum() / total_balance


# =============================================================================
# Utility Functions
# =============================================================================

def convert_dataframe_to_loans(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, str]] = None,
) -> List[LoanRecord]:
    """
    Convert a DataFrame to list of LoanRecord objects.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with loan data
    column_mapping : Optional[Dict[str, str]]
        Mapping from DataFrame columns to LoanRecord attributes
        
    Returns
    -------
    List[LoanRecord]
        List of loan records
    """
    # Default mapping
    default_mapping = {
        'Loan_ID': 'loan_id',
        'Current_Balance': 'current_balance',
        'Original_Balance': 'original_balance',
        'Interest_Rate': 'interest_rate',
        'LTV': 'original_ltv',
        'FICO': 'fico_score',
        'State': 'property_state',
    }
    
    mapping = column_mapping or default_mapping
    
    # Rename columns
    df_mapped = df.rename(columns={v: k for k, v in mapping.items() if v in df.columns})
    
    exporter = LoanLevelExporter(df_mapped)
    return exporter.loans


def validate_loan_data(
    loans: List[LoanRecord],
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Validate loan data for export completeness.
    
    Parameters
    ----------
    loans : List[LoanRecord]
        Loans to validate
    required_fields : Optional[List[str]]
        Required field names
        
    Returns
    -------
    Dict[str, Any]
        Validation results
    """
    required = required_fields or ['loan_id', 'current_balance', 'interest_rate']
    
    issues = []
    for i, loan in enumerate(loans):
        loan_dict = loan.to_dict()
        for field in required:
            if field not in loan_dict or loan_dict[field] in [None, '', 0]:
                issues.append({
                    "loan_index": i,
                    "loan_id": loan.loan_id,
                    "field": field,
                    "issue": "Missing or empty value",
                })
    
    return {
        "is_valid": len(issues) == 0,
        "loan_count": len(loans),
        "issue_count": len(issues),
        "issues": issues[:100],  # Limit to first 100
    }
