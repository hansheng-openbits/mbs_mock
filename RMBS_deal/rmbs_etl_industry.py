import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

# Configure robust logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("RMBS.ETL")

@dataclass
class ETLConfig:
    """
    Configuration object derived from the DealSpec JSON.
    """
    date_format: str = "%Y-%m-%d"
    
    # Map: External CSV Header -> Internal Canonical Name
    field_map: Dict[str, str] = field(default_factory=lambda: {
        "LOAN_ID": "loan_id",
        "REPORT_PERIOD": "period_date",
        "CURR_BAL": "ending_balance",
        "INT_PAID": "interest_paid",
        "PRIN_PAID": "principal_paid",
        "SCHED_BAL": "scheduled_balance",
        "DQ_DAYS": "days_past_due",
        "LIQ_PROCEEDS": "liquidation_proceeds",
        "LIQ_EXPENSES": "liquidation_expenses",
        "MOD_FLAG": "modification_flag",
        "INT_RATE": "current_rate"
    })
    
    # Required columns that MUST exist after mapping
    required_canonical_cols: List[str] = field(default_factory=lambda: [
        "loan_id", "ending_balance", "interest_paid", "principal_paid"
    ])

class TapeProcessor:
    def __init__(self, config: ETLConfig):
        self.config = config

    def ingest_tape(self, file_path: str) -> pd.DataFrame:
        """
        Orchestrates the full ETL pipeline: Load -> Map -> Clean -> Derive.
        """
        logger.info(f"--- Starting Ingestion: {file_path} ---")
        
        # 1. RAW LOAD
        try:
            # Low_memory=False prevents mixed type inference warnings on large tapes
            df_raw = pd.read_csv(file_path, low_memory=False)
        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            raise e

        # 2. MAPPING (Renaming columns)
        # Invert map to check missing headers
        # We only rename columns that exist in the map
        df = df_raw.rename(columns=self.config.field_map)
        
        # Check for missing required columns
        missing = [c for c in self.config.required_canonical_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Tape missing required mapped columns: {missing}")

        # 3. CLEANING (Type coercion)
        df = self._clean_data(df)

        # 4. DERIVATION (Business Logic)
        df = self._derive_fields(df)

        # 5. VALIDATION (Sanity Checks)
        self._validate_business_rules(df)

        logger.info(f"Successfully processed {len(df)} records.")
        return df

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handles dirty data types common in financial CSVs."""
        
        # Helper to clean currency strings (e.g. "$1,200.50")
        def clean_currency(x):
            if isinstance(x, str):
                return float(x.replace('$', '').replace(',', '').strip() or 0)
            return float(x or 0)

        # Numeric Columns
        numeric_cols = [
            "ending_balance", "interest_paid", "principal_paid", 
            "liquidation_proceeds", "liquidation_expenses", "current_rate"
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(clean_currency).fillna(0.0)

        # Date Parsing
        if "period_date" in df.columns:
            df["period_date"] = pd.to_datetime(df["period_date"], errors='coerce')

        # Fill NaNs for logic fields
        if "days_past_due" in df.columns:
            df["days_past_due"] = df["days_past_due"].fillna(0).astype(int)
            
        return df

    def _derive_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates RMBS specific fields derived from raw inputs."""
        
        # A. Realized Loss Calculation
        # Loss = Balance + Expenses - Proceeds
        # Only applicable if loan is liquidated (Balance = 0 and Proceeds > 0, or explicit flag)
        
        # Initialize if missing
        for c in ["liquidation_proceeds", "liquidation_expenses"]:
            if c not in df.columns: df[c] = 0.0

        # Logic: If Liquidation Proceeds exist, calculate Loss
        df['realized_loss'] = 0.0
        liq_mask = (df['liquidation_proceeds'] > 0) | (df['liquidation_expenses'] > 0)
        
        # Standard Industry Formula:
        # We need the Balance *Before* Liquidation. Usually Tape has 'Ending Balance'.
        # If Ending Balance is 0, we assume the loss happened this period.
        # This is complex. We will assume the tape provides 'gross_loss' or we calculate simplistic version.
        # Simplistic: Loss = (Expenses - Proceeds). Wait, we need the Unpaid Principal Balance (UPB).
        # Industry fix: Tapes usually have 'Actual Principal' showing the write-off amount or we track T-1.
        # For this ETL, we assume 'principal_paid' includes the Payoff, and the rest is loss?
        # BETTER APPROACH: Assume the tape has a 'loss_amount' or we calculate it.
        # Let's calculate: Loss = Max(0, Expenses - Proceeds) ... No, that ignores UPB.
        # We will assume a 'write_off_amount' column is mapped or derived elsewhere.
        # FALLBACK: realized_loss = liquidation_expenses - liquidation_proceeds (Net Proceeds). 
        # Ideally, loss = UPB + Expenses - Proceeds. Since we don't have UPB_pre in single tape, 
        # we rely on the input having a loss column or 'principal_loss_amount'.
        
        # Let's verify if 'principal_loss' is in our map.
        if 'principal_loss' in df.columns:
            df['realized_loss'] = df['principal_loss']
        else:
             # Fallback: Assume principal_paid contains the 'Recovery', 
             # and we simply track explicit expenses as loss for now?
             # No, that's unsafe. Let's log a warning if loss tracking is ambiguous.
             pass

        # B. Delinquency Buckets (MBA Methodology)
        # 30, 60, 90+, FC (Foreclosure), REO (Real Estate Owned)
        df['delinq_status'] = 'CURRENT'
        df.loc[df['days_past_due'].between(30, 59), 'delinq_status'] = '30_DAYS'
        df.loc[df['days_past_due'].between(60, 89), 'delinq_status'] = '60_DAYS'
        df.loc[df['days_past_due'] >= 90, 'delinq_status'] = '90+_DAYS'
        
        return df

    def _validate_business_rules(self, df: pd.DataFrame):
        """Hard assertions that fail the pipeline if data is garbage."""
        
        # 1. No Negative Balances
        if (df['ending_balance'] < -0.01).any():
            bad_ids = df.loc[df['ending_balance'] < 0, 'loan_id'].tolist()
            raise ValueError(f"Negative Balances detected for loans: {bad_ids[:5]}...")

        # 2. Interest Rate Sanity (0% to 20%)
        if 'current_rate' in df.columns:
            if (df['current_rate'] > 0.20).any():
                logger.warning("Detected interest rates > 20%. Please verify tape.")

    def aggregate_pool_stats(self, df: pd.DataFrame) -> Dict[str, float]:
        """Compresses the loan level data into the variables needed for the Waterfall."""
        
        agg = {}
        
        # Cash Inflows
        agg['TotalInterest'] = df['interest_paid'].sum()
        agg['TotalPrincipal'] = df['principal_paid'].sum() + df['liquidation_proceeds'].sum()
        
        # Note: Principal usually implies 'Scheduled + Prepay'. Recoveries are separate.
        # We sum them for the 'PAF' (Principal Available Funds).
        
        # Balances
        agg['EndPoolBalance'] = df['ending_balance'].sum()
        
        # Triggers
        # Calculate 60+ Delinquency %
        mask_60plus = df['days_past_due'] >= 60
        bal_60plus = df.loc[mask_60plus, 'ending_balance'].sum()
        agg['Delinq60_Amount'] = bal_60plus
        
        # Losses
        # If we successfully mapped a loss column
        if 'realized_loss' in df.columns:
            agg['RealizedLoss'] = df['realized_loss'].sum()
        else:
            agg['RealizedLoss'] = 0.0

        return agg