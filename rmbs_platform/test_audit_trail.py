"""
Test: Audit Trail Enhancement
===============================

This test demonstrates the waterfall audit trail functionality,
which captures detailed step-by-step execution logs for debugging,
validation, and compliance purposes.

The audit trail is essential for:
1. **Root Cause Analysis**: Trace why a bond received a specific cashflow
2. **Compliance**: Provide detailed logs for SEC/rating agency review
3. **Model Validation**: Compare execution between tool versions
4. **Web3 Transparency**: Publish execution logs for investor trust

Author: RMBS Platform Development Team
Date: January 2026
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from engine.loader import DealLoader
from engine.state import DealState
from engine.waterfall import WaterfallRunner
from engine.compute import ExpressionEngine
from engine.audit_trail import AuditTrail


def create_test_deal():
    """Create a simple deal for testing audit trail."""
    return {
        "meta": {
            "deal_id": "AUDIT_TEST_001",
            "deal_name": "Audit Trail Test Deal",
            "asset_type": "NON_AGENCY_RMBS",
            "version": "1.0"
        },
        "collateral": {
            "original_balance": 300000000,
            "current_balance": 300000000,
            "wac": 0.055,
            "wam": 357,
            "pool_type": "PRIME",
            "geography": "National"
        },
        "bonds": [
            {
                "id": "ClassA",
                "name": "Class A Senior Notes",
                "type": "SENIOR",
                "original_balance": 270000000,
                "current_balance": 270000000,
                "coupon": {
                    "kind": "FIXED",
                    "fixed_rate": 0.045
                },
                "priority": {
                    "interest": 1,
                    "principal": 1
                },
                "group": "Senior",
                "subordination_pct": 10.0
            },
            {
                "id": "ClassB",
                "name": "Class B Mezzanine Notes",
                "type": "MEZZANINE",
                "original_balance": 25000000,
                "current_balance": 25000000,
                "coupon": {
                    "kind": "FIXED",
                    "fixed_rate": 0.065
                },
                "priority": {
                    "interest": 2,
                    "principal": 2
                },
                "group": "Mezzanine",
                "subordination_pct": 1.67
            }
        ],
        "funds": [
            {"id": "IAF", "description": "Interest Allocation Fund"},
            {"id": "PAF", "description": "Principal Allocation Fund"}
        ],
        "variables": {
            "ServicingFeeAmount": "collateral.current_balance * 0.0025 / 12"
        },
        "tests": [],
        "waterfalls": {
            "interest": {
                "steps": [
                    {
                        "priority": 1,
                        "from_fund": "IAF",
                        "action": "PAY_FEE",
                        "amount_rule": "ServicingFeeAmount",
                        "condition": "true"
                    },
                    {
                        "priority": 2,
                        "from_fund": "IAF",
                        "action": "PAY_BOND_INTEREST",
                        "group": "ClassA",
                        "amount_rule": "1012500",
                        "condition": "true"
                    },
                    {
                        "priority": 3,
                        "from_fund": "IAF",
                        "action": "PAY_BOND_INTEREST",
                        "group": "ClassB",
                        "amount_rule": "135416",
                        "condition": "true"
                    }
                ]
            },
            "principal": {
                "steps": [
                    {
                        "priority": 1,
                        "from_fund": "PAF",
                        "action": "PAY_BOND_PRINCIPAL",
                        "group": "ClassA",
                        "amount_rule": "ALL",
                        "condition": "true"
                    }
                ]
            },
            "loss_allocation": {
                "write_down_order": ["ClassB", "ClassA"]
            }
        }
    }


def main():
    print("=" * 80)
    print("AUDIT TRAIL ENHANCEMENT TEST")
    print("=" * 80)
    print()

    # 1. Create deal
    print("1. Creating test deal...")
    deal_json = create_test_deal()
    loader = DealLoader()
    deal_def = loader.load_from_json(deal_json)
    state = DealState(deal_def)
    print("   ✅ Deal created")
    print()

    # 2. Initialize collateral
    print("2. Initializing collateral...")
    collateral = deal_def.collateral
    state.collateral["current_balance"] = collateral.get("original_balance", 300000000)
    state.collateral["original_balance"] = collateral.get("original_balance", 300000000)
    state.collateral["wac"] = collateral.get("wac", 0.055)
    print(f"   Current Balance: ${state.collateral['current_balance']:,.0f}")
    print(f"   WAC: {state.collateral['wac']:.2%}")
    print("   ✅ Collateral initialized")
    print()

    # 3. Create audit trail
    print("3. Creating audit trail...")
    trail = AuditTrail(enabled=True, level="detailed")
    print("   ✅ Audit trail enabled (level: detailed)")
    print()

    # 4. Create runner with audit trail
    print("4. Creating waterfall runner...")
    engine = ExpressionEngine()
    runner = WaterfallRunner(
        engine,
        use_iterative_solver=True,
        max_iterations=10,
        convergence_tol=0.01,
        audit_trail=trail
    )
    print("   ✅ Runner created with audit trail integration")
    print()

    # 5. Run 3 periods
    print("5. Running simulation (3 periods)...")
    print()
    
    for period in range(3):
        print(f"   Period {period + 1}:")
        
        # Deposit funds
        coll_balance = state.collateral.get("current_balance", 300000000)
        coll_wac = state.collateral.get("wac", 0.055)
        gross_interest = coll_balance * coll_wac / 12
        principal_payment = 1000000  # $1M principal
        
        state.deposit_funds("IAF", gross_interest)
        state.deposit_funds("PAF", principal_payment)
        
        print(f"     Interest deposited: ${gross_interest:,.2f}")
        print(f"     Principal deposited: ${principal_payment:,.2f}")
        
        # Run period
        runner.run_period(state)
        
        # Update collateral balance
        state.collateral["current_balance"] = coll_balance - principal_payment
        
        print(f"     ✅ Period complete")
        print()
    
    print("   ✅ Simulation complete")
    print()

    # 6. Export audit trail
    print("6. Exporting audit trail...")
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)
    
    audit_file = output_dir / "audit_trail_test.json"
    trail.export_to_json(audit_file)
    print(f"   ✅ Full audit trail exported to: {audit_file}")
    
    # Export individual period
    period_file = output_dir / "audit_period_1.json"
    trail.export_period_to_json(1, period_file)
    print(f"   ✅ Period 1 exported to: {period_file}")
    print()

    # 7. Generate summary reports
    print("7. Generating summary reports...")
    print()
    print("=" * 80)
    print(trail.get_period_summary(1))
    print("=" * 80)
    print()

    # 8. Demonstrate detail access
    print("8. Audit Trail Statistics:")
    print(f"   Total Periods Captured: {len(trail.periods)}")
    
    for period_trace in trail.periods:
        print(f"\n   Period {period_trace.period}:")
        print(f"     Steps Executed: {len(period_trace.steps)}")
        print(f"     Variables Calculated: {len(period_trace.variables_calculated)}")
        print(f"     Tests Evaluated: {len(period_trace.tests_evaluated)}")
        print(f"     Interest Allocated: ${period_trace.total_interest_allocated:,.2f}")
        print(f"     Principal Allocated: ${period_trace.total_principal_allocated:,.2f}")
        
        if period_trace.solver_iterations > 1:
            print(f"     Solver Iterations: {period_trace.solver_iterations}")
            print(f"     Solver Converged: {'✅' if period_trace.solver_converged else '❌'}")
    
    print()

    # 9. Show audit file contents sample
    print("9. Sample Audit Trail JSON Structure:")
    print()
    with open(audit_file) as f:
        audit_data = json.load(f)
    
    print(f"   Metadata:")
    print(f"     Created: {audit_data['metadata']['created_at']}")
    print(f"     Version: {audit_data['metadata']['version']}")
    print(f"     Level: {audit_data['metadata']['level']}")
    print()
    
    if audit_data['periods']:
        first_period = audit_data['periods'][0]
        print(f"   Period 1 Summary:")
        print(f"     Steps: {len(first_period['steps'])}")
        print(f"     Variables: {len(first_period['variables_calculated'])}")
        print(f"     Tests: {len(first_period['tests_evaluated'])}")
        
        if first_period['variables_calculated']:
            print(f"\n   Sample Variables:")
            for var_name, var_value in list(first_period['variables_calculated'].items())[:3]:
                print(f"     {var_name}: {var_value}")
        
        if first_period['tests_evaluated']:
            print(f"\n   Sample Tests:")
            for test_id, test_result in first_period['tests_evaluated'].items():
                status = "✅ PASS" if test_result['passed'] else "❌ FAIL"
                print(f"     {test_id}: {status}")
                print(f"       Value: {test_result['value']:.4f}")
                print(f"       Threshold: {test_result['threshold']:.4f}")
    
    print()

    # 10. Summary
    print("=" * 80)
    print("AUDIT TRAIL TEST COMPLETE")
    print("=" * 80)
    print()
    print("✅ Key Features Demonstrated:")
    print("   1. Period-level execution tracking")
    print("   2. Variable calculation recording")
    print("   3. Test evaluation logging")
    print("   4. Solver iteration tracking")
    print("   5. JSON export for compliance")
    print("   6. Human-readable summaries")
    print()
    print("📋 Use Cases:")
    print("   - Root cause analysis: Trace why a bond received specific cashflow")
    print("   - Compliance: Provide detailed logs for SEC/rating agency review")
    print("   - Model validation: Compare execution between tool versions")
    print("   - Web3 transparency: Publish execution logs on-chain")
    print()
    print(f"📁 Audit files saved to: {output_dir}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
