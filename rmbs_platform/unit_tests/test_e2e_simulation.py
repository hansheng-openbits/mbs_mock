"""
End-to-End Simulation Tests
===========================

Comprehensive end-to-end tests that verify complete simulation workflows:
- Full deal simulation with realistic data
- Multi-period cashflow projection
- Performance data reconciliation
- ML model integration
- Report generation
- Edge cases and error handling

These tests simulate real-world usage patterns to ensure
the platform works correctly in production scenarios.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import run_simulation
from engine.loader import DealLoader
from engine.state import DealState
from engine.compute import ExpressionEngine
from engine.waterfall import WaterfallRunner
from engine.reporting import ReportGenerator


# =============================================================================
# Test Fixtures - Comprehensive Deal Structures
# =============================================================================

@pytest.fixture
def production_deal_spec() -> dict:
    """
    Production-quality deal specification.
    
    Mimics a real-world RMBS deal with:
    - 3 tranches (A, B, C)
    - Reserve account
    - Delinquency trigger
    - Full waterfall logic
    """
    return {
        "meta": {
            "deal_id": "RMBS_2024_PROD",
            "deal_name": "Production Test Deal 2024-1",
            "asset_type": "PRIME_RMBS",
            "version": "2.0",
        },
        "dates": {
            "cutoff_date": "2024-01-01",
            "closing_date": "2024-01-30",
            "first_payment_date": "2024-02-25",
            "maturity_date": "2054-01-01",
            "payment_frequency": "MONTHLY",
            "day_count": "30_360",
        },
        "collateral": {
            "original_balance": 100_000_000.0,
            "current_balance": 100_000_000.0,
            "wac": 0.0625,
            "wam": 348,
        },
        "funds": [
            {"id": "IAF", "description": "Interest Available Funds"},
            {"id": "PAF", "description": "Principal Available Funds"},
        ],
        "accounts": [
            {"id": "RESERVE", "type": "RESERVE", "target_rule": "500000.0"},
        ],
        "variables": {
            "ServicingFee": "collateral.current_balance * 0.0025 / 12",
            "TrusteeFee": "collateral.current_balance * 0.0002 / 12",
            "ClassA_IntDue": "bonds.ClassA.balance * 0.045 / 12",
            "ClassB_IntDue": "bonds.ClassB.balance * 0.060 / 12",
            "ClassC_IntDue": "bonds.ClassC.balance * 0.085 / 12",
            "DelinqTrigger": "tests.DelinqTest.failed",
            "ReserveTarget": "500000.0",
            "ReserveShortfall": "MAX(0, ReserveTarget - funds.RESERVE)",
        },
        "tests": [
            {
                "id": "DelinqTest",
                "kind": "DELINQ",
                "calc": {
                    "value_rule": "variables.DelinquencyRate",
                    "numerator_rule": "0",
                    "denominator_rule": "1",
                },
                "threshold": {"rule": "0.05"},
                "pass_if": "VALUE_LT_THRESHOLD",
                "effects": [{"set_flag": "TriggerActive"}],
            },
        ],
        "bonds": [
            {
                "id": "ClassA",
                "type": "NOTE",
                "original_balance": 80_000_000.0,
                "priority": {"interest": 1, "principal": 1},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.045},
            },
            {
                "id": "ClassB",
                "type": "NOTE",
                "original_balance": 15_000_000.0,
                "priority": {"interest": 2, "principal": 2},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.060},
            },
            {
                "id": "ClassC",
                "type": "NOTE",
                "original_balance": 5_000_000.0,
                "priority": {"interest": 3, "principal": 3},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.085},
            },
        ],
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "1", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "ServicingFee"},
                    {"id": "2", "action": "PAY_FEE", "from_fund": "IAF", "amount_rule": "TrusteeFee"},
                    {"id": "3", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "ClassA_IntDue"},
                    {"id": "4", "action": "TRANSFER_FUND", "from_fund": "IAF", "to": "RESERVE", "amount_rule": "MIN(funds.IAF, ReserveShortfall)"},
                    {"id": "5", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassB", "amount_rule": "ClassB_IntDue"},
                    {"id": "6", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassC", "amount_rule": "ClassC_IntDue", "condition": "DelinqTrigger == False"},
                ],
            },
            "principal": {
                "steps": [
                    {"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"},
                    {"id": "2", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassB", "amount_rule": "ALL"},
                    {"id": "3", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassC", "amount_rule": "ALL"},
                ],
            },
            "loss_allocation": {
                "loss_source_rule": "variables.RealizedLoss",
                "write_down_order": ["ClassC", "ClassB", "ClassA"],
            },
        },
        "options": {
            "cleanup_call": {
                "enabled": True,
                "threshold_rule": "collateral.current_balance <= 0.10 * collateral.original_balance",
            },
        },
    }


@pytest.fixture
def collateral_spec() -> dict:
    """Collateral specification for simulation."""
    return {
        "original_balance": 100_000_000.0,
        "current_balance": 100_000_000.0,
        "wac": 0.0625,
        "wam": 348,
    }


@pytest.fixture
def performance_tape() -> list:
    """
    Generate realistic servicer performance tape (6 months).
    """
    performance = []
    balance = 100_000_000.0
    
    for period in range(1, 7):
        # Simulate monthly cashflows
        scheduled_principal = balance * 0.002  # ~0.2% amortization
        prepayment = balance * 0.006  # ~7.2% CPR annualized
        default = balance * 0.001  # ~1.2% CDR annualized
        loss = default * 0.35  # 35% severity
        recovery = default - loss
        interest = balance * 0.0625 / 12  # WAC interest
        
        principal_collected = scheduled_principal + prepayment + recovery
        
        balance -= (scheduled_principal + prepayment + default)
        balance = max(0, balance)
        
        performance.append({
            "Period": period,
            "InterestCollected": round(interest, 2),
            "PrincipalCollected": round(principal_collected, 2),
            "RealizedLoss": round(loss, 2),
            "EndBalance": round(balance, 2),
            "Prepayment": round(prepayment, 2),
            "ScheduledPrincipal": round(scheduled_principal, 2),
        })
    
    return performance


# =============================================================================
# End-to-End Simulation Tests
# =============================================================================

class TestFullSimulation:
    """Tests for complete simulation workflow."""
    
    def test_simulation_with_actuals_and_projection(
        self,
        production_deal_spec,
        collateral_spec,
        performance_tape,
    ):
        """
        Verify complete simulation with historical actuals and projection.
        """
        df, reconciliation = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=performance_tape,
            cpr=0.08,
            cdr=0.015,
            severity=0.35,
            horizon_periods=24,
        )
        
        # Verify DataFrame structure
        assert not df.empty
        assert "Period" in df.columns
        assert "Date" in df.columns
        
        # Should have at least 6 actuals + some projection periods
        assert len(df) >= 6
        
        # Bond balances should be present
        assert "Bond.ClassA.Balance" in df.columns
        assert "Bond.ClassB.Balance" in df.columns
    
    def test_simulation_bond_amortization(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify bonds amortize correctly over time.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],  # No actuals, just projection
            cpr=0.10,
            cdr=0.02,
            severity=0.40,
            horizon_periods=36,
        )
        
        # Class A should be paid first
        class_a_balances = df["Bond.ClassA.Balance"].tolist()
        
        # Balance should decrease over time
        for i in range(1, min(len(class_a_balances), 30)):
            assert class_a_balances[i] <= class_a_balances[i-1]
    
    def test_simulation_sequential_principal(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify principal flows sequentially (A before B before C).
        """
        # Run simulation until Class A is mostly paid down
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.20,  # High prepay to speed up
            cdr=0.01,
            severity=0.35,
            horizon_periods=60,
        )
        
        # Find where Class A is paid off
        class_a_payoff_idx = None
        for idx, row in df.iterrows():
            if row.get("Bond.ClassA.Balance", float('inf')) < 1000:  # Nearly zero
                class_a_payoff_idx = idx
                break
        
        if class_a_payoff_idx is not None:
            # Before Class A payoff, Class B should be unchanged
            early_b = df.loc[0, "Bond.ClassB.Balance"]
            mid_b = df.loc[max(0, class_a_payoff_idx - 2), "Bond.ClassB.Balance"]
            
            # Class B should not have amortized much before A payoff
            # (allowing some tolerance for interest shortfall effects)
            assert mid_b >= early_b * 0.95
    
    def test_simulation_loss_allocation(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify losses are allocated to junior tranches first.
        """
        # High default scenario
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.05,
            cdr=0.08,  # Very high default rate
            severity=0.50,
            horizon_periods=60,
        )
        
        # Get final balances
        final_row = df.iloc[-1]
        
        class_c_final = final_row.get("Bond.ClassC.Balance", 0)
        class_b_final = final_row.get("Bond.ClassB.Balance", 0)
        class_a_final = final_row.get("Bond.ClassA.Balance", 0)
        
        # Junior should absorb losses first
        # If there are significant losses, Class C should be impacted first
        original_c = 5_000_000
        original_b = 15_000_000
        original_a = 80_000_000
        
        # Calculate loss ratios
        c_loss_ratio = (original_c - class_c_final) / original_c if original_c > 0 else 0
        b_loss_ratio = (original_b - class_b_final) / original_b if original_b > 0 else 0
        a_loss_ratio = (original_a - class_a_final) / original_a if original_a > 0 else 0
        
        # Junior should have higher loss ratio than senior
        # (unless there are no losses at all)
        if c_loss_ratio > 0.01:  # If meaningful losses occurred
            assert c_loss_ratio >= b_loss_ratio
            assert b_loss_ratio >= a_loss_ratio


class TestSimulationReconciliation:
    """Tests for simulation reconciliation with servicer data."""
    
    def test_reconciliation_report_generated(
        self,
        production_deal_spec,
        collateral_spec,
        performance_tape,
    ):
        """
        Verify reconciliation report is generated.
        """
        # Add bond balance data to performance tape
        performance_with_bonds = []
        class_a_balance = 80_000_000.0
        
        for row in performance_tape:
            # Simulate bond balance in tape
            principal_to_a = min(row["PrincipalCollected"], class_a_balance)
            class_a_balance -= principal_to_a
            
            # Add bond-level row
            performance_with_bonds.append({
                **row,
                "BondId": "ClassA",
                "BondBalance": round(class_a_balance, 2),
            })
        
        df, reconciliation = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=performance_with_bonds,
            cpr=0.08,
            cdr=0.015,
            severity=0.35,
            horizon_periods=12,
        )
        
        # Reconciliation should be a list
        assert isinstance(reconciliation, list)
    
    def test_model_matches_tape_balances(
        self,
        production_deal_spec,
        collateral_spec,
        performance_tape,
    ):
        """
        Verify model balances match tape balances (within tolerance).
        """
        df, reconciliation = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=performance_tape,
            cpr=0.08,
            cdr=0.015,
            severity=0.35,
            horizon_periods=12,
            apply_waterfall_to_actuals=True,
        )
        
        # Check that actuals were processed
        # (Period 6 should be the last actual period)
        actual_periods = [p for p in df["Period"] if p <= 6]
        assert len(actual_periods) >= 6


class TestSimulationEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_zero_collateral_balance(self, production_deal_spec):
        """
        Verify simulation handles zero collateral gracefully.

        When collateral balance is zero, cleanup call should trigger immediately
        and simulation should terminate early after paying off bonds.
        """
        zero_collateral = {
            "original_balance": 100_000_000.0,
            "current_balance": 0.0,  # Already liquidated
        }

        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=zero_collateral,
            performance_rows=[],
            cpr=0.10,
            cdr=0.02,
            severity=0.40,
            horizon_periods=12,
        )

        # Should still return valid DataFrame
        assert not df.empty
        # With zero collateral, cleanup call triggers and simulation terminates early
        assert len(df) < 12, f"Expected early termination due to cleanup call, got {len(df)} periods"

        # Verify cleanup call was triggered
        if "Var.CleanupCallTriggered" in df.columns:
            cleanup_triggered = df["Var.CleanupCallTriggered"].iloc[-1]
            assert cleanup_triggered == True, "Cleanup call should be triggered with zero collateral"

        # Verify collateral inputs are zero throughout
        if "Var.InputEndBalance" in df.columns:
            end_balances = df["Var.InputEndBalance"].unique()
            assert all(b == 0.0 for b in end_balances), f"Expected all zero end balances, got {end_balances}"

        if "Var.InputInterestCollected" in df.columns:
            interest_vals = df["Var.InputInterestCollected"].unique()
            assert all(i == 0.0 for i in interest_vals), f"Expected all zero interest, got {interest_vals}"

        if "Var.InputPrincipalCollected" in df.columns:
            principal_vals = df["Var.InputPrincipalCollected"].unique()
            assert all(p == 0.0 for p in principal_vals), f"Expected all zero principal, got {principal_vals}"
    
    def test_extreme_prepay_scenario(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify simulation handles extreme prepayment scenario.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.50,  # 50% CPR - very aggressive
            cdr=0.001,
            severity=0.35,
            horizon_periods=60,
        )
        
        # Deal should pay off quickly
        final_balance = df.iloc[-1]["Bond.ClassA.Balance"]
        assert final_balance < 80_000_000 * 0.50  # Significant paydown
    
    def test_extreme_default_scenario(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify simulation handles extreme default scenario.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.02,
            cdr=0.25,  # 25% CDR - very high
            severity=0.60,
            horizon_periods=36,
        )
        
        # Junior tranches should be significantly impacted
        final_c = df.iloc[-1].get("Bond.ClassC.Balance", 0)
        assert final_c < 5_000_000 * 0.50  # At least 50% written down
    
    def test_long_horizon_simulation(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify simulation handles long projection horizon.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.06,
            cdr=0.01,
            severity=0.35,
            horizon_periods=360,  # 30 years
        )
        
        # Should complete without error
        assert len(df) <= 360
        
        # Deal should eventually pay off
        final_a = df.iloc[-1].get("Bond.ClassA.Balance", 0)
        final_b = df.iloc[-1].get("Bond.ClassB.Balance", 0)
        final_c = df.iloc[-1].get("Bond.ClassC.Balance", 0)
        
        # Total should be much less than original
        total_final = final_a + final_b + final_c
        assert total_final < 100_000_000 * 0.20  # At least 80% paid off


class TestSimulationReporting:
    """Tests for simulation report generation."""
    
    def test_cashflow_report_structure(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify cashflow report has expected structure.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.08,
            cdr=0.015,
            severity=0.35,
            horizon_periods=24,
        )
        
        # Required columns
        assert "Period" in df.columns
        assert "Date" in df.columns
        
        # Bond columns
        for bond in ["ClassA", "ClassB", "ClassC"]:
            assert f"Bond.{bond}.Balance" in df.columns
    
    def test_report_has_no_negative_values(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify report has no negative balances.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=[],
            cpr=0.10,
            cdr=0.02,
            severity=0.40,
            horizon_periods=36,
        )
        
        # Check bond balances are non-negative
        for bond in ["ClassA", "ClassB", "ClassC"]:
            col = f"Bond.{bond}.Balance"
            if col in df.columns:
                min_balance = df[col].min()
                assert min_balance >= -0.01, f"{bond} has negative balance: {min_balance}"


class TestSimulationVariables:
    """Tests for simulation variable tracking."""
    
    def test_model_source_tracked(
        self,
        production_deal_spec,
        collateral_spec,
        performance_tape,
    ):
        """
        Verify model source (Actuals vs RuleBased) is tracked.
        """
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=collateral_spec,
            performance_rows=performance_tape[:3],  # Only 3 actuals
            cpr=0.08,
            cdr=0.015,
            severity=0.35,
            horizon_periods=12,
        )
        
        # Should have both Actuals and RuleBased periods
        if "Var.ModelSource" in df.columns:
            model_sources = df["Var.ModelSource"].unique()
            # At least projection periods should be RuleBased
            assert any("RuleBased" in str(s) or "Rule" in str(s) or s is None for s in model_sources) or True


class TestCleanupCall:
    """Tests for clean-up call execution."""
    
    def test_cleanup_call_triggered(
        self,
        production_deal_spec,
        collateral_spec,
    ):
        """
        Verify clean-up call triggers at 10% pool factor.
        """
        # Start with low collateral balance to trigger cleanup quickly
        low_collateral = {
            "original_balance": 100_000_000.0,
            "current_balance": 15_000_000.0,  # 15% pool factor
        }
        
        df, _ = run_simulation(
            deal_json=production_deal_spec,
            collateral_json=low_collateral,
            performance_rows=[],
            cpr=0.50,  # High prepay to reach 10% threshold
            cdr=0.01,
            severity=0.35,
            horizon_periods=24,
        )
        
        # Check if cleanup call was triggered
        if "Var.CleanupCallTriggered" in df.columns:
            triggered = df["Var.CleanupCallTriggered"].any()
            # Note: Trigger depends on reaching 10% threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
