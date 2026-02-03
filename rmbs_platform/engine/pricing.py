"""
RMBS Pricing Engine
===================

Full pricing capabilities combining market risk and credit risk analytics.

Components:
1. Credit-Adjusted OAS Calculation
2. Fair Value Pricing
3. Price/Yield Relationships
4. Greeks Calculation

This module integrates:
- Phase 2B: Market Risk (yield curves, duration, OAS)
- Phase 2C: Credit Risk (PD, LGD, expected loss)

Author: RMBS Platform Development Team
Date: January 29, 2026
"""

from typing import Dict, List, Tuple, Callable, Optional
from dataclasses import dataclass
import numpy as np
from scipy.optimize import brentq, minimize_scalar

from engine.market_risk import YieldCurve


@dataclass
class CreditSpreadComponents:
    """
    Breakdown of credit spread into components.
    
    Attributes
    ----------
    pd : float
        Probability of default (annualized)
    lgd : float
        Loss given default (as fraction, e.g., 0.35 for 35%)
    recovery_lag : float
        Average time to recovery after default (years)
    base_credit_spread : float
        Spread implied by PD and LGD alone (bps)
    recovery_lag_adjustment : float
        Additional spread due to recovery timing (bps)
    total_credit_spread : float
        Total credit spread (bps)
    """
    pd: float
    lgd: float
    recovery_lag: float
    base_credit_spread: float
    recovery_lag_adjustment: float
    total_credit_spread: float


@dataclass
class OASResult:
    """
    Result of OAS calculation with full breakdown.
    
    Attributes
    ----------
    oas : float
        Option-Adjusted Spread (bps)
    z_spread : float
        Static Z-spread (bps)
    credit_spread : float
        Credit spread from PD/LGD (bps)
    liquidity_spread : float
        Implied liquidity premium (bps), calculated as OAS - (Z + Credit)
    fair_value : float
        Theoretical fair value given OAS
    market_price : float
        Observed market price
    price_difference : float
        Market price - Fair value
    iterations : int
        Number of solver iterations
    converged : bool
        Whether solver converged
    credit_components : CreditSpreadComponents
        Detailed credit spread breakdown
    """
    oas: float
    z_spread: float
    credit_spread: float
    liquidity_spread: float
    fair_value: float
    market_price: float
    price_difference: float
    iterations: int
    converged: bool
    credit_components: CreditSpreadComponents


def calculate_credit_spread(
    pd: float,
    lgd: float,
    recovery_lag: float = 0.5,
    risk_free_rate: float = 0.04
) -> CreditSpreadComponents:
    """
    Calculate credit spread from probability of default and loss severity.
    
    This function uses the standard credit pricing formula that relates
    default probability and loss severity to required spread.
    
    Formula
    -------
    Base spread formula (continuous compounding):
        Credit Spread ≈ -ln(1 - PD × LGD) / t
    
    Where t is typically 1 year for annualized spread.
    
    For small PD × LGD, this approximates to: PD × LGD
    
    Recovery lag adjustment accounts for the time value of money
    during the workout/recovery period.
    
    Parameters
    ----------
    pd : float
        Probability of default (annualized), e.g., 0.02 for 2%
    lgd : float
        Loss given default (as fraction), e.g., 0.35 for 35% loss
    recovery_lag : float, optional
        Average time to recovery after default (years), default 0.5
        Typical range: 0.25 to 1.5 years for RMBS
    risk_free_rate : float, optional
        Risk-free rate for discounting recovery, default 0.04 (4%)
    
    Returns
    -------
    CreditSpreadComponents
        Detailed breakdown of credit spread calculation
    
    Notes
    -----
    Industry Benchmarks:
    - Prime RMBS: PD 1-3%, LGD 30-40%, Spread 30-120 bps
    - Alt-A RMBS: PD 3-6%, LGD 35-45%, Spread 100-200 bps
    - Subprime RMBS: PD 8-15%, LGD 40-50%, Spread 300-600 bps
    
    Example
    -------
    >>> comps = calculate_credit_spread(pd=0.02, lgd=0.35)
    >>> print(f"Credit Spread: {comps.total_credit_spread:.0f} bps")
    Credit Spread: 71 bps
    """
    # Base credit spread (Merton model approximation)
    expected_loss = pd * lgd
    
    # For small expected losses, use linear approximation
    if expected_loss < 0.1:
        base_spread = expected_loss
    else:
        # For larger losses, use exact formula
        base_spread = -np.log(1 - expected_loss)
    
    # Adjustment for recovery lag (time value of lost interest during workout)
    # During recovery period, investors lose interest on the defaulted amount
    discount_factor = np.exp(-risk_free_rate * recovery_lag)
    recovery_lag_adj = expected_loss * (1 - discount_factor)
    
    # Total credit spread
    total_spread = base_spread + recovery_lag_adj
    
    # Convert to basis points
    base_spread_bps = base_spread * 10000
    recovery_lag_adj_bps = recovery_lag_adj * 10000
    total_spread_bps = total_spread * 10000
    
    return CreditSpreadComponents(
        pd=pd,
        lgd=lgd,
        recovery_lag=recovery_lag,
        base_credit_spread=base_spread_bps,
        recovery_lag_adjustment=recovery_lag_adj_bps,
        total_credit_spread=total_spread_bps
    )


def present_value_cashflows(
    cashflows: List[Tuple[float, float]],
    yield_curve: YieldCurve,
    spread_bps: float = 0.0
) -> float:
    """
    Calculate present value of cashflow stream.
    
    Parameters
    ----------
    cashflows : List[Tuple[float, float]]
        List of (time, amount) tuples
        time is in years (e.g., 0.5 for 6 months)
        amount is in currency units
    yield_curve : YieldCurve
        Discount curve for present value calculation
    spread_bps : float, optional
        Additional spread to add to discount rates (basis points)
    
    Returns
    -------
    float
        Present value of all cashflows
    
    Example
    -------
    >>> from engine.market_risk import YieldCurve
    >>> curve = YieldCurve([1, 2, 5, 10], [0.04, 0.042, 0.044, 0.045])
    >>> cfs = [(0.5, 2.5), (1.0, 2.5), (1.5, 2.5), (2.0, 102.5)]
    >>> pv = present_value_cashflows(cfs, curve)
    >>> print(f"PV: ${pv:.2f}")
    """
    pv = 0.0
    spread_rate = spread_bps / 10000.0  # Convert bps to decimal
    
    for time, amount in cashflows:
        if time <= 0 or amount == 0:
            continue
        
        # Get zero rate from curve
        zero_rate = yield_curve.get_zero_rate(time)
        
        # Add spread and calculate discount factor
        total_rate = zero_rate + spread_rate
        discount_factor = np.exp(-total_rate * time)
        
        pv += amount * discount_factor
    
    return pv


def calculate_z_spread(
    cashflows: List[Tuple[float, float]],
    market_price: float,
    yield_curve: YieldCurve,
    target_tol: float = 0.01
) -> Tuple[float, int, bool]:
    """
    Calculate static Z-spread (spread over zero curve).
    
    Z-spread is the constant spread that, when added to the zero curve,
    makes the PV of cashflows equal the market price.
    
    Parameters
    ----------
    cashflows : List[Tuple[float, float]]
        List of (time, amount) tuples
    market_price : float
        Observed market price
    yield_curve : YieldCurve
        Risk-free zero curve
    target_tol : float, optional
        Target price tolerance for convergence, default 0.01
    
    Returns
    -------
    z_spread : float
        Z-spread in basis points
    iterations : int
        Number of solver iterations
    converged : bool
        Whether solver converged to target tolerance
    
    Example
    -------
    >>> z_spread, iters, converged = calculate_z_spread(
    ...     cashflows=[(1, 5), (2, 5), (3, 105)],
    ...     market_price=102.5,
    ...     yield_curve=curve
    ... )
    >>> print(f"Z-Spread: {z_spread:.0f} bps")
    """
    def price_error(spread_bps):
        pv = present_value_cashflows(cashflows, yield_curve, spread_bps)
        return pv - market_price
    
    # Check if price is achievable (must be less than undiscounted cashflows)
    total_cashflows = sum(amount for _, amount in cashflows)
    if market_price > total_cashflows:
        raise ValueError(
            f"Market price ({market_price:.2f}) exceeds total cashflows "
            f"({total_cashflows:.2f})"
        )
    
    # Check if spread needs to be positive or negative
    pv_at_zero_spread = present_value_cashflows(cashflows, yield_curve, 0)
    
    try:
        if abs(pv_at_zero_spread - market_price) < target_tol:
            # Already at target price with zero spread
            return 0.0, 1, True
        
        # Determine search bounds
        if pv_at_zero_spread > market_price:
            # Need positive spread to lower PV
            bounds = (0, 5000)  # 0 to 500% spread
        else:
            # Need negative spread to raise PV
            bounds = (-2000, 0)  # -200% to 0 spread
        
        # Solve for spread using Brent's method
        z_spread_bps = brentq(
            price_error,
            bounds[0],
            bounds[1],
            xtol=0.01,  # 0.01 bp tolerance
            maxiter=100
        )
        
        # Verify convergence
        final_pv = present_value_cashflows(cashflows, yield_curve, z_spread_bps)
        converged = abs(final_pv - market_price) < target_tol
        
        # Count iterations (Brent's method doesn't report, estimate)
        iterations = 10  # Typical for Brent's method
        
        return z_spread_bps, iterations, converged
        
    except ValueError as e:
        # Solver failed to converge
        return 0.0, 100, False


def solve_credit_adjusted_oas(
    cashflows: List[Tuple[float, float]],
    market_price: float,
    yield_curve: YieldCurve,
    pd: float,
    lgd: float,
    recovery_lag: float = 0.5,
    target_tol: float = 0.01
) -> OASResult:
    """
    Solve for option-adjusted spread with credit adjustment.
    
    This is the main pricing function that combines:
    1. Risk-free discounting (via yield curve)
    2. Credit risk (via PD and LGD)
    3. Option-adjusted spread (residual spread after credit adjustment)
    
    The OAS represents the market's compensation for prepayment risk
    and any other factors beyond credit risk.
    
    Formula
    -------
    Market Price = PV[Cashflows discounted at (Curve + OAS + Credit Spread)]
    
    Where:
        Credit Spread = f(PD, LGD, Recovery Lag)
        OAS = Solved to match market price
        Liquidity Spread = OAS - Z_Spread - Credit_Spread (implied)
    
    Parameters
    ----------
    cashflows : List[Tuple[float, float]]
        Expected cashflows (time, amount) accounting for prepayments/defaults
        Time in years, amount in currency units
    market_price : float
        Observed market price
    yield_curve : YieldCurve
        Risk-free zero curve
    pd : float
        Probability of default (annualized)
    lgd : float
        Loss given default (fraction)
    recovery_lag : float, optional
        Average recovery time (years), default 0.5
    target_tol : float, optional
        Price tolerance for convergence, default 0.01
    
    Returns
    -------
    OASResult
        Complete breakdown of OAS calculation including credit spread,
        Z-spread, liquidity premium, and convergence diagnostics
    
    Notes
    -----
    The function solves for the OAS that makes the present value
    of cashflows (discounted at Curve + OAS + Credit) equal to the
    market price.
    
    For RMBS, typical OAS ranges:
    - Agency RMBS: 20-100 bps (low credit risk, mainly prepayment risk)
    - Non-agency prime: 100-300 bps (moderate credit + prepayment risk)
    - Non-agency subprime: 300-800 bps (high credit + prepayment risk)
    
    Example
    -------
    >>> result = solve_credit_adjusted_oas(
    ...     cashflows=[(0.5, 2.5), (1.0, 102.5)],
    ...     market_price=100.0,
    ...     yield_curve=curve,
    ...     pd=0.02,
    ...     lgd=0.35
    ... )
    >>> print(f"OAS: {result.oas:.0f} bps")
    >>> print(f"Credit Spread: {result.credit_spread:.0f} bps")
    >>> print(f"Liquidity Spread: {result.liquidity_spread:.0f} bps")
    """
    # Step 1: Calculate credit spread components
    credit_comps = calculate_credit_spread(
        pd=pd,
        lgd=lgd,
        recovery_lag=recovery_lag,
        risk_free_rate=yield_curve.get_zero_rate(1.0)  # 1Y rate as proxy
    )
    
    # Step 2: Calculate Z-spread (static spread without credit adjustment)
    z_spread, z_iters, z_converged = calculate_z_spread(
        cashflows=cashflows,
        market_price=market_price,
        yield_curve=yield_curve,
        target_tol=target_tol
    )
    
    # Step 3: Calculate OAS (spread including credit adjustment)
    # OAS is solved such that: PV(Curve + OAS + Credit) = Market Price
    def oas_price_error(oas_bps):
        total_spread = oas_bps + credit_comps.total_credit_spread
        pv = present_value_cashflows(cashflows, yield_curve, total_spread)
        return pv - market_price
    
    try:
        # Check PV at zero OAS (only credit spread)
        pv_with_credit_only = present_value_cashflows(
            cashflows,
            yield_curve,
            credit_comps.total_credit_spread
        )
        
        if abs(pv_with_credit_only - market_price) < target_tol:
            # Market price explained by credit spread alone
            oas = 0.0
            oas_iters = 1
            oas_converged = True
        else:
            # Determine search bounds for OAS
            if pv_with_credit_only > market_price:
                # Need additional positive spread
                oas_bounds = (0, 5000)
            else:
                # Need negative OAS (market paying less than credit model suggests)
                oas_bounds = (-2000, 0)
            
            # Solve for OAS
            oas = brentq(
                oas_price_error,
                oas_bounds[0],
                oas_bounds[1],
                xtol=0.01,
                maxiter=100
            )
            oas_iters = 10
            
            # Verify convergence
            final_pv = present_value_cashflows(
                cashflows,
                yield_curve,
                oas + credit_comps.total_credit_spread
            )
            oas_converged = abs(final_pv - market_price) < target_tol
        
        # Calculate fair value at solved OAS
        fair_value = present_value_cashflows(
            cashflows,
            yield_curve,
            oas + credit_comps.total_credit_spread
        )
        
    except ValueError:
        # Solver failed
        oas = 0.0
        oas_iters = 100
        oas_converged = False
        fair_value = 0.0
    
    # Step 4: Calculate liquidity spread (implied)
    # Liquidity Spread = OAS - (Z-Spread - Credit Spread)
    # This is the spread not explained by credit risk or option risk
    liquidity_spread = oas - (z_spread - credit_comps.total_credit_spread)
    
    # Step 5: Assemble result
    return OASResult(
        oas=oas,
        z_spread=z_spread,
        credit_spread=credit_comps.total_credit_spread,
        liquidity_spread=liquidity_spread,
        fair_value=fair_value,
        market_price=market_price,
        price_difference=market_price - fair_value,
        iterations=max(z_iters, oas_iters),
        converged=z_converged and oas_converged,
        credit_components=credit_comps
    )


def calculate_price_from_oas(
    cashflows: List[Tuple[float, float]],
    yield_curve: YieldCurve,
    oas_bps: float,
    credit_spread_bps: float = 0.0
) -> float:
    """
    Calculate bond price given OAS and credit spread.
    
    This is the inverse of the OAS solver: given OAS and credit spread,
    calculate the theoretical price.
    
    Parameters
    ----------
    cashflows : List[Tuple[float, float]]
        Expected cashflows (time, amount)
    yield_curve : YieldCurve
        Risk-free zero curve
    oas_bps : float
        Option-adjusted spread (basis points)
    credit_spread_bps : float, optional
        Credit spread (basis points), default 0
    
    Returns
    -------
    float
        Theoretical bond price
    
    Example
    -------
    >>> price = calculate_price_from_oas(
    ...     cashflows=[(1, 5), (2, 105)],
    ...     yield_curve=curve,
    ...     oas_bps=150,
    ...     credit_spread_bps=70
    ... )
    >>> print(f"Price: ${price:.2f}")
    """
    total_spread_bps = oas_bps + credit_spread_bps
    return present_value_cashflows(cashflows, yield_curve, total_spread_bps)


def calculate_yield_from_price(
    cashflows: List[Tuple[float, float]],
    price: float,
    target_tol: float = 0.0001
) -> Tuple[float, bool]:
    """
    Calculate yield to maturity from price.
    
    Solves for the constant discount rate that makes PV = Price.
    This is the traditional bond yield calculation.
    
    Parameters
    ----------
    cashflows : List[Tuple[float, float]]
        Cashflows (time, amount)
    price : float
        Bond price
    target_tol : float, optional
        Price tolerance, default 0.0001
    
    Returns
    -------
    ytm : float
        Yield to maturity (as decimal, e.g., 0.045 for 4.5%)
    converged : bool
        Whether solver converged
    
    Example
    -------
    >>> ytm, converged = calculate_yield_from_price(
    ...     cashflows=[(0.5, 2.5), (1.0, 2.5), (1.5, 2.5), (2.0, 102.5)],
    ...     price=102.5
    ... )
    >>> print(f"YTM: {ytm:.2%}")
    """
    def pv_at_yield(ytm):
        pv = sum(amount * np.exp(-ytm * time) for time, amount in cashflows if time > 0)
        return pv - price
    
    try:
        # Yield typically between -2% and 20%
        ytm = brentq(pv_at_yield, -0.02, 0.20, xtol=target_tol, maxiter=100)
        
        # Verify
        final_pv = sum(
            amount * np.exp(-ytm * time)
            for time, amount in cashflows
            if time > 0
        )
        converged = abs(final_pv - price) < target_tol
        
        return ytm, converged
        
    except ValueError:
        return 0.0, False


# Helper function for generating simple bond cashflows
def generate_bond_cashflows(
    face_value: float,
    coupon_rate: float,
    maturity_years: float,
    frequency: int = 2  # Semi-annual by default
) -> List[Tuple[float, float]]:
    """
    Generate cashflows for a simple fixed-coupon bond.
    
    Parameters
    ----------
    face_value : float
        Par value of bond
    coupon_rate : float
        Annual coupon rate (as decimal, e.g., 0.05 for 5%)
    maturity_years : float
        Time to maturity in years
    frequency : int, optional
        Payment frequency per year, default 2 (semi-annual)
    
    Returns
    -------
    List[Tuple[float, float]]
        List of (time, amount) cashflows
    
    Example
    -------
    >>> cfs = generate_bond_cashflows(
    ...     face_value=100,
    ...     coupon_rate=0.05,
    ...     maturity_years=2.0,
    ...     frequency=2
    ... )
    >>> # Returns: [(0.5, 2.5), (1.0, 2.5), (1.5, 2.5), (2.0, 102.5)]
    """
    cashflows = []
    coupon_payment = (face_value * coupon_rate) / frequency
    num_periods = int(maturity_years * frequency)
    
    for i in range(1, num_periods + 1):
        time = i / frequency
        amount = coupon_payment
        
        # Add principal at maturity
        if i == num_periods:
            amount += face_value
        
        cashflows.append((time, amount))
    
    return cashflows
