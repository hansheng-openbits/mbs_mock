"""
Prepayment Model Training
=========================

This module provides training utilities for prepayment prediction models
using survival analysis techniques. It trains both Cox Proportional Hazards
and Random Survival Forest models.

The training pipeline:

1. Loads and preprocesses a survival dataset.
2. Engineers prepayment features (rate incentive, burnout proxy).
3. Splits data into train/test sets.
4. Trains Cox PH and RSF models.
5. Evaluates model performance (concordance index).
6. Serializes trained models for deployment.

Functions
---------
train_prepay_models
    Main training function that produces both Cox and RSF models.

Features Used
-------------
- RATE_INCENTIVE: Current note rate - market rate (refinance incentive)
- BURNOUT_PROXY: Cumulative rate incentive over loan life
- CREDIT_SCORE: FICO score at origination
- ORIGINAL_LTV: Loan-to-value ratio at origination
- ORIGINAL_DEBT_TO_INCOME_RATIO: DTI at origination
- ORIGINAL_INTEREST_RATE: Note rate at origination

Example
-------
>>> from rmbs_platform.ml.train_prepay import train_prepay_models
>>> cph, rsf = train_prepay_models(
...     data_file="data/survival_dataset.csv",
...     output_dir="models/",
...     test_size=0.25
... )
>>> print(f"Cox model features: {cph.params_.index.tolist()}")

See Also
--------
etl_freddie : Creates the survival dataset from raw Freddie Mac files.
features.add_prepay_features : Engineers rate incentive features.
models.UniversalModel : Wrapper for loading trained models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .features import add_prepay_features, normalize_columns

# Model features for prepayment prediction
FEATURES = [
    "RATE_INCENTIVE",
    "BURNOUT_PROXY",
    "CREDIT_SCORE",
    "ORIGINAL_LTV",
    "ORIGINAL_DEBT_TO_INCOME_RATIO",
    "ORIGINAL_INTEREST_RATE",
]


def train_prepay_models(
    data_file: str,
    output_dir: str,
    test_size: float = 0.25,
    seed: int = 42,
) -> Tuple[object, object]:
    """
    Train Cox and RSF prepayment models from a survival dataset.

    This function trains two complementary models:

    1. **Cox Proportional Hazards (CoxPH)**: Linear model that estimates
       hazard ratios for each feature. Fast to train and interpret.
    2. **Random Survival Forest (RSF)**: Non-linear ensemble model that
       captures complex interactions. Better predictive performance but
       slower and less interpretable.

    Parameters
    ----------
    data_file : str
        Path to the survival dataset CSV (from etl_freddie).
        Must contain DURATION, EVENT columns and feature columns.
    output_dir : str
        Directory to save trained model files (.pkl).
    test_size : float, default 0.25
        Fraction of data to use for testing.
    seed : int, default 42
        Random seed for reproducibility.

    Returns
    -------
    tuple of (CoxPHFitter, RandomSurvivalForest)
        Trained model objects.

    Notes
    -----
    **Output Files**:

    - ``cox_prepayment_model.pkl``: Serialized Cox PH model
    - ``rsf_prepayment_model.pkl``: Serialized Random Survival Forest

    **Model Evaluation**:

    The function computes concordance index (C-index) on the test set.
    C-index measures the model's ability to rank loans by prepayment risk:
    - 0.5 = random (no predictive power)
    - 1.0 = perfect ranking
    - >0.7 = generally considered good for mortgage prepayment

    **Dependencies**:

    - lifelines: Cox PH implementation
    - scikit-survival: RSF implementation
    - joblib: Model serialization

    Example
    -------
    >>> cph, rsf = train_prepay_models(
    ...     "data/mortgage_survival_dataset.csv",
    ...     "models/"
    ... )
    >>> # Inspect Cox coefficients
    >>> print(cph.summary)
    >>> # Get RSF feature importance
    >>> print(dict(zip(FEATURES, rsf.feature_importances_)))
    """
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    from sklearn.model_selection import train_test_split
    from sksurv.ensemble import RandomSurvivalForest
    from sksurv.util import Surv
    import joblib

    # Load and preprocess data
    df = pd.read_csv(data_file, low_memory=False)
    df = add_prepay_features(df)
    df["IS_PREPAID"] = df["EVENT"].apply(lambda x: 1 if x == 1 else 0)

    # Clean and split data
    df_clean = normalize_columns(df, FEATURES + ["DURATION", "IS_PREPAID"]).dropna()
    train, test = train_test_split(df_clean, test_size=test_size, random_state=seed)

    # Train Cox Proportional Hazards
    cph = CoxPHFitter()
    cph.fit(train, duration_col="DURATION", event_col="IS_PREPAID")
    cox_pred = cph.predict_partial_hazard(test)
    _ = concordance_index(test["DURATION"], -cox_pred, test["IS_PREPAID"])

    # Train Random Survival Forest
    X_train = train[FEATURES]
    X_test = test[FEATURES]
    y_train_surv = Surv.from_dataframe("IS_PREPAID", "DURATION", train)
    y_test_surv = Surv.from_dataframe("IS_PREPAID", "DURATION", test)

    rsf = RandomSurvivalForest(
        n_estimators=100,
        min_samples_split=10,
        min_samples_leaf=15,
        n_jobs=-1,
        random_state=seed,
    )
    rsf.fit(X_train, y_train_surv)
    _ = rsf.score(X_test, y_test_surv)

    # Save models
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(cph, out_dir / "cox_prepayment_model.pkl")
    joblib.dump(rsf, out_dir / "rsf_prepayment_model.pkl")

    return cph, rsf


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train prepayment models.")
    parser.add_argument(
        "--data", required=True, help="Path to mortgage_survival_dataset.csv"
    )
    parser.add_argument("--out", required=True, help="Output directory for models")
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_prepay_models(args.data, args.out, args.test_size, args.seed)
