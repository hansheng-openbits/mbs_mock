import pandas as pd
import logging
from typing import List, Dict, Any

from rmbs_state import Snapshot

logger = logging.getLogger("RMBS.Reporting")

class ReportGenerator:
    def __init__(self, history: List[Snapshot]):
        self.history = history

    def generate_cashflow_report(self) -> pd.DataFrame:
        """
        Converts the list of Snapshots into a Pandas DataFrame.
        Columns will include: Period, Date, Bond Balances, Fund Balances, Ledgers.
        """
        if not self.history:
            logger.warning("No history found. Returning empty DataFrame.")
            return pd.DataFrame()

        rows = []
        
        # Iterate through every snapshot (T=0, T=1, ...)
        for i, snap in enumerate(self.history):
            row: Dict[str, Any] = {
                "Period": snap.period,
                "Date": snap.date
            }
            
            # 1. Flatten Bond Balances
            for bond_id, balance in snap.bond_balances.items():
                row[f"Bond.{bond_id}.Balance"] = balance
                # Calculate Factor
                # Note: In a real engine, we'd look up original balance from definition.
                # Here we simplify.
            
            # 2. Flatten Fund Balances
            for fund_id, amount in snap.funds.items():
                row[f"Fund.{fund_id}.Balance"] = amount
                
            # 3. Flatten Ledgers (Shortfalls, Cumulative Loss)
            for ledger_id, amount in snap.ledgers.items():
                row[f"Ledger.{ledger_id}"] = amount
                
            # 4. Flatten Variables (Triggers, Rates)
            for var_id, val in snap.variables.items():
                row[f"Var.{var_id}"] = val
                
            rows.append(row)

        df = pd.DataFrame(rows)
        
        # 5. DERIVED METRICS (Flows from Stocks)
        # Calculate Principal Payments as Delta of Balance
        # (Balance T-1) - (Balance T)
        bond_cols = [c for c in df.columns if ".Balance" in c and "Bond." in c]
        for col in bond_cols:
            bond_id = col.split(".")[1]
            # diff() calculates T - (T-1). We want opposite for payment.
            # fillna(0) handles the T=0 row.
            payment_col = f"Bond.{bond_id}.Prin_Paid"
            df[payment_col] = -df[col].diff().fillna(0)
            
            # Correction: T=0 usually has full balance, so payment is 0.
            # But diff() at T=0 is NaN. We set T=0 payment to 0 explicitly.
            df.loc[0, payment_col] = 0.0

        # Re-order columns for readability (Period, Date, then the rest)
        cols = ['Period', 'Date'] + [c for c in df.columns if c not in ['Period', 'Date']]
        df = df[cols]
        
        return df

    def save_to_csv(self, df: pd.DataFrame, filename: str):
        try:
            df.to_csv(filename, index=False)
            logger.info(f"Report saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")