"""Model wrappers and rate simulation for ML-based RMBS projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any

import numpy as np


@dataclass
class StochasticRateModel:
    """Simple Vasicek-style short-rate generator for scenario analysis."""
    kappa: float = 0.15
    theta: float = 0.045
    sigma: float = 0.012
    dt: float = 1 / 12

    def generate_paths(
        self,
        n_months: int,
        n_sims: int = 1,
        start_rate: float = 0.045,
        shock_scenario: Optional[str] = None,
    ) -> np.ndarray:
        """Generate simulated short-rate paths for a given scenario."""
        np.random.seed(42)
        rates = np.zeros((n_months, n_sims))
        rates[0, :] = start_rate

        target_mean = self.theta
        if shock_scenario == "rally":
            target_mean = 0.025
        elif shock_scenario == "selloff":
            target_mean = 0.075

        for t in range(1, n_months):
            r_prev = rates[t - 1, :]
            dW = np.random.normal(0, np.sqrt(self.dt), n_sims)
            dr = self.kappa * (target_mean - r_prev) * self.dt + self.sigma * dW
            rates[t, :] = r_prev + dr

        return np.maximum(rates, 0.001)


class UniversalModel:
    """Loads a prepay/default model or falls back to heuristic weights."""

    def __init__(self, model_path: str, model_type: str) -> None:
        self.path = model_path
        self.type = model_type
        self.model = None
        self.strategy = "Unknown"
        if self.type == "Prepay":
            self.backup_weights = {
                "RATE_INCENTIVE": 0.1511,
                "BURNOUT_PROXY": -0.0902,
                "CREDIT_SCORE": 0.0001,
                "ORIGINAL_LTV": -0.0009,
                "ORIGINAL_DEBT_TO_INCOME_RATIO": -0.0004,
            }
            self.baseline = 0.06
        else:
            self.backup_weights = {
                "SATO": 0.5538,
                "HIGH_LTV_FLAG": 0.3920,
                "FICO_BUCKET": 0.0276,
                "CREDIT_SCORE": -0.0020,
            }
            self.baseline = 0.005

        self._initialize()

    def _initialize(self) -> None:
        """Attempt to load a serialized model; otherwise use fallback weights."""
        try:
            import joblib

            self.model = joblib.load(self.path)
            self.strategy = "Pickle"
        except Exception:
            self.strategy = "Hardcoded"

    def predict_multiplier(self, df: Any) -> np.ndarray:
        """Return a hazard multiplier given a feature frame."""
        if self.strategy == "Pickle" and self.model is not None:
            try:
                return self.model.predict_partial_hazard(df)
            except Exception:
                pass

        log_hazard = 0.0
        for feat, weight in self.backup_weights.items():
            if feat in df.columns:
                log_hazard += df[feat] * weight
        return np.exp(log_hazard)
