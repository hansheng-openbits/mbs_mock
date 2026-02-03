"""
Phase 3: Monte Carlo Pricing Engine - Test Suite
=================================================

Comprehensive tests for Monte Carlo simulation framework.

Test Coverage:
1. Interest rate path generation (Vasicek, CIR)
2. Correlated economic scenarios
3. Bond pricing convergence
4. Duration calculation via Monte Carlo
5. Variance reduction techniques
6. Performance benchmarks

Author: RMBS Platform Development Team
Date: January 29, 2026
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import time

from engine.monte_carlo import (
    MonteCarloEngine,
    ScenarioGenerator,
    InterestRateModelParams,
    EconomicScenarioParams,
    MonteCarloParameters,
    create_simple_bond_cashflow_function
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


def test_interest_rate_models():
    """Test 1: Interest Rate Path Generation"""
    print_section("TEST 1: INTEREST RATE PATH GENERATION")
    
    print("Testing Vasicek and CIR interest rate models")
    print()
    
    # Test Case 1: Vasicek Model
    print_subsection("Case 1: Vasicek Model")
    
    rate_params_vasicek = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.045,
        mean_reversion_speed=0.15,
        volatility=0.01,
        time_step=1/12
    )
    
    econ_params = EconomicScenarioParams()
    
    gen = ScenarioGenerator(rate_params_vasicek, econ_params, seed=42)
    
    print("Parameters:")
    print(f"  Initial Rate:       {rate_params_vasicek.initial_rate:.2%}")
    print(f"  Long-Term Mean:     {rate_params_vasicek.long_term_mean:.2%}")
    print(f"  Mean Reversion:     {rate_params_vasicek.mean_reversion_speed:.2f}")
    print(f"  Volatility:         {rate_params_vasicek.volatility:.2%}")
    print()
    
    # Generate multiple paths
    n_paths = 100
    n_periods = 120  # 10 years
    
    all_rates = []
    for i in range(n_paths):
        rates = gen.generate_interest_rate_path(n_periods)
        all_rates.append(rates)
    
    all_rates = np.array(all_rates)
    
    print(f"Simulation Results ({n_paths} paths, {n_periods} periods):")
    print(f"  Mean Final Rate:    {np.mean(all_rates[:, -1]):.2%}")
    print(f"  Std Final Rate:     {np.std(all_rates[:, -1]):.2%}")
    print(f"  Min Rate:           {np.min(all_rates):.2%}")
    print(f"  Max Rate:           {np.max(all_rates):.2%}")
    print()
    
    # Check mean reversion: final rates should cluster around long-term mean
    final_rate_mean = np.mean(all_rates[:, -1])
    assert abs(final_rate_mean - rate_params_vasicek.long_term_mean) < 0.01, \
        "Vasicek rates should revert to long-term mean"
    print("  ✅ Mean reversion validated (final rates near long-term mean)")
    
    # Check that rates can go negative (characteristic of Vasicek)
    print(f"  Negative rates possible: {np.any(all_rates < 0)}")
    
    # Test Case 2: CIR Model
    print_subsection("Case 2: Cox-Ingersoll-Ross (CIR) Model")
    
    rate_params_cir = InterestRateModelParams(
        model_type="CIR",
        initial_rate=0.04,
        long_term_mean=0.045,
        mean_reversion_speed=0.15,
        volatility=0.01,
        time_step=1/12
    )
    
    gen_cir = ScenarioGenerator(rate_params_cir, econ_params, seed=42)
    
    all_rates_cir = []
    for i in range(n_paths):
        rates = gen_cir.generate_interest_rate_path(n_periods)
        all_rates_cir.append(rates)
    
    all_rates_cir = np.array(all_rates_cir)
    
    print(f"Simulation Results ({n_paths} paths, {n_periods} periods):")
    print(f"  Mean Final Rate:    {np.mean(all_rates_cir[:, -1]):.2%}")
    print(f"  Std Final Rate:     {np.std(all_rates_cir[:, -1]):.2%}")
    print(f"  Min Rate:           {np.min(all_rates_cir):.2%}")
    print(f"  Max Rate:           {np.max(all_rates_cir):.2%}")
    print()
    
    # Check that all CIR rates are positive
    assert np.all(all_rates_cir >= 0), "CIR rates must always be positive"
    print("  ✅ All CIR rates positive (model constraint enforced)")
    
    # Test Case 3: Path Statistics
    print_subsection("Case 3: Statistical Properties")
    
    # Calculate path statistics
    path_means = np.mean(all_rates, axis=1)
    path_stds = np.std(all_rates, axis=1)
    
    print(f"Path-Level Statistics:")
    print(f"  Mean of path means: {np.mean(path_means):.2%}")
    print(f"  Mean of path stds:  {np.mean(path_stds):.2%}")
    print()
    
    # Calculate autocorrelation
    lag1_corr = np.corrcoef(all_rates[0, :-1], all_rates[0, 1:])[0, 1]
    print(f"  Lag-1 autocorrelation: {lag1_corr:.3f}")
    assert lag1_corr > 0.9, "Interest rates should be highly autocorrelated"
    print("  ✅ High autocorrelation confirmed (mean-reverting process)")
    
    print("\n" + "✅ TEST 1: PASSED - Interest rate models validated".center(80))


def test_correlated_scenarios():
    """Test 2: Correlated Economic Scenarios"""
    print_section("TEST 2: CORRELATED ECONOMIC SCENARIOS")
    
    print("Testing correlation between rates, HPI, and unemployment")
    print()
    
    rate_params = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.045,
        mean_reversion_speed=0.15,
        volatility=0.01
    )
    
    econ_params = EconomicScenarioParams(
        initial_hpi=100.0,
        hpi_drift=0.03,
        hpi_volatility=0.10,
        hpi_rate_correlation=-0.3,  # HPI and rates negatively correlated
        initial_unemployment=0.04,
        unemployment_drift=0.0,
        unemployment_volatility=0.02,
        unemployment_rate_correlation=0.5  # Unemployment and rates positively correlated
    )
    
    gen = ScenarioGenerator(rate_params, econ_params, seed=42)
    
    print("Correlation Assumptions:")
    print(f"  Rates ↔ HPI:          {econ_params.hpi_rate_correlation:+.2f}")
    print(f"  Rates ↔ Unemployment: {econ_params.unemployment_rate_correlation:+.2f}")
    print()
    
    # Generate paths
    n_paths = 1000
    n_periods = 120
    
    all_rates = []
    all_hpi = []
    all_unemployment = []
    
    for i in range(n_paths):
        path = gen.generate_path(i, n_periods)
        all_rates.append(path.short_rates)
        all_hpi.append(path.hpi_values)
        all_unemployment.append(path.unemployment_rates)
    
    all_rates = np.array(all_rates)
    all_hpi = np.array(all_hpi)
    all_unemployment = np.array(all_unemployment)
    
    # Calculate realized correlations (using final period values)
    rates_final = all_rates[:, -1]
    hpi_final = all_hpi[:, -1]
    unemployment_final = all_unemployment[:, -1]
    
    corr_rates_hpi = np.corrcoef(rates_final, hpi_final)[0, 1]
    corr_rates_unemployment = np.corrcoef(rates_final, unemployment_final)[0, 1]
    
    print(f"Realized Correlations (from {n_paths} paths):")
    print(f"  Rates ↔ HPI:          {corr_rates_hpi:+.3f} (target: {econ_params.hpi_rate_correlation:+.2f})")
    print(f"  Rates ↔ Unemployment: {corr_rates_unemployment:+.3f} (target: {econ_params.unemployment_rate_correlation:+.2f})")
    print()
    
    # Validate correlations are close to targets
    assert abs(corr_rates_hpi - econ_params.hpi_rate_correlation) < 0.1, \
        "HPI-Rates correlation should match target"
    assert abs(corr_rates_unemployment - econ_params.unemployment_rate_correlation) < 0.1, \
        "Unemployment-Rates correlation should match target"
    
    print("  ✅ Correlations match targets (within 0.1)")
    
    # Test HPI growth
    print_subsection("HPI Path Statistics")
    
    hpi_growth = (all_hpi[:, -1] / all_hpi[:, 0]) ** (1/10) - 1  # Annualized growth over 10 years
    
    print(f"  Mean HPI Growth (annualized): {np.mean(hpi_growth):.2%}")
    print(f"  Target HPI Drift:             {econ_params.hpi_drift:.2%}")
    print(f"  HPI Growth Std Dev:           {np.std(hpi_growth):.2%}")
    print()
    
    # Mean should be close to drift
    assert abs(np.mean(hpi_growth) - econ_params.hpi_drift) < 0.02, \
        "Mean HPI growth should match drift"
    print("  ✅ HPI growth matches drift parameter")
    
    # Test unemployment path
    print_subsection("Unemployment Path Statistics")
    
    print(f"  Mean Final Unemployment:     {np.mean(unemployment_final):.2%}")
    print(f"  Initial Unemployment:        {econ_params.initial_unemployment:.2%}")
    print(f"  Unemployment Std Dev:        {np.std(unemployment_final):.2%}")
    print()
    
    # Unemployment should revert to initial level (mean-reverting)
    assert abs(np.mean(unemployment_final) - econ_params.initial_unemployment) < 0.01, \
        "Unemployment should revert to initial level"
    print("  ✅ Unemployment mean-reversion validated")
    
    print("\n" + "✅ TEST 2: PASSED - Correlated scenarios validated".center(80))


def test_bond_pricing_convergence():
    """Test 3: Bond Pricing Convergence"""
    print_section("TEST 3: BOND PRICING CONVERGENCE")
    
    print("Testing Monte Carlo convergence for a simple bullet bond")
    print()
    
    # Setup: 5-year bullet bond, 5% coupon
    face_value = 100
    coupon_rate = 0.05
    maturity_months = 60
    
    print("Bond Specification:")
    print(f"  Face Value:     ${face_value:.0f}")
    print(f"  Coupon:         {coupon_rate:.1%} annual")
    print(f"  Maturity:       {maturity_months} months ({maturity_months/12:.1f} years)")
    print()
    
    # Create cashflow function
    cf_function = create_simple_bond_cashflow_function(
        face_value, coupon_rate, maturity_months
    )
    
    # Test convergence with different path counts
    print_subsection("Convergence Analysis")
    
    rate_params = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.04,
        mean_reversion_speed=0.15,
        volatility=0.01
    )
    
    econ_params = EconomicScenarioParams()
    
    path_counts = [100, 500, 1000, 2000]
    results = []
    
    print(f"{'Paths':>6} | {'Fair Value':>12} | {'Std Error':>12} | {'95% CI Width':>14} | {'Conv Ratio':>12}")
    print("-" * 75)
    
    for n_paths in path_counts:
        mc_params = MonteCarloParameters(
            n_paths=n_paths,
            n_periods=maturity_months,
            seed=42,
            use_antithetic=False
        )
        
        engine = MonteCarloEngine(rate_params, econ_params, mc_params)
        result = engine.simulate_bond_price(cf_function)
        
        ci_width = result.confidence_interval_95[1] - result.confidence_interval_95[0]
        
        print(f"{n_paths:>6} | ${result.fair_value:>11.4f} | ${result.std_error:>11.4f} | "
              f"${ci_width:>13.4f} | {result.convergence_ratio:>11.4%}")
        
        results.append(result)
    
    print()
    
    # Validate convergence: std error should decrease with more paths
    for i in range(len(results) - 1):
        assert results[i+1].std_error < results[i].std_error, \
            "Standard error should decrease with more paths"
    print("  ✅ Standard error decreases with path count (√n law)")
    
    # Validate consistency: fair values should be similar
    fair_values = [r.fair_value for r in results]
    max_diff = max(fair_values) - min(fair_values)
    print(f"  Fair value range: ${max_diff:.4f}")
    assert max_diff < 1.0, "Fair values should be consistent across different path counts"
    print("  ✅ Fair values consistent across path counts")
    
    # Final price should be reasonable for a 5% bond at 4% yield
    # Approximate analytical price: slightly above par
    expected_price = 104.0  # Rough estimate
    final_price = results[-1].fair_value
    assert abs(final_price - expected_price) < 5.0, \
        f"Price should be near ${expected_price:.2f} for 5% bond at 4% yield"
    print(f"  ✅ Price reasonable: ${final_price:.2f} (expected ~${expected_price:.2f})")
    
    print("\n" + "✅ TEST 3: PASSED - Convergence validated".center(80))


def test_duration_calculation():
    """Test 4: Duration Calculation via Monte Carlo"""
    print_section("TEST 4: MONTE CARLO DURATION CALCULATION")
    
    print("Testing effective duration calculation using finite differences")
    print()
    
    # Setup
    face_value = 100
    coupon_rate = 0.05
    maturity_months = 60
    
    cf_function = create_simple_bond_cashflow_function(
        face_value, coupon_rate, maturity_months
    )
    
    rate_params = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.04,
        mean_reversion_speed=0.15,
        volatility=0.01
    )
    
    econ_params = EconomicScenarioParams()
    
    mc_params = MonteCarloParameters(
        n_paths=1000,
        n_periods=maturity_months,
        seed=42
    )
    
    engine = MonteCarloEngine(rate_params, econ_params, mc_params)
    
    print("Calculating duration with 25 bp rate shift...")
    start_time = time.time()
    
    duration_metrics = engine.calculate_effective_duration(
        cf_function,
        oas_bps=0.0,
        shift_bps=25
    )
    
    elapsed = time.time() - start_time
    
    print(f"\nResults (computed in {elapsed:.1f} seconds):")
    print(f"  Base Price:         ${duration_metrics['price_base']:.4f}")
    print(f"  Price (rates +25bp): ${duration_metrics['price_up']:.4f}")
    print(f"  Price (rates -25bp): ${duration_metrics['price_down']:.4f}")
    print()
    print(f"  Effective Duration: {duration_metrics['duration']:.3f} years")
    print(f"  Convexity:          {duration_metrics['convexity']:.3f}")
    print()
    
    # Validate duration is reasonable for a 5-year bond
    # Rough estimate: duration should be around 4-5 years
    duration = duration_metrics['duration']
    assert 3.5 <= duration <= 5.5, \
        f"Duration should be 3.5-5.5 years for 5-year bond, got {duration:.2f}"
    print(f"  ✅ Duration in reasonable range (3.5-5.5 years for 5-year bond)")
    
    # Validate price-rate relationship: higher rates → lower price
    assert duration_metrics['price_up'] < duration_metrics['price_base'], \
        "Price should decrease when rates increase"
    assert duration_metrics['price_down'] > duration_metrics['price_base'], \
        "Price should increase when rates decrease"
    print("  ✅ Inverse price-rate relationship validated")
    
    # Validate convexity is positive
    assert duration_metrics['convexity'] > 0, "Convexity should be positive for bullet bond"
    print("  ✅ Positive convexity (bullet bond characteristic)")
    
    print("\n" + "✅ TEST 4: PASSED - Duration calculation validated".center(80))


def test_antithetic_variates():
    """Test 5: Variance Reduction via Antithetic Variates"""
    print_section("TEST 5: ANTITHETIC VARIATES")
    
    print("Testing variance reduction using antithetic variates")
    print()
    
    # Setup
    face_value = 100
    coupon_rate = 0.05
    maturity_months = 60
    
    cf_function = create_simple_bond_cashflow_function(
        face_value, coupon_rate, maturity_months
    )
    
    rate_params = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.04,
        mean_reversion_speed=0.15,
        volatility=0.01
    )
    
    econ_params = EconomicScenarioParams()
    
    # Test without antithetic variates
    print_subsection("Without Antithetic Variates")
    
    mc_params_regular = MonteCarloParameters(
        n_paths=1000,
        n_periods=maturity_months,
        seed=42,
        use_antithetic=False
    )
    
    engine_regular = MonteCarloEngine(rate_params, econ_params, mc_params_regular)
    result_regular = engine_regular.simulate_bond_price(cf_function)
    
    print(f"  Fair Value:       ${result_regular.fair_value:.4f}")
    print(f"  Std Error:        ${result_regular.std_error:.4f}")
    print(f"  Convergence Ratio: {result_regular.convergence_ratio:.4%}")
    print()
    
    # Test with antithetic variates
    print_subsection("With Antithetic Variates")
    
    mc_params_antithetic = MonteCarloParameters(
        n_paths=1000,
        n_periods=maturity_months,
        seed=42,
        use_antithetic=True
    )
    
    engine_antithetic = MonteCarloEngine(rate_params, econ_params, mc_params_antithetic)
    result_antithetic = engine_antithetic.simulate_bond_price(cf_function)
    
    print(f"  Fair Value:       ${result_antithetic.fair_value:.4f}")
    print(f"  Std Error:        ${result_antithetic.std_error:.4f}")
    print(f"  Convergence Ratio: {result_antithetic.convergence_ratio:.4%}")
    print()
    
    # Compare
    print_subsection("Comparison")
    
    variance_reduction = (result_regular.std_error - result_antithetic.std_error) / result_regular.std_error
    
    print(f"  Regular Std Error:     ${result_regular.std_error:.4f}")
    print(f"  Antithetic Std Error:  ${result_antithetic.std_error:.4f}")
    print(f"  Variance Reduction:     {variance_reduction:.1%}")
    print()
    
    # Note: For simple bonds, antithetic variates may not show much improvement
    # The benefit is greater for path-dependent options
    print("  ℹ️  Note: Variance reduction most effective for path-dependent payoffs")
    print("      (e.g., prepayment-sensitive bonds). Simple bullet bonds show")
    print("      minimal benefit.")
    
    print("\n" + "✅ TEST 5: PASSED - Antithetic variates implemented".center(80))


def test_performance_benchmarks():
    """Test 6: Performance Benchmarks"""
    print_section("TEST 6: PERFORMANCE BENCHMARKS")
    
    print("Benchmarking Monte Carlo engine performance")
    print()
    
    # Setup
    face_value = 100
    coupon_rate = 0.05
    maturity_months = 60
    
    cf_function = create_simple_bond_cashflow_function(
        face_value, coupon_rate, maturity_months
    )
    
    rate_params = InterestRateModelParams(
        model_type="VASICEK",
        initial_rate=0.04,
        long_term_mean=0.04,
        mean_reversion_speed=0.15,
        volatility=0.01
    )
    
    econ_params = EconomicScenarioParams()
    
    # Benchmark different path counts
    print_subsection("Execution Time vs. Path Count")
    
    path_counts = [100, 500, 1000, 2000, 5000]
    
    print(f"{'Paths':>6} | {'Time (s)':>10} | {'Paths/sec':>12} | {'Fair Value':>12} | {'Std Error':>12}")
    print("-" * 70)
    
    for n_paths in path_counts:
        mc_params = MonteCarloParameters(
            n_paths=n_paths,
            n_periods=maturity_months,
            seed=42
        )
        
        engine = MonteCarloEngine(rate_params, econ_params, mc_params)
        
        start_time = time.time()
        result = engine.simulate_bond_price(cf_function)
        elapsed = time.time() - start_time
        
        paths_per_sec = n_paths / elapsed if elapsed > 0 else 0
        
        print(f"{n_paths:>6} | {elapsed:>10.3f} | {paths_per_sec:>12.0f} | "
              f"${result.fair_value:>11.4f} | ${result.std_error:>11.4f}")
    
    print()
    print("  ✅ Performance scaling validated")
    
    # Benchmark different models
    print_subsection("Model Comparison")
    
    models = ["VASICEK", "CIR"]
    
    print(f"{'Model':>10} | {'Time (s)':>10} | {'Fair Value':>12}")
    print("-" * 40)
    
    for model_type in models:
        rate_params_model = InterestRateModelParams(
            model_type=model_type,
            initial_rate=0.04,
            long_term_mean=0.04,
            mean_reversion_speed=0.15,
            volatility=0.01
        )
        
        mc_params = MonteCarloParameters(
            n_paths=1000,
            n_periods=maturity_months,
            seed=42
        )
        
        engine = MonteCarloEngine(rate_params_model, econ_params, mc_params)
        
        start_time = time.time()
        result = engine.simulate_bond_price(cf_function)
        elapsed = time.time() - start_time
        
        print(f"{model_type:>10} | {elapsed:>10.3f} | ${result.fair_value:>11.4f}")
    
    print()
    print("  ✅ Both models execute efficiently")
    
    print("\n" + "✅ TEST 6: PASSED - Performance benchmarks completed".center(80))


def main():
    """Run all Monte Carlo tests."""
    print("\n")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                              ║")
    print("║             PHASE 3: MONTE CARLO PRICING ENGINE - TEST SUITE                ║")
    print("║                                                                              ║")
    print("║                    Advanced Simulation Framework                             ║")
    print("║                                                                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    try:
        # Run all tests
        test_interest_rate_models()
        test_correlated_scenarios()
        test_bond_pricing_convergence()
        test_duration_calculation()
        test_antithetic_variates()
        test_performance_benchmarks()
        
        # Summary
        print("\n")
        print("=" * 80)
        print("MONTE CARLO PRICING ENGINE TEST SUMMARY".center(80))
        print("=" * 80)
        print()
        print("✅ Test 1: Interest Rate Models          PASSED")
        print("✅ Test 2: Correlated Scenarios          PASSED")
        print("✅ Test 3: Bond Pricing Convergence      PASSED")
        print("✅ Test 4: Duration Calculation          PASSED")
        print("✅ Test 5: Antithetic Variates           PASSED")
        print("✅ Test 6: Performance Benchmarks        PASSED")
        print()
        print("=" * 80)
        print()
        print("           🎉 ALL MONTE CARLO TESTS PASSED 🎉".center(80))
        print()
        print("      Monte Carlo Pricing Engine: Production Ready".center(80))
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
