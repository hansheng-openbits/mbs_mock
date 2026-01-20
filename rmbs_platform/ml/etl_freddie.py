"""
Freddie Mac ETL Utilities
=========================

This module provides Extract-Transform-Load (ETL) utilities for processing
Freddie Mac Single-Family Loan-Level Dataset files into a survival analysis
format suitable for prepayment and default modeling.

The ETL pipeline:

1. Reads pipe-delimited origination and performance files.
2. Determines loan outcome (prepay, default, or censored).
3. Calculates time-to-event (duration) for each loan.
4. Outputs a survival dataset for model training.

Functions
---------
build_survival_dataset
    Main ETL function that merges origination and performance data.

Example
-------
>>> from rmbs_platform.ml.etl_freddie import build_survival_dataset
>>> df = build_survival_dataset(
...     orig_file="data/origination_2017Q1.csv",
...     perf_file="data/performance_2017Q1.csv",
...     output_file="data/survival_dataset.csv"
... )
>>> print(df[["LOAN_SEQUENCE_NUMBER", "DURATION", "EVENT"]].head())

Notes
-----
**Event Types**:

- 0: Censored (loan still active at observation end)
- 1: Prepaid (voluntary payoff, ZERO_BALANCE_CODE = 1)
- 2: Defaulted (foreclosure/charge-off, ZERO_BALANCE_CODE in [3, 6, 9])

See Also
--------
train_prepay : Uses the survival dataset for prepayment model training.
train_default : Uses the survival dataset for default model training.
config.TIME_COLS : Column names for Freddie Mac performance files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .config import TIME_COLS


def _get_event_status(group: pd.DataFrame) -> Tuple[int, int]:
    """
    Derive event type and duration for a single loan's performance history.

    This function analyzes a loan's monthly performance records to determine
    the ultimate outcome (prepay, default, or censored) and the time to that
    event.

    Parameters
    ----------
    group : pd.DataFrame
        All performance records for a single loan, with LOAN_AGE,
        ZERO_BALANCE_CODE, and CURRENT_LOAN_DELINQUENCY_STATUS columns.

    Returns
    -------
    tuple of (int, int)
        - duration: Months from origination to event (or last observation).
        - event_type: 0=censored, 1=prepaid, 2=defaulted.

    Notes
    -----
    **Event Detection Logic**:

    1. Check ZERO_BALANCE_CODE in final record:
       - 1 = Voluntary prepayment
       - 3, 6, 9 = Default-related termination
    2. If no zero balance code, check for serious delinquency (6+ months DQ).
    3. Otherwise, loan is censored (still active).

    Example
    -------
    >>> duration, event = _get_event_status(loan_perf_df)
    >>> if event == 1:
    ...     print(f"Loan prepaid at month {duration}")
    """
    group = group.sort_values("LOAN_AGE")
    last_row = group.iloc[-1]

    zbc = last_row.get("ZERO_BALANCE_CODE")
    try:
        zbc_float = float(zbc)
    except (ValueError, TypeError):
        zbc_float = 0.0

    # Prepayment: ZERO_BALANCE_CODE = 1
    if zbc_float == 1.0:
        return int(last_row["LOAN_AGE"]), 1

    # Default-related: ZERO_BALANCE_CODE in [3, 6, 9]
    if zbc_float in [3.0, 6.0, 9.0]:
        return int(last_row["LOAN_AGE"]), 2

    # Check for serious delinquency (6+ months)
    delinq_vals = pd.to_numeric(
        group["CURRENT_LOAN_DELINQUENCY_STATUS"], errors="coerce"
    ).fillna(0)
    if (delinq_vals >= 6).any():
        first_def_idx = (delinq_vals >= 6).idxmax()
        duration = int(group.loc[first_def_idx, "LOAN_AGE"])
        return duration, 2

    # Censored: loan still active
    return int(last_row["LOAN_AGE"]), 0


def build_survival_dataset(
    orig_file: str,
    perf_file: str,
    output_file: str,
) -> pd.DataFrame:
    """
    Create a survival dataset from Freddie Mac origination/performance tapes.

    This function merges loan characteristics from the origination file with
    event outcomes derived from the performance file, producing a dataset
    suitable for survival analysis (Cox PH, Random Survival Forest, etc.).

    Parameters
    ----------
    orig_file : str
        Path to the origination file (pipe-delimited).
        Contains loan attributes at origination.
    perf_file : str
        Path to the performance file (pipe-delimited).
        Contains monthly loan status records.
    output_file : str
        Path for the output CSV file.

    Returns
    -------
    pd.DataFrame
        Survival dataset with original columns plus:
        - ``DURATION``: Months from origination to event/censoring.
        - ``EVENT``: Outcome code (0=censored, 1=prepaid, 2=defaulted).

    Notes
    -----
    **File Formats**:

    The origination file should contain standard Freddie Mac columns:
    - LOAN_SEQUENCE_NUMBER, ORIGINAL_UPB, ORIGINAL_INTEREST_RATE
    - CREDIT_SCORE, ORIGINAL_LTV, FIRST_PAYMENT_DATE, etc.

    The performance file should contain monthly records with TIME_COLS.

    **Memory Usage**:

    Large datasets may require chunked processing. This implementation
    loads both files into memory, which may be problematic for very
    large portfolios.

    Example
    -------
    >>> df = build_survival_dataset(
    ...     "data/origination_2017.csv",
    ...     "data/performance_2017.csv",
    ...     "output/survival_2017.csv"
    ... )
    >>> prepay_count = (df["EVENT"] == 1).sum()
    >>> default_count = (df["EVENT"] == 2).sum()
    >>> print(f"Prepays: {prepay_count}, Defaults: {default_count}")
    """
    orig_path = Path(orig_file)
    perf_path = Path(perf_file)

    df_orig = pd.read_csv(orig_path, sep="|", low_memory=False)
    df_perf = pd.read_csv(
        perf_path, sep="|", names=TIME_COLS, header=0, low_memory=False
    )

    # Filter performance to loans in origination file
    target_ids = set(df_orig["LOAN_SEQUENCE_NUMBER"])
    df_perf = df_perf[df_perf["LOAN_SEQUENCE_NUMBER"].isin(target_ids)]

    # Derive event status for each loan
    events = df_perf.groupby("LOAN_SEQUENCE_NUMBER").apply(_get_event_status)
    df_events = pd.DataFrame(
        events.tolist(), index=events.index, columns=["DURATION", "EVENT"]
    )

    # Merge with origination data
    final_df = df_orig.merge(
        df_events, left_on="LOAN_SEQUENCE_NUMBER", right_index=True
    )
    final_df.to_csv(output_file, index=False)
    return final_df


def _cli() -> None:
    """
    CLI entry point for ETL processing.

    This function provides a command-line interface for running the
    survival dataset ETL process.

    Usage
    -----
    python -m rmbs_platform.ml.etl_freddie --orig data/orig.csv --perf data/perf.csv --out output.csv
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Build survival dataset from Freddie Mac tapes."
    )
    parser.add_argument(
        "--orig", required=True, help="Path to origination file (pipe-delimited)."
    )
    parser.add_argument(
        "--perf", required=True, help="Path to performance file (pipe-delimited)."
    )
    parser.add_argument("--out", required=True, help="Output CSV path.")
    args = parser.parse_args()

    build_survival_dataset(args.orig, args.perf, args.out)


if __name__ == "__main__":
    _cli()
