"""
Default Model Training
======================

This module provides training utilities for credit default prediction
models using survival analysis techniques. It focuses on Cox Proportional
Hazards models for default risk.

The training pipeline:

1. Loads and preprocesses a survival dataset.
2. Engineers default risk features (SATO, FICO bucket, high LTV flag).
3. Trains a Cox PH model for time-to-default.
4. Serializes the trained model for deployment.

Functions
---------
build_default_dataset
    Preprocess raw survival data with default features.
train_default_model
    Main training function that produces a Cox default model.

Features Used
-------------
- CREDIT_SCORE: FICO score at origination
- ORIGINAL_LTV: Loan-to-value ratio at origination
- ORIGINAL_DEBT_TO_INCOME_RATIO: DTI at origination
- SATO: Spread at origination (note rate - market rate)
- FICO_BUCKET: Credit tier (1=excellent to 4=poor)
- HIGH_LTV_FLAG: Binary indicator for LTV > 80%

Example
-------
>>> from rmbs_platform.ml.train_default import train_default_model
>>> cph = train_default_model(
...     data_file="data/survival_dataset.csv",
...     output_dir="models/"
... )
>>> print(f"Default model hazard ratios: {cph.hazard_ratios_}")

Notes
-----
Default modeling focuses on identifying loans at high risk of foreclosure
or charge-off. Unlike prepayment, defaults are typically involuntary and
driven by:

- Economic stress (job loss, income reduction)
- Negative equity (home value < loan balance)
- Credit deterioration

See Also
--------
etl_freddie : Creates the survival dataset from raw Freddie Mac files.
features.add_default_features : Engineers SATO, FICO bucket features.
models.UniversalModel : Wrapper for loading trained models.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .features import add_default_features, normalize_columns

# Model features for default prediction
FEATURES = [
    "CREDIT_SCORE",
    "ORIGINAL_LTV",
    "ORIGINAL_DEBT_TO_INCOME_RATIO",
    "SATO",
    "FICO_BUCKET",
    "HIGH_LTV_FLAG",
]


def build_default_dataset(data_file: str, output_file: str) -> pd.DataFrame:
    """
    Prepare a default modeling dataset with engineered features.

    This function loads a survival dataset, adds default-specific features,
    and creates the IS_DEFAULT binary outcome variable.

    Parameters
    ----------
    data_file : str
        Path to the survival dataset CSV (from etl_freddie).
    output_file : str
        Path to save the preprocessed dataset.

    Returns
    -------
    pd.DataFrame
        Preprocessed dataset with DURATION, IS_DEFAULT, and feature columns.

    Notes
    -----
    **IS_DEFAULT Definition**:

    IS_DEFAULT = 1 if EVENT == 2 (loan terminated due to default)
    IS_DEFAULT = 0 otherwise (prepaid, censored, or still active)

    Example
    -------
    >>> df = build_default_dataset("survival.csv", "default_dataset.csv")
    >>> default_rate = df["IS_DEFAULT"].mean()
    >>> print(f"Historical default rate: {default_rate:.2%}")
    """
    df = pd.read_csv(data_file, low_memory=False)
    df = add_default_features(df)
    df["IS_DEFAULT"] = df["EVENT"].apply(lambda x: 1 if x == 2 else 0)
    df_default = normalize_columns(df, ["DURATION", "IS_DEFAULT"] + FEATURES).dropna()
    df_default.to_csv(output_file, index=False)
    return df_default


def train_default_model(data_file: str, output_dir: str) -> object:
    """
    Train a Cox default model and persist it to disk.

    This function trains a Cox Proportional Hazards model to predict
    time-to-default risk based on borrower and loan characteristics.

    Parameters
    ----------
    data_file : str
        Path to the survival dataset CSV (from etl_freddie).
    output_dir : str
        Directory to save trained model file.

    Returns
    -------
    CoxPHFitter
        Trained Cox PH model object.

    Notes
    -----
    **Output Files**:

    - ``default_modeling_dataset.csv``: Preprocessed training data
    - ``cox_default_model.pkl``: Serialized Cox PH model

    **Interpretation**:

    The Cox model produces hazard ratios for each feature:
    - HR > 1: Feature increases default risk
    - HR < 1: Feature decreases default risk
    - HR = 1: No effect

    For example, if FICO_BUCKET has HR = 1.5, moving from tier 1 to tier 2
    increases default hazard by 50%.

    Example
    -------
    >>> cph = train_default_model("survival.csv", "models/")
    >>> # View significant predictors
    >>> print(cph.summary[cph.summary["p"] < 0.05])
    """
    from lifelines import CoxPHFitter
    import joblib

    df = build_default_dataset(
        data_file, Path(output_dir) / "default_modeling_dataset.csv"
    )
    cph = CoxPHFitter()
    cph.fit(df, duration_col="DURATION", event_col="IS_DEFAULT")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(cph, out_dir / "cox_default_model.pkl")
    return cph


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train default model.")
    parser.add_argument(
        "--data", required=True, help="Path to mortgage_survival_dataset.csv"
    )
    parser.add_argument("--out", required=True, help="Output directory for models")
    args = parser.parse_args()

    train_default_model(args.data, args.out)
