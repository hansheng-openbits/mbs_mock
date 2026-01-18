"""Feature engineering utilities for prepay/default modeling."""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

import pandas as pd

from .config import MARKET_RATES


def get_rate_incentive_metrics(
    first_payment_yyyymm: int,
    duration_months: int,
    note_rate: float,
    market_rates: Dict[int, float] | None = None,
) -> Tuple[float, float]:
    """Compute current and cumulative rate incentive for a loan."""
    rates = market_rates or MARKET_RATES
    start_year = first_payment_yyyymm // 100
    start_month = first_payment_yyyymm % 100

    cumulative = 0.0
    current = 0.0
    duration = min(int(duration_months or 0), 360)

    for i in range(duration):
        total_months = start_month + i - 1
        curr_year = start_year + (total_months // 12)
        curr_month = total_months % 12
        if curr_month == 0:
            curr_month = 12
            curr_year -= 1
        yyyymm = curr_year * 100 + curr_month
        market_rate = rates.get(yyyymm, 4.0)
        incentive = note_rate - market_rate
        if incentive > 0:
            cumulative += incentive
        if i == duration - 1:
            current = incentive

    return current, cumulative


def add_prepay_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add prepayment-related features to a loan tape."""
    def apply_metrics(row):
        try:
            current, cumulative = get_rate_incentive_metrics(
                int(row["FIRST_PAYMENT_DATE"]),
                int(row["DURATION"]),
                float(row["ORIGINAL_INTEREST_RATE"]),
            )
            return pd.Series([current, cumulative])
        except Exception:
            return pd.Series([0.0, 0.0])

    metrics = df.apply(apply_metrics, axis=1)
    df = df.copy()
    df[["RATE_INCENTIVE", "BURNOUT_PROXY"]] = metrics
    return df


def add_default_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add default-related features to a loan tape."""
    def engineer(row):
        try:
            orig_date = int(row["FIRST_PAYMENT_DATE"])
            mkt_rate = MARKET_RATES.get(orig_date, 4.0)
            sato = float(row["ORIGINAL_INTEREST_RATE"]) - mkt_rate
        except Exception:
            sato = 0.0

        fico = float(row.get("CREDIT_SCORE", 0) or 0)
        if fico >= 750:
            fico_bucket = 1
        elif fico >= 700:
            fico_bucket = 2
        elif fico >= 660:
            fico_bucket = 3
        else:
            fico_bucket = 4

        ltv = float(row.get("ORIGINAL_LTV", 0) or 0)
        high_ltv_flag = 1 if ltv > 80 else 0

        return pd.Series([sato, fico_bucket, high_ltv_flag])

    df = df.copy()
    df[["SATO", "FICO_BUCKET", "HIGH_LTV_FLAG"]] = df.apply(engineer, axis=1)
    return df


def normalize_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    """Ensure required columns exist, raising a clear error if missing."""
    df = df.copy()
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df
