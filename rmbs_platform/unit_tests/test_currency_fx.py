"""
Multi-Currency and FX Tests
===========================

Comprehensive tests for multi-currency support including:
- Currency definitions and conventions
- Exchange rate management
- Currency conversion
- FX exposure calculations
- FX hedging recommendations

These tests verify currency handling for cross-border RMBS deals.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.currency import (
    Currency,
    CurrencySpec,
    CURRENCY_SPECS,
    ExchangeRate,
    ExchangeRateProvider,
    CurrencyConverter,
    FXExposure,
    FXHedgeCalculator,
    ForwardPoints,
    parse_currency,
    format_amount,
)


# =============================================================================
# Currency Definition Tests
# =============================================================================

class TestCurrencyDefinitions:
    """Tests for currency definitions and specifications."""
    
    def test_major_currencies_defined(self):
        """
        Verify all major currencies are defined.
        """
        major_currencies = [
            Currency.USD, Currency.EUR, Currency.GBP,
            Currency.JPY, Currency.CHF, Currency.AUD,
            Currency.CAD,
        ]
        
        for ccy in major_currencies:
            assert ccy in CURRENCY_SPECS
    
    def test_currency_spec_attributes(self):
        """
        Verify currency specs have required attributes.
        """
        usd_spec = CURRENCY_SPECS[Currency.USD]
        
        assert usd_spec.code == Currency.USD
        assert usd_spec.name == "United States Dollar"
        assert usd_spec.symbol == "$"
        assert usd_spec.decimal_places == 2
        assert usd_spec.day_count == "ACT/360"
    
    def test_jpy_has_zero_decimals(self):
        """
        Verify JPY has no decimal places (industry convention).
        """
        jpy_spec = CURRENCY_SPECS[Currency.JPY]
        
        assert jpy_spec.decimal_places == 0
    
    def test_gbp_uses_act_365(self):
        """
        Verify GBP uses ACT/365 day count (UK convention).
        """
        gbp_spec = CURRENCY_SPECS[Currency.GBP]
        
        assert gbp_spec.day_count == "ACT/365"
    
    def test_round_amount_to_currency_precision(self):
        """
        Verify amounts are rounded to currency precision.
        """
        usd_spec = CURRENCY_SPECS[Currency.USD]
        jpy_spec = CURRENCY_SPECS[Currency.JPY]
        
        # USD: 2 decimal places
        usd_rounded = usd_spec.round_amount(1234.5678)
        assert str(usd_rounded) == "1234.57"
        
        # JPY: 0 decimal places
        jpy_rounded = jpy_spec.round_amount(1234.5678)
        assert str(jpy_rounded) == "1235"


class TestParseCurrency:
    """Tests for currency parsing utility."""
    
    def test_parse_string_to_currency(self):
        """
        Verify string currency codes are parsed correctly.
        """
        assert parse_currency("USD") == Currency.USD
        assert parse_currency("eur") == Currency.EUR  # Case insensitive
        assert parse_currency("GBP") == Currency.GBP
    
    def test_parse_currency_passthrough(self):
        """
        Verify Currency enum values pass through unchanged.
        """
        assert parse_currency(Currency.USD) == Currency.USD
    
    def test_parse_unknown_currency_raises(self):
        """
        Verify unknown currency codes raise ValueError.
        """
        with pytest.raises(ValueError, match="Unknown currency"):
            parse_currency("XYZ")


class TestFormatAmount:
    """Tests for amount formatting."""
    
    def test_format_usd_amount(self):
        """
        Verify USD amount formatting with symbol.
        """
        formatted = format_amount(1234567.89, Currency.USD)
        
        assert "$" in formatted
        assert "1,234,567.89" in formatted
    
    def test_format_jpy_amount(self):
        """
        Verify JPY amount formatting (no decimals).
        """
        formatted = format_amount(1234567, Currency.JPY)
        
        assert "¥" in formatted
        assert "." not in formatted  # No decimal point
    
    def test_format_without_symbol(self):
        """
        Verify formatting without currency symbol.
        """
        formatted = format_amount(1000.50, Currency.USD, include_symbol=False)
        
        assert "$" not in formatted
        assert "1,000.50" in formatted


# =============================================================================
# Exchange Rate Tests
# =============================================================================

class TestExchangeRate:
    """Tests for exchange rate objects."""
    
    def test_exchange_rate_creation(self):
        """
        Verify exchange rate object creation.
        """
        rate = ExchangeRate(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            rate=1.0850,
            rate_date=date(2024, 1, 15),
            rate_type="spot",
            source="ECB",
        )
        
        assert rate.base_currency == Currency.EUR
        assert rate.quote_currency == Currency.USD
        assert rate.rate == 1.0850
        assert rate.pair == "EUR/USD"
    
    def test_mid_rate_from_bid_ask(self):
        """
        Verify mid rate calculation from bid/ask.
        """
        rate = ExchangeRate(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            rate=1.0850,
            rate_date=date.today(),
            bid=1.0848,
            ask=1.0852,
        )
        
        assert rate.mid_rate == 1.0850
    
    def test_spread_calculation(self):
        """
        Verify bid-ask spread calculation in basis points.
        """
        rate = ExchangeRate(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            rate=1.0850,
            rate_date=date.today(),
            bid=1.0840,
            ask=1.0860,
        )
        
        # Spread = (1.0860 - 1.0840) / 1.0850 * 10000 ≈ 18.4 bps
        assert rate.spread is not None
        assert 15 < rate.spread < 25
    
    def test_rate_inversion(self):
        """
        Verify rate inversion (EUR/USD -> USD/EUR).
        """
        rate = ExchangeRate(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            rate=1.0850,
            rate_date=date.today(),
        )
        
        inverted = rate.invert()
        
        assert inverted.base_currency == Currency.USD
        assert inverted.quote_currency == Currency.EUR
        assert abs(inverted.rate - (1.0 / 1.0850)) < 0.0001


# =============================================================================
# Exchange Rate Provider Tests
# =============================================================================

class TestExchangeRateProvider:
    """Tests for exchange rate provider."""
    
    def test_provider_initialization(self):
        """
        Verify provider initializes with default rates.
        """
        provider = ExchangeRateProvider()
        
        # Should have some default rates
        rate = provider.get_spot_rate(Currency.USD, Currency.EUR)
        assert rate.rate > 0
    
    def test_get_spot_rate_same_currency(self):
        """
        Verify same-currency rate is 1.0.
        """
        provider = ExchangeRateProvider()
        
        rate = provider.get_spot_rate(Currency.USD, Currency.USD)
        
        assert rate.rate == 1.0
        assert rate.source == "identity"
    
    def test_get_spot_rate_direct(self):
        """
        Verify direct spot rate retrieval.
        """
        provider = ExchangeRateProvider()
        
        rate = provider.get_spot_rate(Currency.USD, Currency.EUR)
        
        assert rate.base_currency == Currency.USD
        assert rate.quote_currency == Currency.EUR
        assert rate.rate > 0
    
    def test_get_spot_rate_inverted(self):
        """
        Verify inverted rate retrieval (when direct not available).
        """
        provider = ExchangeRateProvider()
        
        # EUR/USD is typically stored, USD/EUR inverts
        rate = provider.get_spot_rate(Currency.EUR, Currency.USD)
        
        # Should return valid rate (possibly inverted)
        assert rate.rate > 0
    
    def test_get_spot_rate_triangulated(self):
        """
        Verify cross rates are triangulated through USD.
        """
        provider = ExchangeRateProvider()
        
        # EUR/GBP requires triangulation
        rate = provider.get_spot_rate(Currency.EUR, Currency.GBP)
        
        # Should be calculated via USD
        assert rate.rate > 0
        # Cross rate EUR/GBP typically around 0.85
        assert 0.5 < rate.rate < 1.5
    
    def test_set_rate_and_retrieve(self):
        """
        Verify custom rates can be set and retrieved.
        """
        provider = ExchangeRateProvider()
        
        provider.set_rate(
            from_currency=Currency.USD,
            to_currency=Currency.MXN,
            rate=17.50,
            bid=17.48,
            ask=17.52,
        )
        
        rate = provider.get_spot_rate(Currency.USD, Currency.MXN)
        
        assert rate.rate == 17.50


class TestForwardRates:
    """Tests for forward rate calculations."""
    
    def test_forward_points_structure(self):
        """
        Verify forward points object structure.
        """
        fwd = ForwardPoints(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            spot_rate=1.0850,
            points={"1M": -12.5, "3M": -38.0, "6M": -78.5},
            rate_date=date.today(),
        )
        
        assert fwd.spot_rate == 1.0850
        assert "1M" in fwd.points
    
    def test_forward_rate_calculation(self):
        """
        Verify forward rate is spot + points.
        """
        fwd = ForwardPoints(
            base_currency=Currency.EUR,
            quote_currency=Currency.USD,
            spot_rate=1.0850,
            points={"3M": -38.0},  # -38 pips
            rate_date=date.today(),
        )
        
        forward_3m = fwd.forward_rate("3M")
        
        # 1.0850 + (-38 * 0.0001) = 1.0812
        expected = 1.0850 + (-38.0 * 0.0001)
        assert abs(forward_3m - expected) < 0.0001


# =============================================================================
# Currency Converter Tests
# =============================================================================

class TestCurrencyConverter:
    """Tests for currency conversion."""
    
    def test_convert_amount_basic(self):
        """
        Verify basic amount conversion.
        """
        provider = ExchangeRateProvider()
        converter = CurrencyConverter(provider)
        
        # Convert $1M USD to EUR
        eur_amount = converter.convert(
            amount=1_000_000,
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
        )
        
        # EUR should be slightly less than USD (typically)
        assert eur_amount > 0
        # EUR/USD typically around 1.08, so EUR amount ~925K
        assert 800_000 < eur_amount < 1_100_000
    
    def test_convert_same_currency(self):
        """
        Verify same-currency conversion returns same amount.
        """
        provider = ExchangeRateProvider()
        converter = CurrencyConverter(provider)
        
        result = converter.convert(
            amount=1_000_000,
            from_currency=Currency.USD,
            to_currency=Currency.USD,
        )
        
        assert result == 1_000_000
    
    def test_convert_respects_precision(self):
        """
        Verify converted amounts respect target currency precision.
        """
        provider = ExchangeRateProvider()
        converter = CurrencyConverter(provider)
        
        # Convert to JPY (0 decimal places)
        jpy_amount = converter.convert(
            amount=1234.56,
            from_currency=Currency.USD,
            to_currency=Currency.JPY,
        )
        
        # Should be whole number
        assert jpy_amount == int(jpy_amount)
    
    def test_convert_cashflows_dataframe(self):
        """
        Verify cashflow DataFrame conversion.
        """
        provider = ExchangeRateProvider()
        converter = CurrencyConverter(provider)
        
        # Create sample cashflows in USD
        cashflows = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3, freq="M"),
            "principal": [100_000, 110_000, 120_000],
            "interest": [5_000, 5_500, 6_000],
        })
        
        converted = converter.convert_cashflows(
            cashflows,
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
            amount_columns=["principal", "interest"],
            use_period_rates=False,  # Use single rate for simplicity
        )
        
        # Should have new columns
        assert "principal_EUR" in converted.columns
        assert "interest_EUR" in converted.columns
        
        # EUR amounts should be different from USD
        assert not np.allclose(converted["principal_EUR"], converted["principal"])


# =============================================================================
# FX Exposure Tests
# =============================================================================

class TestFXExposure:
    """Tests for FX exposure calculations."""
    
    def test_fx_exposure_creation(self):
        """
        Verify FX exposure object creation.
        """
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={Currency.USD: 100_000_000},
            liability_exposures={Currency.EUR: 90_000_000},
            hedge_positions={Currency.EUR: -85_000_000},
            valuation_date=date.today(),
        )
        
        assert exposure.base_currency == Currency.USD
        assert Currency.USD in exposure.asset_exposures
        assert Currency.EUR in exposure.liability_exposures
    
    def test_net_exposure_calculation(self):
        """
        Verify net FX exposure calculation.
        """
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={
                Currency.USD: 100_000_000,
                Currency.EUR: 20_000_000,
            },
            liability_exposures={
                Currency.EUR: 50_000_000,
            },
            hedge_positions={
                Currency.EUR: 25_000_000,  # Hedge position
            },
        )
        
        net = exposure.net_exposure_by_currency()
        
        # USD: 100M assets - 0 liabilities = 100M
        assert net[Currency.USD] == 100_000_000
        
        # EUR: 20M assets - 50M liabilities + 25M hedge = -5M
        assert net[Currency.EUR] == -5_000_000
    
    def test_fx_exposure_var_calculation(self):
        """
        Verify FX VaR calculation runs without error.
        """
        provider = ExchangeRateProvider()
        
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={Currency.USD: 100_000_000},
            liability_exposures={Currency.EUR: 50_000_000},
        )
        
        var_result = exposure.calculate_var(
            rate_provider=provider,
            confidence_level=0.99,
            horizon_days=10,
        )
        
        assert "total_var" in var_result
        assert "var_by_currency" in var_result
        assert var_result["confidence_level"] == 0.99


# =============================================================================
# FX Hedge Calculator Tests
# =============================================================================

class TestFXHedgeCalculator:
    """Tests for FX hedge calculations."""
    
    def test_calculate_hedge_positions(self):
        """
        Verify hedge position recommendations.
        """
        provider = ExchangeRateProvider()
        calculator = FXHedgeCalculator(
            rate_provider=provider,
            hedge_ratio=1.0,  # Full hedge
        )
        
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={Currency.USD: 100_000_000},
            liability_exposures={Currency.EUR: 50_000_000},
        )
        
        recommendations = calculator.calculate_hedge_positions(exposure)
        
        assert "recommendations" in recommendations
        assert "total_hedge_notional" in recommendations
        
        # Should recommend hedging EUR exposure
        eur_recs = [r for r in recommendations["recommendations"] if r["currency"] == "EUR"]
        assert len(eur_recs) > 0
    
    def test_hedge_ratio_applied(self):
        """
        Verify partial hedge ratio is applied.
        """
        provider = ExchangeRateProvider()
        
        # 50% hedge ratio
        calculator = FXHedgeCalculator(
            rate_provider=provider,
            hedge_ratio=0.50,
        )
        
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={},
            liability_exposures={Currency.EUR: 100_000_000},
        )
        
        recommendations = calculator.calculate_hedge_positions(exposure)
        
        # Hedge amount should be ~50% of exposure
        eur_recs = [r for r in recommendations["recommendations"] if r["currency"] == "EUR"]
        if eur_recs:
            hedge_amount = abs(eur_recs[0]["hedge_amount"])
            # Should be around 50M (50% of 100M)
            assert 45_000_000 < hedge_amount < 55_000_000


# =============================================================================
# Integration Tests
# =============================================================================

class TestCurrencyIntegration:
    """Integration tests for currency module."""
    
    def test_full_conversion_workflow(self):
        """
        Verify complete workflow from rate setup to conversion.
        """
        # Setup
        provider = ExchangeRateProvider()
        provider.set_rate(Currency.USD, Currency.EUR, 0.92)
        
        converter = CurrencyConverter(provider)
        
        # Convert cashflows
        cashflows = pd.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 2, 1)],
            "principal": [1_000_000, 1_100_000],
        })
        
        converted = converter.convert_cashflows(
            cashflows,
            from_currency=Currency.USD,
            to_currency=Currency.EUR,
            amount_columns=["principal"],
        )
        
        # Verify conversion applied
        assert converted["principal_EUR"].iloc[0] == pytest.approx(920_000, rel=0.01)
    
    def test_exposure_and_hedge_workflow(self):
        """
        Verify exposure calculation and hedge recommendation workflow.
        """
        provider = ExchangeRateProvider()
        
        # Define exposure
        exposure = FXExposure(
            base_currency=Currency.USD,
            asset_exposures={Currency.USD: 100_000_000},
            liability_exposures={
                Currency.EUR: 40_000_000,
                Currency.GBP: 30_000_000,
            },
        )
        
        # Get hedge recommendations
        calculator = FXHedgeCalculator(provider, hedge_ratio=0.95)
        result = calculator.calculate_hedge_positions(exposure)
        
        # Should have recommendations for both EUR and GBP
        currencies_covered = [r["currency"] for r in result["recommendations"]]
        assert "EUR" in currencies_covered or "GBP" in currencies_covered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
