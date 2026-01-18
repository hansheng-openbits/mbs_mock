"""Train default model dataset and Cox model."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .features import add_default_features, normalize_columns


FEATURES = [
    "CREDIT_SCORE",
    "ORIGINAL_LTV",
    "ORIGINAL_DEBT_TO_INCOME_RATIO",
    "SATO",
    "FICO_BUCKET",
    "HIGH_LTV_FLAG",
]


def build_default_dataset(data_file: str, output_file: str) -> pd.DataFrame:
    """Prepare a default modeling dataset with engineered features."""
    df = pd.read_csv(data_file, low_memory=False)
    df = add_default_features(df)
    df["IS_DEFAULT"] = df["EVENT"].apply(lambda x: 1 if x == 2 else 0)
    df_default = normalize_columns(df, ["DURATION", "IS_DEFAULT"] + FEATURES).dropna()
    df_default.to_csv(output_file, index=False)
    return df_default


def train_default_model(data_file: str, output_dir: str) -> object:
    """Train a Cox default model and persist it to disk."""
    from lifelines import CoxPHFitter
    import joblib

    df = build_default_dataset(data_file, Path(output_dir) / "default_modeling_dataset.csv")
    cph = CoxPHFitter()
    cph.fit(df, duration_col="DURATION", event_col="IS_DEFAULT")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(cph, out_dir / "cox_default_model.pkl")
    return cph


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train default model.")
    parser.add_argument("--data", required=True, help="Path to mortgage_survival_dataset.csv")
    parser.add_argument("--out", required=True, help="Output directory for models")
    args = parser.parse_args()

    train_default_model(args.data, args.out)
