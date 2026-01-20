"""
Stress Testing Framework for RMBS Engine.
==========================================

This module provides a comprehensive stress testing framework for
RMBS deals, enabling analysis under adverse economic scenarios:

- Predefined regulatory stress scenarios (CCAR, DFAST, EBA)
- Custom scenario definition and execution
- Multi-factor stress (rates, HPI, unemployment)
- Sensitivity analysis (single-factor shocks)
- Reverse stress testing (finding break-even points)
- Monte Carlo stress simulations
- Loss distribution analysis

Industry Context
----------------
Stress testing is mandated by regulators and critical for risk management:

1. **CCAR/DFAST** (US): Federal Reserve stress scenarios for banks
2. **EBA Stress Tests** (EU): European Banking Authority scenarios
3. **Basel III/IV**: Capital adequacy stress testing
4. **IOSCO**: Securities regulation stress requirements
5. **Internal Risk Management**: Enterprise risk frameworks

Standard stress factors for RMBS:
- Interest rate paths (parallel shifts, twists, inversions)
- House price depreciation (HPI shocks)
- Unemployment rate increases
- Prepayment speed changes (CPR shocks)
- Default rate increases (CDR multipliers)
- Loss severity increases
- Correlation stresses

References
----------
- Federal Reserve CCAR/DFAST Instructions
- EBA Stress Test Methodology
- Basel Committee: Stress Testing Principles
- Moody's Analytics Scenario Forecasting

Examples
--------
>>> from rmbs_platform.engine.stress_testing import (
...     StressTestingEngine, StressScenario, ScenarioType
... )
>>> 
>>> # Initialize engine
>>> engine = StressTestingEngine()
>>> 
>>> # Run predefined stress scenario
>>> result = engine.run_scenario(
...     deal_state=current_state,
...     scenario=StressScenario.SEVERE_DOWNTURN
... )
>>> 
>>> # Custom stress test
>>> custom = engine.create_scenario(
...     name='Custom Stress',
...     hpi_shock=-0.25,
...     unemployment_increase=0.05,
...     rate_shock=0.02
... )
>>> result = engine.run_scenario(current_state, custom)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import copy


# =============================================================================
# Enums and Constants
# =============================================================================

class ScenarioType(str, Enum):
    """
    Types of stress scenarios.
    """
    
    BASELINE = "Baseline"
    ADVERSE = "Adverse"
    SEVERELY_ADVERSE = "Severely Adverse"
    CUSTOM = "Custom"
    SENSITIVITY = "Sensitivity"
    REVERSE = "Reverse Stress"
    MONTE_CARLO = "Monte Carlo"


class StressFactor(str, Enum):
    """
    Individual stress factors that can be applied.
    """
    
    INTEREST_RATE = "Interest Rate"
    HPI = "House Price Index"
    UNEMPLOYMENT = "Unemployment"
    GDP = "GDP Growth"
    CPR = "Prepayment Rate"
    CDR = "Default Rate"
    SEVERITY = "Loss Severity"
    SPREAD = "Credit Spread"
    VOLATILITY = "Volatility"


class RateShockType(str, Enum):
    """
    Types of interest rate shocks.
    """
    
    PARALLEL_UP = "Parallel Up"
    PARALLEL_DOWN = "Parallel Down"
    STEEPENER = "Steepener"
    FLATTENER = "Flattener"
    SHORT_UP = "Short End Up"
    LONG_UP = "Long End Up"
    INVERSION = "Curve Inversion"


# =============================================================================
# Regulatory Scenario Definitions
# =============================================================================

# Federal Reserve DFAST/CCAR-style scenarios (simplified)
REGULATORY_SCENARIOS = {
    "CCAR_BASELINE_2024": {
        "name": "CCAR Baseline 2024",
        "type": ScenarioType.BASELINE,
        "horizon_quarters": 9,
        "factors": {
            "unemployment_rate": [4.0, 4.0, 4.1, 4.1, 4.2, 4.2, 4.1, 4.1, 4.0],
            "gdp_growth": [2.5, 2.4, 2.3, 2.2, 2.1, 2.0, 2.0, 2.1, 2.2],
            "hpi_change": [0.04, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02],
            "fed_funds_rate": [5.25, 5.00, 4.75, 4.50, 4.25, 4.00, 3.75, 3.50, 3.50],
            "10yr_treasury": [4.50, 4.40, 4.30, 4.20, 4.10, 4.00, 3.90, 3.80, 3.80],
        },
    },
    "CCAR_ADVERSE_2024": {
        "name": "CCAR Adverse 2024",
        "type": ScenarioType.ADVERSE,
        "horizon_quarters": 9,
        "factors": {
            "unemployment_rate": [4.5, 5.5, 6.5, 7.5, 8.0, 8.0, 7.5, 7.0, 6.5],
            "gdp_growth": [0.5, -1.0, -2.5, -2.0, -0.5, 0.5, 1.0, 1.5, 2.0],
            "hpi_change": [0.0, -0.05, -0.10, -0.10, -0.08, -0.05, -0.02, 0.0, 0.02],
            "fed_funds_rate": [5.00, 4.50, 3.50, 2.50, 1.50, 1.00, 1.00, 1.25, 1.50],
            "10yr_treasury": [4.00, 3.50, 3.00, 2.50, 2.25, 2.25, 2.50, 2.75, 3.00],
        },
    },
    "CCAR_SEVERELY_ADVERSE_2024": {
        "name": "CCAR Severely Adverse 2024",
        "type": ScenarioType.SEVERELY_ADVERSE,
        "horizon_quarters": 9,
        "factors": {
            "unemployment_rate": [5.0, 7.0, 9.0, 10.5, 11.0, 10.5, 10.0, 9.5, 9.0],
            "gdp_growth": [-1.0, -4.0, -6.0, -4.0, -2.0, 0.0, 1.0, 1.5, 2.0],
            "hpi_change": [-0.05, -0.15, -0.20, -0.15, -0.10, -0.05, 0.0, 0.02, 0.03],
            "fed_funds_rate": [4.50, 3.00, 1.50, 0.50, 0.25, 0.25, 0.25, 0.50, 0.75],
            "10yr_treasury": [3.50, 2.50, 1.75, 1.25, 1.00, 1.25, 1.50, 1.75, 2.00],
        },
    },
    "EBA_ADVERSE_2024": {
        "name": "EBA Adverse 2024",
        "type": ScenarioType.ADVERSE,
        "horizon_quarters": 12,
        "factors": {
            "unemployment_rate": [7.0, 8.0, 9.0, 9.5, 9.5, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0, 6.8],
            "gdp_growth": [-0.5, -1.5, -2.0, -1.5, -0.5, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0],
            "hpi_change": [-0.02, -0.08, -0.12, -0.10, -0.08, -0.05, -0.03, 0.0, 0.01, 0.02, 0.02, 0.02],
            "euribor_3m": [3.50, 3.00, 2.50, 2.00, 1.50, 1.25, 1.25, 1.50, 1.75, 2.00, 2.00, 2.00],
        },
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class StressScenario:
    """
    Complete stress scenario definition.
    
    Parameters
    ----------
    scenario_id : str
        Unique scenario identifier
    name : str
        Descriptive name
    scenario_type : ScenarioType
        Classification of scenario
    horizon_months : int
        Stress horizon in months
    description : str
        Detailed description
    
    Stress Factors (all optional)
    -----------------------------
    rate_shock : float
        Parallel interest rate shock (e.g., +0.02 = +200bps)
    rate_shock_type : RateShockType
        Type of rate curve movement
    hpi_shock : float
        House price index shock (e.g., -0.20 = -20%)
    unemployment_shock : float
        Unemployment rate change (e.g., +0.05 = +5 ppts)
    cpr_multiplier : float
        Prepayment rate multiplier (e.g., 0.5 = 50% of base)
    cdr_multiplier : float
        Default rate multiplier (e.g., 2.0 = 2x base)
    severity_add : float
        Additional loss severity (e.g., +0.10 = +10 ppts)
    spread_shock : float
        Credit spread shock
    
    Examples
    --------
    >>> scenario = StressScenario(
    ...     scenario_id='custom_stress_1',
    ...     name='Custom Recession',
    ...     scenario_type=ScenarioType.CUSTOM,
    ...     horizon_months=24,
    ...     hpi_shock=-0.25,
    ...     unemployment_shock=0.05,
    ...     cdr_multiplier=2.5,
    ... )
    """
    
    scenario_id: str
    name: str
    scenario_type: ScenarioType = ScenarioType.CUSTOM
    horizon_months: int = 24
    description: str = ""
    
    # Interest rate factors
    rate_shock: float = 0.0
    rate_shock_type: RateShockType = RateShockType.PARALLEL_UP
    rate_path: Optional[List[float]] = None  # Custom rate path
    
    # Economic factors
    hpi_shock: float = 0.0
    hpi_path: Optional[List[float]] = None  # Period-by-period HPI changes
    unemployment_shock: float = 0.0
    unemployment_path: Optional[List[float]] = None
    gdp_shock: float = 0.0
    gdp_path: Optional[List[float]] = None
    
    # Performance factors
    cpr_multiplier: float = 1.0
    cpr_path: Optional[List[float]] = None
    cdr_multiplier: float = 1.0
    cdr_path: Optional[List[float]] = None
    severity_add: float = 0.0
    severity_path: Optional[List[float]] = None
    
    # Market factors
    spread_shock: float = 0.0
    volatility_multiplier: float = 1.0
    
    # Time-varying factors (for CCAR-style scenarios)
    quarterly_factors: Optional[Dict[str, List[float]]] = None
    
    def get_factor_at_period(
        self,
        factor: StressFactor,
        period: int,
    ) -> float:
        """
        Get stress factor value at a specific period.
        
        Parameters
        ----------
        factor : StressFactor
            Factor to retrieve
        period : int
            Period index (0-based)
            
        Returns
        -------
        float
            Factor value
        """
        # Check quarterly factors first
        if self.quarterly_factors:
            quarter = period // 3
            factor_key = factor.value.lower().replace(" ", "_")
            if factor_key in self.quarterly_factors:
                path = self.quarterly_factors[factor_key]
                if quarter < len(path):
                    return path[quarter]
        
        # Check period-specific paths
        paths = {
            StressFactor.INTEREST_RATE: self.rate_path,
            StressFactor.HPI: self.hpi_path,
            StressFactor.UNEMPLOYMENT: self.unemployment_path,
            StressFactor.CPR: self.cpr_path,
            StressFactor.CDR: self.cdr_path,
            StressFactor.SEVERITY: self.severity_path,
            StressFactor.GDP: self.gdp_path,
        }
        
        path = paths.get(factor)
        if path and period < len(path):
            return path[period]
        
        # Return static shocks
        static = {
            StressFactor.INTEREST_RATE: self.rate_shock,
            StressFactor.HPI: self.hpi_shock,
            StressFactor.UNEMPLOYMENT: self.unemployment_shock,
            StressFactor.CPR: self.cpr_multiplier,
            StressFactor.CDR: self.cdr_multiplier,
            StressFactor.SEVERITY: self.severity_add,
            StressFactor.GDP: self.gdp_shock,
            StressFactor.SPREAD: self.spread_shock,
        }
        
        return static.get(factor, 0.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, np.ndarray):
                result[key] = value.tolist()
            else:
                result[key] = value
        return result


@dataclass
class StressResult:
    """
    Results from a stress test execution.
    
    Parameters
    ----------
    scenario : StressScenario
        The scenario that was run
    execution_date : date
        When the test was run
    base_case_metrics : Dict[str, float]
        Metrics under base case
    stressed_metrics : Dict[str, float]
        Metrics under stress
    period_results : pd.DataFrame
        Period-by-period results
    """
    
    scenario: StressScenario
    execution_date: date
    base_case_metrics: Dict[str, float]
    stressed_metrics: Dict[str, float]
    period_results: pd.DataFrame
    
    # Impact analysis
    total_loss_base: float = 0.0
    total_loss_stressed: float = 0.0
    incremental_loss: float = 0.0
    loss_multiple: float = 1.0
    
    # Tranche-level impacts
    tranche_impacts: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Rating implications
    rating_impact: Optional[Dict[str, Any]] = None
    
    # Execution metadata
    execution_time_seconds: float = 0.0
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.total_loss_base > 0:
            self.loss_multiple = self.total_loss_stressed / self.total_loss_base
        self.incremental_loss = self.total_loss_stressed - self.total_loss_base
    
    @property
    def summary(self) -> Dict[str, Any]:
        """Get summary of stress results."""
        return {
            "scenario_name": self.scenario.name,
            "scenario_type": self.scenario.scenario_type.value,
            "execution_date": self.execution_date.isoformat(),
            "base_total_loss": self.total_loss_base,
            "stressed_total_loss": self.total_loss_stressed,
            "incremental_loss": self.incremental_loss,
            "loss_multiple": self.loss_multiple,
            "key_metrics_base": self.base_case_metrics,
            "key_metrics_stressed": self.stressed_metrics,
        }


@dataclass
class SensitivityResult:
    """
    Results from sensitivity analysis.
    
    Parameters
    ----------
    factor : StressFactor
        Factor being tested
    shock_values : List[float]
        Shock magnitudes tested
    metric_values : Dict[str, List[float]]
        Metric values at each shock level
    """
    
    factor: StressFactor
    shock_values: List[float]
    metric_values: Dict[str, List[float]]
    base_value: float = 0.0
    
    def get_sensitivity(self, metric: str) -> float:
        """
        Calculate sensitivity (delta metric / delta shock).
        
        Parameters
        ----------
        metric : str
            Metric name
            
        Returns
        -------
        float
            Sensitivity coefficient
        """
        if metric not in self.metric_values:
            return 0.0
        
        values = self.metric_values[metric]
        shocks = self.shock_values
        
        if len(values) < 2 or len(shocks) < 2:
            return 0.0
        
        # Linear regression slope
        x = np.array(shocks)
        y = np.array(values)
        
        slope = np.polyfit(x, y, 1)[0]
        return slope
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert to DataFrame."""
        data = {"shock": self.shock_values}
        data.update(self.metric_values)
        return pd.DataFrame(data)


@dataclass
class ReverseStressResult:
    """
    Results from reverse stress testing.
    
    Parameters
    ----------
    target_metric : str
        The metric being targeted
    target_value : float
        The threshold value
    required_shocks : Dict[StressFactor, float]
        Shocks required to reach target
    """
    
    target_metric: str
    target_value: float
    achieved_value: float
    required_shocks: Dict[StressFactor, float]
    iterations: int = 0
    converged: bool = False
    
    @property
    def cushion(self) -> float:
        """Distance from current state to target."""
        return abs(self.achieved_value - self.target_value)


# =============================================================================
# Stress Testing Engine
# =============================================================================

class StressTestingEngine:
    """
    Comprehensive stress testing engine for RMBS deals.
    
    Executes stress scenarios against deal portfolios, calculating
    impacts on cashflows, credit enhancement, and tranche performance.
    
    Parameters
    ----------
    base_cpr : float
        Base prepayment rate assumption
    base_cdr : float
        Base default rate assumption
    base_severity : float
        Base loss severity assumption
    simulation_engine : Optional[Callable]
        Custom simulation function
    
    Attributes
    ----------
    scenarios : Dict[str, StressScenario]
        Registered scenarios
    results_history : List[StressResult]
        Historical stress results
    
    Examples
    --------
    >>> engine = StressTestingEngine(base_cpr=0.06, base_cdr=0.02, base_severity=0.35)
    >>> 
    >>> # Load regulatory scenarios
    >>> engine.load_regulatory_scenarios()
    >>> 
    >>> # Run stress test
    >>> result = engine.run_stress_test(
    ...     loan_data=loans_df,
    ...     deal_structure=deal_spec,
    ...     scenario_id='CCAR_SEVERELY_ADVERSE_2024'
    ... )
    >>> 
    >>> # Sensitivity analysis
    >>> sensitivity = engine.run_sensitivity_analysis(
    ...     loan_data=loans_df,
    ...     factor=StressFactor.HPI,
    ...     shock_range=(-0.30, 0.10, 0.05)
    ... )
    """
    
    def __init__(
        self,
        base_cpr: float = 0.06,
        base_cdr: float = 0.02,
        base_severity: float = 0.35,
        simulation_engine: Optional[Callable] = None,
        parallel_workers: int = 4,
    ) -> None:
        self.base_cpr = base_cpr
        self.base_cdr = base_cdr
        self.base_severity = base_severity
        self.simulation_engine = simulation_engine
        self.parallel_workers = parallel_workers
        
        # Scenario storage
        self.scenarios: Dict[str, StressScenario] = {}
        self.results_history: List[StressResult] = []
        
        # Load built-in scenarios
        self._load_builtin_scenarios()
    
    def _load_builtin_scenarios(self) -> None:
        """Load built-in regulatory scenarios."""
        for scenario_id, spec in REGULATORY_SCENARIOS.items():
            scenario = StressScenario(
                scenario_id=scenario_id,
                name=spec["name"],
                scenario_type=spec["type"],
                horizon_months=spec["horizon_quarters"] * 3,
                quarterly_factors=spec["factors"],
            )
            self.scenarios[scenario_id] = scenario
    
    def load_regulatory_scenarios(self, year: int = 2024) -> None:
        """
        Load regulatory stress scenarios for a given year.
        
        Parameters
        ----------
        year : int
            Scenario year (affects parameter calibration)
        """
        # Already loaded in __init__, but could be extended
        # to fetch updated scenarios from a data source
        pass
    
    def create_scenario(
        self,
        scenario_id: str,
        name: str,
        **kwargs,
    ) -> StressScenario:
        """
        Create a custom stress scenario.
        
        Parameters
        ----------
        scenario_id : str
            Unique identifier
        name : str
            Scenario name
        **kwargs
            Stress factors (hpi_shock, cdr_multiplier, etc.)
            
        Returns
        -------
        StressScenario
            Created scenario
        """
        scenario = StressScenario(
            scenario_id=scenario_id,
            name=name,
            scenario_type=ScenarioType.CUSTOM,
            **kwargs,
        )
        self.scenarios[scenario_id] = scenario
        return scenario
    
    def get_scenario(self, scenario_id: str) -> StressScenario:
        """Get a registered scenario by ID."""
        if scenario_id not in self.scenarios:
            raise ValueError(f"Scenario not found: {scenario_id}")
        return self.scenarios[scenario_id]
    
    def run_stress_test(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        scenario_id: str,
        as_of_date: Optional[date] = None,
    ) -> StressResult:
        """
        Run a stress test for a specific scenario.
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan-level data
        deal_structure : Dict[str, Any]
            Deal specification
        scenario_id : str
            Scenario identifier
        as_of_date : Optional[date]
            Valuation date
            
        Returns
        -------
        StressResult
            Stress test results
        """
        import time
        start_time = time.time()
        
        scenario = self.get_scenario(scenario_id)
        as_of = as_of_date or date.today()
        
        # Run base case
        base_results = self._run_projection(
            loan_data,
            deal_structure,
            scenario=None,  # No stress
            horizon_months=scenario.horizon_months,
        )
        
        # Run stressed case
        stressed_results = self._run_projection(
            loan_data,
            deal_structure,
            scenario=scenario,
            horizon_months=scenario.horizon_months,
        )
        
        # Calculate impacts
        base_metrics = self._calculate_metrics(base_results)
        stressed_metrics = self._calculate_metrics(stressed_results)
        
        # Build period-by-period comparison
        period_results = self._build_period_comparison(base_results, stressed_results)
        
        # Tranche-level impacts
        tranche_impacts = self._calculate_tranche_impacts(
            deal_structure,
            base_results,
            stressed_results,
        )
        
        result = StressResult(
            scenario=scenario,
            execution_date=as_of,
            base_case_metrics=base_metrics,
            stressed_metrics=stressed_metrics,
            period_results=period_results,
            total_loss_base=base_metrics.get("total_losses", 0),
            total_loss_stressed=stressed_metrics.get("total_losses", 0),
            tranche_impacts=tranche_impacts,
            execution_time_seconds=time.time() - start_time,
        )
        
        self.results_history.append(result)
        return result
    
    def run_all_regulatory_scenarios(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        as_of_date: Optional[date] = None,
    ) -> Dict[str, StressResult]:
        """
        Run all registered regulatory scenarios.
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan-level data
        deal_structure : Dict[str, Any]
            Deal specification
        as_of_date : Optional[date]
            Valuation date
            
        Returns
        -------
        Dict[str, StressResult]
            Results by scenario ID
        """
        results = {}
        
        for scenario_id in self.scenarios:
            try:
                result = self.run_stress_test(
                    loan_data,
                    deal_structure,
                    scenario_id,
                    as_of_date,
                )
                results[scenario_id] = result
            except Exception as e:
                results[scenario_id] = StressResult(
                    scenario=self.scenarios[scenario_id],
                    execution_date=as_of_date or date.today(),
                    base_case_metrics={},
                    stressed_metrics={},
                    period_results=pd.DataFrame(),
                    warnings=[str(e)],
                )
        
        return results
    
    def run_sensitivity_analysis(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        factor: StressFactor,
        shock_range: Tuple[float, float, float],
        metrics: Optional[List[str]] = None,
    ) -> SensitivityResult:
        """
        Run single-factor sensitivity analysis.
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan-level data
        deal_structure : Dict[str, Any]
            Deal specification
        factor : StressFactor
            Factor to stress
        shock_range : Tuple[float, float, float]
            (min, max, step) for shock values
        metrics : Optional[List[str]]
            Metrics to track
            
        Returns
        -------
        SensitivityResult
            Sensitivity analysis results
        """
        metrics = metrics or ["total_losses", "npv", "waf"]
        
        # Generate shock values
        min_shock, max_shock, step = shock_range
        shock_values = list(np.arange(min_shock, max_shock + step, step))
        
        # Run projection for each shock
        metric_values: Dict[str, List[float]] = {m: [] for m in metrics}
        
        for shock in shock_values:
            # Create scenario for this shock
            scenario_kwargs = self._factor_to_scenario_kwargs(factor, shock)
            scenario = StressScenario(
                scenario_id=f"sensitivity_{factor.value}_{shock}",
                name=f"Sensitivity {factor.value} {shock:+.2%}",
                **scenario_kwargs,
            )
            
            # Run projection
            results = self._run_projection(
                loan_data,
                deal_structure,
                scenario=scenario,
                horizon_months=24,
            )
            
            # Calculate metrics
            calc_metrics = self._calculate_metrics(results)
            
            for m in metrics:
                metric_values[m].append(calc_metrics.get(m, 0))
        
        return SensitivityResult(
            factor=factor,
            shock_values=shock_values,
            metric_values=metric_values,
            base_value=metric_values[metrics[0]][len(shock_values) // 2] if shock_values else 0,
        )
    
    def run_multi_factor_sensitivity(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        factor_ranges: Dict[StressFactor, Tuple[float, float, float]],
        target_metric: str = "total_losses",
    ) -> pd.DataFrame:
        """
        Run multi-factor sensitivity analysis (stress surface).
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan data
        deal_structure : Dict[str, Any]
            Deal specification
        factor_ranges : Dict[StressFactor, Tuple]
            Range specs for each factor
        target_metric : str
            Metric to track
            
        Returns
        -------
        pd.DataFrame
            Multi-dimensional sensitivity surface
        """
        # For simplicity, support 2 factors
        factors = list(factor_ranges.keys())
        if len(factors) != 2:
            raise ValueError("Multi-factor sensitivity requires exactly 2 factors")
        
        factor1, factor2 = factors
        range1 = factor_ranges[factor1]
        range2 = factor_ranges[factor2]
        
        values1 = list(np.arange(range1[0], range1[1] + range1[2], range1[2]))
        values2 = list(np.arange(range2[0], range2[1] + range2[2], range2[2]))
        
        results = []
        
        for v1 in values1:
            for v2 in values2:
                kwargs1 = self._factor_to_scenario_kwargs(factor1, v1)
                kwargs2 = self._factor_to_scenario_kwargs(factor2, v2)
                kwargs1.update(kwargs2)
                
                scenario = StressScenario(
                    scenario_id=f"multi_{factor1.value}_{v1}_{factor2.value}_{v2}",
                    name="Multi-factor",
                    **kwargs1,
                )
                
                proj_results = self._run_projection(
                    loan_data,
                    deal_structure,
                    scenario=scenario,
                    horizon_months=24,
                )
                
                metrics = self._calculate_metrics(proj_results)
                
                results.append({
                    factor1.value: v1,
                    factor2.value: v2,
                    target_metric: metrics.get(target_metric, 0),
                })
        
        return pd.DataFrame(results)
    
    def run_reverse_stress_test(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        target_metric: str,
        target_value: float,
        factors: List[StressFactor],
        max_iterations: int = 50,
        tolerance: float = 0.01,
    ) -> ReverseStressResult:
        """
        Run reverse stress test to find break-even scenario.
        
        Find the combination of stresses that causes a specific
        metric to reach a target threshold (e.g., what stress causes
        the mezzanine tranche to take principal losses).
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan data
        deal_structure : Dict[str, Any]
            Deal specification
        target_metric : str
            Metric to target
        target_value : float
            Threshold value
        factors : List[StressFactor]
            Factors to stress
        max_iterations : int
            Maximum solver iterations
        tolerance : float
            Convergence tolerance
            
        Returns
        -------
        ReverseStressResult
            Reverse stress results
        """
        # Initialize shock values
        current_shocks = {f: 0.0 for f in factors}
        
        for iteration in range(max_iterations):
            # Build scenario from current shocks
            kwargs = {}
            for factor, shock in current_shocks.items():
                kwargs.update(self._factor_to_scenario_kwargs(factor, shock))
            
            scenario = StressScenario(
                scenario_id=f"reverse_{iteration}",
                name="Reverse Stress",
                **kwargs,
            )
            
            # Run projection
            results = self._run_projection(
                loan_data,
                deal_structure,
                scenario=scenario,
                horizon_months=24,
            )
            
            metrics = self._calculate_metrics(results)
            current_value = metrics.get(target_metric, 0)
            
            # Check convergence
            if abs(current_value - target_value) < tolerance * abs(target_value):
                return ReverseStressResult(
                    target_metric=target_metric,
                    target_value=target_value,
                    achieved_value=current_value,
                    required_shocks={f: s for f, s in current_shocks.items()},
                    iterations=iteration + 1,
                    converged=True,
                )
            
            # Adjust shocks (simple gradient descent)
            error = target_value - current_value
            for factor in factors:
                # Estimate gradient
                adjustment = error * 0.01  # Learning rate
                current_shocks[factor] += adjustment
                
                # Clamp to reasonable bounds
                if factor == StressFactor.HPI:
                    current_shocks[factor] = max(-0.50, min(0.20, current_shocks[factor]))
                elif factor == StressFactor.CDR:
                    current_shocks[factor] = max(0.5, min(5.0, current_shocks[factor]))
        
        # Did not converge
        return ReverseStressResult(
            target_metric=target_metric,
            target_value=target_value,
            achieved_value=current_value,
            required_shocks={f: s for f, s in current_shocks.items()},
            iterations=max_iterations,
            converged=False,
        )
    
    def run_monte_carlo_stress(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        num_simulations: int = 1000,
        correlation_matrix: Optional[np.ndarray] = None,
        factor_vols: Optional[Dict[StressFactor, float]] = None,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo stress simulation.
        
        Parameters
        ----------
        loan_data : pd.DataFrame
            Loan data
        deal_structure : Dict[str, Any]
            Deal specification
        num_simulations : int
            Number of simulations
        correlation_matrix : Optional[np.ndarray]
            Factor correlation matrix
        factor_vols : Optional[Dict]
            Factor volatilities
            
        Returns
        -------
        Dict[str, Any]
            Monte Carlo results with loss distribution
        """
        # Default factor volatilities (annualized)
        vols = factor_vols or {
            StressFactor.HPI: 0.10,
            StressFactor.CDR: 0.30,
            StressFactor.CPR: 0.20,
            StressFactor.INTEREST_RATE: 0.15,
        }
        
        factors = list(vols.keys())
        n_factors = len(factors)
        
        # Default correlation (moderate positive correlation)
        if correlation_matrix is None:
            correlation_matrix = np.eye(n_factors) * 0.5 + np.ones((n_factors, n_factors)) * 0.5
            np.fill_diagonal(correlation_matrix, 1.0)
        
        # Generate correlated random shocks
        chol = np.linalg.cholesky(correlation_matrix)
        random_shocks = np.random.normal(0, 1, (num_simulations, n_factors))
        correlated_shocks = random_shocks @ chol.T
        
        # Scale by volatilities
        for i, factor in enumerate(factors):
            correlated_shocks[:, i] *= vols[factor]
        
        # Run simulations
        loss_results = []
        
        for sim in range(min(num_simulations, 100)):  # Limit for performance
            # Create scenario from this simulation's shocks
            kwargs = {}
            for i, factor in enumerate(factors):
                kwargs.update(self._factor_to_scenario_kwargs(factor, correlated_shocks[sim, i]))
            
            scenario = StressScenario(
                scenario_id=f"mc_{sim}",
                name=f"MC Simulation {sim}",
                **kwargs,
            )
            
            results = self._run_projection(
                loan_data,
                deal_structure,
                scenario=scenario,
                horizon_months=24,
            )
            
            metrics = self._calculate_metrics(results)
            loss_results.append(metrics.get("total_losses", 0))
        
        loss_array = np.array(loss_results)
        
        return {
            "num_simulations": len(loss_results),
            "mean_loss": np.mean(loss_array),
            "std_loss": np.std(loss_array),
            "var_95": np.percentile(loss_array, 95),
            "var_99": np.percentile(loss_array, 99),
            "expected_shortfall_95": np.mean(loss_array[loss_array >= np.percentile(loss_array, 95)]),
            "min_loss": np.min(loss_array),
            "max_loss": np.max(loss_array),
            "loss_distribution": loss_array.tolist(),
        }
    
    def _factor_to_scenario_kwargs(
        self,
        factor: StressFactor,
        shock: float,
    ) -> Dict[str, Any]:
        """Convert factor and shock to scenario parameters."""
        mapping = {
            StressFactor.INTEREST_RATE: {"rate_shock": shock},
            StressFactor.HPI: {"hpi_shock": shock},
            StressFactor.UNEMPLOYMENT: {"unemployment_shock": shock},
            StressFactor.CPR: {"cpr_multiplier": max(0, 1 + shock)},
            StressFactor.CDR: {"cdr_multiplier": max(0, 1 + shock)},
            StressFactor.SEVERITY: {"severity_add": shock},
            StressFactor.GDP: {"gdp_shock": shock},
            StressFactor.SPREAD: {"spread_shock": shock},
        }
        return mapping.get(factor, {})
    
    def _run_projection(
        self,
        loan_data: pd.DataFrame,
        deal_structure: Dict[str, Any],
        scenario: Optional[StressScenario],
        horizon_months: int,
    ) -> pd.DataFrame:
        """
        Run cashflow projection with optional stress scenario.
        
        This is a simplified projection for stress testing purposes.
        In production, this would call the full simulation engine.
        """
        # Extract key loan metrics
        if 'Current_Balance' in loan_data.columns:
            total_balance = loan_data['Current_Balance'].sum()
        elif 'current_balance' in loan_data.columns:
            total_balance = loan_data['current_balance'].sum()
        else:
            total_balance = 100_000_000  # Default
        
        # Base rates
        cpr = self.base_cpr
        cdr = self.base_cdr
        severity = self.base_severity
        
        # Apply stress factors
        if scenario:
            cpr *= scenario.cpr_multiplier
            cdr *= scenario.cdr_multiplier
            severity = min(1.0, severity + scenario.severity_add)
            
            # HPI affects severity
            if scenario.hpi_shock < 0:
                severity = min(1.0, severity + abs(scenario.hpi_shock) * 0.3)
        
        # Generate monthly projections
        periods = []
        balance = total_balance
        
        for month in range(horizon_months):
            # Get period-specific factors if available
            if scenario:
                period_cdr = cdr * scenario.get_factor_at_period(StressFactor.CDR, month)
                period_severity = severity + scenario.get_factor_at_period(StressFactor.SEVERITY, month)
            else:
                period_cdr = cdr
                period_severity = severity
            
            # Monthly rates
            monthly_cpr = 1 - (1 - cpr) ** (1/12)
            monthly_cdr = 1 - (1 - period_cdr) ** (1/12)
            
            # Cashflows
            scheduled_principal = balance * 0.005  # Simplified amortization
            prepayment = (balance - scheduled_principal) * monthly_cpr
            default = (balance - scheduled_principal - prepayment) * monthly_cdr
            loss = default * min(1.0, period_severity)
            recovery = default - loss
            
            ending_balance = balance - scheduled_principal - prepayment - default
            
            periods.append({
                "period": month + 1,
                "beginning_balance": balance,
                "scheduled_principal": scheduled_principal,
                "prepayment": prepayment,
                "default": default,
                "loss": loss,
                "recovery": recovery,
                "ending_balance": max(0, ending_balance),
                "cpr_applied": cpr,
                "cdr_applied": period_cdr,
                "severity_applied": period_severity,
            })
            
            balance = max(0, ending_balance)
        
        return pd.DataFrame(periods)
    
    def _calculate_metrics(self, results: pd.DataFrame) -> Dict[str, float]:
        """Calculate summary metrics from projection results."""
        return {
            "total_losses": results['loss'].sum() if 'loss' in results else 0,
            "total_defaults": results['default'].sum() if 'default' in results else 0,
            "total_prepayments": results['prepayment'].sum() if 'prepayment' in results else 0,
            "cumulative_cdr": results['cdr_applied'].mean() * 12 if 'cdr_applied' in results else 0,
            "cumulative_cpr": results['cpr_applied'].mean() * 12 if 'cpr_applied' in results else 0,
            "avg_severity": results['severity_applied'].mean() if 'severity_applied' in results else 0,
            "ending_balance": results['ending_balance'].iloc[-1] if len(results) > 0 else 0,
            "pool_factor": results['ending_balance'].iloc[-1] / results['beginning_balance'].iloc[0] if len(results) > 0 else 1,
        }
    
    def _build_period_comparison(
        self,
        base_results: pd.DataFrame,
        stressed_results: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build period-by-period comparison of base vs stressed."""
        comparison = pd.DataFrame({
            "period": base_results['period'],
            "base_balance": base_results['ending_balance'],
            "stressed_balance": stressed_results['ending_balance'],
            "base_loss": base_results['loss'],
            "stressed_loss": stressed_results['loss'],
            "incremental_loss": stressed_results['loss'] - base_results['loss'],
        })
        
        comparison['cumulative_base_loss'] = comparison['base_loss'].cumsum()
        comparison['cumulative_stressed_loss'] = comparison['stressed_loss'].cumsum()
        comparison['cumulative_incremental'] = comparison['incremental_loss'].cumsum()
        
        return comparison
    
    def _calculate_tranche_impacts(
        self,
        deal_structure: Dict[str, Any],
        base_results: pd.DataFrame,
        stressed_results: pd.DataFrame,
    ) -> Dict[str, Dict[str, float]]:
        """Calculate impact on each tranche."""
        tranches = deal_structure.get("bonds", [])
        
        total_base_loss = base_results['loss'].sum()
        total_stressed_loss = stressed_results['loss'].sum()
        incremental_loss = total_stressed_loss - total_base_loss
        
        impacts = {}
        remaining_loss = incremental_loss
        
        # Allocate losses bottom-up
        for tranche in reversed(tranches):
            tid = tranche.get("id", tranche.get("bond_id", "Unknown"))
            balance = tranche.get("original_balance", tranche.get("balance", 0))
            
            loss_to_tranche = min(remaining_loss, balance)
            remaining_loss = max(0, remaining_loss - balance)
            
            impacts[tid] = {
                "original_balance": balance,
                "loss_allocated": loss_to_tranche,
                "loss_percentage": loss_to_tranche / balance * 100 if balance > 0 else 0,
                "remaining_balance": max(0, balance - loss_to_tranche),
                "principal_impaired": loss_to_tranche > 0,
            }
        
        return impacts
    
    def generate_stress_report(
        self,
        results: Dict[str, StressResult],
        output_format: str = "html",
    ) -> str:
        """
        Generate comprehensive stress testing report.
        
        Parameters
        ----------
        results : Dict[str, StressResult]
            Results by scenario
        output_format : str
            Output format ('html', 'text')
            
        Returns
        -------
        str
            Formatted report
        """
        if output_format == "html":
            return self._generate_html_report(results)
        else:
            return self._generate_text_report(results)
    
    def _generate_text_report(self, results: Dict[str, StressResult]) -> str:
        """Generate plain text stress report."""
        lines = [
            "=" * 70,
            "STRESS TESTING REPORT",
            f"Generated: {date.today()}",
            "=" * 70,
            "",
        ]
        
        for scenario_id, result in results.items():
            lines.extend([
                f"\n{'=' * 50}",
                f"Scenario: {result.scenario.name}",
                f"Type: {result.scenario.scenario_type.value}",
                f"{'=' * 50}",
                "",
                "Key Metrics:",
                f"  Base Total Loss:     ${result.total_loss_base:,.0f}",
                f"  Stressed Total Loss: ${result.total_loss_stressed:,.0f}",
                f"  Incremental Loss:    ${result.incremental_loss:,.0f}",
                f"  Loss Multiple:       {result.loss_multiple:.2f}x",
                "",
            ])
            
            if result.tranche_impacts:
                lines.append("Tranche Impacts:")
                for tid, impact in result.tranche_impacts.items():
                    lines.append(
                        f"  {tid}: {impact['loss_percentage']:.1f}% loss "
                        f"({'IMPAIRED' if impact['principal_impaired'] else 'Protected'})"
                    )
                lines.append("")
        
        return "\n".join(lines)
    
    def _generate_html_report(self, results: Dict[str, StressResult]) -> str:
        """Generate HTML stress report."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Stress Testing Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        h2 { color: #666; border-bottom: 2px solid #4CAF50; padding-bottom: 5px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: right; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .impaired { background-color: #ffcccc; }
        .protected { background-color: #ccffcc; }
        .metric-card { 
            display: inline-block; 
            padding: 15px; 
            margin: 10px; 
            border-radius: 8px; 
            background-color: #f5f5f5;
            min-width: 150px;
        }
        .metric-value { font-size: 24px; font-weight: bold; color: #333; }
        .metric-label { font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <h1>Stress Testing Report</h1>
    <p>Generated: """ + str(date.today()) + """</p>
"""
        
        for scenario_id, result in results.items():
            html += f"""
    <h2>{result.scenario.name}</h2>
    <p><em>Type: {result.scenario.scenario_type.value}</em></p>
    
    <div class="metrics">
        <div class="metric-card">
            <div class="metric-value">${result.total_loss_base:,.0f}</div>
            <div class="metric-label">Base Loss</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">${result.total_loss_stressed:,.0f}</div>
            <div class="metric-label">Stressed Loss</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{result.loss_multiple:.2f}x</div>
            <div class="metric-label">Loss Multiple</div>
        </div>
    </div>
    
    <h3>Tranche Impacts</h3>
    <table>
        <tr>
            <th>Tranche</th>
            <th>Original Balance</th>
            <th>Loss Allocated</th>
            <th>Loss %</th>
            <th>Status</th>
        </tr>
"""
            
            for tid, impact in result.tranche_impacts.items():
                status_class = "impaired" if impact['principal_impaired'] else "protected"
                status_text = "IMPAIRED" if impact['principal_impaired'] else "Protected"
                html += f"""
        <tr class="{status_class}">
            <td style="text-align:left">{tid}</td>
            <td>${impact['original_balance']:,.0f}</td>
            <td>${impact['loss_allocated']:,.0f}</td>
            <td>{impact['loss_percentage']:.1f}%</td>
            <td>{status_text}</td>
        </tr>
"""
            
            html += """
    </table>
"""
        
        html += """
</body>
</html>
"""
        return html


# =============================================================================
# Predefined Stress Scenarios
# =============================================================================

# Convenience constructors for common scenarios
def create_severe_recession_scenario() -> StressScenario:
    """Create a severe recession stress scenario."""
    return StressScenario(
        scenario_id="severe_recession",
        name="Severe Recession",
        scenario_type=ScenarioType.SEVERELY_ADVERSE,
        horizon_months=36,
        hpi_shock=-0.25,
        unemployment_shock=0.06,
        gdp_shock=-0.04,
        cdr_multiplier=3.0,
        cpr_multiplier=0.5,
        severity_add=0.15,
        rate_shock=-0.02,
        description="Severe economic downturn with 25% HPI decline and 3x default rate",
    )


def create_rate_shock_scenario(shock_bps: int = 300) -> StressScenario:
    """Create an interest rate shock scenario."""
    return StressScenario(
        scenario_id=f"rate_shock_{shock_bps}bps",
        name=f"Rate Shock +{shock_bps}bps",
        scenario_type=ScenarioType.SENSITIVITY,
        horizon_months=24,
        rate_shock=shock_bps / 10000,
        rate_shock_type=RateShockType.PARALLEL_UP,
        cpr_multiplier=0.7,  # Lower prepays with higher rates
        description=f"Parallel rate increase of {shock_bps} basis points",
    )


def create_hpi_decline_scenario(decline_pct: float = 0.20) -> StressScenario:
    """Create an HPI decline scenario."""
    return StressScenario(
        scenario_id=f"hpi_decline_{int(decline_pct*100)}pct",
        name=f"HPI Decline {decline_pct:.0%}",
        scenario_type=ScenarioType.SENSITIVITY,
        horizon_months=24,
        hpi_shock=-decline_pct,
        cdr_multiplier=1.5,
        severity_add=decline_pct * 0.5,  # Severity increases with HPI decline
        description=f"House price decline of {decline_pct:.0%}",
    )
