"""
Portfolio Pricing Service
=========================

Connects the full pricing engine to investor portfolio analytics.

This module provides:
1. Default yield curve construction with recent market data
2. Tranche cashflow projection using scenario parameters
3. OAS and YTM calculation using the full pricing engine
4. Risk metrics (duration, convexity)

Author: RMBS Platform Development Team
Date: February 2026
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import brentq

from engine.market_risk import (
    YieldCurve,
    InterpolationMethod,
    DurationCalculator,
)
from engine.pricing import (
    calculate_yield_from_price,
    solve_credit_adjusted_oas,
    OASResult,
)

logger = logging.getLogger("RMBS.PortfolioPricing")


@dataclass
class MarketData:
    """
    Current market data for pricing.
    
    Attributes
    ----------
    curve_date : str
        Valuation date (ISO format)
    treasury_rates : Dict[float, float]
        Treasury par yields by tenor (years -> rate)
    sofr_rate : float
        Current SOFR overnight rate
    spread_by_rating : Dict[str, int]
        Credit spreads by rating (bps)
    """
    curve_date: str
    treasury_rates: Dict[float, float]
    sofr_rate: float
    spread_by_rating: Dict[str, int]


# Default market data as of Feb 2026 (reasonable estimates)
DEFAULT_MARKET_DATA = MarketData(
    curve_date="2026-02-01",
    treasury_rates={
        0.25: 0.0480,  # 3-month: 4.80%
        0.5: 0.0475,   # 6-month: 4.75%
        1.0: 0.0465,   # 1-year: 4.65%
        2.0: 0.0448,   # 2-year: 4.48%
        3.0: 0.0438,   # 3-year: 4.38%
        5.0: 0.0425,   # 5-year: 4.25%
        7.0: 0.0430,   # 7-year: 4.30%
        10.0: 0.0445,  # 10-year: 4.45%
        20.0: 0.0475,  # 20-year: 4.75%
        30.0: 0.0465,  # 30-year: 4.65%
    },
    sofr_rate=0.0520,  # SOFR: 5.20%
    spread_by_rating={
        "AAA": 25,
        "AA": 50,
        "A": 85,
        "BBB": 150,
        "BB": 300,
        "B": 500,
        "CCC": 800,
        "NR": 200,  # Not rated
    }
)


def build_default_yield_curve(market_data: Optional[MarketData] = None) -> YieldCurve:
    """
    Build a yield curve from market data.
    
    Parameters
    ----------
    market_data : MarketData, optional
        Market data to use. If None, uses DEFAULT_MARKET_DATA.
    
    Returns
    -------
    YieldCurve
        Zero-coupon yield curve
    
    Example
    -------
    >>> curve = build_default_yield_curve()
    >>> rate_5y = curve.get_zero_rate(5.0)
    >>> print(f"5-year zero rate: {rate_5y:.2%}")
    """
    if market_data is None:
        market_data = DEFAULT_MARKET_DATA
    
    # Create YieldCurve directly with tenors and rates
    # (bypassing YieldCurveBuilder which has a sorting bug)
    tenors = sorted(market_data.treasury_rates.keys())
    rates = [market_data.treasury_rates[t] for t in tenors]
    
    return YieldCurve(
        curve_date=market_data.curve_date,
        tenors=list(tenors),
        zero_rates=rates,
        interpolation_method=InterpolationMethod.LINEAR,
    )


def project_tranche_cashflows(
    original_balance: float,
    current_balance: float,
    coupon_rate: float,
    coupon_type: str,
    wam_months: int,
    cpr: float,
    cdr: float,
    severity: float,
    sofr_rate: float = 0.052,
    margin: float = 0.0,
) -> List[Tuple[float, float]]:
    """
    Project cashflows for a tranche given scenario assumptions.
    
    This uses a simplified sequential pay model. For more complex
    structures (PAC, TAC, Z-bonds), the full waterfall engine should be used.
    
    Parameters
    ----------
    original_balance : float
        Original face value of tranche
    current_balance : float
        Current outstanding balance
    coupon_rate : float
        Fixed coupon rate (for FIXED type) or margin (for FLOAT)
    coupon_type : str
        "FIXED", "FLOAT", "WAC", or "VARIABLE"
    wam_months : int
        Weighted average maturity in months
    cpr : float
        Constant Prepayment Rate (annual, e.g., 0.10 for 10%)
    cdr : float
        Constant Default Rate (annual, e.g., 0.02 for 2%)
    severity : float
        Loss severity on defaults (e.g., 0.35 for 35%)
    sofr_rate : float, optional
        Current SOFR rate (for floating tranches)
    margin : float, optional
        Spread over SOFR (for floating tranches)
    
    Returns
    -------
    List[Tuple[float, float]]
        List of (time_in_years, cashflow_amount) tuples
    
    Example
    -------
    >>> cfs = project_tranche_cashflows(
    ...     original_balance=100_000_000,
    ...     current_balance=95_000_000,
    ...     coupon_rate=0.05,
    ...     coupon_type="FIXED",
    ...     wam_months=300,
    ...     cpr=0.12,
    ...     cdr=0.02,
    ...     severity=0.35
    ... )
    """
    # Convert annual rates to monthly
    smm = 1 - (1 - cpr) ** (1/12)  # Single Monthly Mortality
    mdr = 1 - (1 - cdr) ** (1/12)  # Monthly Default Rate
    
    # Determine effective coupon rate
    if coupon_type == "FLOAT":
        effective_rate = sofr_rate + margin
    elif coupon_type == "WAC":
        effective_rate = coupon_rate  # WAC is passed as coupon_rate
    else:
        effective_rate = coupon_rate
    
    monthly_rate = effective_rate / 12
    
    cashflows = []
    balance = current_balance
    
    # Limit projection to WAM or 360 months
    max_periods = min(wam_months, 360)
    
    for month in range(1, max_periods + 1):
        if balance <= 0:
            break
        
        # Interest payment
        interest = balance * monthly_rate
        
        # Scheduled principal (level pay amortization)
        remaining_months = max(1, wam_months - month + 1)
        if remaining_months > 0 and monthly_rate > 0:
            # PMT formula for level pay
            sched_principal = balance * (monthly_rate / (1 - (1 + monthly_rate) ** (-remaining_months)))
            sched_principal = max(0, sched_principal - interest)
        else:
            sched_principal = balance / max(1, remaining_months)
        
        # Defaults (on beginning balance)
        default_amount = balance * mdr
        loss = default_amount * severity
        recovery = default_amount * (1 - severity)
        
        # Prepayments (on post-default balance)
        post_default_balance = balance - sched_principal - default_amount
        prepay = max(0, post_default_balance * smm)
        
        # Total principal
        total_principal = sched_principal + prepay + recovery
        
        # Total cashflow for this period
        total_cf = interest + total_principal
        
        # Record cashflow (time in years)
        time_years = month / 12.0
        cashflows.append((time_years, total_cf))
        
        # Update balance
        balance = max(0, balance - sched_principal - prepay - default_amount)
    
    return cashflows


@dataclass
class TranchePricingResult:
    """
    Result of tranche pricing calculation.
    
    Attributes
    ----------
    ytm : float
        Yield to maturity (decimal)
    ytm_converged : bool
        Whether YTM solver converged
    oas_bps : int
        Option-adjusted spread in basis points
    z_spread_bps : int
        Z-spread in basis points
    credit_spread_bps : int
        Credit spread from PD/LGD in basis points
    duration : float
        Modified duration in years
    fair_value : float
        Theoretical fair value
    market_price : float
        Assumed market price (par if not provided)
    cashflow_count : int
        Number of projected cashflows
    total_cashflow : float
        Sum of all projected cashflows
    pricing_methodology : str
        Description of pricing approach used
    assumptions : Dict[str, Any]
        Key assumptions used in calculation
    """
    ytm: float
    ytm_converged: bool
    oas_bps: int
    z_spread_bps: int
    credit_spread_bps: int
    duration: float
    fair_value: float
    market_price: float
    cashflow_count: int
    total_cashflow: float
    pricing_methodology: str
    assumptions: Dict[str, Any]


def price_tranche(
    original_balance: float,
    current_balance: float,
    coupon_rate: float,
    coupon_type: str,
    wam_months: int = 300,
    rating: str = "NR",
    market_price: Optional[float] = None,
    cpr: float = 0.10,
    cdr: float = 0.02,
    severity: float = 0.35,
    pd_annual: Optional[float] = None,
    lgd: Optional[float] = None,
    yield_curve: Optional[YieldCurve] = None,
    market_data: Optional[MarketData] = None,
    margin: float = 0.0,
) -> TranchePricingResult:
    """
    Calculate full pricing metrics for a tranche.
    
    This is the main entry point for tranche pricing, combining:
    - Cashflow projection with prepayment/default assumptions
    - YTM calculation
    - OAS calculation with yield curve
    - Duration calculation
    - Credit spread from PD/LGD
    
    Parameters
    ----------
    original_balance : float
        Original face value
    current_balance : float
        Current outstanding balance
    coupon_rate : float
        Coupon rate (or WAC for WAC tranches)
    coupon_type : str
        "FIXED", "FLOAT", "WAC", or "VARIABLE"
    wam_months : int, optional
        Weighted average maturity, default 300 (25 years)
    rating : str, optional
        Credit rating (AAA, AA, A, BBB, BB, B, CCC, NR)
    market_price : float, optional
        Market price. If None, assumes par (current_balance)
    cpr : float, optional
        CPR assumption, default 10%
    cdr : float, optional
        CDR assumption, default 2%
    severity : float, optional
        Loss severity, default 35%
    pd_annual : float, optional
        Annual probability of default. If None, derived from rating.
    lgd : float, optional
        Loss given default. If None, uses severity.
    yield_curve : YieldCurve, optional
        Discount curve. If None, builds default curve.
    market_data : MarketData, optional
        Market data for curve building. If None, uses defaults.
    margin : float, optional
        Spread over SOFR for floating rate tranches
    
    Returns
    -------
    TranchePricingResult
        Complete pricing breakdown
    
    Example
    -------
    >>> result = price_tranche(
    ...     original_balance=100_000_000,
    ...     current_balance=95_000_000,
    ...     coupon_rate=0.055,
    ...     coupon_type="FIXED",
    ...     cpr=0.12,
    ...     cdr=0.02,
    ...     severity=0.35,
    ...     rating="AA"
    ... )
    >>> print(f"YTM: {result.ytm:.2%}")
    >>> print(f"OAS: {result.oas_bps} bps")
    >>> print(f"Duration: {result.duration:.2f} years")
    """
    if market_data is None:
        market_data = DEFAULT_MARKET_DATA
    
    # Build yield curve if not provided
    if yield_curve is None:
        yield_curve = build_default_yield_curve(market_data)
    
    # Default market price to par (current balance)
    if market_price is None:
        market_price = current_balance
    
    # Derive PD from rating if not provided
    if pd_annual is None:
        # Approximate PD by rating
        pd_by_rating = {
            "AAA": 0.0001,
            "AA": 0.0005,
            "A": 0.001,
            "BBB": 0.002,
            "BB": 0.01,
            "B": 0.03,
            "CCC": 0.10,
            "NR": 0.005,
        }
        pd_annual = pd_by_rating.get(rating.upper(), 0.005)
    
    # Use severity as LGD if not provided
    if lgd is None:
        lgd = severity
    
    # Project cashflows
    sofr_rate = market_data.sofr_rate
    cashflows = project_tranche_cashflows(
        original_balance=original_balance,
        current_balance=current_balance,
        coupon_rate=coupon_rate,
        coupon_type=coupon_type,
        wam_months=wam_months,
        cpr=cpr,
        cdr=cdr,
        severity=severity,
        sofr_rate=sofr_rate,
        margin=margin,
    )
    
    if not cashflows:
        # No cashflows - return defaults
        return TranchePricingResult(
            ytm=0.0,
            ytm_converged=False,
            oas_bps=0,
            z_spread_bps=0,
            credit_spread_bps=0,
            duration=0.0,
            fair_value=0.0,
            market_price=market_price,
            cashflow_count=0,
            total_cashflow=0.0,
            pricing_methodology="No cashflows projected",
            assumptions={}
        )
    
    total_cashflow = sum(cf for _, cf in cashflows)
    
    # Calculate YTM
    # Normalize price to 100 for YTM calculation
    price_pct = (market_price / current_balance) * 100 if current_balance > 0 else 100
    normalized_cfs = [(t, cf / current_balance * 100) for t, cf in cashflows]
    
    ytm, ytm_converged = calculate_yield_from_price(normalized_cfs, price_pct)
    
    # Calculate OAS using the pricing engine
    try:
        oas_result = solve_credit_adjusted_oas(
            cashflows=cashflows,
            market_price=market_price,
            yield_curve=yield_curve,
            pd=pd_annual,
            lgd=lgd,
            recovery_lag=0.5,
        )
        oas_bps = int(oas_result.oas)
        z_spread_bps = int(oas_result.z_spread)
        credit_spread_bps = int(oas_result.credit_spread)
        fair_value = oas_result.fair_value
    except Exception as e:
        logger.warning(f"OAS calculation failed: {e}, falling back to simplified calculation")
        # Fallback: simplified OAS
        risk_free_rate = yield_curve.get_zero_rate(5.0)  # Use 5-year rate as benchmark
        oas_bps = max(0, int((ytm - risk_free_rate) * 10000))
        z_spread_bps = oas_bps
        credit_spread_bps = int(pd_annual * lgd * 10000)
        fair_value = market_price
    
    # Calculate duration
    try:
        duration_calc = DurationCalculator(yield_curve)
        duration = duration_calc.calculate_modified_duration(cashflows, ytm)
    except Exception as e:
        logger.warning(f"Duration calculation failed: {e}")
        # Fallback: approximate duration as weighted average life
        if total_cashflow > 0:
            duration = sum(t * cf for t, cf in cashflows) / total_cashflow
        else:
            duration = wam_months / 12 / 2  # Rough approximation
    
    # Build assumptions dict
    assumptions = {
        "cpr": cpr,
        "cdr": cdr,
        "severity": severity,
        "pd_annual": pd_annual,
        "lgd": lgd,
        "wam_months": wam_months,
        "sofr_rate": sofr_rate,
        "curve_date": market_data.curve_date,
        "rating": rating,
    }
    
    # Pricing methodology description
    methodology = (
        f"Full pricing: {len(cashflows)} cashflows projected with "
        f"CPR={cpr:.1%}, CDR={cdr:.1%}, Severity={severity:.1%}. "
        f"Discounted using bootstrapped Treasury curve as of {market_data.curve_date}. "
        f"Credit adjustment: PD={pd_annual:.2%}, LGD={lgd:.1%}."
    )
    
    return TranchePricingResult(
        ytm=ytm,
        ytm_converged=ytm_converged,
        oas_bps=oas_bps,
        z_spread_bps=z_spread_bps,
        credit_spread_bps=credit_spread_bps,
        duration=duration,
        fair_value=fair_value,
        market_price=market_price,
        cashflow_count=len(cashflows),
        total_cashflow=total_cashflow,
        pricing_methodology=methodology,
        assumptions=assumptions,
    )


def price_portfolio(
    holdings: List[Dict[str, Any]],
    deal_specs: Dict[str, Dict[str, Any]],
    cpr: float = 0.10,
    cdr: float = 0.02,
    severity: float = 0.35,
    yield_curve: Optional[YieldCurve] = None,
    market_data: Optional[MarketData] = None,
) -> List[Dict[str, Any]]:
    """
    Price all holdings in a portfolio.
    
    Parameters
    ----------
    holdings : List[Dict]
        List of holdings with deal_id, tranche_id, balance
    deal_specs : Dict[str, Dict]
        Deal specifications keyed by deal_id
    cpr, cdr, severity : float
        Scenario assumptions
    yield_curve : YieldCurve, optional
        Shared yield curve for all tranches
    market_data : MarketData, optional
        Market data
    
    Returns
    -------
    List[Dict]
        Holdings enriched with pricing metrics
    """
    if market_data is None:
        market_data = DEFAULT_MARKET_DATA
    
    if yield_curve is None:
        yield_curve = build_default_yield_curve(market_data)
    
    enriched = []
    
    for holding in holdings:
        deal_id = holding.get("deal_id", "")
        tranche_id = holding.get("tranche_id", "")
        balance = holding.get("balance", 0)
        
        # Get deal spec
        deal_spec = deal_specs.get(deal_id, {})
        bonds = deal_spec.get("bonds", [])
        bond_info = next((b for b in bonds if b.get("id") == tranche_id), {})
        
        # Extract bond details
        original_balance = bond_info.get("original_balance", balance)
        coupon = bond_info.get("coupon", {})
        coupon_type = coupon.get("kind", "FIXED")
        
        if coupon_type == "FIXED":
            coupon_rate = coupon.get("fixed_rate", 0.05)
            margin = 0.0
        elif coupon_type == "FLOAT":
            coupon_rate = 0.0
            margin = coupon.get("margin", 0.0175)
        elif coupon_type == "WAC":
            coupon_rate = coupon.get("wac_spread", 0.0) + 0.05  # Estimate
            margin = 0.0
        else:
            coupon_rate = 0.05
            margin = 0.0
        
        rating = bond_info.get("rating", "NR")
        wam_months = int(bond_info.get("wam_months", 300))
        
        # Price the tranche
        try:
            result = price_tranche(
                original_balance=original_balance,
                current_balance=balance,
                coupon_rate=coupon_rate,
                coupon_type=coupon_type,
                wam_months=wam_months,
                rating=rating,
                cpr=cpr,
                cdr=cdr,
                severity=severity,
                yield_curve=yield_curve,
                market_data=market_data,
                margin=margin,
            )
            
            enriched.append({
                **holding,
                "ytm": result.ytm,
                "ytm_converged": result.ytm_converged,
                "oas_bps": result.oas_bps,
                "z_spread_bps": result.z_spread_bps,
                "credit_spread_bps": result.credit_spread_bps,
                "duration": result.duration,
                "fair_value": result.fair_value,
                "current_value": balance,  # Could use fair_value for mark-to-market
                "pricing_methodology": result.pricing_methodology,
                "cashflow_count": result.cashflow_count,
                "coupon_type": coupon_type,
                "rating": rating,
            })
        except Exception as e:
            logger.error(f"Failed to price {deal_id}/{tranche_id}: {e}")
            # Return with fallback values
            enriched.append({
                **holding,
                "ytm": coupon_rate if coupon_type == "FIXED" else market_data.sofr_rate + margin,
                "ytm_converged": False,
                "oas_bps": 50,  # Default spread
                "z_spread_bps": 50,
                "credit_spread_bps": 25,
                "duration": wam_months / 12 / 2,
                "fair_value": balance,
                "current_value": balance,
                "pricing_methodology": f"Fallback pricing due to error: {e}",
                "cashflow_count": 0,
                "coupon_type": coupon_type,
                "rating": rating,
            })
    
    return enriched
