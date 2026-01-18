"""Train prepayment models (Cox + RSF)."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .features import add_prepay_features, normalize_columns


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
    """Train Cox and RSF prepayment models from a survival dataset."""
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    from sklearn.model_selection import train_test_split
    from sksurv.ensemble import RandomSurvivalForest
    from sksurv.util import Surv
    import joblib

    df = pd.read_csv(data_file, low_memory=False)
    df = add_prepay_features(df)
    df["IS_PREPAID"] = df["EVENT"].apply(lambda x: 1 if x == 1 else 0)

    df_clean = normalize_columns(df, FEATURES + ["DURATION", "IS_PREPAID"]).dropna()
    train, test = train_test_split(df_clean, test_size=test_size, random_state=seed)

    cph = CoxPHFitter()
    cph.fit(train, duration_col="DURATION", event_col="IS_PREPAID")
    cox_pred = cph.predict_partial_hazard(test)
    _ = concordance_index(test["DURATION"], -cox_pred, test["IS_PREPAID"])

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

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(cph, out_dir / "cox_prepayment_model.pkl")
    joblib.dump(rsf, out_dir / "rsf_prepayment_model.pkl")
    return cph, rsf


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train prepayment models.")
    parser.add_argument("--data", required=True, help="Path to mortgage_survival_dataset.csv")
    parser.add_argument("--out", required=True, help="Output directory for models")
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_prepay_models(args.data, args.out, args.test_size, args.seed)
