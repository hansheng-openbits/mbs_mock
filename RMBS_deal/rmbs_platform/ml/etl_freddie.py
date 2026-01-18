"""ETL for Freddie Mac origination + performance tapes."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .config import TIME_COLS


def _get_event_status(group: pd.DataFrame) -> Tuple[int, int]:
    """Derive event type and duration for a single loan's performance history."""
    group = group.sort_values("LOAN_AGE")
    last_row = group.iloc[-1]

    zbc = last_row.get("ZERO_BALANCE_CODE")
    try:
        zbc_float = float(zbc)
    except (ValueError, TypeError):
        zbc_float = 0.0

    if zbc_float == 1.0:
        return int(last_row["LOAN_AGE"]), 1

    if zbc_float in [3.0, 6.0, 9.0]:
        return int(last_row["LOAN_AGE"]), 2

    delinq_vals = pd.to_numeric(
        group["CURRENT_LOAN_DELINQUENCY_STATUS"], errors="coerce"
    ).fillna(0)
    if (delinq_vals >= 6).any():
        first_def_idx = (delinq_vals >= 6).idxmax()
        duration = int(group.loc[first_def_idx, "LOAN_AGE"])
        return duration, 2

    return int(last_row["LOAN_AGE"]), 0


def build_survival_dataset(
    orig_file: str,
    perf_file: str,
    output_file: str,
) -> pd.DataFrame:
    """Create a survival dataset from Freddie Mac origination/performance tapes."""
    orig_path = Path(orig_file)
    perf_path = Path(perf_file)

    df_orig = pd.read_csv(orig_path, sep="|", low_memory=False)
    df_perf = pd.read_csv(perf_path, sep="|", names=TIME_COLS, header=0, low_memory=False)

    target_ids = set(df_orig["LOAN_SEQUENCE_NUMBER"])
    df_perf = df_perf[df_perf["LOAN_SEQUENCE_NUMBER"].isin(target_ids)]

    events = df_perf.groupby("LOAN_SEQUENCE_NUMBER").apply(_get_event_status)
    df_events = pd.DataFrame(events.tolist(), index=events.index, columns=["DURATION", "EVENT"])

    final_df = df_orig.merge(df_events, left_on="LOAN_SEQUENCE_NUMBER", right_index=True)
    final_df.to_csv(output_file, index=False)
    return final_df


def _cli() -> None:
    """CLI entry point for ETL processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Build survival dataset from Freddie Mac tapes.")
    parser.add_argument("--orig", required=True, help="Path to origination file (pipe-delimited).")
    parser.add_argument("--perf", required=True, help="Path to performance file (pipe-delimited).")
    parser.add_argument("--out", required=True, help="Output CSV path.")
    args = parser.parse_args()

    build_survival_dataset(args.orig, args.perf, args.out)


if __name__ == "__main__":
    _cli()
