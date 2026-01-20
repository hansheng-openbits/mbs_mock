"""
Multi-Currency Support Module for RMBS Engine.
==============================================

This module provides comprehensive multi-currency support for international
RMBS transactions, including:

- Currency definitions with ISO 4217 codes and conventions
- Real-time and historical exchange rate management
- FX exposure calculation and hedging support
- Currency basis swap pricing
- Cross-currency cashflow conversion

Industry Context
----------------
International RMBS deals (e.g., Euro-denominated deals backed by USD mortgages,
or GBP deals with EUR collateral) require sophisticated currency handling:

1. **Denomination Currency**: The currency in which bonds are issued
2. **Collateral Currency**: The currency of underlying loan payments
3. **Hedging Currency**: Currencies used in FX hedges (swaps, forwards)

Key conventions follow market standards:
- Day count conventions per currency (ACT/360 for USD, ACT/365 for GBP)
- Settlement conventions (T+2 for most majors)
- Spot rate quotation conventions (USD/XXX vs XXX/USD)

References
----------
- ISO 4217 Currency Codes
- ISDA FX Definitions
- BIS Triennial Survey conventions

Examples
--------
>>> from rmbs_platform.engine.currency import (
...     Currency, ExchangeRateProvider, CurrencyConverter
... )
>>> 
>>> # Define currencies
>>> usd = Currency.USD
>>> eur = Currency.EUR
>>> 
>>> # Get exchange rate
>>> provider = ExchangeRateProvider()
>>> rate = provider.get_spot_rate(usd, eur)
>>> 
>>> # Convert cashflows
>>> converter = CurrencyConverter(provider)
>>> eur_amount = converter.convert(1_000_000, usd, eur)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


# =============================================================================
# Currency Definitions
# =============================================================================

class Currency(str, Enum):
    """
    ISO 4217 currency codes with market conventions.
    
    This enum defines currencies commonly used in structured finance,
    including their standard conventions for day counts, settlement,
    and quotation.
    
    Attributes
    ----------
    USD : str
        United States Dollar - primary reserve currency
    EUR : str
        Euro - Eurozone common currency
    GBP : str
        British Pound Sterling
    JPY : str
        Japanese Yen
    CHF : str
        Swiss Franc
    AUD : str
        Australian Dollar
    CAD : str
        Canadian Dollar
    CNY : str
        Chinese Yuan Renminbi
    HKD : str
        Hong Kong Dollar
    SGD : str
        Singapore Dollar
    
    Examples
    --------
    >>> Currency.USD.value
    'USD'
    >>> Currency.EUR in [Currency.USD, Currency.EUR]
    True
    """
    
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CHF = "CHF"
    AUD = "AUD"
    CAD = "CAD"
    CNY = "CNY"
    HKD = "HKD"
    SGD = "SGD"
    MXN = "MXN"
    BRL = "BRL"
    KRW = "KRW"
    INR = "INR"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"
    NZD = "NZD"
    ZAR = "ZAR"
    PLN = "PLN"


@dataclass(frozen=True)
class CurrencySpec:
    """
    Currency specification with market conventions.
    
    This dataclass captures the essential conventions for each currency
    that affect calculations in structured finance.
    
    Parameters
    ----------
    code : Currency
        ISO 4217 currency code
    name : str
        Full currency name
    symbol : str
        Currency symbol (e.g., '$', '€', '£')
    decimal_places : int
        Standard decimal places (2 for most, 0 for JPY/KRW)
    day_count : str
        Standard day count convention for money markets
    settlement_days : int
        Standard settlement period (T+N)
    is_quote_currency : bool
        True if typically quoted as XXX/USD (vs USD/XXX)
    calendar : str
        Holiday calendar identifier
    
    Examples
    --------
    >>> usd_spec = CURRENCY_SPECS[Currency.USD]
    >>> usd_spec.decimal_places
    2
    >>> usd_spec.day_count
    'ACT/360'
    """
    
    code: Currency
    name: str
    symbol: str
    decimal_places: int = 2
    day_count: str = "ACT/360"
    settlement_days: int = 2
    is_quote_currency: bool = False
    calendar: str = "TARGET"
    
    def round_amount(self, amount: float) -> Decimal:
        """
        Round amount to currency's standard precision.
        
        Parameters
        ----------
        amount : float
            Amount to round
            
        Returns
        -------
        Decimal
            Rounded amount with proper precision
        """
        quantize_str = f"0.{'0' * self.decimal_places}" if self.decimal_places > 0 else "1"
        return Decimal(str(amount)).quantize(
            Decimal(quantize_str), 
            rounding=ROUND_HALF_UP
        )


# Standard currency specifications following market conventions
CURRENCY_SPECS: Dict[Currency, CurrencySpec] = {
    Currency.USD: CurrencySpec(
        code=Currency.USD,
        name="United States Dollar",
        symbol="$",
        decimal_places=2,
        day_count="ACT/360",
        settlement_days=2,
        is_quote_currency=False,
        calendar="US",
    ),
    Currency.EUR: CurrencySpec(
        code=Currency.EUR,
        name="Euro",
        symbol="€",
        decimal_places=2,
        day_count="ACT/360",
        settlement_days=2,
        is_quote_currency=True,
        calendar="TARGET",
    ),
    Currency.GBP: CurrencySpec(
        code=Currency.GBP,
        name="British Pound Sterling",
        symbol="£",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=True,
        calendar="UK",
    ),
    Currency.JPY: CurrencySpec(
        code=Currency.JPY,
        name="Japanese Yen",
        symbol="¥",
        decimal_places=0,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=False,
        calendar="JP",
    ),
    Currency.CHF: CurrencySpec(
        code=Currency.CHF,
        name="Swiss Franc",
        symbol="CHF",
        decimal_places=2,
        day_count="ACT/360",
        settlement_days=2,
        is_quote_currency=False,
        calendar="CH",
    ),
    Currency.AUD: CurrencySpec(
        code=Currency.AUD,
        name="Australian Dollar",
        symbol="A$",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=True,
        calendar="AU",
    ),
    Currency.CAD: CurrencySpec(
        code=Currency.CAD,
        name="Canadian Dollar",
        symbol="C$",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=1,  # T+1 for CAD
        is_quote_currency=False,
        calendar="CA",
    ),
    Currency.CNY: CurrencySpec(
        code=Currency.CNY,
        name="Chinese Yuan Renminbi",
        symbol="¥",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=False,
        calendar="CN",
    ),
    Currency.HKD: CurrencySpec(
        code=Currency.HKD,
        name="Hong Kong Dollar",
        symbol="HK$",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=False,
        calendar="HK",
    ),
    Currency.SGD: CurrencySpec(
        code=Currency.SGD,
        name="Singapore Dollar",
        symbol="S$",
        decimal_places=2,
        day_count="ACT/365",
        settlement_days=2,
        is_quote_currency=False,
        calendar="SG",
    ),
}

# Add remaining currencies with default conventions
for ccy in Currency:
    if ccy not in CURRENCY_SPECS:
        CURRENCY_SPECS[ccy] = CurrencySpec(
            code=ccy,
            name=ccy.value,
            symbol=ccy.value,
            decimal_places=2,
            day_count="ACT/360",
            settlement_days=2,
            is_quote_currency=False,
            calendar="TARGET",
        )


# =============================================================================
# Exchange Rate Management
# =============================================================================

@dataclass
class ExchangeRate:
    """
    Exchange rate between two currencies.
    
    Represents a single FX rate with full metadata for audit trails
    and time-series analysis.
    
    Parameters
    ----------
    base_currency : Currency
        Base currency (numerator in XXX/YYY quote)
    quote_currency : Currency
        Quote currency (denominator in XXX/YYY quote)
    rate : float
        Exchange rate value
    rate_date : date
        Date the rate applies to
    rate_type : str
        Type of rate ('spot', 'forward', 'fixing')
    source : str
        Rate source identifier
    bid : Optional[float]
        Bid rate for two-way quotes
    ask : Optional[float]
        Ask rate for two-way quotes
    
    Examples
    --------
    >>> rate = ExchangeRate(
    ...     base_currency=Currency.EUR,
    ...     quote_currency=Currency.USD,
    ...     rate=1.0850,
    ...     rate_date=date(2024, 1, 15),
    ...     rate_type='spot',
    ...     source='ECB'
    ... )
    >>> rate.mid_rate
    1.085
    """
    
    base_currency: Currency
    quote_currency: Currency
    rate: float
    rate_date: date
    rate_type: str = "spot"
    source: str = "internal"
    bid: Optional[float] = None
    ask: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    @property
    def mid_rate(self) -> float:
        """Return mid rate (average of bid/ask or the rate itself)."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.rate
    
    @property
    def spread(self) -> Optional[float]:
        """Return bid-ask spread in basis points."""
        if self.bid is not None and self.ask is not None:
            return (self.ask - self.bid) / self.mid_rate * 10_000
        return None
    
    @property
    def pair(self) -> str:
        """Return currency pair string (e.g., 'EUR/USD')."""
        return f"{self.base_currency.value}/{self.quote_currency.value}"
    
    def invert(self) -> "ExchangeRate":
        """
        Return inverted exchange rate.
        
        Returns
        -------
        ExchangeRate
            New rate with currencies swapped and rate inverted
        """
        return ExchangeRate(
            base_currency=self.quote_currency,
            quote_currency=self.base_currency,
            rate=1.0 / self.rate if self.rate != 0 else 0.0,
            rate_date=self.rate_date,
            rate_type=self.rate_type,
            source=self.source,
            bid=1.0 / self.ask if self.ask else None,
            ask=1.0 / self.bid if self.bid else None,
            timestamp=self.timestamp,
        )


@dataclass
class ForwardPoints:
    """
    FX forward points for a currency pair.
    
    Forward points represent the interest rate differential between
    two currencies and are used to calculate forward rates.
    
    Parameters
    ----------
    base_currency : Currency
        Base currency
    quote_currency : Currency
        Quote currency
    spot_rate : float
        Current spot rate
    points : Dict[str, float]
        Forward points by tenor (e.g., '1M': 15.5, '3M': 45.2)
    rate_date : date
        Valuation date
    
    Examples
    --------
    >>> fwd = ForwardPoints(
    ...     base_currency=Currency.EUR,
    ...     quote_currency=Currency.USD,
    ...     spot_rate=1.0850,
    ...     points={'1M': -12.5, '3M': -38.0, '6M': -78.5},
    ...     rate_date=date(2024, 1, 15)
    ... )
    >>> fwd.forward_rate('3M')
    1.0812
    """
    
    base_currency: Currency
    quote_currency: Currency
    spot_rate: float
    points: Dict[str, float]  # Tenor -> points (in pips)
    rate_date: date
    
    def forward_rate(self, tenor: str) -> float:
        """
        Calculate forward rate for a given tenor.
        
        Parameters
        ----------
        tenor : str
            Tenor string (e.g., '1M', '3M', '1Y')
            
        Returns
        -------
        float
            Forward rate
        """
        if tenor not in self.points:
            raise ValueError(f"Tenor {tenor} not available. Available: {list(self.points.keys())}")
        
        # Points are typically quoted in pips (0.0001)
        pip_value = 0.0001
        if self.quote_currency == Currency.JPY:
            pip_value = 0.01
            
        return self.spot_rate + (self.points[tenor] * pip_value)


class ExchangeRateProvider:
    """
    Exchange rate provider with caching and rate history.
    
    This class manages FX rates from multiple sources, providing
    spot rates, forward rates, and historical rate lookups with
    proper caching for performance.
    
    Parameters
    ----------
    base_currency : Currency
        Default base currency for the provider
    rate_source : str
        Primary rate source identifier
    cache_duration_minutes : int
        How long to cache rates before refresh
    
    Attributes
    ----------
    rates_cache : Dict
        Internal cache of exchange rates
    historical_rates : pd.DataFrame
        Time series of historical rates
    
    Examples
    --------
    >>> provider = ExchangeRateProvider(base_currency=Currency.USD)
    >>> rate = provider.get_spot_rate(Currency.USD, Currency.EUR)
    >>> provider.load_historical_rates('EUR/USD', start_date, end_date)
    """
    
    def __init__(
        self,
        base_currency: Currency = Currency.USD,
        rate_source: str = "internal",
        cache_duration_minutes: int = 15,
    ) -> None:
        self.base_currency = base_currency
        self.rate_source = rate_source
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        
        # Internal storage
        self._rates_cache: Dict[str, Tuple[ExchangeRate, datetime]] = {}
        self._historical_rates: Dict[str, pd.DataFrame] = {}
        self._forward_points: Dict[str, ForwardPoints] = {}
        
        # Initialize with default rates (in production, load from external source)
        self._initialize_default_rates()
    
    def _initialize_default_rates(self) -> None:
        """Initialize with standard market rates for testing/defaults."""
        today = date.today()
        
        # Default rates vs USD (approximate market rates)
        default_rates = {
            Currency.EUR: 1.0850,
            Currency.GBP: 1.2650,
            Currency.JPY: 148.50,
            Currency.CHF: 0.8650,
            Currency.AUD: 0.6550,
            Currency.CAD: 1.3450,
            Currency.CNY: 7.1950,
            Currency.HKD: 7.8150,
            Currency.SGD: 1.3350,
        }
        
        for ccy, rate in default_rates.items():
            fx_rate = ExchangeRate(
                base_currency=Currency.USD,
                quote_currency=ccy,
                rate=rate,
                rate_date=today,
                rate_type="spot",
                source="default",
            )
            cache_key = f"{Currency.USD.value}/{ccy.value}"
            self._rates_cache[cache_key] = (fx_rate, datetime.now())
    
    def get_spot_rate(
        self,
        from_currency: Currency,
        to_currency: Currency,
        rate_date: Optional[date] = None,
    ) -> ExchangeRate:
        """
        Get spot exchange rate between two currencies.
        
        Parameters
        ----------
        from_currency : Currency
            Source currency
        to_currency : Currency
            Target currency
        rate_date : Optional[date]
            Date for rate lookup (None for current)
            
        Returns
        -------
        ExchangeRate
            Exchange rate object
            
        Raises
        ------
        ValueError
            If rate is not available
        """
        if from_currency == to_currency:
            return ExchangeRate(
                base_currency=from_currency,
                quote_currency=to_currency,
                rate=1.0,
                rate_date=rate_date or date.today(),
                rate_type="spot",
                source="identity",
            )
        
        # Check cache
        direct_key = f"{from_currency.value}/{to_currency.value}"
        inverse_key = f"{to_currency.value}/{from_currency.value}"
        
        if direct_key in self._rates_cache:
            cached_rate, cache_time = self._rates_cache[direct_key]
            if datetime.now() - cache_time < self.cache_duration:
                return cached_rate
        
        if inverse_key in self._rates_cache:
            cached_rate, cache_time = self._rates_cache[inverse_key]
            if datetime.now() - cache_time < self.cache_duration:
                return cached_rate.invert()
        
        # Try triangulation through USD
        if from_currency != Currency.USD and to_currency != Currency.USD:
            from_usd = self.get_spot_rate(from_currency, Currency.USD, rate_date)
            usd_to = self.get_spot_rate(Currency.USD, to_currency, rate_date)
            
            cross_rate = from_usd.rate * usd_to.rate
            return ExchangeRate(
                base_currency=from_currency,
                quote_currency=to_currency,
                rate=cross_rate,
                rate_date=rate_date or date.today(),
                rate_type="spot",
                source="triangulated",
            )
        
        raise ValueError(f"Exchange rate not available: {direct_key}")
    
    def set_rate(
        self,
        from_currency: Currency,
        to_currency: Currency,
        rate: float,
        rate_date: Optional[date] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> None:
        """
        Set or update an exchange rate.
        
        Parameters
        ----------
        from_currency : Currency
            Base currency
        to_currency : Currency
            Quote currency
        rate : float
            Mid rate value
        rate_date : Optional[date]
            Date for the rate
        bid : Optional[float]
            Bid rate
        ask : Optional[float]
            Ask rate
        """
        fx_rate = ExchangeRate(
            base_currency=from_currency,
            quote_currency=to_currency,
            rate=rate,
            rate_date=rate_date or date.today(),
            rate_type="spot",
            source=self.rate_source,
            bid=bid,
            ask=ask,
            timestamp=datetime.now(),
        )
        
        cache_key = f"{from_currency.value}/{to_currency.value}"
        self._rates_cache[cache_key] = (fx_rate, datetime.now())
    
    def get_forward_rate(
        self,
        from_currency: Currency,
        to_currency: Currency,
        tenor: str,
        rate_date: Optional[date] = None,
    ) -> ExchangeRate:
        """
        Get forward exchange rate for a given tenor.
        
        Parameters
        ----------
        from_currency : Currency
            Base currency
        to_currency : Currency
            Quote currency
        tenor : str
            Forward tenor (e.g., '1M', '3M', '1Y')
        rate_date : Optional[date]
            Valuation date
            
        Returns
        -------
        ExchangeRate
            Forward exchange rate
        """
        pair_key = f"{from_currency.value}/{to_currency.value}"
        
        if pair_key in self._forward_points:
            fwd_points = self._forward_points[pair_key]
            fwd_rate = fwd_points.forward_rate(tenor)
            
            return ExchangeRate(
                base_currency=from_currency,
                quote_currency=to_currency,
                rate=fwd_rate,
                rate_date=rate_date or date.today(),
                rate_type=f"forward_{tenor}",
                source=self.rate_source,
            )
        
        # Fall back to spot rate if no forward points
        return self.get_spot_rate(from_currency, to_currency, rate_date)
    
    def load_historical_rates(
        self,
        pair: str,
        start_date: date,
        end_date: date,
        source: str = "internal",
    ) -> pd.DataFrame:
        """
        Load historical exchange rates for analysis.
        
        Parameters
        ----------
        pair : str
            Currency pair (e.g., 'EUR/USD')
        start_date : date
            Start of date range
        end_date : date
            End of date range
        source : str
            Rate source identifier
            
        Returns
        -------
        pd.DataFrame
            DataFrame with columns: date, rate, bid, ask
        """
        if pair in self._historical_rates:
            df = self._historical_rates[pair]
            mask = (df['date'] >= start_date) & (df['date'] <= end_date)
            return df.loc[mask].copy()
        
        # Generate synthetic historical data for testing
        dates = pd.date_range(start_date, end_date, freq='B')
        base_rate = 1.0
        
        # Get current rate if available
        try:
            base, quote = pair.split('/')
            current = self.get_spot_rate(Currency(base), Currency(quote))
            base_rate = current.rate
        except (ValueError, KeyError):
            pass
        
        # Generate with some volatility
        np.random.seed(42)
        returns = np.random.normal(0, 0.005, len(dates))
        rates = base_rate * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates.date,
            'rate': rates,
            'bid': rates * 0.9999,
            'ask': rates * 1.0001,
        })
        
        self._historical_rates[pair] = df
        return df


# =============================================================================
# Currency Conversion
# =============================================================================

class CurrencyConverter:
    """
    Currency conversion engine for cashflow transformation.
    
    Provides methods to convert single amounts, cashflow streams,
    and entire DataFrames between currencies with proper handling
    of conventions and precision.
    
    Parameters
    ----------
    rate_provider : ExchangeRateProvider
        Source for exchange rates
    rounding_mode : str
        Rounding mode ('HALF_UP', 'HALF_DOWN', 'FLOOR', 'CEIL')
    
    Examples
    --------
    >>> provider = ExchangeRateProvider()
    >>> converter = CurrencyConverter(provider)
    >>> 
    >>> # Convert single amount
    >>> eur_amount = converter.convert(1_000_000, Currency.USD, Currency.EUR)
    >>> 
    >>> # Convert cashflow DataFrame
    >>> converted_cf = converter.convert_cashflows(
    ...     cashflows_df,
    ...     from_currency=Currency.USD,
    ...     to_currency=Currency.EUR,
    ...     amount_columns=['principal', 'interest']
    ... )
    """
    
    def __init__(
        self,
        rate_provider: ExchangeRateProvider,
        rounding_mode: str = "HALF_UP",
    ) -> None:
        self.rate_provider = rate_provider
        self.rounding_mode = rounding_mode
    
    def convert(
        self,
        amount: float,
        from_currency: Currency,
        to_currency: Currency,
        rate_date: Optional[date] = None,
        use_forward: bool = False,
        forward_tenor: Optional[str] = None,
    ) -> float:
        """
        Convert amount between currencies.
        
        Parameters
        ----------
        amount : float
            Amount to convert
        from_currency : Currency
            Source currency
        to_currency : Currency
            Target currency
        rate_date : Optional[date]
            Date for rate lookup
        use_forward : bool
            Use forward rate instead of spot
        forward_tenor : Optional[str]
            Forward tenor if use_forward is True
            
        Returns
        -------
        float
            Converted amount
        """
        if from_currency == to_currency:
            return amount
        
        if use_forward and forward_tenor:
            rate = self.rate_provider.get_forward_rate(
                from_currency, to_currency, forward_tenor, rate_date
            )
        else:
            rate = self.rate_provider.get_spot_rate(
                from_currency, to_currency, rate_date
            )
        
        converted = amount * rate.rate
        
        # Apply proper rounding
        to_spec = CURRENCY_SPECS.get(to_currency)
        if to_spec:
            converted = float(to_spec.round_amount(converted))
        
        return converted
    
    def convert_cashflows(
        self,
        cashflows: pd.DataFrame,
        from_currency: Currency,
        to_currency: Currency,
        amount_columns: List[str],
        date_column: str = "date",
        use_period_rates: bool = True,
    ) -> pd.DataFrame:
        """
        Convert cashflow DataFrame to target currency.
        
        Parameters
        ----------
        cashflows : pd.DataFrame
            Cashflow data with amount columns
        from_currency : Currency
            Original currency of amounts
        to_currency : Currency
            Target currency
        amount_columns : List[str]
            Column names containing amounts to convert
        date_column : str
            Column containing dates (for period-specific rates)
        use_period_rates : bool
            Use date-specific rates vs single rate
            
        Returns
        -------
        pd.DataFrame
            Converted cashflows with new columns
        """
        result = cashflows.copy()
        
        if use_period_rates and date_column in result.columns:
            # Get rates for each period
            for col in amount_columns:
                converted_col = f"{col}_{to_currency.value}"
                converted_values = []
                
                for idx, row in result.iterrows():
                    rate_date = row[date_column]
                    if isinstance(rate_date, datetime):
                        rate_date = rate_date.date()
                    elif isinstance(rate_date, str):
                        rate_date = pd.to_datetime(rate_date).date()
                    
                    converted = self.convert(
                        row[col],
                        from_currency,
                        to_currency,
                        rate_date=rate_date,
                    )
                    converted_values.append(converted)
                
                result[converted_col] = converted_values
        else:
            # Use single rate
            rate = self.rate_provider.get_spot_rate(from_currency, to_currency)
            
            for col in amount_columns:
                converted_col = f"{col}_{to_currency.value}"
                result[converted_col] = result[col] * rate.rate
        
        # Add metadata
        result.attrs['converted_from'] = from_currency.value
        result.attrs['converted_to'] = to_currency.value
        
        return result


# =============================================================================
# FX Exposure Analysis
# =============================================================================

@dataclass
class FXExposure:
    """
    FX exposure calculation for a deal or portfolio.
    
    Captures currency mismatches between assets (collateral) and
    liabilities (bonds) for risk management purposes.
    
    Parameters
    ----------
    base_currency : Currency
        Reporting currency
    asset_exposures : Dict[Currency, float]
        Notional exposure by currency on asset side
    liability_exposures : Dict[Currency, float]
        Notional exposure by currency on liability side
    hedge_positions : Dict[Currency, float]
        FX hedge notionals by currency
    valuation_date : date
        Date of exposure calculation
    
    Examples
    --------
    >>> exposure = FXExposure(
    ...     base_currency=Currency.USD,
    ...     asset_exposures={Currency.USD: 100_000_000},
    ...     liability_exposures={Currency.EUR: 90_000_000},
    ...     hedge_positions={Currency.EUR: -85_000_000},
    ...     valuation_date=date(2024, 1, 15)
    ... )
    >>> net_exposure = exposure.net_exposure_by_currency()
    """
    
    base_currency: Currency
    asset_exposures: Dict[Currency, float]
    liability_exposures: Dict[Currency, float]
    hedge_positions: Dict[Currency, float] = field(default_factory=dict)
    valuation_date: date = field(default_factory=date.today)
    
    def net_exposure_by_currency(self) -> Dict[Currency, float]:
        """
        Calculate net FX exposure by currency.
        
        Returns
        -------
        Dict[Currency, float]
            Net exposure (assets - liabilities + hedges) by currency
        """
        all_currencies = set(
            list(self.asset_exposures.keys()) +
            list(self.liability_exposures.keys()) +
            list(self.hedge_positions.keys())
        )
        
        net = {}
        for ccy in all_currencies:
            assets = self.asset_exposures.get(ccy, 0.0)
            liabilities = self.liability_exposures.get(ccy, 0.0)
            hedges = self.hedge_positions.get(ccy, 0.0)
            
            net[ccy] = assets - liabilities + hedges
        
        return net
    
    def calculate_var(
        self,
        rate_provider: ExchangeRateProvider,
        confidence_level: float = 0.99,
        horizon_days: int = 10,
    ) -> Dict[str, float]:
        """
        Calculate Value-at-Risk for FX exposure.
        
        Uses parametric VaR based on historical volatility.
        
        Parameters
        ----------
        rate_provider : ExchangeRateProvider
            Rate provider with historical data
        confidence_level : float
            VaR confidence level (e.g., 0.99 for 99%)
        horizon_days : int
            Risk horizon in business days
            
        Returns
        -------
        Dict[str, float]
            VaR metrics including total and by currency
        """
        from scipy import stats
        
        z_score = stats.norm.ppf(confidence_level)
        net_exposures = self.net_exposure_by_currency()
        
        var_by_ccy = {}
        total_var = 0.0
        
        for ccy, exposure in net_exposures.items():
            if ccy == self.base_currency or abs(exposure) < 1:
                continue
            
            # Get historical volatility (simplified - use 10% annual vol as default)
            annual_vol = 0.10
            daily_vol = annual_vol / np.sqrt(252)
            horizon_vol = daily_vol * np.sqrt(horizon_days)
            
            var_amount = abs(exposure) * horizon_vol * z_score
            var_by_ccy[ccy.value] = var_amount
            total_var += var_amount ** 2  # Sum of squares for diversified VaR
        
        return {
            "total_var": np.sqrt(total_var),
            "var_by_currency": var_by_ccy,
            "confidence_level": confidence_level,
            "horizon_days": horizon_days,
        }


class FXHedgeCalculator:
    """
    Calculate optimal FX hedge ratios and positions.
    
    Determines hedge positions needed to minimize or eliminate
    FX exposure in cross-currency deals.
    
    Parameters
    ----------
    rate_provider : ExchangeRateProvider
        Exchange rate provider
    hedge_ratio : float
        Target hedge ratio (1.0 = fully hedged)
    min_hedge_amount : float
        Minimum hedge notional (for cost efficiency)
    
    Examples
    --------
    >>> calculator = FXHedgeCalculator(provider, hedge_ratio=0.95)
    >>> hedges = calculator.calculate_hedge_positions(exposure)
    """
    
    def __init__(
        self,
        rate_provider: ExchangeRateProvider,
        hedge_ratio: float = 1.0,
        min_hedge_amount: float = 100_000.0,
    ) -> None:
        self.rate_provider = rate_provider
        self.hedge_ratio = hedge_ratio
        self.min_hedge_amount = min_hedge_amount
    
    def calculate_hedge_positions(
        self,
        exposure: FXExposure,
        target_currency: Optional[Currency] = None,
    ) -> Dict[str, Any]:
        """
        Calculate hedge positions to cover FX exposure.
        
        Parameters
        ----------
        exposure : FXExposure
            Current FX exposure
        target_currency : Optional[Currency]
            Currency to hedge into (defaults to base currency)
            
        Returns
        -------
        Dict[str, Any]
            Recommended hedge positions and analysis
        """
        target = target_currency or exposure.base_currency
        net_exposures = exposure.net_exposure_by_currency()
        
        recommendations = []
        total_hedge_notional = 0.0
        
        for ccy, net_amount in net_exposures.items():
            if ccy == target:
                continue
            
            # Skip small exposures
            if abs(net_amount) < self.min_hedge_amount:
                continue
            
            # Calculate hedge amount
            hedge_amount = -net_amount * self.hedge_ratio
            
            # Get rate for notional conversion
            rate = self.rate_provider.get_spot_rate(ccy, target)
            hedge_notional_target = abs(hedge_amount) * rate.rate
            
            recommendations.append({
                "currency": ccy.value,
                "current_exposure": net_amount,
                "hedge_amount": hedge_amount,
                "hedge_notional_in_target": hedge_notional_target,
                "instrument": "FX Forward" if abs(hedge_amount) > 1_000_000 else "FX Spot",
                "direction": "sell" if hedge_amount < 0 else "buy",
            })
            
            total_hedge_notional += hedge_notional_target
        
        return {
            "target_currency": target.value,
            "hedge_ratio": self.hedge_ratio,
            "recommendations": recommendations,
            "total_hedge_notional": total_hedge_notional,
            "residual_exposure": self._calculate_residual(exposure, recommendations),
        }
    
    def _calculate_residual(
        self,
        exposure: FXExposure,
        recommendations: List[Dict],
    ) -> Dict[str, float]:
        """Calculate residual exposure after hedging."""
        net = exposure.net_exposure_by_currency()
        
        for rec in recommendations:
            ccy = Currency(rec["currency"])
            net[ccy] = net.get(ccy, 0.0) + rec["hedge_amount"]
        
        return {k.value: v for k, v in net.items() if abs(v) > 0.01}


# =============================================================================
# Utility Functions
# =============================================================================

def parse_currency(value: Union[str, Currency]) -> Currency:
    """
    Parse string or Currency to Currency enum.
    
    Parameters
    ----------
    value : Union[str, Currency]
        Currency code string or enum
        
    Returns
    -------
    Currency
        Parsed currency enum
        
    Raises
    ------
    ValueError
        If currency code is not recognized
    """
    if isinstance(value, Currency):
        return value
    
    value = str(value).upper().strip()
    
    try:
        return Currency(value)
    except ValueError:
        raise ValueError(f"Unknown currency code: {value}")


def format_amount(
    amount: float,
    currency: Currency,
    include_symbol: bool = True,
    thousands_sep: str = ",",
) -> str:
    """
    Format amount with currency conventions.
    
    Parameters
    ----------
    amount : float
        Amount to format
    currency : Currency
        Currency for formatting rules
    include_symbol : bool
        Include currency symbol
    thousands_sep : str
        Thousands separator
        
    Returns
    -------
    str
        Formatted amount string
    """
    spec = CURRENCY_SPECS.get(currency, CURRENCY_SPECS[Currency.USD])
    rounded = spec.round_amount(amount)
    
    # Format with proper decimal places
    format_str = f"{{:,.{spec.decimal_places}f}}"
    formatted = format_str.format(float(rounded))
    
    # Replace comma with requested separator
    if thousands_sep != ",":
        formatted = formatted.replace(",", thousands_sep)
    
    if include_symbol:
        return f"{spec.symbol}{formatted}"
    
    return formatted
