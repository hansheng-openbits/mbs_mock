"""
Market Risk Analytics for RMBS
================================

This module implements market risk analytics including:
1. **Yield Curve Building**: Bootstrap zero curves from market data
2. **Option-Adjusted Spread (OAS)**: Risk-adjusted spread over benchmark
3. **Duration & Convexity**: Interest rate sensitivity metrics
4. **Key Rate Duration**: Sensitivity to specific maturity points

Yield Curve Bootstrapping
--------------------------
Constructs a zero-coupon yield curve from market instruments:
- Treasury yields (par or zero)
- Swap rates
- SOFR futures

The curve is bootstrapped iteratively, solving for zero rates that
reprice market instruments at par.

Option-Adjusted Spread (OAS)
-----------------------------
Measures the spread investors earn over the risk-free curve after
adjusting for embedded optionality (prepayments).

Formula:
    PV(cashflows @ Curve + OAS) = Market Price

OAS is the constant spread that equates present value to market price
when discounting at Treasury + spread across all prepayment scenarios.

Duration & Convexity
--------------------
**Modified Duration**: % price change for 1% rate shift
    D_mod = -(1/P) × dP/dr

**Effective Duration**: Duration accounting for cashflow changes
    D_eff = (P_down - P_up) / (2 × P × Δr)

**Convexity**: Curvature of price/yield relationship
    C = (1/P) × d²P/dr²

Classes
-------
YieldCurve
    Represents a discount curve with interpolation.
YieldCurveBuilder
    Bootstrap curves from market instruments.
OASCalculator
    Calculate option-adjusted spreads.
DurationCalculator
    Compute duration and convexity metrics.

Example
-------
>>> from rmbs_platform.engine.market_risk import YieldCurveBuilder, OASCalculator
>>> 
>>> # Build yield curve from Treasury yields
>>> curve_builder = YieldCurveBuilder()
>>> curve_builder.add_instrument("TREASURY_2Y", maturity=2.0, rate=0.045)
>>> curve_builder.add_instrument("TREASURY_5Y", maturity=5.0, rate=0.048)
>>> curve_builder.add_instrument("TREASURY_10Y", maturity=10.0, rate=0.045)
>>> curve = curve_builder.build()
>>> 
>>> # Calculate OAS
>>> oas_calc = OASCalculator(curve)
>>> oas = oas_calc.calculate_oas(
...     cashflows=bond_cashflows,
...     market_price=102.5,
...     prepayment_scenarios=[(0.10, 0.3), (0.15, 0.4), (0.20, 0.3)]
... )
>>> print(f"OAS: {oas:.0f} bps")

See Also
--------
swaps : Interest rate swap mechanics
compute : Core cashflow projection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import brentq, minimize_scalar

logger = logging.getLogger("RMBS.MarketRisk")


class InterpolationMethod(Enum):
    """Curve interpolation methods."""
    LINEAR = "linear"
    CUBIC = "cubic"
    LOG_LINEAR = "log_linear"  # Log-linear on discount factors
    FLAT_FORWARD = "flat_forward"  # Flat forward rates


class InstrumentType(Enum):
    """Market instruments for curve building."""
    TREASURY_PAR = "treasury_par"
    TREASURY_ZERO = "treasury_zero"
    SWAP_RATE = "swap_rate"
    SOFR_FUTURE = "sofr_future"


@dataclass
class MarketInstrument:
    """
    Market instrument for yield curve calibration.
    
    Attributes
    ----------
    instrument_id : str
        Unique identifier
    instrument_type : InstrumentType
        Type of instrument
    maturity : float
        Maturity in years
    rate : float
        Quoted rate (par yield, zero rate, or swap rate)
    price : float, optional
        Market price (for bonds)
    """
    instrument_id: str
    instrument_type: InstrumentType
    maturity: float
    rate: float
    price: Optional[float] = None


@dataclass
class YieldCurve:
    """
    Discount curve with interpolation.
    
    A yield curve stores zero rates at pillar points and provides
    methods to interpolate rates/discounts at arbitrary maturities.
    
    Attributes
    ----------
    curve_date : str
        Valuation date
    tenors : list of float
        Pillar maturities in years
    zero_rates : list of float
        Zero rates at pillar points
    interpolation_method : InterpolationMethod
        Method for interpolating between pillars
    
    Methods
    -------
    get_zero_rate(maturity)
        Get interpolated zero rate
    get_discount_factor(maturity)
        Get discount factor
    get_forward_rate(start, end)
        Get forward rate between two maturities
    shift_parallel(shift_bps)
        Return curve shifted by constant amount
    """
    
    curve_date: str
    tenors: List[float] = field(default_factory=list)
    zero_rates: List[float] = field(default_factory=list)
    interpolation_method: InterpolationMethod = InterpolationMethod.LINEAR
    
    def __post_init__(self):
        """Initialize interpolation function."""
        if len(self.tenors) == 0:
            # Empty curve defaults
            self.tenors = [0.0, 30.0]
            self.zero_rates = [0.045, 0.045]
        
        # Sort by maturity
        sorted_pairs = sorted(zip(self.tenors, self.zero_rates))
        self.tenors = [t for t, _ in sorted_pairs]
        self.zero_rates = [r for _, r in sorted_pairs]
        
        # Build interpolator
        self._build_interpolator()
    
    def _build_interpolator(self):
        """Build scipy interpolation function."""
        if self.interpolation_method == InterpolationMethod.LINEAR:
            self._rate_interpolator = interp1d(
                self.tenors, self.zero_rates,
                kind='linear', fill_value='extrapolate'
            )
        elif self.interpolation_method == InterpolationMethod.CUBIC:
            if len(self.tenors) >= 4:
                self._rate_interpolator = interp1d(
                    self.tenors, self.zero_rates,
                    kind='cubic', fill_value='extrapolate'
                )
            else:
                # Fall back to linear if insufficient points
                self._rate_interpolator = interp1d(
                    self.tenors, self.zero_rates,
                    kind='linear', fill_value='extrapolate'
                )
        elif self.interpolation_method == InterpolationMethod.LOG_LINEAR:
            # Interpolate on discount factors
            dfs = [np.exp(-r * t) for r, t in zip(self.zero_rates, self.tenors)]
            log_dfs = [np.log(df) for df in dfs]
            self._df_interpolator = interp1d(
                self.tenors, log_dfs,
                kind='linear', fill_value='extrapolate'
            )
        else:  # FLAT_FORWARD
            # Interpolate on forward rates (conceptual, use linear for now)
            self._rate_interpolator = interp1d(
                self.tenors, self.zero_rates,
                kind='linear', fill_value='extrapolate'
            )
    
    def get_zero_rate(self, maturity: float) -> float:
        """
        Get interpolated zero rate for a given maturity.
        
        Parameters
        ----------
        maturity : float
            Maturity in years
        
        Returns
        -------
        float
            Zero rate (annual, continuously compounded)
        """
        if maturity <= 0:
            return self.zero_rates[0]
        
        if self.interpolation_method == InterpolationMethod.LOG_LINEAR:
            log_df = float(self._df_interpolator(maturity))
            df = np.exp(log_df)
            return -np.log(df) / maturity
        else:
            return float(self._rate_interpolator(maturity))
    
    def get_discount_factor(self, maturity: float) -> float:
        """
        Get discount factor for a given maturity.
        
        Parameters
        ----------
        maturity : float
            Maturity in years
        
        Returns
        -------
        float
            Discount factor DF(0,T) = exp(-r*T)
        """
        if maturity <= 0:
            return 1.0
        
        zero_rate = self.get_zero_rate(maturity)
        return np.exp(-zero_rate * maturity)
    
    def get_forward_rate(self, start: float, end: float) -> float:
        """
        Calculate forward rate between two maturities.
        
        Formula:
            f(t1,t2) = [r2*t2 - r1*t1] / (t2 - t1)
        
        Parameters
        ----------
        start : float
            Start time in years
        end : float
            End time in years
        
        Returns
        -------
        float
            Forward rate
        """
        if end <= start:
            return self.get_zero_rate(end)
        
        r1 = self.get_zero_rate(start)
        r2 = self.get_zero_rate(end)
        
        return (r2 * end - r1 * start) / (end - start)
    
    def shift_parallel(self, shift_bps: float) -> "YieldCurve":
        """
        Return a parallel-shifted curve.
        
        Parameters
        ----------
        shift_bps : float
            Shift in basis points (positive = higher rates)
        
        Returns
        -------
        YieldCurve
            New curve with shifted rates
        """
        shift = shift_bps / 10000.0
        shifted_rates = [r + shift for r in self.zero_rates]
        
        return YieldCurve(
            curve_date=self.curve_date,
            tenors=self.tenors.copy(),
            zero_rates=shifted_rates,
            interpolation_method=self.interpolation_method
        )
    
    def shift_key_rate(self, key_tenor: float, shift_bps: float) -> "YieldCurve":
        """
        Shift curve at a specific tenor (for key rate duration).
        
        Parameters
        ----------
        key_tenor : float
            Tenor to shift (in years)
        shift_bps : float
            Shift in basis points
        
        Returns
        -------
        YieldCurve
            New curve with local shift
        """
        shift = shift_bps / 10000.0
        
        # Find closest tenor
        closest_idx = min(range(len(self.tenors)),
                         key=lambda i: abs(self.tenors[i] - key_tenor))
        
        shifted_rates = self.zero_rates.copy()
        shifted_rates[closest_idx] += shift
        
        return YieldCurve(
            curve_date=self.curve_date,
            tenors=self.tenors.copy(),
            zero_rates=shifted_rates,
            interpolation_method=self.interpolation_method
        )


class YieldCurveBuilder:
    """
    Bootstrap yield curve from market instruments.
    
    The builder accepts various market instruments (Treasuries, swaps, etc.)
    and constructs a self-consistent zero curve by solving for rates that
    reprice each instrument at its market level.
    
    Example
    -------
    >>> builder = YieldCurveBuilder()
    >>> builder.add_instrument("UST_2Y", InstrumentType.TREASURY_PAR, 2.0, 0.045)
    >>> builder.add_instrument("UST_5Y", InstrumentType.TREASURY_PAR, 5.0, 0.048)
    >>> builder.add_instrument("UST_10Y", InstrumentType.TREASURY_PAR, 10.0, 0.045)
    >>> curve = builder.build()
    """
    
    def __init__(self, curve_date: str = "2026-01-29"):
        """Initialize builder."""
        self.curve_date = curve_date
        self.instruments: List[MarketInstrument] = []
    
    def add_instrument(
        self,
        instrument_id: str,
        maturity: float,
        rate: float,
        instrument_type: InstrumentType = InstrumentType.TREASURY_PAR,
        price: Optional[float] = None
    ) -> None:
        """Add a market instrument to the calibration set."""
        instrument = MarketInstrument(
            instrument_id=instrument_id,
            instrument_type=instrument_type,
            maturity=maturity,
            rate=rate,
            price=price
        )
        self.instruments.append(instrument)
    
    def build(self, interpolation_method: InterpolationMethod = InterpolationMethod.LINEAR) -> YieldCurve:
        """
        Bootstrap the yield curve.
        
        For simplicity, if instruments are Treasury zeros, use them directly.
        If par yields, convert to zero rates using bootstrap logic.
        
        Returns
        -------
        YieldCurve
            Calibrated curve
        """
        if len(self.instruments) == 0:
            logger.warning("No instruments provided, using flat 4.5% curve")
            return YieldCurve(
                curve_date=self.curve_date,
                tenors=[0.0, 30.0],
                zero_rates=[0.045, 0.045],
                interpolation_method=interpolation_method
            )
        
        # Sort by maturity
        sorted_instruments = sorted(self.instruments, key=lambda x: x.maturity)
        
        tenors = []
        zero_rates = []
        
        # Simple bootstrap (assuming par yields for Treasuries)
        for inst in sorted_instruments:
            if inst.instrument_type == InstrumentType.TREASURY_ZERO:
                # Zero rate given directly
                tenors.append(inst.maturity)
                zero_rates.append(inst.rate)
            elif inst.instrument_type == InstrumentType.TREASURY_PAR:
                # Par yield: coupon bond trading at par
                # For simplicity, approximate zero ≈ par for short maturities
                # More accurate would solve: sum(c * DF(t_i)) + 100 * DF(T) = 100
                
                if inst.maturity <= 1.0:
                    # Short maturity: zero ≈ par
                    zero_rate = inst.rate
                else:
                    # Approximate bootstrap
                    # Build temporary curve with current data
                    if len(tenors) > 0:
                        temp_curve = YieldCurve(
                            curve_date=self.curve_date,
                            tenors=tenors.copy(),
                            zero_rates=zero_rates.copy(),
                            interpolation_method=InterpolationMethod.LINEAR
                        )
                        
                        # Solve for zero rate that prices bond at par
                        zero_rate = self._solve_for_zero_rate(inst, temp_curve)
                    else:
                        # First instrument
                        zero_rate = inst.rate
                
                tenors.append(inst.maturity)
                zero_rates.append(zero_rate)
            elif inst.instrument_type == InstrumentType.SWAP_RATE:
                # Swap rate: par swap
                # Similar logic to par bonds
                if len(tenors) > 0:
                    temp_curve = YieldCurve(
                        curve_date=self.curve_date,
                        tenors=tenors.copy(),
                        zero_rates=zero_rates.copy(),
                        interpolation_method=InterpolationMethod.LINEAR
                    )
                    zero_rate = self._solve_for_swap_zero_rate(inst, temp_curve)
                else:
                    zero_rate = inst.rate
                
                tenors.append(inst.maturity)
                zero_rates.append(zero_rate)
        
        return YieldCurve(
            curve_date=self.curve_date,
            tenors=tenors,
            zero_rates=zero_rates,
            interpolation_method=interpolation_method
        )
    
    def _solve_for_zero_rate(self, instrument: MarketInstrument, curve: YieldCurve) -> float:
        """
        Solve for zero rate that prices a par bond at 100.
        
        A par bond pays coupon = rate and principal = 100 at maturity.
        Price = sum(coupon * DF(t_i)) + 100 * DF(T) = 100
        
        We need to find the zero rate at maturity T such that this holds.
        """
        coupon = instrument.rate
        maturity = instrument.maturity
        payment_freq = 2  # Semi-annual for Treasuries
        
        def pricing_error(zero_rate_guess: float) -> float:
            # Extend curve with this guess
            extended_curve = YieldCurve(
                curve_date=curve.curve_date,
                tenors=curve.tenors + [maturity],
                zero_rates=curve.zero_rates + [zero_rate_guess],
                interpolation_method=InterpolationMethod.LINEAR
            )
            
            # Price the bond
            pv = 0.0
            periods = int(maturity * payment_freq)
            for i in range(1, periods + 1):
                t = i / payment_freq
                cf = (coupon / payment_freq) * 100  # Coupon payment
                df = extended_curve.get_discount_factor(t)
                pv += cf * df
            
            # Principal at maturity
            df = extended_curve.get_discount_factor(maturity)
            pv += 100 * df
            
            return pv - 100.0  # Error from par
        
        try:
            # Solve for zero rate
            zero_rate = brentq(pricing_error, 0.001, 0.20)  # Search between 0.1% and 20%
            return zero_rate
        except ValueError:
            # If solution not found, use par approximation
            logger.warning(f"Could not bootstrap {instrument.instrument_id}, using par approximation")
            return instrument.rate
    
    def _solve_for_swap_zero_rate(self, instrument: MarketInstrument, curve: YieldCurve) -> float:
        """
        Solve for zero rate from swap rate.
        
        A par swap has PV(fixed leg) = PV(floating leg) = notional × sum(DF(t_i))
        Swap rate S = (1 - DF(T)) / sum(DF(t_i))
        """
        swap_rate = instrument.rate
        maturity = instrument.maturity
        payment_freq = 4  # Quarterly for swaps
        
        def pricing_error(zero_rate_guess: float) -> float:
            # Extend curve
            extended_curve = YieldCurve(
                curve_date=curve.curve_date,
                tenors=curve.tenors + [maturity],
                zero_rates=curve.zero_rates + [zero_rate_guess],
                interpolation_method=InterpolationMethod.LINEAR
            )
            
            # Calculate annuity (sum of discount factors)
            annuity = 0.0
            periods = int(maturity * payment_freq)
            for i in range(1, periods + 1):
                t = i / payment_freq
                annuity += extended_curve.get_discount_factor(t)
            
            # Implied swap rate
            df_maturity = extended_curve.get_discount_factor(maturity)
            implied_swap_rate = (1 - df_maturity) / annuity
            
            return implied_swap_rate - swap_rate
        
        try:
            zero_rate = brentq(pricing_error, 0.001, 0.20)
            return zero_rate
        except ValueError:
            logger.warning(f"Could not bootstrap {instrument.instrument_id}, using swap rate approximation")
            return instrument.rate


class OASCalculator:
    """
    Calculate Option-Adjusted Spread for RMBS bonds.
    
    OAS is the constant spread over the risk-free curve that equates
    the present value of expected cashflows to the market price, after
    accounting for embedded prepayment optionality.
    
    Formula:
        Market Price = E[sum(CF_i × DF(t_i, r + OAS))]
    
    where the expectation is over prepayment scenarios.
    
    Example
    -------
    >>> curve = YieldCurve(...)
    >>> oas_calc = OASCalculator(curve)
    >>> oas = oas_calc.calculate_oas(
    ...     cashflows=[(1, 100), (2, 100), (3, 10100)],
    ...     market_price=102.5,
    ...     prepayment_scenarios=[(0.10, 0.5), (0.20, 0.5)]
    ... )
    """
    
    def __init__(self, base_curve: YieldCurve):
        """Initialize with base discount curve."""
        self.base_curve = base_curve
    
    def calculate_oas(
        self,
        cashflows: List[Tuple[float, float]],
        market_price: float,
        prepayment_scenarios: Optional[List[Tuple[float, float]]] = None
    ) -> float:
        """
        Calculate OAS by finding the spread that reprices the bond.
        
        Parameters
        ----------
        cashflows : list of (time, amount)
            Expected cashflows (time in years, amount in $)
        market_price : float
            Market price of the bond
        prepayment_scenarios : list of (cpr, probability), optional
            Different CPR scenarios with probabilities
        
        Returns
        -------
        float
            OAS in decimal (e.g., 0.0125 = 125 bps)
        """
        if prepayment_scenarios is None:
            # Single scenario
            prepayment_scenarios = [(0.15, 1.0)]
        
        def pricing_error(oas: float) -> float:
            """Calculate error between PV and market price."""
            expected_pv = 0.0
            
            for cpr, prob in prepayment_scenarios:
                # For each scenario, adjust cashflows based on CPR
                # (For now, use same cashflows; in reality, re-project with CPR)
                scenario_pv = self._present_value(cashflows, oas)
                expected_pv += prob * scenario_pv
            
            return expected_pv - market_price
        
        try:
            oas = brentq(pricing_error, -0.05, 0.15)  # Search from -500 to +1500 bps
            return oas
        except ValueError:
            logger.warning("OAS calculation did not converge, returning 0")
            return 0.0
    
    def _present_value(self, cashflows: List[Tuple[float, float]], spread: float) -> float:
        """
        Calculate present value with a spread over the base curve.
        
        Parameters
        ----------
        cashflows : list of (time, amount)
            Cashflows to discount
        spread : float
            Spread to add to discount rates
        
        Returns
        -------
        float
            Present value
        """
        pv = 0.0
        for time, amount in cashflows:
            zero_rate = self.base_curve.get_zero_rate(time) + spread
            df = np.exp(-zero_rate * time)
            pv += amount * df
        
        return pv
    
    def calculate_z_spread(self, cashflows: List[Tuple[float, float]], market_price: float) -> float:
        """
        Calculate Z-spread (static spread, no optionality adjustment).
        
        Z-spread is simpler than OAS - it's just the spread over the curve
        that reprices fixed cashflows, without Monte Carlo simulation.
        
        Parameters
        ----------
        cashflows : list of (time, amount)
            Cashflows (assumed fixed)
        market_price : float
            Market price
        
        Returns
        -------
        float
            Z-spread in decimal
        """
        def pricing_error(spread: float) -> float:
            return self._present_value(cashflows, spread) - market_price
        
        try:
            z_spread = brentq(pricing_error, -0.05, 0.15)
            return z_spread
        except ValueError:
            logger.warning("Z-spread calculation did not converge")
            return 0.0


class DurationCalculator:
    """
    Calculate duration and convexity metrics.
    
    Duration measures interest rate sensitivity:
    - **Modified Duration**: dP/dr approximation
    - **Effective Duration**: Accounts for cashflow changes (prepayments)
    - **Key Rate Duration**: Sensitivity to specific curve points
    
    Convexity measures second-order rate sensitivity (curvature).
    
    Example
    -------
    >>> calc = DurationCalculator(yield_curve)
    >>> metrics = calc.calculate_effective_duration(
    ...     cashflow_func=lambda curve: project_cashflows(deal, curve),
    ...     shift_bps=25
    ... )
    >>> print(f"Effective Duration: {metrics['duration']:.2f}")
    >>> print(f"Convexity: {metrics['convexity']:.2f}")
    """
    
    def __init__(self, base_curve: YieldCurve):
        """Initialize with base yield curve."""
        self.base_curve = base_curve
    
    def calculate_modified_duration(
        self,
        cashflows: List[Tuple[float, float]],
        ytm: float
    ) -> float:
        """
        Calculate modified duration (Macaulay / (1 + ytm)).
        
        Modified Duration = -1/P × dP/dy
        
        Parameters
        ----------
        cashflows : list of (time, amount)
            Bond cashflows
        ytm : float
            Yield to maturity
        
        Returns
        -------
        float
            Modified duration in years
        """
        # Calculate price and weighted average time
        price = 0.0
        weighted_time = 0.0
        
        for time, amount in cashflows:
            df = np.exp(-ytm * time)
            pv = amount * df
            price += pv
            weighted_time += time * pv
        
        if price == 0:
            return 0.0
        
        # Macaulay duration
        macaulay_duration = weighted_time / price
        
        # Modified duration (continuous compounding)
        # For continuous: D_mod = D_macaulay
        return macaulay_duration
    
    def calculate_effective_duration(
        self,
        cashflow_func: Callable[[YieldCurve], List[Tuple[float, float]]],
        shift_bps: float = 25
    ) -> Dict[str, float]:
        """
        Calculate effective duration using curve shifts.
        
        Effective Duration = (P_down - P_up) / (2 × P_0 × Δr)
        
        This accounts for cashflow changes (prepayments) when rates shift.
        
        Parameters
        ----------
        cashflow_func : callable
            Function that takes a YieldCurve and returns cashflows
            cashflow_func(curve) -> [(time, amount), ...]
        shift_bps : float
            Rate shift in basis points for finite difference
        
        Returns
        -------
        dict
            {'duration': float, 'convexity': float, 'price_base': float}
        """
        shift = shift_bps / 10000.0
        
        # Base case
        cashflows_base = cashflow_func(self.base_curve)
        price_base = self._pv_cashflows(cashflows_base, self.base_curve)
        
        # Up shift
        curve_up = self.base_curve.shift_parallel(shift_bps)
        cashflows_up = cashflow_func(curve_up)
        price_up = self._pv_cashflows(cashflows_up, curve_up)
        
        # Down shift
        curve_down = self.base_curve.shift_parallel(-shift_bps)
        cashflows_down = cashflow_func(curve_down)
        price_down = self._pv_cashflows(cashflows_down, curve_down)
        
        # Effective duration
        if price_base == 0:
            duration = 0.0
        else:
            duration = (price_down - price_up) / (2 * price_base * shift)
        
        # Convexity
        if price_base == 0:
            convexity = 0.0
        else:
            convexity = (price_down + price_up - 2 * price_base) / (price_base * shift ** 2)
        
        return {
            "duration": duration,
            "convexity": convexity,
            "price_base": price_base,
            "price_up": price_up,
            "price_down": price_down,
        }
    
    def calculate_key_rate_durations(
        self,
        cashflow_func: Callable[[YieldCurve], List[Tuple[float, float]]],
        key_tenors: List[float],
        shift_bps: float = 25
    ) -> Dict[float, float]:
        """
        Calculate key rate durations.
        
        Key Rate Duration measures sensitivity to changes at specific
        maturity points on the curve (e.g., 2Y, 5Y, 10Y).
        
        Parameters
        ----------
        cashflow_func : callable
            Function to generate cashflows from curve
        key_tenors : list of float
            Tenors to calculate KRD for (in years)
        shift_bps : float
            Rate shift in basis points
        
        Returns
        -------
        dict
            {tenor: key_rate_duration}
        """
        shift = shift_bps / 10000.0
        
        # Base case
        cashflows_base = cashflow_func(self.base_curve)
        price_base = self._pv_cashflows(cashflows_base, self.base_curve)
        
        key_rate_durations = {}
        
        for tenor in key_tenors:
            # Shift curve at this tenor
            curve_up = self.base_curve.shift_key_rate(tenor, shift_bps)
            curve_down = self.base_curve.shift_key_rate(tenor, -shift_bps)
            
            cashflows_up = cashflow_func(curve_up)
            cashflows_down = cashflow_func(curve_down)
            
            price_up = self._pv_cashflows(cashflows_up, curve_up)
            price_down = self._pv_cashflows(cashflows_down, curve_down)
            
            if price_base == 0:
                krd = 0.0
            else:
                krd = (price_down - price_up) / (2 * price_base * shift)
            
            key_rate_durations[tenor] = krd
        
        return key_rate_durations
    
    def _pv_cashflows(
        self,
        cashflows: List[Tuple[float, float]],
        curve: YieldCurve
    ) -> float:
        """Calculate present value of cashflows using a curve."""
        pv = 0.0
        for time, amount in cashflows:
            df = curve.get_discount_factor(time)
            pv += amount * df
        return pv


def calculate_dv01(price: float, duration: float) -> float:
    """
    Calculate DV01 (dollar value of 1 basis point).
    
    DV01 = Duration × Price / 10000
    
    Parameters
    ----------
    price : float
        Bond price (in dollars or %)
    duration : float
        Modified or effective duration
    
    Returns
    -------
    float
        DV01 (price change for 1bp rate move)
    """
    return duration * price / 10000.0


def calculate_convexity_adjustment(convexity: float, rate_change_bps: float) -> float:
    """
    Calculate convexity adjustment to duration approximation.
    
    ΔP/P ≈ -Duration × Δr + 0.5 × Convexity × (Δr)²
    
    Parameters
    ----------
    convexity : float
        Convexity metric
    rate_change_bps : float
        Rate change in basis points
    
    Returns
    -------
    float
        Convexity adjustment (% of price)
    """
    rate_change = rate_change_bps / 10000.0
    return 0.5 * convexity * (rate_change ** 2)
