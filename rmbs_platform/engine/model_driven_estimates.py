"""
Model-Driven Pricing Estimates
==============================

This module provides ML-driven estimates for CPR, CDR, and Loss Severity
based on pool characteristics and market conditions. It bridges the ML
models in `ml/` with the investor pricing interface.

The estimates use:
- Prepayment model coefficients for CPR
- Default model coefficients for CDR
- Severity model for Loss Given Default

Example
-------
>>> from engine.model_driven_estimates import ModelDrivenEstimator
>>> estimator = ModelDrivenEstimator()
>>> result = estimator.estimate(
...     wa_fico=720,
...     wa_ltv=75,
...     wa_coupon=0.05,
...     current_market_rate=0.065,
...     rate_scenario="base"
... )
>>> print(f"CPR: {result.cpr:.1%}, CDR: {result.cdr:.1%}, Severity: {result.severity:.1%}")
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Tuple, List
import numpy as np


@dataclass
class ModelEstimate:
    """Container for model-driven CPR/CDR/Severity estimates with confidence intervals."""
    
    # Point estimates
    cpr: float
    cdr: float
    severity: float
    
    # Confidence intervals (low, high)
    cpr_range: Tuple[float, float]
    cdr_range: Tuple[float, float]
    severity_range: Tuple[float, float]
    
    # Model inputs used
    inputs: Dict[str, Any]
    
    # Component breakdowns
    cpr_components: Dict[str, float]
    cdr_components: Dict[str, float]
    severity_components: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return asdict(self)


class ModelDrivenEstimator:
    """
    Provides ML-driven estimates for pricing assumptions.
    
    Uses the actual model coefficients from the trained prepayment,
    default, and severity models to generate realistic estimates
    based on pool characteristics.
    """
    
    # Prepayment model coefficients (from ml/models.py)
    PREPAY_WEIGHTS = {
        "RATE_INCENTIVE": 0.1511,      # + rate incentive → higher prepay
        "BURNOUT_PROXY": -0.0902,       # - cumulative incentive → burnout
        "CREDIT_SCORE": 0.0001,         # + FICO → slightly higher prepay
        "ORIGINAL_LTV": -0.0009,        # + LTV → lower prepay (less equity)
        "ORIGINAL_DTI": -0.0004,        # + DTI → lower prepay
    }
    PREPAY_BASELINE = 0.06  # 6% annualized baseline SMM
    
    # Default model coefficients (from ml/models.py)
    DEFAULT_WEIGHTS = {
        "SATO": 0.5538,                 # + spread at origination → higher default
        "HIGH_LTV_FLAG": 0.3920,        # LTV > 80 → higher default
        "FICO_BUCKET": 0.0276,          # + FICO bucket (worse) → higher default
        "CREDIT_SCORE": -0.0020,        # + FICO → lower default
    }
    DEFAULT_BASELINE = 0.005  # 0.5% annualized baseline CDR
    
    # Severity model coefficients (from ml/severity.py)
    SEVERITY_BASE = 0.35
    SEVERITY_LTV_COEF = 0.004          # per point above 80 LTV
    SEVERITY_FICO_COEF = -0.0002       # per FICO point above 700
    SEVERITY_DTI_COEF = 0.002          # per point above 36 DTI
    
    # Rate scenario adjustments
    RATE_SCENARIOS = {
        "rally": {"target_rate": 0.025, "prepay_multiplier": 1.8, "default_multiplier": 0.9},
        "base": {"target_rate": 0.045, "prepay_multiplier": 1.0, "default_multiplier": 1.0},
        "selloff": {"target_rate": 0.075, "prepay_multiplier": 0.5, "default_multiplier": 1.2},
    }
    
    # Economic stress scenarios
    ECONOMIC_SCENARIOS = {
        "expansion": {"unemployment": 0.04, "hpi_change": 0.05, "default_mult": 0.7, "severity_adj": -0.05},
        "stable": {"unemployment": 0.05, "hpi_change": 0.02, "default_mult": 1.0, "severity_adj": 0.0},
        "mild_recession": {"unemployment": 0.07, "hpi_change": -0.05, "default_mult": 1.5, "severity_adj": 0.05},
        "severe_recession": {"unemployment": 0.10, "hpi_change": -0.15, "default_mult": 2.5, "severity_adj": 0.15},
    }
    
    def __init__(self):
        """Initialize the estimator."""
        pass
    
    def estimate(
        self,
        # Pool characteristics
        wa_fico: float = 720.0,
        wa_ltv: float = 75.0,
        wa_dti: float = 36.0,
        wa_coupon: float = 0.05,
        wa_seasoning: int = 12,  # months
        
        # Market conditions
        current_market_rate: float = 0.065,
        rate_scenario: str = "base",
        economic_scenario: str = "stable",
        
        # Property mix (optional)
        pct_high_ltv: float = 0.20,  # % of pool with LTV > 80
        pct_investor: float = 0.05,  # % investment properties
        pct_condo: float = 0.10,     # % condos
        
        # Geographic risk (optional)
        pct_judicial_states: float = 0.30,  # % in judicial foreclosure states
        
    ) -> ModelEstimate:
        """
        Generate model-driven estimates for CPR, CDR, and Severity.
        
        Parameters
        ----------
        wa_fico : float
            Weighted-average FICO score of the pool.
        wa_ltv : float
            Weighted-average loan-to-value ratio.
        wa_dti : float
            Weighted-average debt-to-income ratio.
        wa_coupon : float
            Weighted-average coupon rate (decimal).
        wa_seasoning : int
            Average loan age in months.
        current_market_rate : float
            Current mortgage market rate (decimal).
        rate_scenario : str
            Rate scenario: "rally", "base", "selloff".
        economic_scenario : str
            Economic scenario: "expansion", "stable", "mild_recession", "severe_recession".
        pct_high_ltv : float
            Percentage of pool with LTV > 80%.
        pct_investor : float
            Percentage of investment properties.
        pct_condo : float
            Percentage of condos/co-ops.
        pct_judicial_states : float
            Percentage in judicial foreclosure states.
            
        Returns
        -------
        ModelEstimate
            Container with point estimates, confidence intervals, and component breakdowns.
        """
        # Store inputs
        inputs = {
            "wa_fico": wa_fico,
            "wa_ltv": wa_ltv,
            "wa_dti": wa_dti,
            "wa_coupon": wa_coupon,
            "wa_seasoning": wa_seasoning,
            "current_market_rate": current_market_rate,
            "rate_scenario": rate_scenario,
            "economic_scenario": economic_scenario,
            "pct_high_ltv": pct_high_ltv,
            "pct_investor": pct_investor,
            "pct_condo": pct_condo,
            "pct_judicial_states": pct_judicial_states,
        }
        
        # Calculate CPR
        cpr, cpr_components = self._estimate_cpr(
            wa_fico=wa_fico,
            wa_ltv=wa_ltv,
            wa_dti=wa_dti,
            wa_coupon=wa_coupon,
            wa_seasoning=wa_seasoning,
            current_market_rate=current_market_rate,
            rate_scenario=rate_scenario,
        )
        
        # Calculate CDR
        cdr, cdr_components = self._estimate_cdr(
            wa_fico=wa_fico,
            wa_ltv=wa_ltv,
            wa_coupon=wa_coupon,
            current_market_rate=current_market_rate,
            economic_scenario=economic_scenario,
            pct_high_ltv=pct_high_ltv,
        )
        
        # Calculate Severity
        severity, severity_components = self._estimate_severity(
            wa_fico=wa_fico,
            wa_ltv=wa_ltv,
            wa_dti=wa_dti,
            economic_scenario=economic_scenario,
            pct_condo=pct_condo,
            pct_judicial_states=pct_judicial_states,
        )
        
        # Calculate confidence intervals (±20% for demo, in production would use model uncertainty)
        cpr_range = (max(0.0, cpr * 0.7), min(0.50, cpr * 1.3))
        cdr_range = (max(0.0, cdr * 0.6), min(0.20, cdr * 1.5))
        severity_range = (max(0.10, severity * 0.8), min(0.80, severity * 1.2))
        
        return ModelEstimate(
            cpr=cpr,
            cdr=cdr,
            severity=severity,
            cpr_range=cpr_range,
            cdr_range=cdr_range,
            severity_range=severity_range,
            inputs=inputs,
            cpr_components=cpr_components,
            cdr_components=cdr_components,
            severity_components=severity_components,
        )
    
    def _estimate_cpr(
        self,
        wa_fico: float,
        wa_ltv: float,
        wa_dti: float,
        wa_coupon: float,
        wa_seasoning: int,
        current_market_rate: float,
        rate_scenario: str,
    ) -> Tuple[float, Dict[str, float]]:
        """Estimate CPR using prepayment model."""
        
        components = {}
        
        # Rate incentive: positive means refinance incentive
        rate_incentive = wa_coupon - current_market_rate
        components["rate_incentive"] = rate_incentive * self.PREPAY_WEIGHTS["RATE_INCENTIVE"]
        
        # Burnout proxy: assume cumulative incentive based on seasoning
        burnout = max(0, rate_incentive * wa_seasoning / 12)
        components["burnout"] = burnout * self.PREPAY_WEIGHTS["BURNOUT_PROXY"]
        
        # Credit score effect
        components["fico"] = (wa_fico - 700) * self.PREPAY_WEIGHTS["CREDIT_SCORE"]
        
        # LTV effect
        components["ltv"] = (wa_ltv - 80) * self.PREPAY_WEIGHTS["ORIGINAL_LTV"]
        
        # DTI effect
        components["dti"] = (wa_dti - 36) * self.PREPAY_WEIGHTS["ORIGINAL_DTI"]
        
        # Seasoning ramp (PSA-style)
        seasoning_factor = min(1.0, wa_seasoning / 30)  # Ramp to 100% over 30 months
        components["seasoning"] = seasoning_factor - 1.0  # Adjustment from baseline
        
        # Calculate log hazard and convert to rate
        log_hazard = sum(components.values())
        smm = self.PREPAY_BASELINE * np.exp(log_hazard) * seasoning_factor
        
        # Apply rate scenario multiplier
        scenario = self.RATE_SCENARIOS.get(rate_scenario, self.RATE_SCENARIOS["base"])
        smm *= scenario["prepay_multiplier"]
        components["scenario_multiplier"] = scenario["prepay_multiplier"] - 1.0
        
        # Convert SMM to CPR: CPR = 1 - (1 - SMM)^12
        cpr = 1.0 - (1.0 - smm) ** 12
        cpr = np.clip(cpr, 0.01, 0.50)  # Floor at 1%, cap at 50%
        
        # Store final CPR in components for transparency
        components["baseline"] = self.PREPAY_BASELINE
        components["smm"] = smm
        components["cpr"] = cpr
        
        return cpr, components
    
    def _estimate_cdr(
        self,
        wa_fico: float,
        wa_ltv: float,
        wa_coupon: float,
        current_market_rate: float,
        economic_scenario: str,
        pct_high_ltv: float,
    ) -> Tuple[float, Dict[str, float]]:
        """Estimate CDR using default model."""
        
        components = {}
        
        # SATO: Spread at origination (higher = riskier borrower)
        # Assume origination was at market rate at time, so use coupon as proxy
        sato = max(0, wa_coupon - 0.04)  # Assume 4% was historical average
        components["sato"] = sato * self.DEFAULT_WEIGHTS["SATO"]
        
        # High LTV flag
        components["high_ltv"] = pct_high_ltv * self.DEFAULT_WEIGHTS["HIGH_LTV_FLAG"]
        
        # FICO bucket (1=excellent, 4=poor)
        if wa_fico >= 750:
            fico_bucket = 1
        elif wa_fico >= 700:
            fico_bucket = 2
        elif wa_fico >= 660:
            fico_bucket = 3
        else:
            fico_bucket = 4
        components["fico_bucket"] = (fico_bucket - 2) * self.DEFAULT_WEIGHTS["FICO_BUCKET"]
        
        # Credit score linear effect
        components["fico_linear"] = (wa_fico - 700) * self.DEFAULT_WEIGHTS["CREDIT_SCORE"]
        
        # Calculate log hazard and convert to rate
        log_hazard = sum(components.values())
        mdr = self.DEFAULT_BASELINE * np.exp(log_hazard)  # Monthly default rate
        
        # Apply economic scenario multiplier
        econ = self.ECONOMIC_SCENARIOS.get(economic_scenario, self.ECONOMIC_SCENARIOS["stable"])
        mdr *= econ["default_mult"]
        components["economic_multiplier"] = econ["default_mult"] - 1.0
        
        # Convert MDR to CDR: CDR = 1 - (1 - MDR)^12
        cdr = 1.0 - (1.0 - mdr) ** 12
        cdr = np.clip(cdr, 0.001, 0.20)  # Floor at 0.1%, cap at 20%
        
        # Store final values
        components["baseline"] = self.DEFAULT_BASELINE
        components["mdr"] = mdr
        components["cdr"] = cdr
        
        return cdr, components
    
    def _estimate_severity(
        self,
        wa_fico: float,
        wa_ltv: float,
        wa_dti: float,
        economic_scenario: str,
        pct_condo: float,
        pct_judicial_states: float,
    ) -> Tuple[float, Dict[str, float]]:
        """Estimate loss severity using severity model."""
        
        components = {}
        
        # Base severity
        components["base"] = self.SEVERITY_BASE
        
        # LTV adjustment
        if wa_ltv > 80:
            ltv_adj = (wa_ltv - 80) * self.SEVERITY_LTV_COEF
        else:
            ltv_adj = 0.0
        components["ltv_adj"] = ltv_adj
        
        # FICO adjustment
        fico_adj = (wa_fico - 700) * self.SEVERITY_FICO_COEF
        components["fico_adj"] = fico_adj
        
        # DTI adjustment
        if wa_dti > 36:
            dti_adj = (wa_dti - 36) * self.SEVERITY_DTI_COEF
        else:
            dti_adj = 0.0
        components["dti_adj"] = dti_adj
        
        # Property type adjustment
        condo_adj = pct_condo * 0.05  # Condos have +5% severity
        components["property_adj"] = condo_adj
        
        # Judicial state adjustment
        judicial_adj = pct_judicial_states * 0.05  # Judicial states +5% severity
        components["judicial_adj"] = judicial_adj
        
        # Economic scenario adjustment (HPI effect)
        econ = self.ECONOMIC_SCENARIOS.get(economic_scenario, self.ECONOMIC_SCENARIOS["stable"])
        components["economic_adj"] = econ["severity_adj"]
        
        # Sum up
        severity = sum(components.values())
        severity = np.clip(severity, 0.10, 0.80)
        
        components["severity"] = severity
        
        return severity, components
    
    def run_sensitivity_analysis(
        self,
        base_params: Dict[str, Any],
        vary_param: str,
        vary_values: List[float],
    ) -> List[Dict[str, Any]]:
        """
        Run sensitivity analysis by varying one parameter.
        
        Parameters
        ----------
        base_params : dict
            Base parameters for estimate().
        vary_param : str
            Parameter name to vary.
        vary_values : list
            Values to test for the varying parameter.
            
        Returns
        -------
        list of dict
            Estimate results for each value.
        """
        results = []
        for val in vary_values:
            params = base_params.copy()
            params[vary_param] = val
            estimate = self.estimate(**params)
            results.append({
                vary_param: val,
                "cpr": estimate.cpr,
                "cdr": estimate.cdr,
                "severity": estimate.severity,
            })
        return results


# Convenience function
def get_model_estimates(
    wa_fico: float = 720.0,
    wa_ltv: float = 75.0,
    wa_dti: float = 36.0,
    wa_coupon: float = 0.05,
    current_market_rate: float = 0.065,
    rate_scenario: str = "base",
    economic_scenario: str = "stable",
    **kwargs,
) -> Dict[str, Any]:
    """
    Convenience function to get model-driven estimates.
    
    Returns a dictionary with CPR, CDR, Severity and their components.
    """
    estimator = ModelDrivenEstimator()
    result = estimator.estimate(
        wa_fico=wa_fico,
        wa_ltv=wa_ltv,
        wa_dti=wa_dti,
        wa_coupon=wa_coupon,
        current_market_rate=current_market_rate,
        rate_scenario=rate_scenario,
        economic_scenario=economic_scenario,
        **kwargs,
    )
    return result.to_dict()
