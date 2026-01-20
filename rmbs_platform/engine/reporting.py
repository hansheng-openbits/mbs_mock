"""
Cashflow Reporting
==================

This module provides reporting utilities that convert simulation history
into analyst-friendly tabular formats. The :class:`ReportGenerator` takes
the snapshot history from a simulation run and produces a comprehensive
cashflow report.

The output DataFrame includes:

- Period and date columns
- Bond balances and principal payments
- Fund balances
- Ledger values (cumulative loss, shortfalls)
- Computed variables and ML diagnostics

Example
-------
>>> from rmbs_platform.engine.reporting import ReportGenerator
>>> reporter = ReportGenerator(state.history)
>>> df = reporter.generate_cashflow_report()
>>> print(df[["Period", "Bond.A.Balance", "Bond.A.Prin_Paid"]].head())

See Also
--------
state.Snapshot : Point-in-time state records used as input.
state.DealState : Maintains the history list.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from .state import Snapshot

logger = logging.getLogger("RMBS.Reporting")


class ReportGenerator:
    """
    Build tabular cashflow reports from deal simulation snapshots.

    The generator transforms a list of Snapshot objects into a pandas
    DataFrame suitable for analysis, visualization, and export.

    Parameters
    ----------
    history : list of Snapshot
        Chronological list of deal state snapshots, one per period.

    Attributes
    ----------
    history : list
        Reference to the input snapshot list.

    Notes
    -----
    The generated report includes derived metrics computed from stock
    changes between periods:

    - ``Bond.<id>.Prin_Paid``: Principal payment = balance(T-1) - balance(T)

    Example
    -------
    >>> reporter = ReportGenerator(state.history)
    >>> df = reporter.generate_cashflow_report()
    >>> df.to_csv("deal_cashflows.csv", index=False)
    """

    def __init__(self, history: List[Snapshot]) -> None:
        """
        Initialize the report generator with simulation history.

        Parameters
        ----------
        history : list of Snapshot
            Snapshots from the completed simulation.
        """
        self.history = history

    def generate_cashflow_report(self) -> pd.DataFrame:
        """
        Convert snapshots into a period-by-period cashflow report.

        This method flattens the nested snapshot structure into a
        wide-format DataFrame where each row is a period and columns
        represent different state components.

        Returns
        -------
        pd.DataFrame
            Cashflow report with columns:

            - ``Period``: Period number (1-indexed)
            - ``Date``: Period end date (ISO format)
            - ``Bond.<id>.Balance``: Current balance for each tranche
            - ``Bond.<id>.Prin_Paid``: Principal paid during period
            - ``Fund.<id>.Balance``: Fund balance at period end
            - ``Ledger.<id>``: Ledger values (cumulative loss, etc.)
            - ``Var.<name>``: Variable values and ML diagnostics

        Notes
        -----
        Principal payments are computed as the negative of balance changes:
        ``Prin_Paid = Balance(T-1) - Balance(T)``

        Returns an empty DataFrame if history is empty.

        Example
        -------
        >>> df = reporter.generate_cashflow_report()
        >>> # Filter to simulated periods
        >>> sim_df = df[df["Period"] > last_actual_period]
        >>> print(sim_df[["Period", "Bond.A.Balance"]].tail())
        """
        if not self.history:
            logger.warning("No history found. Returning empty DataFrame.")
            return pd.DataFrame()

        rows: List[Dict[str, Any]] = []

        # Iterate through every snapshot (T=0, T=1, ...)
        for i, snap in enumerate(self.history):
            row: Dict[str, Any] = {"Period": snap.period, "Date": snap.date}

            # 1. Flatten Bond Balances
            for bond_id, balance in snap.bond_balances.items():
                row[f"Bond.{bond_id}.Balance"] = balance

            # 2. Flatten Fund Balances
            for fund_id, amount in snap.funds.items():
                row[f"Fund.{fund_id}.Balance"] = amount

            # 3. Flatten Ledgers (Shortfalls, Cumulative Loss)
            for ledger_id, amount in snap.ledgers.items():
                row[f"Ledger.{ledger_id}"] = amount

            # 4. Flatten Variables (Triggers, Rates, ML diagnostics)
            for var_id, val in snap.variables.items():
                row[f"Var.{var_id}"] = val

            rows.append(row)

        df = pd.DataFrame(rows)

        # 5. DERIVED METRICS (Flows from Stocks)
        # Calculate Principal Payments as Delta of Balance
        bond_cols = [c for c in df.columns if ".Balance" in c and "Bond." in c]
        for col in bond_cols:
            bond_id = col.split(".")[1]
            # diff() calculates T - (T-1). We want the opposite for payment.
            payment_col = f"Bond.{bond_id}.Prin_Paid"
            df[payment_col] = -df[col].diff().fillna(0)

            # T=0 usually has full balance, so payment is 0
            df.loc[0, payment_col] = 0.0

        # Re-order columns for readability (Period, Date, then the rest)
        cols = ["Period", "Date"] + [c for c in df.columns if c not in ["Period", "Date"]]
        df = df[cols]

        return df

    def save_to_csv(self, df: pd.DataFrame, filename: str) -> None:
        """
        Persist a cashflow report to disk as CSV.

        Parameters
        ----------
        df : pd.DataFrame
            Report DataFrame to save.
        filename : str
            Output file path.

        Notes
        -----
        Uses UTF-8 encoding and excludes the DataFrame index.

        Example
        -------
        >>> df = reporter.generate_cashflow_report()
        >>> reporter.save_to_csv(df, "output/cashflows.csv")
        """
        try:
            df.to_csv(filename, index=False)
            logger.info(f"Report saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")
