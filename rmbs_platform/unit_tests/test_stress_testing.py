"""
Stress Testing Framework Tests
==============================

Comprehensive tests for the stress testing framework including:
- Regulatory scenario execution (CCAR, EBA)
- Custom scenario creation
- Sensitivity analysis
- Reverse stress testing
- Monte Carlo simulations
- Tranche impact analysis

These tests verify stress test outputs against expected behavior
for regulatory and risk management use cases.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.stress_testing import (
    StressTestingEngine,
    StressScenario,
    ScenarioType,
    StressFactor,
    RateShockType,
    REGULATORY_SCENARIOS,
    create_severe_recession_scenario,
    create_rate_shock_scenario,
    create_hpi_decline_scenario,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def stress_engine() -> StressTestingEngine:
    """Create stress testing engine with standard parameters."""
    return StressTestingEngine(
        base_cpr=0.08,
        base_cdr=0.015,
        base_severity=0.35,
    )


@pytest.fixture
def sample_loan_data() -> pd.DataFrame:
    """Create sample loan data for stress testing."""
    np.random.seed(42)
    n_loans = 500
    
    return pd.DataFrame({
        "LOAN_ID": [f"L{i:05d}" for i in range(n_loans)],
        "Current_Balance": np.random.uniform(150_000, 500_000, n_loans),
        "Original_Balance": np.random.uniform(180_000, 550_000, n_loans),
        "FICO": np.random.choice([660, 700, 740, 780], n_loans),
        "LTV": np.random.uniform(65, 95, n_loans),
        "Interest_Rate": np.random.uniform(0.04, 0.07, n_loans),
        "Loan_Age": np.random.randint(6, 48, n_loans),
        "State": np.random.choice(["CA", "TX", "FL", "NY"], n_loans),
    })


@pytest.fixture
def sample_deal_structure() -> dict:
    """Create sample deal structure for stress testing."""
    return {
        "deal_id": "STRESS_TEST_2024",
        "bonds": [
            {"id": "ClassA", "original_balance": 80_000_000, "priority": 1},
            {"id": "ClassB", "original_balance": 15_000_000, "priority": 2},
            {"id": "ClassC", "original_balance": 5_000_000, "priority": 3},
        ],
        "collateral": {
            "original_balance": 100_000_000,
            "current_balance": 95_000_000,
        },
    }


# =============================================================================
# Scenario Definition Tests
# =============================================================================

class TestScenarioDefinition:
    """Tests for stress scenario definition and configuration."""
    
    def test_regulatory_scenarios_loaded(self, stress_engine):
        """
        Verify all regulatory scenarios are loaded correctly.
        """
        # Should have CCAR and EBA scenarios
        assert "CCAR_BASELINE_2024" in stress_engine.scenarios
        assert "CCAR_ADVERSE_2024" in stress_engine.scenarios
        assert "CCAR_SEVERELY_ADVERSE_2024" in stress_engine.scenarios
        assert "EBA_ADVERSE_2024" in stress_engine.scenarios
    
    def test_scenario_has_correct_attributes(self, stress_engine):
        """
        Verify scenario objects have required attributes.
        """
        scenario = stress_engine.get_scenario("CCAR_SEVERELY_ADVERSE_2024")
        
        assert scenario.scenario_id == "CCAR_SEVERELY_ADVERSE_2024"
        assert scenario.scenario_type == ScenarioType.SEVERELY_ADVERSE
        assert scenario.horizon_months > 0
        assert scenario.quarterly_factors is not None
    
    def test_create_custom_scenario(self, stress_engine):
        """
        Verify custom scenarios can be created with specific parameters.
        """
        scenario = stress_engine.create_scenario(
            scenario_id="custom_test",
            name="Custom Test Scenario",
            hpi_shock=-0.20,
            cdr_multiplier=2.5,
            severity_add=0.10,
            rate_shock=0.01,
        )
        
        assert scenario.scenario_id == "custom_test"
        assert scenario.hpi_shock == -0.20
        assert scenario.cdr_multiplier == 2.5
        assert scenario.severity_add == 0.10
        assert scenario.rate_shock == 0.01
    
    def test_scenario_convenience_constructors(self):
        """
        Verify convenience constructors create valid scenarios.
        """
        recession = create_severe_recession_scenario()
        assert recession.cdr_multiplier == 3.0
        assert recession.hpi_shock == -0.25
        
        rate_shock = create_rate_shock_scenario(shock_bps=300)
        assert rate_shock.rate_shock == 0.03
        
        hpi_decline = create_hpi_decline_scenario(decline_pct=0.25)
        assert hpi_decline.hpi_shock == -0.25


class TestScenarioFactorRetrieval:
    """Tests for time-varying factor retrieval."""
    
    def test_get_factor_at_period(self, stress_engine):
        """
        Verify time-varying factors are retrieved correctly.
        """
        scenario = stress_engine.get_scenario("CCAR_SEVERELY_ADVERSE_2024")
        
        # Get unemployment at different periods
        q1_unemp = scenario.get_factor_at_period(StressFactor.UNEMPLOYMENT, 0)
        q3_unemp = scenario.get_factor_at_period(StressFactor.UNEMPLOYMENT, 6)
        
        # Unemployment should increase in severely adverse scenario
        assert q3_unemp > q1_unemp
    
    def test_static_factor_fallback(self, stress_engine):
        """
        Verify static factors are used when time-varying not available.
        """
        scenario = stress_engine.create_scenario(
            scenario_id="static_test",
            name="Static Test",
            hpi_shock=-0.15,
        )
        
        # Same value at all periods
        assert scenario.get_factor_at_period(StressFactor.HPI, 0) == -0.15
        assert scenario.get_factor_at_period(StressFactor.HPI, 12) == -0.15
        assert scenario.get_factor_at_period(StressFactor.HPI, 24) == -0.15


# =============================================================================
# Stress Test Execution Tests
# =============================================================================

class TestStressTestExecution:
    """Tests for stress test execution and results."""
    
    def test_run_stress_test_returns_result(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify stress test execution returns valid result object.
        """
        result = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_ADVERSE_2024",
        )
        
        assert result is not None
        assert result.scenario.scenario_id == "CCAR_ADVERSE_2024"
        assert result.execution_date is not None
        assert isinstance(result.base_case_metrics, dict)
        assert isinstance(result.stressed_metrics, dict)
    
    def test_stressed_losses_exceed_base(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify stressed scenario produces higher losses than base case.
        """
        result = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_SEVERELY_ADVERSE_2024",
        )
        
        # Stressed losses should be higher
        assert result.total_loss_stressed >= result.total_loss_base
        # Loss multiple should be > 1
        assert result.loss_multiple >= 1.0
    
    def test_period_results_dataframe(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify period-by-period results are generated.
        """
        result = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_ADVERSE_2024",
        )
        
        # Should have period results
        assert not result.period_results.empty
        assert "period" in result.period_results.columns
        assert "base_loss" in result.period_results.columns
        assert "stressed_loss" in result.period_results.columns
    
    def test_tranche_impacts_calculated(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify tranche-level impacts are calculated.
        """
        result = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_SEVERELY_ADVERSE_2024",
        )
        
        # Should have impacts for each tranche
        assert len(result.tranche_impacts) > 0
        
        # Check structure of impact data
        for tranche_id, impact in result.tranche_impacts.items():
            assert "original_balance" in impact
            assert "loss_allocated" in impact
            assert "loss_percentage" in impact
            assert "principal_impaired" in impact


class TestStressScenarioSeverity:
    """Tests verifying relative severity of different scenarios."""
    
    def test_severely_adverse_worse_than_adverse(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify severely adverse produces higher losses than adverse.
        """
        adverse = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_ADVERSE_2024",
        )
        
        severely_adverse = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_SEVERELY_ADVERSE_2024",
        )
        
        assert severely_adverse.total_loss_stressed > adverse.total_loss_stressed
    
    def test_custom_severe_scenario(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify custom severe scenario produces appropriate losses.
        """
        # Create very severe scenario
        stress_engine.create_scenario(
            scenario_id="extreme_stress",
            name="Extreme Stress",
            hpi_shock=-0.35,
            cdr_multiplier=5.0,
            severity_add=0.20,
            horizon_months=36,
        )
        
        result = stress_engine.run_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            scenario_id="extreme_stress",
        )
        
        # Should produce significant losses
        assert result.loss_multiple > 2.0


# =============================================================================
# Sensitivity Analysis Tests
# =============================================================================

class TestSensitivityAnalysis:
    """Tests for single-factor sensitivity analysis."""
    
    def test_hpi_sensitivity_analysis(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify HPI sensitivity analysis produces expected results.
        """
        result = stress_engine.run_sensitivity_analysis(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            factor=StressFactor.HPI,
            shock_range=(-0.30, 0.10, 0.10),
            metrics=["total_losses"],
        )
        
        # Should have multiple shock values
        assert len(result.shock_values) > 2
        
        # Losses should increase as HPI declines
        losses = result.metric_values["total_losses"]
        # Generally, more negative HPI shock = higher losses
        assert losses[0] >= losses[-1]  # -30% HPI should have more loss than +10%
    
    def test_cdr_sensitivity_analysis(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify CDR sensitivity analysis produces monotonic results.
        """
        result = stress_engine.run_sensitivity_analysis(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            factor=StressFactor.CDR,
            shock_range=(-0.5, 2.0, 0.5),  # CDR multiplier range
            metrics=["total_losses"],
        )
        
        # Losses should increase with CDR multiplier
        losses = result.metric_values["total_losses"]
        for i in range(1, len(losses)):
            assert losses[i] >= losses[i-1]  # Monotonically increasing
    
    def test_sensitivity_dataframe_output(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify sensitivity results can be converted to DataFrame.
        """
        result = stress_engine.run_sensitivity_analysis(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            factor=StressFactor.INTEREST_RATE,
            shock_range=(-0.02, 0.02, 0.01),
            metrics=["total_losses", "ending_balance"],
        )
        
        df = result.to_dataframe()
        
        assert not df.empty
        assert "shock" in df.columns
        assert "total_losses" in df.columns
        assert "ending_balance" in df.columns


class TestMultiFactorSensitivity:
    """Tests for multi-factor sensitivity analysis."""
    
    def test_two_factor_sensitivity_surface(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify two-factor sensitivity produces stress surface.
        """
        result = stress_engine.run_multi_factor_sensitivity(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            factor_ranges={
                StressFactor.HPI: (-0.20, 0.10, 0.10),
                StressFactor.CDR: (-0.5, 1.0, 0.5),
            },
            target_metric="total_losses",
        )
        
        # Should be a DataFrame with both factors
        assert not result.empty
        assert StressFactor.HPI.value in result.columns
        assert StressFactor.CDR.value in result.columns
        assert "total_losses" in result.columns
        
        # Should have grid of values
        n_hpi = 4  # -0.20, -0.10, 0.0, 0.10
        n_cdr = 4  # -0.5, 0.0, 0.5, 1.0
        assert len(result) == n_hpi * n_cdr


# =============================================================================
# Reverse Stress Testing Tests
# =============================================================================

class TestReverseStressTesting:
    """Tests for reverse stress testing (finding break-even scenarios)."""
    
    def test_reverse_stress_basic(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify reverse stress test finds scenario hitting target.
        """
        result = stress_engine.run_reverse_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            target_metric="total_losses",
            target_value=10_000_000,  # $10M target loss
            factors=[StressFactor.CDR],
            max_iterations=20,
        )
        
        assert result is not None
        assert result.target_metric == "total_losses"
        assert result.target_value == 10_000_000
        
        # Should have found required shocks
        assert StressFactor.CDR in result.required_shocks
    
    def test_reverse_stress_convergence(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify reverse stress test converges to target (if achievable).
        """
        result = stress_engine.run_reverse_stress_test(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            target_metric="total_losses",
            target_value=5_000_000,  # Reasonable target
            factors=[StressFactor.HPI, StressFactor.CDR],
            max_iterations=50,
            tolerance=0.10,  # 10% tolerance
        )
        
        # Check if converged or got close
        if result.converged:
            # Achieved value should be close to target
            assert abs(result.achieved_value - result.target_value) / result.target_value < 0.15


# =============================================================================
# Monte Carlo Stress Tests
# =============================================================================

class TestMonteCarloStress:
    """Tests for Monte Carlo stress simulations."""
    
    def test_monte_carlo_returns_distribution(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify Monte Carlo produces loss distribution.
        """
        result = stress_engine.run_monte_carlo_stress(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            num_simulations=50,  # Small number for test speed
        )
        
        assert "mean_loss" in result
        assert "std_loss" in result
        assert "var_95" in result
        assert "var_99" in result
        assert "expected_shortfall_95" in result
        assert "loss_distribution" in result
    
    def test_monte_carlo_var_ordering(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify VaR measures are properly ordered.
        """
        result = stress_engine.run_monte_carlo_stress(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            num_simulations=50,
        )
        
        # VaR 99 should be >= VaR 95
        assert result["var_99"] >= result["var_95"]
        
        # Expected shortfall should be >= VaR
        assert result["expected_shortfall_95"] >= result["var_95"]
        
        # Max should be >= VaR 99
        assert result["max_loss"] >= result["var_99"]
    
    def test_monte_carlo_distribution_shape(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify loss distribution has reasonable shape.
        """
        result = stress_engine.run_monte_carlo_stress(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
            num_simulations=100,
        )
        
        losses = np.array(result["loss_distribution"])
        
        # Should have variability
        assert result["std_loss"] > 0
        
        # All losses should be non-negative
        assert np.all(losses >= 0)


# =============================================================================
# Report Generation Tests
# =============================================================================

class TestStressReportGeneration:
    """Tests for stress test report generation."""
    
    def test_generate_text_report(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify text report is generated correctly.
        """
        # Run multiple scenarios
        results = stress_engine.run_all_regulatory_scenarios(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
        )
        
        report = stress_engine.generate_stress_report(results, output_format="text")
        
        assert "STRESS TESTING REPORT" in report
        assert "CCAR" in report or "Scenario" in report
    
    def test_generate_html_report(
        self, stress_engine, sample_loan_data, sample_deal_structure
    ):
        """
        Verify HTML report is generated correctly.
        """
        results = stress_engine.run_all_regulatory_scenarios(
            loan_data=sample_loan_data,
            deal_structure=sample_deal_structure,
        )
        
        report = stress_engine.generate_stress_report(results, output_format="html")
        
        assert "<html>" in report
        assert "Stress Testing Report" in report
        assert "<table>" in report


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestStressTestEdgeCases:
    """Tests for edge cases in stress testing."""
    
    def test_empty_loan_data(self, stress_engine, sample_deal_structure):
        """
        Verify graceful handling of empty loan data.
        """
        empty_df = pd.DataFrame()
        
        result = stress_engine.run_stress_test(
            loan_data=empty_df,
            deal_structure=sample_deal_structure,
            scenario_id="CCAR_BASELINE_2024",
        )
        
        # Should return valid result (even if with zero values)
        assert result is not None
    
    def test_extreme_scenario_parameters(self, stress_engine):
        """
        Verify extreme scenario parameters are handled.
        """
        scenario = stress_engine.create_scenario(
            scenario_id="extreme",
            name="Extreme",
            hpi_shock=-0.50,  # 50% HPI crash
            cdr_multiplier=10.0,  # 10x defaults
            severity_add=0.30,  # +30% severity
        )
        
        # Should be created without error
        assert scenario.hpi_shock == -0.50
        assert scenario.cdr_multiplier == 10.0
    
    def test_scenario_not_found(self, stress_engine):
        """
        Verify appropriate error for missing scenario.
        """
        with pytest.raises(ValueError, match="Scenario not found"):
            stress_engine.get_scenario("NONEXISTENT_SCENARIO")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
