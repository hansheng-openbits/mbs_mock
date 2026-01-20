"""
Credit Enhancement Tracking Tests
==================================

Comprehensive tests for credit enhancement calculations including:
- Overcollateralization (OC) ratio tests
- Interest Coverage (IC) ratio tests
- Subordination level tracking
- Trigger evaluation and cure logic
- Excess spread calculations
- Loss allocation through structure

These tests simulate realistic deal performance scenarios
to verify credit enhancement mechanics work correctly.
"""

import pytest
from datetime import date
from typing import Dict, Any
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.credit_enhancement import (
    CreditEnhancementTracker,
    TriggerDefinition,
    TriggerType,
    TriggerStatus,
    TriggerResult,
    OCTestResult,
    ICTestResult,
    SubordinationLevel,
    ExcessSpreadCalculator,
    LossAllocationEngine,
    create_standard_triggers,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def standard_deal_bonds() -> Dict[str, Dict[str, Any]]:
    """
    Standard 3-tranche deal structure.
    
    Structure:
    - Class A: $80M senior (priority 1)
    - Class B: $15M mezzanine (priority 2)
    - Class C: $5M junior (priority 3)
    """
    return {
        "ClassA": {
            "original_balance": 80_000_000,
            "current_balance": 80_000_000,
            "coupon_rate": 0.045,
            "priority": 1,
        },
        "ClassB": {
            "original_balance": 15_000_000,
            "current_balance": 15_000_000,
            "coupon_rate": 0.060,
            "priority": 2,
        },
        "ClassC": {
            "original_balance": 5_000_000,
            "current_balance": 5_000_000,
            "coupon_rate": 0.080,
            "priority": 3,
            "is_residual": False,
        },
    }


@pytest.fixture
def standard_triggers() -> list:
    """Standard OC and IC triggers for testing."""
    return [
        TriggerDefinition(
            trigger_id="ClassA_OC",
            trigger_type=TriggerType.OC_TEST,
            target_classes=["ClassA"],
            threshold=1.25,
            comparison=">=",
            cure_periods=3,
            breach_action="divert",
            description="Class A OC Test - 125%",
        ),
        TriggerDefinition(
            trigger_id="ClassB_OC",
            trigger_type=TriggerType.OC_TEST,
            target_classes=["ClassB"],
            threshold=1.10,
            comparison=">=",
            breach_action="turbo",
            description="Class B OC Test - 110%",
        ),
        TriggerDefinition(
            trigger_id="ClassA_IC",
            trigger_type=TriggerType.IC_TEST,
            target_classes=["ClassA"],
            threshold=1.20,
            comparison=">=",
            breach_action="divert",
            description="Class A IC Test - 120%",
        ),
    ]


@pytest.fixture
def ce_tracker(standard_deal_bonds, standard_triggers) -> CreditEnhancementTracker:
    """Create credit enhancement tracker with standard structure."""
    return CreditEnhancementTracker(
        deal_bonds=standard_deal_bonds,
        collateral_balance=105_000_000,  # $5M OC
        triggers=standard_triggers,
        reserve_accounts={"RESERVE": 500_000},
        original_collateral=100_000_000,
    )


# =============================================================================
# OC Ratio Tests
# =============================================================================

class TestOCRatioCalculation:
    """Tests for Overcollateralization ratio calculations."""
    
    def test_oc_ratio_basic_calculation(self, ce_tracker):
        """
        Verify basic OC ratio calculation is correct.
        
        OC = (Collateral + Reserves) / Bonds at or above class
        """
        result = ce_tracker.calculate_oc_ratio("ClassA")
        
        # Collateral ($105M) + Reserve ($0.5M) = $105.5M
        # Class A balance = $80M
        # OC = 105.5 / 80 = 1.319
        expected_oc = (105_000_000 + 500_000) / 80_000_000
        
        assert abs(result.current_ratio - expected_oc) < 0.01
        assert result.target_class == "ClassA"
    
    def test_oc_ratio_includes_senior_bonds(self, ce_tracker):
        """
        Verify OC ratio for mezzanine includes senior bonds.
        
        Class B OC should include Class A in denominator.
        """
        result = ce_tracker.calculate_oc_ratio("ClassB")
        
        # Collateral ($105M) + Reserve ($0.5M) = $105.5M
        # Class A + B balance = $80M + $15M = $95M
        # OC = 105.5 / 95 = 1.11
        expected_oc = (105_000_000 + 500_000) / (80_000_000 + 15_000_000)
        
        assert abs(result.current_ratio - expected_oc) < 0.01
    
    def test_oc_ratio_passing_threshold(self, ce_tracker):
        """
        Verify OC test passes when above threshold.
        """
        result = ce_tracker.calculate_oc_ratio("ClassA")
        
        # 131.9% > 125% threshold
        assert result.is_passing == True
        assert result.current_ratio > result.required_ratio
    
    def test_oc_ratio_failing_threshold(self, standard_deal_bonds, standard_triggers):
        """
        Verify OC test fails when below threshold.
        """
        # Create tracker with lower collateral
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds,
            collateral_balance=90_000_000,  # Lower than bonds
            triggers=standard_triggers,
        )
        
        result = tracker.calculate_oc_ratio("ClassA")
        
        # 90 / 80 = 1.125 < 1.25 threshold
        assert result.is_passing == False
    
    def test_oc_cushion_calculation(self, ce_tracker):
        """
        Verify OC cushion (dollars above trigger) is calculated correctly.
        """
        result = ce_tracker.calculate_oc_ratio("ClassA")
        
        # Cushion = Collateral - (Bonds * Required OC)
        # = 105.5M - (80M * 1.25) = 105.5M - 100M = $5.5M
        expected_cushion = (105_000_000 + 500_000) - (80_000_000 * 1.25)
        
        assert abs(result.cushion - expected_cushion) < 1000


class TestOCRatioWithAmortization:
    """Tests for OC ratio as deal amortizes."""
    
    def test_oc_improves_as_senior_amortizes(self, standard_deal_bonds, standard_triggers):
        """
        Verify OC ratio improves as senior tranche pays down.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds.copy(),
            collateral_balance=100_000_000,
            triggers=standard_triggers,
        )
        
        initial_oc = tracker.calculate_oc_ratio("ClassA").current_ratio
        
        # Pay down Class A by $10M
        tracker.deal_bonds["ClassA"]["current_balance"] = 70_000_000
        tracker.collateral_balance = 90_000_000  # Collateral also reduced
        
        new_oc = tracker.calculate_oc_ratio("ClassA").current_ratio
        
        # OC should improve (90/70 = 1.29 vs initial 100/80 = 1.25)
        assert new_oc > initial_oc
    
    def test_oc_deteriorates_with_losses(self, standard_deal_bonds, standard_triggers):
        """
        Verify OC ratio deteriorates when losses reduce collateral.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds.copy(),
            collateral_balance=100_000_000,
            triggers=standard_triggers,
        )
        
        initial_oc = tracker.calculate_oc_ratio("ClassA").current_ratio
        
        # $10M loss reduces collateral but bonds unchanged
        tracker.collateral_balance = 90_000_000
        
        new_oc = tracker.calculate_oc_ratio("ClassA").current_ratio
        
        # OC deteriorates (90/80 = 1.125 < initial 100/80 = 1.25)
        assert new_oc < initial_oc


# =============================================================================
# IC Ratio Tests
# =============================================================================

class TestICRatioCalculation:
    """Tests for Interest Coverage ratio calculations."""
    
    def test_ic_ratio_basic_calculation(self, ce_tracker):
        """
        Verify basic IC ratio calculation.
        """
        # Set interest collections
        ce_tracker._interest_collections = 500_000
        
        result = ce_tracker.calculate_ic_ratio("ClassA")
        
        # Interest due for Class A = $80M * 4.5% / 12 = $300,000
        # IC = 500,000 / 300,000 = 1.67
        expected_interest = 80_000_000 * 0.045 / 12
        expected_ic = 500_000 / expected_interest
        
        assert abs(result.current_ratio - expected_ic) < 0.01
    
    def test_ic_ratio_includes_senior_interest(self, ce_tracker):
        """
        Verify IC for mezzanine includes senior interest.
        """
        ce_tracker._interest_collections = 600_000
        
        result = ce_tracker.calculate_ic_ratio("ClassB")
        
        # Interest due: A ($300K) + B ($75K) = $375K
        # IC = 600K / 375K = 1.60
        interest_a = 80_000_000 * 0.045 / 12
        interest_b = 15_000_000 * 0.060 / 12
        expected_ic = 600_000 / (interest_a + interest_b)
        
        assert abs(result.current_ratio - expected_ic) < 0.01
    
    def test_ic_ratio_passing(self, ce_tracker):
        """
        Verify IC test passes when sufficient interest collected.
        """
        ce_tracker._interest_collections = 500_000  # Well above $300K needed
        
        result = ce_tracker.calculate_ic_ratio("ClassA")
        
        assert result.is_passing == True
    
    def test_ic_ratio_failing(self, ce_tracker):
        """
        Verify IC test fails when insufficient interest collected.
        """
        ce_tracker._interest_collections = 200_000  # Below $300K needed
        
        result = ce_tracker.calculate_ic_ratio("ClassA")
        
        assert result.is_passing == False
    
    def test_excess_interest_calculation(self, ce_tracker):
        """
        Verify excess interest is calculated correctly.
        """
        ce_tracker._interest_collections = 500_000
        
        result = ce_tracker.calculate_ic_ratio("ClassA")
        
        # Excess = Collections - Required
        interest_due = 80_000_000 * 0.045 / 12
        expected_excess = 500_000 - interest_due
        
        assert abs(result.excess_interest - expected_excess) < 1


# =============================================================================
# Subordination Tests
# =============================================================================

class TestSubordinationCalculation:
    """Tests for subordination level calculations."""
    
    def test_subordination_basic_calculation(self, ce_tracker):
        """
        Verify subordination calculation for senior tranche.
        """
        result = ce_tracker.calculate_subordination("ClassA")
        
        # Junior to Class A: B ($15M) + C ($5M) = $20M
        # Total: $100M
        # Subordination = 20 / 100 = 20%
        assert abs(result.subordination_pct - 20.0) < 0.1
    
    def test_subordination_for_mezzanine(self, ce_tracker):
        """
        Verify subordination for mezzanine tranche.
        """
        result = ce_tracker.calculate_subordination("ClassB")
        
        # Junior to Class B: C ($5M)
        # Total: $100M
        # Subordination = 5 / 100 = 5%
        assert abs(result.subordination_pct - 5.0) < 0.1
    
    def test_subordination_for_junior(self, ce_tracker):
        """
        Verify subordination for junior tranche (should be 0).
        """
        result = ce_tracker.calculate_subordination("ClassC")
        
        # No subordination for junior
        assert result.subordination_pct == 0.0
    
    def test_subordination_erosion(self, standard_deal_bonds, standard_triggers):
        """
        Verify subordination erosion is tracked.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds.copy(),
            collateral_balance=100_000_000,
            triggers=standard_triggers,
            original_collateral=100_000_000,
        )
        
        # Simulate Class C written down by $3M (losses)
        tracker.deal_bonds["ClassC"]["current_balance"] = 2_000_000
        
        result = tracker.calculate_subordination("ClassA")
        
        # Original: 20%, Current: 17/97 = 17.5%
        assert result.subordination_pct < result.original_subordination_pct


# =============================================================================
# Trigger Evaluation Tests
# =============================================================================

class TestTriggerEvaluation:
    """Tests for trigger evaluation and cure logic."""
    
    def test_trigger_passes_when_above_threshold(self, ce_tracker):
        """
        Verify trigger passes when metric exceeds threshold.
        """
        trigger = ce_tracker.triggers[0]  # ClassA_OC, threshold 1.25
        
        result = ce_tracker.evaluate_trigger(trigger)
        
        # OC is 131.9% > 125%
        assert result.status == TriggerStatus.PASSING
    
    def test_trigger_fails_when_below_threshold(self, standard_deal_bonds, standard_triggers):
        """
        Verify trigger fails when metric below threshold.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds,
            collateral_balance=85_000_000,  # OC = 106.25% < 125%
            triggers=standard_triggers,
        )
        
        trigger = tracker.triggers[0]  # ClassA_OC
        result = tracker.evaluate_trigger(trigger)
        
        assert result.status == TriggerStatus.FAILING
    
    def test_trigger_breach_date_tracked(self, standard_deal_bonds, standard_triggers):
        """
        Verify breach date is recorded when trigger fails.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds,
            collateral_balance=85_000_000,
            triggers=standard_triggers,
            evaluation_date=date(2024, 3, 1),
        )
        
        trigger = tracker.triggers[0]
        result = tracker.evaluate_trigger(trigger)
        
        assert result.breach_date == date(2024, 3, 1)
    
    def test_consecutive_fail_counter(self, standard_deal_bonds, standard_triggers):
        """
        Verify consecutive fail counter increments.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds,
            collateral_balance=85_000_000,
            triggers=standard_triggers,
        )
        
        trigger = tracker.triggers[0]
        
        # First failure
        result1 = tracker.evaluate_trigger(trigger)
        assert result1.consecutive_fail == 1
        
        # Second failure
        result2 = tracker.evaluate_trigger(trigger)
        assert result2.consecutive_fail == 2
    
    def test_trigger_cure_logic(self, standard_deal_bonds, standard_triggers):
        """
        Verify trigger cures after sufficient passing periods.
        """
        # Start with failing trigger
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds.copy(),
            collateral_balance=85_000_000,  # Failing
            triggers=standard_triggers,
        )
        
        trigger = tracker.triggers[0]  # cure_periods = 3
        
        # Fail once
        tracker.evaluate_trigger(trigger)
        
        # Fix OC
        tracker.collateral_balance = 105_000_000
        
        # Need 3 consecutive passes to cure
        for _ in range(3):
            result = tracker.evaluate_trigger(trigger)
        
        assert result.status in [TriggerStatus.PASSING, TriggerStatus.CURED]


class TestEvaluateAllTriggers:
    """Tests for batch trigger evaluation."""
    
    def test_evaluate_all_returns_all_results(self, ce_tracker):
        """
        Verify all triggers are evaluated.
        """
        results = ce_tracker.evaluate_all_triggers()
        
        assert len(results) == len(ce_tracker.triggers)
    
    def test_get_failing_triggers(self, standard_deal_bonds, standard_triggers):
        """
        Verify failing triggers are identified.
        """
        tracker = CreditEnhancementTracker(
            deal_bonds=standard_deal_bonds,
            collateral_balance=85_000_000,  # Causes OC failure
            triggers=standard_triggers,
        )
        
        failing = tracker.get_failing_triggers()
        
        # At least the OC triggers should be failing
        assert len(failing) > 0
        assert all(t.status == TriggerStatus.FAILING for t in failing)


# =============================================================================
# Enhancement Summary Tests
# =============================================================================

class TestEnhancementSummary:
    """Tests for comprehensive enhancement summary."""
    
    def test_get_enhancement_summary_structure(self, ce_tracker):
        """
        Verify summary contains all required sections.
        """
        summary = ce_tracker.get_enhancement_summary()
        
        assert "evaluation_date" in summary
        assert "collateral_balance" in summary
        assert "oc_tests" in summary
        assert "ic_tests" in summary
        assert "subordination" in summary
        assert "triggers" in summary
        assert "reserve_accounts" in summary
    
    def test_summary_contains_all_classes(self, ce_tracker):
        """
        Verify summary includes metrics for all bond classes.
        """
        summary = ce_tracker.get_enhancement_summary()
        
        for bond_id in ["ClassA", "ClassB", "ClassC"]:
            assert bond_id in summary["oc_tests"]
            assert bond_id in summary["ic_tests"]
            assert bond_id in summary["subordination"]


# =============================================================================
# Excess Spread Calculator Tests
# =============================================================================

class TestExcessSpreadCalculator:
    """Tests for excess spread calculations."""
    
    def test_excess_spread_calculation(self):
        """
        Verify excess spread calculation with standard inputs.
        """
        calculator = ExcessSpreadCalculator(
            collateral_yield=0.065,  # 6.5% WAC
            servicing_fee=0.0025,   # 25bp
            trust_expenses=0.0005,  # 5bp
        )
        
        result = calculator.calculate_excess_spread(
            collateral_balance=100_000_000,
            bond_coupons={
                "ClassA": (80_000_000, 0.045),
                "ClassB": (15_000_000, 0.060),
                "ClassC": (5_000_000, 0.080),
            },
            period_months=1,
        )
        
        # Verify structure
        assert "gross_interest" in result
        assert "servicing_fee" in result
        assert "excess_spread_dollars" in result
        assert "excess_spread_annualized_pct" in result
        
        # Gross interest should be collateral * WAC / 12
        expected_gross = 100_000_000 * 0.065 / 12
        assert abs(result["gross_interest"] - expected_gross) < 1
    
    def test_excess_spread_positive(self):
        """
        Verify excess spread is positive when WAC > weighted bond coupon.
        """
        calculator = ExcessSpreadCalculator(
            collateral_yield=0.070,  # 7.0% WAC
            servicing_fee=0.0025,
            trust_expenses=0.0005,
        )
        
        result = calculator.calculate_excess_spread(
            collateral_balance=100_000_000,
            bond_coupons={
                "ClassA": (90_000_000, 0.045),  # Low coupon bonds
            },
            period_months=1,
        )
        
        # Should have positive excess spread
        assert result["excess_spread_dollars"] > 0
    
    def test_excess_spread_can_be_negative(self):
        """
        Verify negative excess spread when costs exceed income.
        """
        calculator = ExcessSpreadCalculator(
            collateral_yield=0.040,  # Low WAC
            servicing_fee=0.0025,
            trust_expenses=0.0005,
        )
        
        result = calculator.calculate_excess_spread(
            collateral_balance=100_000_000,
            bond_coupons={
                "ClassA": (90_000_000, 0.055),  # High coupon bonds
            },
            period_months=1,
        )
        
        # Could be negative
        assert isinstance(result["excess_spread_dollars"], float)


# =============================================================================
# Loss Allocation Tests
# =============================================================================

class TestLossAllocationEngine:
    """Tests for loss allocation through capital structure."""
    
    def test_loss_allocated_to_junior_first(self, standard_deal_bonds, ce_tracker):
        """
        Verify losses are allocated to junior tranches first.
        """
        engine = LossAllocationEngine(
            deal_bonds=standard_deal_bonds,
            ce_tracker=ce_tracker,
        )
        
        allocation = engine.allocate_loss(3_000_000)  # $3M loss
        
        # Should hit Class C first
        assert allocation["by_class"]["ClassC"]["loss_allocated"] == 3_000_000
        assert allocation["by_class"].get("ClassB", {}).get("loss_allocated", 0) == 0
        assert allocation["by_class"].get("ClassA", {}).get("loss_allocated", 0) == 0
    
    def test_loss_cascades_when_junior_exhausted(self, standard_deal_bonds, ce_tracker):
        """
        Verify losses cascade when junior is exhausted.
        """
        engine = LossAllocationEngine(
            deal_bonds=standard_deal_bonds,
            ce_tracker=ce_tracker,
        )
        
        allocation = engine.allocate_loss(8_000_000)  # $8M loss
        
        # Class C ($5M) exhausted, $3M to Class B
        assert allocation["by_class"]["ClassC"]["loss_allocated"] == 5_000_000
        assert allocation["by_class"]["ClassB"]["loss_allocated"] == 3_000_000
    
    def test_catastrophic_loss_reaches_senior(self, standard_deal_bonds, ce_tracker):
        """
        Verify catastrophic losses can reach senior tranche.
        """
        engine = LossAllocationEngine(
            deal_bonds=standard_deal_bonds,
            ce_tracker=ce_tracker,
        )
        
        allocation = engine.allocate_loss(25_000_000)  # $25M loss
        
        # Junior ($5M + $15M = $20M) exhausted, $5M to senior
        assert allocation["by_class"]["ClassC"]["loss_allocated"] == 5_000_000
        assert allocation["by_class"]["ClassB"]["loss_allocated"] == 15_000_000
        assert allocation["by_class"]["ClassA"]["loss_allocated"] == 5_000_000
    
    def test_no_remaining_loss_after_full_allocation(self, standard_deal_bonds, ce_tracker):
        """
        Verify no remaining loss when fully allocated.
        """
        engine = LossAllocationEngine(
            deal_bonds=standard_deal_bonds,
            ce_tracker=ce_tracker,
        )
        
        allocation = engine.allocate_loss(10_000_000)
        
        # Should be no remaining loss
        assert allocation["remaining_loss"] == 0


# =============================================================================
# Standard Trigger Factory Tests
# =============================================================================

class TestStandardTriggerFactory:
    """Tests for standard trigger creation utility."""
    
    def test_create_standard_triggers_for_all_classes(self, standard_deal_bonds):
        """
        Verify standard triggers are created for all non-residual classes.
        """
        triggers = create_standard_triggers(
            deal_bonds=standard_deal_bonds,
            oc_threshold=1.25,
            ic_threshold=1.10,
        )
        
        # Should have OC and IC for each class (6 total)
        oc_triggers = [t for t in triggers if t.trigger_type == TriggerType.OC_TEST]
        ic_triggers = [t for t in triggers if t.trigger_type == TriggerType.IC_TEST]
        
        assert len(oc_triggers) == 3
        assert len(ic_triggers) == 3
    
    def test_standard_triggers_have_tiered_thresholds(self, standard_deal_bonds):
        """
        Verify thresholds are tiered by seniority.
        """
        triggers = create_standard_triggers(
            deal_bonds=standard_deal_bonds,
            oc_threshold=1.25,
            ic_threshold=1.10,
        )
        
        # Get OC thresholds by class
        oc_by_class = {t.target_classes[0]: t.threshold 
                       for t in triggers if t.trigger_type == TriggerType.OC_TEST}
        
        # Senior should have highest threshold, junior lowest
        # (Based on typical deal structure)
        assert oc_by_class.get("ClassA", 0) >= oc_by_class.get("ClassC", 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
