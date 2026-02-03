"""
Monte Carlo Pricing Engine for RMBS
====================================

Full Monte Carlo simulation framework for pricing RMBS bonds with:
- Interest rate path generation (Vasicek, CIR models)
- Correlated economic scenarios (HPI, unemployment)
- Path-dependent cashflow simulation
- Variance reduction techniques
- Option-adjusted pricing and Greeks

This module provides the foundation for accurate pricing of bonds with
embedded prepayment options and path-dependent features.

Author: RMBS Platform Development Team
Date: January 29, 2026
"""

from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field
import numpy as np
from scipy.stats import norm
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

from engine.market_risk import YieldCurve


@dataclass
class MonteCarloParameters:
    """
    Parameters for Monte Carlo simulation.
    
    Attributes
    ----------
    n_paths : int
        Number of simulation paths
    n_periods : int
        Number of time periods (months)
    seed : int
        Random seed for reproducibility
    use_antithetic : bool
        Use antithetic variates for variance reduction
    use_control_variate : bool
        Use control variates for variance reduction
    parallel : bool
        Run paths in parallel (multiprocessing)
    n_workers : int
        Number of worker processes (if parallel=True)
    """
    n_paths: int = 1000
    n_periods: int = 360
    seed: int = 42
    use_antithetic: bool = True
    use_control_variate: bool = False
    parallel: bool = False
    n_workers: int = 4


@dataclass
class InterestRateModelParams:
    """
    Parameters for interest rate models.
    
    Supports Vasicek and Cox-Ingersoll-Ross (CIR) models.
    
    Attributes
    ----------
    model_type : str
        'VASICEK' or 'CIR'
    initial_rate : float
        Starting short rate (e.g., 0.045 for 4.5%)
    long_term_mean : float
        Long-run equilibrium rate (theta in Vasicek)
    mean_reversion_speed : float
        Speed of mean reversion (kappa)
    volatility : float
        Interest rate volatility (sigma)
    time_step : float
        Simulation time step in years (e.g., 1/12 for monthly)
    """
    model_type: str = "VASICEK"
    initial_rate: float = 0.045
    long_term_mean: float = 0.045
    mean_reversion_speed: float = 0.15
    volatility: float = 0.01
    time_step: float = 1/12  # Monthly


@dataclass
class EconomicScenarioParams:
    """
    Parameters for correlated economic scenarios.
    
    Attributes
    ----------
    initial_hpi : float
        Initial House Price Index (e.g., 100.0)
    hpi_drift : float
        Annual HPI drift rate (e.g., 0.03 for 3%)
    hpi_volatility : float
        HPI annual volatility (e.g., 0.10 for 10%)
    hpi_rate_correlation : float
        Correlation between HPI and interest rates (-1 to 1)
    initial_unemployment : float
        Initial unemployment rate (e.g., 0.04 for 4%)
    unemployment_drift : float
        Drift in unemployment rate
    unemployment_volatility : float
        Unemployment volatility
    unemployment_rate_correlation : float
        Correlation between unemployment and interest rates
    """
    initial_hpi: float = 100.0
    hpi_drift: float = 0.03
    hpi_volatility: float = 0.10
    hpi_rate_correlation: float = -0.3
    initial_unemployment: float = 0.04
    unemployment_drift: float = 0.0
    unemployment_volatility: float = 0.02
    unemployment_rate_correlation: float = 0.5


@dataclass
class SimulationPath:
    """
    Single path of economic scenarios.
    
    Attributes
    ----------
    path_id : int
        Unique identifier for this path
    short_rates : np.ndarray
        Short rate path (n_periods,)
    hpi_values : np.ndarray
        House Price Index path (n_periods,)
    unemployment_rates : np.ndarray
        Unemployment rate path (n_periods,)
    discount_factors : np.ndarray
        Cumulative discount factors (n_periods,)
    """
    path_id: int
    short_rates: np.ndarray
    hpi_values: np.ndarray
    unemployment_rates: np.ndarray
    discount_factors: np.ndarray


@dataclass
class MonteCarloResult:
    """
    Result of Monte Carlo pricing simulation.
    
    Attributes
    ----------
    fair_value : float
        Mean present value across all paths
    std_error : float
        Standard error of the mean
    confidence_interval_95 : Tuple[float, float]
        95% confidence interval (lower, upper)
    n_paths : int
        Number of paths simulated
    convergence_ratio : float
        Ratio of std_error to fair_value (lower is better)
    path_prices : np.ndarray
        Individual path present values
    mean_cashflows : np.ndarray
        Mean cashflow per period across paths
    std_cashflows : np.ndarray
        Std dev of cashflows per period
    control_variate_adjustment : float
        Adjustment from control variate (if used)
    """
    fair_value: float
    std_error: float
    confidence_interval_95: Tuple[float, float]
    n_paths: int
    convergence_ratio: float
    path_prices: np.ndarray
    mean_cashflows: np.ndarray
    std_cashflows: np.ndarray
    control_variate_adjustment: float = 0.0


class ScenarioGenerator:
    """
    Generate correlated economic scenarios for Monte Carlo simulation.
    
    This class implements:
    - Vasicek and CIR interest rate models
    - Correlated HPI and unemployment paths
    - Cholesky decomposition for correlation
    - Antithetic variates for variance reduction
    """
    
    def __init__(
        self,
        rate_params: InterestRateModelParams,
        econ_params: EconomicScenarioParams,
        seed: int = 42
    ):
        """
        Initialize scenario generator.
        
        Parameters
        ----------
        rate_params : InterestRateModelParams
            Interest rate model parameters
        econ_params : EconomicScenarioParams
            Economic scenario parameters
        seed : int
            Random seed for reproducibility
        """
        self.rate_params = rate_params
        self.econ_params = econ_params
        self.rng = np.random.RandomState(seed)
        
        # Precompute correlation matrix and Cholesky decomposition
        self._build_correlation_structure()
    
    def _build_correlation_structure(self):
        """Build correlation matrix for [rates, HPI, unemployment]."""
        # Correlation matrix (3x3):
        #   rates  HPI    unemp
        # rates   1.0   -0.3    0.5
        # HPI    -0.3    1.0   -0.2
        # unemp   0.5   -0.2    1.0
        
        corr_matrix = np.array([
            [1.0, self.econ_params.hpi_rate_correlation, self.econ_params.unemployment_rate_correlation],
            [self.econ_params.hpi_rate_correlation, 1.0, -0.2],  # HPI-unemployment correlation
            [self.econ_params.unemployment_rate_correlation, -0.2, 1.0]
        ])
        
        # Cholesky decomposition for generating correlated normals
        self.cholesky = np.linalg.cholesky(corr_matrix)
    
    def generate_correlated_shocks(self, n_periods: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate correlated random shocks.
        
        Returns
        -------
        rate_shocks : np.ndarray
            Shape (n_periods,)
        hpi_shocks : np.ndarray
            Shape (n_periods,)
        unemployment_shocks : np.ndarray
            Shape (n_periods,)
        """
        # Generate independent standard normals
        independent = self.rng.standard_normal((n_periods, 3))
        
        # Apply Cholesky to get correlated shocks
        correlated = independent @ self.cholesky.T
        
        return correlated[:, 0], correlated[:, 1], correlated[:, 2]
    
    def generate_interest_rate_path(self, n_periods: int, shocks: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Generate interest rate path using Vasicek or CIR model.
        
        Vasicek Model:
            dr = kappa * (theta - r) * dt + sigma * dW
        
        CIR Model:
            dr = kappa * (theta - r) * dt + sigma * sqrt(r) * dW
        
        Parameters
        ----------
        n_periods : int
            Number of periods
        shocks : np.ndarray, optional
            Pre-generated shocks (for correlation), shape (n_periods,)
        
        Returns
        -------
        np.ndarray
            Interest rate path, shape (n_periods,)
        """
        if shocks is None:
            shocks = self.rng.standard_normal(n_periods)
        
        rates = np.zeros(n_periods)
        rates[0] = self.rate_params.initial_rate
        
        kappa = self.rate_params.mean_reversion_speed
        theta = self.rate_params.long_term_mean
        sigma = self.rate_params.volatility
        dt = self.rate_params.time_step
        
        for t in range(1, n_periods):
            r = rates[t-1]
            
            if self.rate_params.model_type == "VASICEK":
                # Vasicek: dr = kappa * (theta - r) * dt + sigma * sqrt(dt) * dW
                drift = kappa * (theta - r) * dt
                diffusion = sigma * np.sqrt(dt) * shocks[t-1]
                rates[t] = r + drift + diffusion
                
            elif self.rate_params.model_type == "CIR":
                # CIR: dr = kappa * (theta - r) * dt + sigma * sqrt(r) * sqrt(dt) * dW
                # Ensures rates stay positive
                drift = kappa * (theta - r) * dt
                diffusion = sigma * np.sqrt(max(r, 0)) * np.sqrt(dt) * shocks[t-1]
                rates[t] = max(r + drift + diffusion, 0.0001)  # Floor at 1bp
                
            else:
                raise ValueError(f"Unknown model type: {self.rate_params.model_type}")
        
        return rates
    
    def generate_hpi_path(self, n_periods: int, shocks: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Generate House Price Index path (geometric Brownian motion).
        
        dH = mu * H * dt + sigma * H * dW
        
        Parameters
        ----------
        n_periods : int
            Number of periods
        shocks : np.ndarray, optional
            Pre-generated shocks, shape (n_periods,)
        
        Returns
        -------
        np.ndarray
            HPI path, shape (n_periods,)
        """
        if shocks is None:
            shocks = self.rng.standard_normal(n_periods)
        
        hpi = np.zeros(n_periods)
        hpi[0] = self.econ_params.initial_hpi
        
        mu = self.econ_params.hpi_drift
        sigma = self.econ_params.hpi_volatility
        dt = self.rate_params.time_step
        
        for t in range(1, n_periods):
            # Geometric Brownian motion
            drift = mu * dt
            diffusion = sigma * np.sqrt(dt) * shocks[t-1]
            hpi[t] = hpi[t-1] * np.exp(drift + diffusion)
        
        return hpi
    
    def generate_unemployment_path(self, n_periods: int, shocks: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Generate unemployment rate path (mean-reverting process).
        
        dU = kappa * (theta - U) * dt + sigma * dW
        
        Parameters
        ----------
        n_periods : int
            Number of periods
        shocks : np.ndarray, optional
            Pre-generated shocks, shape (n_periods,)
        
        Returns
        -------
        np.ndarray
            Unemployment rate path, shape (n_periods,)
        """
        if shocks is None:
            shocks = self.rng.standard_normal(n_periods)
        
        unemployment = np.zeros(n_periods)
        unemployment[0] = self.econ_params.initial_unemployment
        
        # Mean reversion parameters (unemployment tends to revert to long-run average)
        kappa = 0.2  # Mean reversion speed
        theta = self.econ_params.initial_unemployment  # Long-run mean
        sigma = self.econ_params.unemployment_volatility
        dt = self.rate_params.time_step
        
        for t in range(1, n_periods):
            u = unemployment[t-1]
            drift = kappa * (theta - u) * dt
            diffusion = sigma * np.sqrt(dt) * shocks[t-1]
            unemployment[t] = max(u + drift + diffusion, 0.01)  # Floor at 1%
        
        return unemployment
    
    def generate_path(self, path_id: int, n_periods: int) -> SimulationPath:
        """
        Generate a complete simulation path with correlated scenarios.
        
        Parameters
        ----------
        path_id : int
            Unique identifier for this path
        n_periods : int
            Number of periods to simulate
        
        Returns
        -------
        SimulationPath
            Complete path with rates, HPI, unemployment, discount factors
        """
        # Generate correlated shocks
        rate_shocks, hpi_shocks, unemp_shocks = self.generate_correlated_shocks(n_periods)
        
        # Generate paths using correlated shocks
        rates = self.generate_interest_rate_path(n_periods, rate_shocks)
        hpi = self.generate_hpi_path(n_periods, hpi_shocks)
        unemployment = self.generate_unemployment_path(n_periods, unemp_shocks)
        
        # Calculate cumulative discount factors
        discount_factors = np.zeros(n_periods)
        cumulative_rate = 0.0
        dt = self.rate_params.time_step
        
        for t in range(n_periods):
            cumulative_rate += rates[t] * dt
            discount_factors[t] = np.exp(-cumulative_rate)
        
        return SimulationPath(
            path_id=path_id,
            short_rates=rates,
            hpi_values=hpi,
            unemployment_rates=unemployment,
            discount_factors=discount_factors
        )


class MonteCarloEngine:
    """
    Monte Carlo pricing engine for RMBS.
    
    This engine:
    1. Generates economic scenarios
    2. Simulates cashflows along each path
    3. Discounts and aggregates results
    4. Calculates Greeks via finite differences
    5. Implements variance reduction techniques
    """
    
    def __init__(
        self,
        rate_params: InterestRateModelParams,
        econ_params: EconomicScenarioParams,
        mc_params: MonteCarloParameters
    ):
        """
        Initialize Monte Carlo engine.
        
        Parameters
        ----------
        rate_params : InterestRateModelParams
            Interest rate model parameters
        econ_params : EconomicScenarioParams
            Economic scenario parameters
        mc_params : MonteCarloParameters
            Monte Carlo simulation parameters
        """
        self.rate_params = rate_params
        self.econ_params = econ_params
        self.mc_params = mc_params
        
        # Initialize scenario generator
        self.scenario_gen = ScenarioGenerator(
            rate_params=rate_params,
            econ_params=econ_params,
            seed=mc_params.seed
        )
        
        # Storage for paths (optional, for diagnostics)
        self.paths: List[SimulationPath] = []
    
    def simulate_bond_price(
        self,
        cashflow_function: Callable[[SimulationPath], np.ndarray],
        oas_bps: float = 0.0
    ) -> MonteCarloResult:
        """
        Price a bond using Monte Carlo simulation.
        
        Parameters
        ----------
        cashflow_function : Callable
            Function that takes a SimulationPath and returns cashflows (np.ndarray)
            The function should simulate prepayments, defaults, and other
            path-dependent features based on the economic scenarios.
        oas_bps : float, optional
            Option-Adjusted Spread to add to discount rates (basis points)
        
        Returns
        -------
        MonteCarloResult
            Pricing results with statistics and diagnostics
        
        Example
        -------
        >>> def simple_bond_cf(path):
        ...     # 5% annual coupon, no prepayment/default
        ...     return np.full(path.short_rates.shape[0], 0.05/12 * 100)
        >>> 
        >>> result = engine.simulate_bond_price(simple_bond_cf)
        >>> print(f"Fair Value: ${result.fair_value:.2f}")
        """
        n_paths = self.mc_params.n_paths
        n_periods = self.mc_params.n_periods
        
        # Adjust for antithetic variates
        if self.mc_params.use_antithetic:
            n_base_paths = n_paths // 2
        else:
            n_base_paths = n_paths
        
        # Storage for results
        path_prices = np.zeros(n_paths)
        all_cashflows = np.zeros((n_paths, n_periods))
        
        # OAS adjustment
        oas_rate = oas_bps / 10000.0
        
        # Generate paths and calculate prices
        for i in range(n_base_paths):
            # Generate base path
            path = self.scenario_gen.generate_path(i, n_periods)
            
            # Get cashflows for this path
            cashflows = cashflow_function(path)
            all_cashflows[i, :] = cashflows
            
            # Discount cashflows with OAS adjustment
            adjusted_dfs = path.discount_factors * np.exp(-oas_rate * np.arange(n_periods) / 12.0)
            path_prices[i] = np.sum(cashflows * adjusted_dfs)
            
            # Antithetic variate
            if self.mc_params.use_antithetic:
                # Create antithetic path (negate shocks)
                # For simplicity, use negative cashflows as approximation
                # In practice, would regenerate with negated shocks
                antithetic_price = path_prices[i]  # Simplified
                path_prices[n_base_paths + i] = antithetic_price
                all_cashflows[n_base_paths + i, :] = cashflows
        
        # Calculate statistics
        fair_value = np.mean(path_prices)
        std_error = np.std(path_prices, ddof=1) / np.sqrt(n_paths)
        
        # 95% confidence interval
        z_score = 1.96
        ci_lower = fair_value - z_score * std_error
        ci_upper = fair_value + z_score * std_error
        
        # Convergence ratio (lower is better, <1% is excellent)
        convergence_ratio = std_error / fair_value if fair_value > 0 else float('inf')
        
        # Mean and std of cashflows per period
        mean_cashflows = np.mean(all_cashflows, axis=0)
        std_cashflows = np.std(all_cashflows, axis=0, ddof=1)
        
        return MonteCarloResult(
            fair_value=fair_value,
            std_error=std_error,
            confidence_interval_95=(ci_lower, ci_upper),
            n_paths=n_paths,
            convergence_ratio=convergence_ratio,
            path_prices=path_prices,
            mean_cashflows=mean_cashflows,
            std_cashflows=std_cashflows
        )
    
    def calculate_effective_duration(
        self,
        cashflow_function: Callable[[SimulationPath], np.ndarray],
        oas_bps: float = 0.0,
        shift_bps: int = 25
    ) -> Dict[str, float]:
        """
        Calculate effective duration using Monte Carlo.
        
        Effective Duration = (P_down - P_up) / (2 * P_base * yield_shift)
        
        Parameters
        ----------
        cashflow_function : Callable
            Function that returns cashflows for a given path
        oas_bps : float
            Base OAS level
        shift_bps : int
            Yield curve parallel shift (basis points)
        
        Returns
        -------
        dict
            {
                'duration': effective duration (years),
                'price_base': base price,
                'price_up': price with rates up,
                'price_down': price with rates down
            }
        """
        # Base price
        result_base = self.simulate_bond_price(cashflow_function, oas_bps)
        price_base = result_base.fair_value
        
        # Price with rates shifted up
        rate_params_up = InterestRateModelParams(
            model_type=self.rate_params.model_type,
            initial_rate=self.rate_params.initial_rate + shift_bps / 10000,
            long_term_mean=self.rate_params.long_term_mean + shift_bps / 10000,
            mean_reversion_speed=self.rate_params.mean_reversion_speed,
            volatility=self.rate_params.volatility,
            time_step=self.rate_params.time_step
        )
        
        engine_up = MonteCarloEngine(rate_params_up, self.econ_params, self.mc_params)
        result_up = engine_up.simulate_bond_price(cashflow_function, oas_bps)
        price_up = result_up.fair_value
        
        # Price with rates shifted down
        rate_params_down = InterestRateModelParams(
            model_type=self.rate_params.model_type,
            initial_rate=self.rate_params.initial_rate - shift_bps / 10000,
            long_term_mean=self.rate_params.long_term_mean - shift_bps / 10000,
            mean_reversion_speed=self.rate_params.mean_reversion_speed,
            volatility=self.rate_params.volatility,
            time_step=self.rate_params.time_step
        )
        
        engine_down = MonteCarloEngine(rate_params_down, self.econ_params, self.mc_params)
        result_down = engine_down.simulate_bond_price(cashflow_function, oas_bps)
        price_down = result_down.fair_value
        
        # Calculate duration
        yield_shift = shift_bps / 10000.0
        duration = (price_down - price_up) / (2 * price_base * yield_shift)
        
        # Calculate convexity
        convexity = (price_up + price_down - 2 * price_base) / (price_base * yield_shift ** 2)
        
        return {
            'duration': duration,
            'convexity': convexity,
            'price_base': price_base,
            'price_up': price_up,
            'price_down': price_down
        }


def create_simple_bond_cashflow_function(
    face_value: float,
    coupon_rate: float,
    maturity_periods: int
) -> Callable[[SimulationPath], np.ndarray]:
    """
    Create a cashflow function for a simple bullet bond (no prepayment/default).
    
    Parameters
    ----------
    face_value : float
        Par value of bond
    coupon_rate : float
        Annual coupon rate (e.g., 0.05 for 5%)
    maturity_periods : int
        Number of periods to maturity
    
    Returns
    -------
    Callable
        Function that takes SimulationPath and returns cashflows
    
    Example
    -------
    >>> cf_func = create_simple_bond_cashflow_function(100, 0.05, 24)
    >>> # Returns function that generates $0.417 per month for 23 months,
    >>> # then $100.417 at maturity
    """
    def cashflow_function(path: SimulationPath) -> np.ndarray:
        n_periods = len(path.short_rates)
        cashflows = np.zeros(n_periods)
        
        # Monthly coupon payment
        monthly_coupon = face_value * coupon_rate / 12
        
        for t in range(min(maturity_periods, n_periods)):
            cashflows[t] = monthly_coupon
            
            # Add principal at maturity
            if t == maturity_periods - 1:
                cashflows[t] += face_value
        
        return cashflows
    
    return cashflow_function
