"""
ML Model Wrappers and Rate Simulation
=====================================

This module provides model wrappers for prepayment and default prediction,
along with a stochastic interest rate generator for scenario analysis.

Classes
-------
StochasticRateModel
    Vasicek-style short-rate generator for interest rate scenarios.
UniversalModel
    Wrapper for trained ML models with fallback to heuristic weights.

The models support two strategies:

1. **Pickle**: Load pre-trained models (CoxPH, RandomSurvivalForest).
2. **Hardcoded**: Use fallback weights when models aren't available.

Example
-------
>>> from rmbs_platform.ml.models import StochasticRateModel, UniversalModel
>>> # Generate rate scenarios
>>> vasicek = StochasticRateModel()
>>> rates = vasicek.generate_paths(60, start_rate=0.045, shock_scenario="rally")
>>> # Load prepayment model
>>> prepay = UniversalModel("models/prepay.pkl", "Prepay")
>>> multipliers = prepay.predict_multiplier(loan_features)

See Also
--------
portfolio.SurveillanceEngine : Uses these models for cashflow projection.
train_prepay : Training script for prepayment models.
train_default : Training script for default models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class StochasticRateModel:
    """
    Simple Vasicek-style short-rate generator for scenario analysis.

    The Vasicek model is a one-factor mean-reverting interest rate model:

        dr = κ(θ - r)dt + σdW

    Where:
    - r: Current short rate
    - κ (kappa): Speed of mean reversion
    - θ (theta): Long-term mean rate
    - σ (sigma): Volatility

    This model is used to generate interest rate paths for scenario analysis,
    which drive the rate incentive feature in prepayment modeling.

    Attributes
    ----------
    kappa : float
        Speed of mean reversion. Higher values = faster return to theta.
    theta : float
        Long-term mean rate (equilibrium level).
    sigma : float
        Volatility of rate changes.
    dt : float
        Time step in years (default: 1/12 for monthly).

    Notes
    -----
    **Shock Scenarios**:

    - ``rally``: Rates converge toward 2.5% (favorable for prepayment).
    - ``selloff``: Rates converge toward 7.5% (unfavorable for prepayment).
    - ``base``: Rates converge toward 4.5% (neutral).

    Example
    -------
    >>> model = StochasticRateModel(kappa=0.15, theta=0.045, sigma=0.012)
    >>> rates = model.generate_paths(60, start_rate=0.05, shock_scenario="rally")
    >>> print(f"Rate path: {rates[:5].round(4)}")
    """

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
        """
        Generate simulated short-rate paths for a given scenario.

        Parameters
        ----------
        n_months : int
            Number of monthly periods to simulate.
        n_sims : int, default 1
            Number of Monte Carlo paths to generate.
        start_rate : float, default 0.045
            Initial short rate (decimal, e.g., 0.045 for 4.5%).
        shock_scenario : str, optional
            Scenario type that adjusts the target mean:
            - "rally": Target 2.5%
            - "selloff": Target 7.5%
            - None or "base": Use default theta

        Returns
        -------
        np.ndarray
            Array of shape (n_months, n_sims) containing rate paths.
            All rates are floored at 0.1% to prevent negative rates.

        Notes
        -----
        Uses a fixed random seed (42) for reproducibility.

        Example
        -------
        >>> model = StochasticRateModel()
        >>> rates = model.generate_paths(60, n_sims=100, shock_scenario="selloff")
        >>> avg_terminal = rates[-1].mean()
        >>> print(f"Average terminal rate: {avg_terminal:.2%}")
        """
        np.random.seed(42)
        rates = np.zeros((n_months, n_sims))
        rates[0, :] = start_rate

        # Adjust target based on scenario
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
    """
    Load a prepay/default model or fall back to heuristic weights.

    This wrapper provides a consistent interface for ML-driven cashflow
    projection regardless of whether trained models are available.

    **Strategies**:

    - ``Pickle``: Successfully loaded a pre-trained model.
    - ``Hardcoded``: Using fallback weights (model loading failed).

    Parameters
    ----------
    model_path : str
        Path to the pickled model file (.pkl).
    model_type : str
        Model type: "Prepay" or "Default".

    Attributes
    ----------
    path : str
        Path to the model file.
    type : str
        Model type identifier.
    model : object or None
        Loaded model object, or None if loading failed.
    strategy : str
        Current strategy: "Pickle", "Hardcoded", or "Unknown".
    backup_weights : dict
        Fallback feature weights for hardcoded prediction.
    baseline : float
        Baseline hazard rate for hardcoded prediction.

    Notes
    -----
    **Fallback Weights**:

    For prepayment models:
    - RATE_INCENTIVE: 0.1511 (positive = higher prepay)
    - BURNOUT_PROXY: -0.0902 (cumulative incentive reduces prepay)
    - CREDIT_SCORE: 0.0001 (higher score = slightly higher prepay)
    - ORIGINAL_LTV: -0.0009 (higher LTV = lower prepay)
    - ORIGINAL_DEBT_TO_INCOME_RATIO: -0.0004

    For default models:
    - SATO: 0.5538 (spread at origination)
    - HIGH_LTV_FLAG: 0.3920 (LTV > 80)
    - FICO_BUCKET: 0.0276 (credit tier)
    - CREDIT_SCORE: -0.0020

    Example
    -------
    >>> model = UniversalModel("models/prepay.pkl", "Prepay")
    >>> print(f"Strategy: {model.strategy}")
    >>> multipliers = model.predict_multiplier(loan_df)
    """

    def __init__(self, model_path: str, model_type: str) -> None:
        """
        Initialize the model wrapper.

        Parameters
        ----------
        model_path : str
            Path to the pickled model file.
        model_type : str
            Model type: "Prepay" or "Default".
        """
        self.path = model_path
        self.type = model_type
        self.model: Optional[Any] = None
        self.strategy = "Unknown"

        # Fallback weights based on model type
        if self.type == "Prepay":
            self.backup_weights: Dict[str, float] = {
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
        """
        Attempt to load a serialized model; otherwise use fallback weights.

        Uses joblib to load pickled models. If loading fails for any reason
        (file not found, incompatible format, etc.), falls back to hardcoded
        weights.
        """
        try:
            import joblib

            self.model = joblib.load(self.path)
            self.strategy = "Pickle"
        except Exception:
            self.strategy = "Hardcoded"

    def predict_multiplier(self, df: Any) -> np.ndarray:
        """
        Return a hazard multiplier given a feature frame.

        The multiplier adjusts the baseline hazard rate based on loan
        characteristics. A multiplier > 1 indicates higher-than-average
        hazard (prepay or default).

        Parameters
        ----------
        df : pd.DataFrame
            Loan-level feature DataFrame with columns matching the
            expected features (RATE_INCENTIVE, CREDIT_SCORE, etc.).

        Returns
        -------
        np.ndarray
            Hazard multiplier for each loan. Shape: (n_loans,).

        Notes
        -----
        If the model is loaded (Pickle strategy), uses the model's
        ``predict_partial_hazard`` method. If using fallback weights,
        computes: ``exp(sum(feature * weight))``

        Example
        -------
        >>> loan_df = pd.DataFrame({
        ...     "RATE_INCENTIVE": [1.5, -0.5],
        ...     "CREDIT_SCORE": [720, 680],
        ...     "ORIGINAL_LTV": [75, 85],
        ... })
        >>> mult = model.predict_multiplier(loan_df)
        >>> print(f"Multipliers: {mult}")
        """
        if self.strategy == "Pickle" and self.model is not None:
            try:
                return self.model.predict_partial_hazard(df)
            except Exception:
                pass

        # Fallback: compute linear combination of features
        log_hazard = 0.0
        for feat, weight in self.backup_weights.items():
            if feat in df.columns:
                log_hazard += df[feat] * weight
        return np.exp(log_hazard)
