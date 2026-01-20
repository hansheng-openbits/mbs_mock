"""
Feature Engineering for Prepayment and Default Modeling
=======================================================

This module provides feature engineering utilities for mortgage prepayment
and default prediction. The features capture economic incentives and
borrower characteristics that drive mortgage termination behavior.

Key Features
------------
**Prepayment Features** (``add_prepay_features``):

- ``RATE_INCENTIVE``: Current note rate - market rate (refinance incentive)
- ``BURNOUT_PROXY``: Cumulative rate incentive (borrower refinance fatigue)

**Default Features** (``add_default_features``):

- ``SATO``: Spread at Origination (note rate - market rate at origination)
- ``FICO_BUCKET``: Credit score tier (1=excellent, 4=subprime)
- ``HIGH_LTV_FLAG``: Binary indicator for LTV > 80%

Example
-------
>>> from rmbs_platform.ml.features import add_prepay_features, add_default_features
>>> df = pd.read_csv("loan_tape.csv")
>>> df = add_prepay_features(df)
>>> df = add_default_features(df)
>>> print(df[["RATE_INCENTIVE", "BURNOUT_PROXY", "SATO"]].describe())

See Also
--------
config.MARKET_RATES : Historical market rate data for feature calculation.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

from .config import MARKET_RATES


def get_rate_incentive_metrics(
    first_payment_yyyymm: int,
    duration_months: int,
    note_rate: float,
    market_rates: Optional[Dict[int, float]] = None,
) -> Tuple[float, float]:
    """
    Compute current and cumulative rate incentive for a loan.

    Rate incentive is the difference between a loan's note rate and the
    prevailing market rate. Positive incentive indicates the borrower
    is paying above-market rates and has refinance motivation.

    Parameters
    ----------
    first_payment_yyyymm : int
        First payment date as YYYYMM integer (e.g., 201901 for Jan 2019).
    duration_months : int
        Number of months since first payment (loan age).
    note_rate : float
        Original note rate (decimal, e.g., 0.045 for 4.5%).
    market_rates : dict, optional
        Custom market rate lookup. If None, uses MARKET_RATES from config.

    Returns
    -------
    tuple of (float, float)
        - current_incentive: Rate incentive at the current period.
        - cumulative_incentive: Sum of positive incentives over loan life.

    Notes
    -----
    **Rate Incentive Interpretation**:

    - Positive: Borrower paying above market → incentive to refinance
    - Negative: Borrower paying below market → no refinance incentive
    - Higher cumulative: "Burnout" - borrowers who haven't refinanced despite
      repeated incentive may be less likely to do so (selection effect).

    Example
    -------
    >>> current, cumulative = get_rate_incentive_metrics(
    ...     first_payment_yyyymm=201901,
    ...     duration_months=36,
    ...     note_rate=0.045
    ... )
    >>> print(f"Current incentive: {current:.2%}, Burnout: {cumulative:.2f}")
    """
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
    """
    Add prepayment-related features to a loan tape.

    This function computes rate incentive and burnout proxy features
    for prepayment modeling. These features capture the economic
    motivation and behavioral fatigue in refinancing decisions.

    Parameters
    ----------
    df : pd.DataFrame
        Loan tape with required columns:
        - ``FIRST_PAYMENT_DATE``: YYYYMM integer
        - ``DURATION``: Months since first payment
        - ``ORIGINAL_INTEREST_RATE``: Note rate (%)

    Returns
    -------
    pd.DataFrame
        Input DataFrame with additional columns:
        - ``RATE_INCENTIVE``: Current note rate - market rate
        - ``BURNOUT_PROXY``: Cumulative positive incentive

    Notes
    -----
    Missing or invalid values default to 0.0 for both features.

    Example
    -------
    >>> df = pd.DataFrame({
    ...     "FIRST_PAYMENT_DATE": [201901, 202001],
    ...     "DURATION": [24, 12],
    ...     "ORIGINAL_INTEREST_RATE": [4.5, 3.5]
    ... })
    >>> df = add_prepay_features(df)
    >>> print(df[["RATE_INCENTIVE", "BURNOUT_PROXY"]])
    """

    def apply_metrics(row: pd.Series) -> pd.Series:
        """Compute rate incentive metrics for a single loan."""
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
    """
    Add default-related features to a loan tape.

    This function computes credit risk features for default modeling.
    These features capture borrower creditworthiness and underwriting
    quality indicators.

    Parameters
    ----------
    df : pd.DataFrame
        Loan tape with required columns:
        - ``FIRST_PAYMENT_DATE``: YYYYMM integer
        - ``ORIGINAL_INTEREST_RATE``: Note rate (%)
        - ``CREDIT_SCORE``: FICO score (optional)
        - ``ORIGINAL_LTV``: Loan-to-value ratio (optional)

    Returns
    -------
    pd.DataFrame
        Input DataFrame with additional columns:
        - ``SATO``: Spread at origination (note rate - market rate)
        - ``FICO_BUCKET``: Credit tier (1=excellent, 2=good, 3=fair, 4=poor)
        - ``HIGH_LTV_FLAG``: 1 if LTV > 80%, else 0

    Notes
    -----
    **SATO (Spread at Origination)**:

    Higher SATO indicates the borrower paid above-market rates at origination,
    which may indicate higher credit risk (subprime or non-prime loans).

    **FICO Buckets**:

    - 1: FICO >= 750 (Excellent)
    - 2: 700 <= FICO < 750 (Good)
    - 3: 660 <= FICO < 700 (Fair)
    - 4: FICO < 660 (Poor)

    Example
    -------
    >>> df = pd.DataFrame({
    ...     "FIRST_PAYMENT_DATE": [201901],
    ...     "ORIGINAL_INTEREST_RATE": [5.0],
    ...     "CREDIT_SCORE": [680],
    ...     "ORIGINAL_LTV": [85]
    ... })
    >>> df = add_default_features(df)
    >>> print(df[["SATO", "FICO_BUCKET", "HIGH_LTV_FLAG"]])
    """

    def engineer(row: pd.Series) -> pd.Series:
        """Compute default risk features for a single loan."""
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
    """
    Ensure required columns exist, raising a clear error if missing.

    This utility function validates that a DataFrame contains all
    columns required for model training or prediction.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to validate.
    required : iterable of str
        Column names that must be present.

    Returns
    -------
    pd.DataFrame
        A copy of the input DataFrame (unchanged if validation passes).

    Raises
    ------
    ValueError
        If any required columns are missing.

    Example
    -------
    >>> df = normalize_columns(loan_df, ["RATE_INCENTIVE", "CREDIT_SCORE"])
    """
    df = df.copy()
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df
