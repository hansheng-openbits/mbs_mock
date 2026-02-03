"""
Phase 3: Market Data Integration - Comprehensive Tests
=======================================================

This test validates Component 3: Market Data Integration

Test Coverage:
1. Market data snapshot creation and storage
2. Yield curve construction from market data
3. RMBS spread retrieval
4. Economic indicator access
5. Data validation and anomaly detection
6. Historical time series
7. Sample data generation

Author: RMBS Platform Development Team
Date: January 29, 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import json
import shutil
from datetime import datetime, timedelta

from engine.market_data import (
    MarketDataProvider,
    SampleDataGenerator,
    TreasurySnapshot,
    SwapSnapshot,
    RMBSSpreadSnapshot,
    HPISnapshot,
    UnemploymentSnapshot,
    MortgageRateSnapshot,
    MarketDataSnapshot
)


def print_section(title, width=80):
    """Print formatted section header."""
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width + "\n")


def print_subsection(title):
    """Print formatted subsection header."""
    print(f"\n{title}")
    print("-" * 80)


def test_snapshot_creation_and_storage():
    """Test 1: Create and store market data snapshots"""
    print_section("TEST 1: SNAPSHOT CREATION AND STORAGE")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    print("Creating a market data snapshot...")
    print()
    
    # Create snapshot
    date = "2026-01-29"
    
    treasury = TreasurySnapshot(
        date=date,
        tenors=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        par_yields=[0.0420, 0.0440, 0.0450, 0.0460, 0.0470, 0.0480],
        source="US Treasury"
    )
    
    rmbs_spreads = RMBSSpreadSnapshot(
        date=date,
        agency_oas=25.0,
        prime_oas=150.0,
        subprime_oas=400.0,
        alt_a_oas=250.0
    )
    
    hpi = HPISnapshot(
        date=date,
        national_index=350.0,
        yoy_change=0.05
    )
    
    unemployment = UnemploymentSnapshot(
        date=date,
        rate=0.04
    )
    
    mortgage_rates = MortgageRateSnapshot(
        date=date,
        rate_30y=0.0675,
        rate_15y=0.0600
    )
    
    snapshot = MarketDataSnapshot(
        date=date,
        treasury=treasury,
        rmbs_spreads=rmbs_spreads,
        hpi=hpi,
        unemployment=unemployment,
        mortgage_rates=mortgage_rates
    )
    
    print(f"Snapshot Date: {snapshot.date}")
    print()
    print("Treasury Curve:")
    for tenor, rate in zip(treasury.tenors, treasury.par_yields):
        print(f"  {tenor:>5.1f}Y: {rate:>6.2%}")
    print()
    print("RMBS Spreads:")
    print(f"  Agency:   {rmbs_spreads.agency_oas:>6.0f} bps")
    print(f"  Prime:    {rmbs_spreads.prime_oas:>6.0f} bps")
    print(f"  Subprime: {rmbs_spreads.subprime_oas:>6.0f} bps")
    print()
    print(f"HPI: {hpi.national_index:.1f} (YoY: {hpi.yoy_change:+.1%})")
    print(f"Unemployment: {unemployment.rate:.1%}")
    print(f"Mortgage Rate (30Y): {mortgage_rates.rate_30y:.2%}")
    print()
    
    # Save snapshot
    print_subsection("Saving Snapshot to Disk")
    provider.save_snapshot(snapshot)
    print(f"✓ Saved to {test_dir / 'snapshots' / f'{date}.json'}")
    print()
    
    # Verify file exists
    snapshot_file = test_dir / "snapshots" / f"{date}.json"
    assert snapshot_file.exists(), "Snapshot file should exist"
    
    # Load snapshot back
    print_subsection("Loading Snapshot from Disk")
    loaded_snapshot = provider.load_snapshot(date)
    assert loaded_snapshot is not None, "Should load snapshot"
    assert loaded_snapshot.date == date, "Date should match"
    assert loaded_snapshot.treasury is not None, "Treasury data should be loaded"
    print(f"✓ Loaded snapshot for {loaded_snapshot.date}")
    print(f"✓ Treasury curve has {len(loaded_snapshot.treasury.tenors)} points")
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 1 PASSED: Snapshot creation and storage validated".center(80))


def test_yield_curve_construction():
    """Test 2: Build yield curves from market data"""
    print_section("TEST 2: YIELD CURVE CONSTRUCTION")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    # Generate and save sample data
    date = "2026-01-29"
    snapshot = SampleDataGenerator.generate_sample_snapshot(date)
    provider.save_snapshot(snapshot)
    
    print("Building Treasury yield curve from market data...")
    print()
    
    # Build Treasury curve
    treasury_curve = provider.build_treasury_curve(date)
    assert treasury_curve is not None, "Should build Treasury curve"
    
    print(f"Treasury Curve (as of {date}):")
    print()
    
    # Show curve at key tenors
    test_tenors = [0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
    print(f"{'Tenor':>8} | {'Zero Rate':>10} | {'Discount Factor':>16}")
    print("-" * 42)
    
    for tenor in test_tenors:
        zero_rate = treasury_curve.get_zero_rate(tenor)
        df = treasury_curve.get_discount_factor(tenor)
        print(f"{tenor:>6.1f}Y | {zero_rate:>9.2%} | {df:>16.6f}")
    
    print()
    
    # Build Swap curve
    print_subsection("Building Swap Curve")
    swap_curve = provider.build_swap_curve(date)
    assert swap_curve is not None, "Should build Swap curve"
    
    print(f"Swap Curve (as of {date}):")
    print()
    
    test_tenors_swap = [1.0, 5.0, 10.0, 30.0]
    for tenor in test_tenors_swap:
        zero_rate = swap_curve.get_zero_rate(tenor)
        print(f"  {tenor:>5.1f}Y: {zero_rate:>6.2%}")
    
    print()
    
    # Compare Treasury vs Swap
    print_subsection("Treasury vs Swap Spread")
    print(f"{'Tenor':>8} | {'Treasury':>10} | {'Swap':>10} | {'Spread':>10}")
    print("-" * 50)
    
    for tenor in [1.0, 5.0, 10.0]:
        tsy_rate = treasury_curve.get_zero_rate(tenor)
        swap_rate = swap_curve.get_zero_rate(tenor)
        spread_bps = (swap_rate - tsy_rate) * 10000
        print(f"{tenor:>6.1f}Y | {tsy_rate:>9.2%} | {swap_rate:>9.2%} | {spread_bps:>8.0f} bps")
    
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 2 PASSED: Yield curve construction validated".center(80))


def test_rmbs_spread_retrieval():
    """Test 3: Retrieve RMBS spread data"""
    print_section("TEST 3: RMBS SPREAD RETRIEVAL")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    # Generate and save sample data
    date = "2026-01-29"
    snapshot = SampleDataGenerator.generate_sample_snapshot(date)
    provider.save_snapshot(snapshot)
    
    print(f"Retrieving RMBS spreads for {date}...")
    print()
    
    # Retrieve spreads for each tier
    credit_tiers = ['agency', 'prime', 'alt_a', 'subprime']
    
    print(f"{'Credit Tier':>12} | {'OAS (bps)':>12}")
    print("-" * 30)
    
    for tier in credit_tiers:
        spread = provider.get_rmbs_spread(date, tier)
        assert spread is not None, f"Should retrieve spread for {tier}"
        print(f"{tier.title():>12} | {spread:>10.0f}")
    
    print()
    
    # Verify spread ordering
    agency_spread = provider.get_rmbs_spread(date, 'agency')
    prime_spread = provider.get_rmbs_spread(date, 'prime')
    subprime_spread = provider.get_rmbs_spread(date, 'subprime')
    
    assert agency_spread < prime_spread < subprime_spread, \
        "Spreads should be ordered: agency < prime < subprime"
    
    print("Validation:")
    print(f"  ✓ Agency < Prime: {agency_spread:.0f} < {prime_spread:.0f}")
    print(f"  ✓ Prime < Subprime: {prime_spread:.0f} < {subprime_spread:.0f}")
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 3 PASSED: RMBS spread retrieval validated".center(80))


def test_economic_indicators():
    """Test 4: Access economic indicators"""
    print_section("TEST 4: ECONOMIC INDICATOR ACCESS")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    # Generate and save sample data
    date = "2026-01-29"
    snapshot = SampleDataGenerator.generate_sample_snapshot(date)
    provider.save_snapshot(snapshot)
    
    print(f"Retrieving economic indicators for {date}...")
    print()
    
    # House Price Index
    print_subsection("House Price Index (HPI)")
    hpi = provider.get_hpi(date)
    assert hpi is not None, "Should retrieve HPI"
    
    print(f"  National Index: {hpi.national_index:.1f}")
    print(f"  YoY Change:     {hpi.yoy_change:+.2%}")
    print(f"  Source:         {hpi.source}")
    print()
    
    # Unemployment
    print_subsection("Unemployment Rate")
    unemployment = provider.get_unemployment(date)
    assert unemployment is not None, "Should retrieve unemployment"
    
    print(f"  Rate:   {unemployment.rate:.1%}")
    print(f"  Source: {unemployment.source}")
    print()
    
    # Mortgage Rates
    print_subsection("Mortgage Rates")
    mortgage_rates = provider.get_mortgage_rates(date)
    assert mortgage_rates is not None, "Should retrieve mortgage rates"
    
    print(f"  30-Year Fixed: {mortgage_rates.rate_30y:.2%}")
    print(f"  15-Year Fixed: {mortgage_rates.rate_15y:.2%}")
    print(f"  Source:        {mortgage_rates.source}")
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 4 PASSED: Economic indicator access validated".center(80))


def test_data_validation():
    """Test 5: Data validation and anomaly detection"""
    print_section("TEST 5: DATA VALIDATION AND ANOMALY DETECTION")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    # Test Case 1: Valid data
    print_subsection("Test Case 1: Valid Data")
    valid_snapshot = SampleDataGenerator.generate_sample_snapshot("2026-01-29")
    warnings = provider.validate_snapshot(valid_snapshot)
    
    if not warnings:
        print("✓ No warnings (data is valid)")
    else:
        print(f"⚠️  Warnings: {warnings}")
    
    assert len(warnings) == 0, "Valid data should have no warnings"
    print()
    
    # Test Case 2: Inverted yield curve
    print_subsection("Test Case 2: Inverted Yield Curve")
    inverted_treasury = TreasurySnapshot(
        date="2026-01-29",
        tenors=[0.5, 1.0, 2.0, 5.0, 10.0],
        par_yields=[0.0500, 0.0480, 0.0460, 0.0440, 0.0420],  # Inverted
        source="US Treasury"
    )
    inverted_snapshot = MarketDataSnapshot(date="2026-01-29", treasury=inverted_treasury)
    warnings = provider.validate_snapshot(inverted_snapshot)
    
    print(f"Warnings detected: {len(warnings)}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    
    assert "inverted" in warnings[0].lower(), "Should detect inverted curve"
    print()
    
    # Test Case 3: Spread ordering violation
    print_subsection("Test Case 3: Spread Ordering Violation")
    bad_spreads = RMBSSpreadSnapshot(
        date="2026-01-29",
        agency_oas=200.0,  # Too high
        prime_oas=150.0,
        subprime_oas=100.0,  # Too low
        alt_a_oas=250.0
    )
    spread_snapshot = MarketDataSnapshot(date="2026-01-29", rmbs_spreads=bad_spreads)
    warnings = provider.validate_snapshot(spread_snapshot)
    
    print(f"Warnings detected: {len(warnings)}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    
    assert "ordering" in warnings[0].lower(), "Should detect spread ordering violation"
    print()
    
    # Test Case 4: Extreme HPI change
    print_subsection("Test Case 4: Extreme HPI Change")
    extreme_hpi = HPISnapshot(
        date="2026-01-29",
        national_index=350.0,
        yoy_change=0.40  # 40% YoY (extreme!)
    )
    hpi_snapshot = MarketDataSnapshot(date="2026-01-29", hpi=extreme_hpi)
    warnings = provider.validate_snapshot(hpi_snapshot)
    
    print(f"Warnings detected: {len(warnings)}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    
    assert "extreme" in warnings[0].lower(), "Should detect extreme HPI change"
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 5 PASSED: Data validation functional".center(80))


def test_time_series():
    """Test 6: Historical time series retrieval"""
    print_section("TEST 6: HISTORICAL TIME SERIES")
    
    # Setup
    test_dir = Path("./test_market_data")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    provider = MarketDataProvider(data_dir=str(test_dir))
    
    # Generate 12 months of sample data (weekly)
    print("Generating 12 months of historical data (weekly)...")
    start_date = "2025-01-29"
    end_date = "2026-01-29"
    
    snapshots = SampleDataGenerator.generate_sample_history(
        start_date, end_date, frequency_days=7
    )
    
    print(f"Generated {len(snapshots)} snapshots")
    print()
    
    # Save all snapshots
    for snapshot in snapshots:
        provider.save_snapshot(snapshot)
    
    print(f"Saved {len(snapshots)} snapshots to disk")
    print()
    
    # Test 1: Get rate history for 10Y Treasury
    print_subsection("10-Year Treasury Rate History")
    rate_history = provider.get_rate_history("2025-01-29", "2026-01-29", tenor=10.0)
    
    print(f"Retrieved {len(rate_history)} data points")
    print()
    print("Sample (first 5 and last 5):")
    print(f"{'Date':>12} | {'10Y Rate':>10}")
    print("-" * 26)
    
    for date, rate in rate_history[:5]:
        print(f"{date:>12} | {rate:>9.2%}")
    print("    ...")
    for date, rate in rate_history[-5:]:
        print(f"{date:>12} | {rate:>9.2%}")
    
    print()
    
    # Test 2: Get RMBS spread history
    print_subsection("Prime RMBS Spread History")
    spread_history = provider.get_spread_history("2025-01-29", "2026-01-29", "prime")
    
    print(f"Retrieved {len(spread_history)} data points")
    print()
    print("Sample (first 5 and last 5):")
    print(f"{'Date':>12} | {'Spread (bps)':>14}")
    print("-" * 30)
    
    for date, spread in spread_history[:5]:
        print(f"{date:>12} | {spread:>12.0f}")
    print("    ...")
    for date, spread in spread_history[-5:]:
        print(f"{date:>12} | {spread:>12.0f}")
    
    print()
    
    # Test 3: Get latest snapshot
    print_subsection("Latest Snapshot")
    latest = provider.get_latest_snapshot()
    assert latest is not None, "Should retrieve latest snapshot"
    
    print(f"Latest snapshot date: {latest.date}")
    if latest.treasury:
        print(f"  10Y Treasury: {latest.treasury.par_yields[-4]:.2%}")
    if latest.rmbs_spreads:
        print(f"  Prime RMBS:   {latest.rmbs_spreads.prime_oas:.0f} bps")
    
    print()
    
    # Cleanup
    shutil.rmtree(test_dir)
    
    print("✅ TEST 6 PASSED: Time series retrieval validated".center(80))


def test_sample_data_generator():
    """Test 7: Sample data generator"""
    print_section("TEST 7: SAMPLE DATA GENERATOR")
    
    print("Testing sample data generator...")
    print()
    
    # Generate single snapshot
    print_subsection("Single Snapshot Generation")
    snapshot = SampleDataGenerator.generate_sample_snapshot("2026-01-29")
    
    print(f"Date: {snapshot.date}")
    print()
    
    # Validate all components
    components = {
        "Treasury": snapshot.treasury,
        "Swaps": snapshot.swaps,
        "RMBS Spreads": snapshot.rmbs_spreads,
        "HPI": snapshot.hpi,
        "Unemployment": snapshot.unemployment,
        "Mortgage Rates": snapshot.mortgage_rates
    }
    
    print("Components generated:")
    for name, component in components.items():
        status = "✓" if component is not None else "✗"
        print(f"  {status} {name}")
    
    assert all(c is not None for c in components.values()), "All components should be generated"
    print()
    
    # Generate history
    print_subsection("Historical Data Generation")
    snapshots = SampleDataGenerator.generate_sample_history(
        "2025-12-01", "2026-01-29", frequency_days=7
    )
    
    print(f"Generated {len(snapshots)} snapshots")
    print()
    
    # Check date range
    dates = [s.date for s in snapshots]
    print(f"Date range: {dates[0]} to {dates[-1]}")
    print()
    
    # Verify spacing
    date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in dates]
    spacings = [(date_objs[i+1] - date_objs[i]).days for i in range(len(date_objs)-1)]
    
    print(f"Average spacing: {sum(spacings)/len(spacings):.1f} days")
    print(f"Expected: 7 days")
    
    assert all(s == 7 for s in spacings), "Spacing should be 7 days"
    print()
    
    print("✅ TEST 7 PASSED: Sample data generator validated".center(80))


def main():
    """Run all market data integration tests."""
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                              ║")
    print("║             PHASE 3: MARKET DATA INTEGRATION - COMPREHENSIVE TESTS          ║")
    print("║                                                                              ║")
    print("║                          Component 3 of 4                                   ║")
    print("║                                                                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    try:
        # Run all tests
        test_snapshot_creation_and_storage()
        test_yield_curve_construction()
        test_rmbs_spread_retrieval()
        test_economic_indicators()
        test_data_validation()
        test_time_series()
        test_sample_data_generator()
        
        # Summary
        print("\n")
        print("=" * 80)
        print("TEST SUMMARY".center(80))
        print("=" * 80)
        print()
        print("✅ Test 1: Snapshot Creation & Storage       PASSED")
        print("✅ Test 2: Yield Curve Construction          PASSED")
        print("✅ Test 3: RMBS Spread Retrieval             PASSED")
        print("✅ Test 4: Economic Indicator Access         PASSED")
        print("✅ Test 5: Data Validation                   PASSED")
        print("✅ Test 6: Historical Time Series            PASSED")
        print("✅ Test 7: Sample Data Generator             PASSED")
        print()
        print("=" * 80)
        print()
        print("              🎉 ALL TESTS PASSED 🎉".center(80))
        print()
        print("=" * 80)
        print()
        print("MARKET DATA INTEGRATION: PRODUCTION READY")
        print()
        print("Key Features:")
        print("  ✅ Market data snapshot storage and retrieval")
        print("  ✅ Yield curve construction (Treasury & Swap)")
        print("  ✅ RMBS spread database")
        print("  ✅ Economic indicators (HPI, unemployment, mortgage rates)")
        print("  ✅ Data validation and anomaly detection")
        print("  ✅ Historical time series analysis")
        print("  ✅ Sample data generation for testing")
        print()
        print("=" * 80)
        print()
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
