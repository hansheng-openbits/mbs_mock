"""Portfolio simulation and structuring logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from .models import UniversalModel
from .features import add_default_features, add_prepay_features


class DataManager:
    def __init__(self, static_file: str, perf_file: Optional[str] = None, feature_source: str = "simulated"):
        self.static_file = static_file
        self.perf_file = perf_file
        self.feature_source = feature_source
        self.raw_df: Optional[pd.DataFrame] = None
        self._load()

    @staticmethod
    def _read_static(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, sep="|", low_memory=False)
        if len(df.columns) == 1 and "," in df.columns[0]:
            df = pd.read_csv(path, sep=",", low_memory=False)
        elif "LoanId" not in df.columns and "LOAN_SEQUENCE_NUMBER" not in df.columns:
            df = pd.read_csv(path, sep=",", low_memory=False)
        return df

    @staticmethod
    def _normalize_static(df: pd.DataFrame) -> pd.DataFrame:
        if "LoanId" in df.columns:
            df = df.rename(
                columns={
                    "LoanId": "LOAN_ID",
                    "OriginalBalance": "ORIG_UPB",
                    "CurrentBalance": "CURRENT_UPB",
                    "NoteRate": "NOTE_RATE",
                    "RemainingTermMonths": "TERM",
                    "LTV": "LTV",
                    "FICO": "FICO",
                    "DTI": "DTI",
                }
            )
            df["LOAN_ID"] = df["LOAN_ID"].astype(str)
        else:
            col_map = {
                "LOAN_SEQUENCE_NUMBER": "LOAN_ID",
                "ORIGINAL_UPB": "ORIG_UPB",
                "ORIGINAL_INTEREST_RATE": "NOTE_RATE",
                "CREDIT_SCORE": "FICO",
                "ORIGINAL_LOAN_TERM": "TERM",
                "ORIGINAL_LTV": "LTV",
                "PROPERTY_STATE": "STATE",
                "ORIGINAL_DEBT_TO_INCOME_RATIO": "DTI",
            }
            df = df.rename(columns=col_map)

        for c in ["ORIG_UPB", "FICO", "LTV", "DTI", "TERM"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        if "DURATION" not in df.columns and "TERM" in df.columns:
            df["DURATION"] = df["TERM"]

        if "NOTE_RATE" not in df.columns:
            for alt in ["OriginalInterestRate", "ORIGINAL_INTEREST_RATE", "NoteRate"]:
                if alt in df.columns:
                    df["NOTE_RATE"] = pd.to_numeric(df[alt], errors="coerce").fillna(0)
                    break
        if "NOTE_RATE" in df.columns:
            df["NOTE_RATE"] = df["NOTE_RATE"].apply(lambda x: x / 100 if x > 1 else x)

        if "CURRENT_UPB" not in df.columns:
            df["CURRENT_UPB"] = df.get("ORIG_UPB", 0)

        return df

    def _load(self):
        if not Path(self.static_file).exists():
            self.raw_df = self._generate_mock(1000)
            return

        df = self._read_static(Path(self.static_file))
        df = self._normalize_static(df)

        if self.feature_source == "market_rates":
            df = add_prepay_features(df)
            df = add_default_features(df)
        if "RATE_INCENTIVE" not in df.columns:
            df["RATE_INCENTIVE"] = (df.get("NOTE_RATE", 0) * 100) - 4.0
        if "SATO" not in df.columns:
            df["SATO"] = df["RATE_INCENTIVE"]
        if "FICO_BUCKET" not in df.columns:
            df["FICO_BUCKET"] = np.select(
                [df.get("FICO", 0) >= 750, df.get("FICO", 0) >= 700],
                [1, 2],
                default=3,
            )
        if "HIGH_LTV_FLAG" not in df.columns:
            df["HIGH_LTV_FLAG"] = (df.get("LTV", 0) > 80).astype(int)
        if "BURNOUT_PROXY" not in df.columns:
            df["BURNOUT_PROXY"] = 0.0

        df["ORIGINAL_INTEREST_RATE"] = df.get("NOTE_RATE", 0)
        df["CREDIT_SCORE"] = df.get("FICO", 0)
        df["ORIGINAL_LTV"] = df.get("LTV", 0)
        df["ORIGINAL_DEBT_TO_INCOME_RATIO"] = df.get("DTI", 0)

        if self.perf_file and Path(self.perf_file).exists():
            df_perf = pd.read_csv(
                self.perf_file,
                sep="|",
                usecols=["LOAN_SEQUENCE_NUMBER", "CURRENT_ACTUAL_UPB"],
                low_memory=False,
            )
            df_perf.rename(columns={"LOAN_SEQUENCE_NUMBER": "LOAN_ID"}, inplace=True)
            latest = df_perf.groupby("LOAN_ID")["CURRENT_ACTUAL_UPB"].last().reset_index()
            df = pd.merge(df, latest, on="LOAN_ID", how="left")
            df["CURRENT_UPB"] = df["CURRENT_ACTUAL_UPB"].fillna(df["ORIG_UPB"])
            df = df[df["CURRENT_UPB"] > 0]
        else:
            df["CURRENT_UPB"] = df["ORIG_UPB"]

        self.raw_df = df

    def _generate_mock(self, n: int) -> pd.DataFrame:
        return pd.DataFrame({"ORIG_UPB": [300000] * n, "CURRENT_UPB": [300000] * n})

    def get_pool(self) -> pd.DataFrame:
        return self.raw_df[self.raw_df["CURRENT_UPB"] > 0].copy()


class SurveillanceEngine:
    def __init__(
        self,
        pool: pd.DataFrame,
        prepay_model: UniversalModel,
        default_model: UniversalModel,
        feature_source: str = "simulated",
    ):
        self.pool = pool.copy()
        self.prepay = prepay_model
        self.default = default_model
        self.feature_source = feature_source

    def run(self, rate_path: np.ndarray) -> pd.DataFrame:
        loans = self.pool.copy()
        if "NOTE_RATE" not in loans.columns:
            loans["NOTE_RATE"] = 0.0
        if "BURNOUT_PROXY" not in loans.columns:
            loans["BURNOUT_PROXY"] = 0.0
        if "FICO" not in loans.columns:
            loans["FICO"] = 0.0
        if "LTV" not in loans.columns:
            loans["LTV"] = 0.0
        if "FICO_BUCKET" not in loans.columns:
            loans["FICO_BUCKET"] = np.select([loans["FICO"] >= 750, loans["FICO"] >= 700], [1, 2], default=3)
        if "HIGH_LTV_FLAG" not in loans.columns:
            loans["HIGH_LTV_FLAG"] = (loans["LTV"] > 80).astype(int)
        if "SATO" not in loans.columns:
            loans["SATO"] = (loans["NOTE_RATE"] * 100) - 4.0
        loans["Active_Bal"] = loans["CURRENT_UPB"]
        history = []

        base_cpr = 0.06
        base_cdr = 0.005

        if len(rate_path.shape) > 1:
            rate_path = rate_path.flatten()

        for t, curr_rate in enumerate(rate_path):
            if loans["Active_Bal"].sum() < 1000:
                break

            if self.feature_source == "simulated":
                loans["RATE_INCENTIVE"] = (loans["NOTE_RATE"] - curr_rate) * 100
                loans["BURNOUT_PROXY"] += np.where(loans["RATE_INCENTIVE"] > 0.5, 1.0, 0.0)

            cpr_mult = np.clip(self.prepay.predict_multiplier(loans), 0.1, 20.0)
            cdr_mult = np.clip(self.default.predict_multiplier(loans), 0.1, 10.0)

            cpr = np.clip(base_cpr * cpr_mult, 0.0, 1.0)
            cdr = np.clip(base_cdr * cdr_mult, 0.0, 1.0)

            smm = 1 - (1 - cpr) ** (1 / 12)
            mdr = 1 - (1 - cdr) ** (1 / 12)

            int_paid = loans["Active_Bal"] * (loans["NOTE_RATE"] / 12)
            r = loans["NOTE_RATE"] / 12
            denom = 1 - (1 + r) ** (-loans["TERM"])
            sched_pmt = loans["Active_Bal"] * r / np.where(denom == 0, 1e-9, denom)
            sched_prin = (sched_pmt - int_paid).clip(lower=0)

            prepay = (loans["Active_Bal"] - sched_prin) * smm
            default = (loans["Active_Bal"] - sched_prin - prepay) * mdr
            loss = default * 0.35

            loans["Active_Bal"] -= (sched_prin + prepay + default)
            loans["Active_Bal"] = loans["Active_Bal"].clip(lower=0)

            history.append({
                "Period": t + 1,
                "Market_Rate": float(curr_rate),
                "Interest": float(int_paid.sum()),
                "Principal": float((sched_prin + prepay + default - loss).sum()),
                "Loss": float(loss.sum()),
                "CPR": float(cpr.mean()),
                "EndBalance": float(loans["Active_Bal"].sum()),
            })

        return pd.DataFrame(history)


@dataclass
class Tranche:
    name: str
    balance: float
    coupon: float
    orig: float
    cfs: List[float]

    @classmethod
    def create(cls, name: str, balance: float, coupon: float) -> "Tranche":
        return cls(name=name, balance=balance, coupon=coupon, orig=balance, cfs=[])


def run_waterfall(tranches: List[Tranche], cfs: pd.DataFrame) -> List[Tranche]:
    equity = tranches[-1]
    for row in cfs.itertuples():
        avail_int = row.Interest
        avail_prin = row.Principal

        for t in tranches[:-1]:
            pay = min(avail_int, t.balance * t.coupon / 12) if t.balance > 0 else 0
            avail_int -= pay
            t.cfs.append(pay)

        for t in tranches[:-1]:
            pay = min(t.balance, avail_prin) if t.balance > 0 else 0
            t.balance -= pay
            avail_prin -= pay
            t.cfs[-1] += pay

        equity.cfs.append(avail_int + avail_prin)

    return tranches
