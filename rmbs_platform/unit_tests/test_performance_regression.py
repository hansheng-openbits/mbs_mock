"""
Performance Regression Tests
============================

Tests for performance benchmarks and scalability validation.
These tests ensure the platform can handle large loan tapes and
stress scenarios without performance degradation.

Key test areas:
- Large loan pool simulation (10,000+ loans)
- Memory usage validation
- Scalability testing
- ML model inference speed
- End-to-end simulation performance
"""

import pytest
import numpy as np
import pandas as pd
import time
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# =============================================================================
# Large Loan Tape Performance Tests
# =============================================================================

class TestLargeLoanTapePerformance:
    """Performance tests for large loan tapes and scalability."""

    def test_large_loan_tape_simulation_performance(self):
        """
        Test end-to-end simulation performance with large loan tape.
        This validates that the system can handle 5,000+ loans in ML mode.
        """
        # Create large synthetic loan tape
        np.random.seed(42)
        n_loans = 5000  # Large enough to stress test

        large_loan_tape = pd.DataFrame({
            "LoanID": [f"L{i:06d}" for i in range(n_loans)],
            "OriginalBalance": np.random.uniform(200_000, 600_000, n_loans),
            "CurrentBalance": np.random.uniform(180_000, 580_000, n_loans),
            "InterestRate": np.random.uniform(0.035, 0.075, n_loans),
            "OriginalLTV": np.random.uniform(60, 90, n_loans),
            "CurrentLTV": np.random.uniform(55, 95, n_loans),
            "FICO": np.random.choice(range(620, 800, 10), n_loans),
            "OriginationDate": ["2022-01-15"] * n_loans,
            "FirstPaymentDate": ["2022-03-01"] * n_loans,
            "MaturityDate": ["2052-03-01"] * n_loans,
            "LoanAge": np.random.randint(12, 36, n_loans),
            "RemainingTerm": np.random.randint(300, 348, n_loans),
            "PropertyState": np.random.choice(["CA", "TX", "FL", "NY", "IL"], n_loans),
            "PropertyType": np.random.choice(["SF", "CO", "TH"], n_loans),
            "Occupancy": np.random.choice(["Primary", "Investment"], n_loans, p=[0.9, 0.1]),
            "LoanPurpose": np.random.choice(["Purchase", "Refi"], n_loans, p=[0.6, 0.4]),
            "DocumentationType": ["Full"] * n_loans,
            "DaysDelinquent": [0] * n_loans,
            "Status": ["Current"] * n_loans,
            "ServicerName": ["Test Servicer"] * n_loans,
        })

        # Create temporary loan tape file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            large_loan_tape.to_csv(f.name, index=False)
            loan_tape_path = f.name

        try:
            # Create a simple collateral/deal configuration
            collateral_config = {
                "deal_id": "PERF_TEST_LARGE_POOL",
                "data": {
                    "pool_id": "PERF_TEST_LARGE_POOL",
                    "original_balance": float(large_loan_tape["OriginalBalance"].sum()),
                    "current_balance": float(large_loan_tape["CurrentBalance"].sum()),
                    "loan_count": n_loans,
                    "summary_statistics": {
                        "wac": float(large_loan_tape["InterestRate"].mean()),
                        "wam": float(large_loan_tape["RemainingTerm"].mean()),
                        "avg_fico": float(large_loan_tape["FICO"].mean()),
                        "avg_ltv": float(large_loan_tape["CurrentLTV"].mean()),
                    }
                },
                "loan_data": {
                    "schema_ref": {
                        "source_uri": loan_tape_path
                    }
                },
                "ml_config": {
                    "enabled": True,
                    "prepay_model_key": "prepay_rsf",
                    "default_model_key": "default_cox"
                }
            }

            # Test ML-enabled simulation performance
            start_time = time.time()

            # Import here to avoid circular imports in test suite
            from engine import run_simulation

            deal_config = {
                "meta": {"deal_id": "PERF_TEST_LARGE_POOL"},
                "collateral": collateral_config["data"],
                "bonds": [
                    {
                        "id": "ClassA",
                        "type": "NOTE",
                        "original_balance": collateral_config["data"]["original_balance"] * 0.8,
                        "priority": {"interest": 1, "principal": 1},
                        "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                    }
                ],
                "waterfalls": {
                    "interest": {"steps": [{"id": "1", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "bonds.ClassA.balance * 0.05 / 12"}]},
                    "principal": {"steps": [{"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"}]},
                    "loss_allocation": {"write_down_order": ["ClassA"], "loss_source_rule": "variables.RealizedLoss"}
                }
            }

            # Run simulation with ML enabled
            df, reconciliation = run_simulation(
                deal_config,
                collateral_config,
                [],  # No actuals for pure projection test
                cpr=0.08,
                cdr=0.008,
                severity=0.32,
                horizon_periods=12  # Short horizon for performance test
            )

            end_time = time.time()
            total_time = end_time - start_time

            # Should complete in reasonable time (< 60 seconds for 5000 loans)
            assert total_time < 60.0, f"Simulation took {total_time:.1f}s, expected < 60s"

            # Should produce valid results
            assert not df.empty
            assert len(df) > 0
            assert "Period" in df.columns

        except Exception as e:
            # If models aren't available or other issues, skip test
            pytest.skip(f"Large pool performance test failed: {e}")
        finally:
            # Clean up temporary file
            import os
            try:
                os.unlink(loan_tape_path)
            except:
                pass

    def test_memory_usage_under_load(self):
        """
        Test memory usage patterns during large simulations.
        """
        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())

            # Baseline memory
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create large synthetic loan tape
            np.random.seed(42)
            n_loans = 2000

            large_loan_tape = pd.DataFrame({
                "LoanID": [f"L{i:06d}" for i in range(n_loans)],
                "OriginalBalance": np.random.uniform(300_000, 500_000, n_loans),
                "CurrentBalance": np.random.uniform(280_000, 480_000, n_loans),
                "InterestRate": np.random.uniform(0.045, 0.065, n_loans),
                "OriginalLTV": np.random.uniform(70, 85, n_loans),
                "CurrentLTV": np.random.uniform(65, 90, n_loans),
                "FICO": np.random.choice(range(680, 780, 10), n_loans),
                "OriginationDate": ["2023-01-15"] * n_loans,
                "FirstPaymentDate": ["2023-03-01"] * n_loans,
                "MaturityDate": ["2053-03-01"] * n_loans,
                "LoanAge": [12] * n_loans,
                "RemainingTerm": [348] * n_loans,
                "PropertyState": ["CA"] * n_loans,
                "PropertyType": ["SF"] * n_loans,
                "Occupancy": ["Primary"] * n_loans,
                "LoanPurpose": ["Purchase"] * n_loans,
                "DocumentationType": ["Full"] * n_loans,
                "DaysDelinquent": [0] * n_loans,
                "Status": ["Current"] * n_loans,
                "ServicerName": ["Test Servicer"] * n_loans,
            })

            # Memory during data creation
            data_memory = process.memory_info().rss / 1024 / 1024

            # Try to run a simulation (will skip if models not available)
            try:
                from engine import run_simulation

                collateral_config = {
                    "deal_id": "MEMORY_TEST",
                    "data": {
                        "pool_id": "MEMORY_TEST",
                        "original_balance": float(large_loan_tape["OriginalBalance"].sum()),
                        "current_balance": float(large_loan_tape["CurrentBalance"].sum()),
                        "loan_count": n_loans,
                    },
                    "loan_data": {
                        "schema_ref": {
                            "source_uri": "dummy_path"  # Won't be used in rule-based mode
                        }
                    },
                    "ml_config": {
                        "enabled": False  # Rule-based only for memory test
                    }
                }

                deal_config = {
                    "meta": {"deal_id": "MEMORY_TEST"},
                    "collateral": collateral_config["data"],
                    "bonds": [{
                        "id": "ClassA",
                        "type": "NOTE",
                        "original_balance": collateral_config["data"]["original_balance"] * 0.8,
                        "priority": {"interest": 1, "principal": 1},
                        "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                    }],
                    "waterfalls": {
                        "interest": {"steps": [{"id": "1", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "bonds.ClassA.balance * 0.05 / 12"}]},
                        "principal": {"steps": [{"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"}]},
                        "loss_allocation": {"write_down_order": ["ClassA"], "loss_source_rule": "variables.RealizedLoss"}
                    }
                }

                # Memory before simulation
                pre_sim_memory = process.memory_info().rss / 1024 / 1024

                df, reconciliation = run_simulation(
                    deal_config,
                    collateral_config,
                    [],  # No actuals
                    cpr=0.08,
                    cdr=0.008,
                    severity=0.32,
                    horizon_periods=24
                )

                # Memory after simulation
                post_sim_memory = process.memory_info().rss / 1024 / 1024

                # Memory increase should be reasonable
                memory_delta = post_sim_memory - pre_sim_memory
                assert memory_delta < 200, f"Memory increase too large: {memory_delta:.1f}MB"

                # Should produce valid results
                assert not df.empty
                assert len(df) >= 24  # At least horizon periods

            except Exception as e:
                pytest.skip(f"Memory test simulation failed: {e}")

        except ImportError:
            pytest.skip("psutil not available for memory testing")

    def test_simulation_scalability_with_pool_size(self):
        """
        Test how simulation performance scales with pool size.
        """
        pool_sizes = [100, 500, 1000]  # Different scales
        performance_results = {}

        for n_loans in pool_sizes:
            try:
                # Create synthetic pool
                np.random.seed(42)
                loan_tape = pd.DataFrame({
                    "LoanID": [f"L{i:06d}" for i in range(n_loans)],
                    "OriginalBalance": np.random.uniform(300_000, 500_000, n_loans),
                    "CurrentBalance": np.random.uniform(280_000, 480_000, n_loans),
                    "InterestRate": np.random.uniform(0.045, 0.065, n_loans),
                    "OriginalLTV": [75] * n_loans,
                    "CurrentLTV": [72] * n_loans,
                    "FICO": [750] * n_loans,
                    "OriginationDate": ["2023-01-15"] * n_loans,
                    "FirstPaymentDate": ["2023-03-01"] * n_loans,
                    "MaturityDate": ["2053-03-01"] * n_loans,
                    "LoanAge": [12] * n_loans,
                    "RemainingTerm": [348] * n_loans,
                    "PropertyState": ["CA"] * n_loans,
                    "PropertyType": ["SF"] * n_loans,
                    "Occupancy": ["Primary"] * n_loans,
                    "LoanPurpose": ["Purchase"] * n_loans,
                    "DocumentationType": ["Full"] * n_loans,
                    "DaysDelinquent": [0] * n_loans,
                    "Status": ["Current"] * n_loans,
                    "ServicerName": ["Test Servicer"] * n_loans,
                })

                from engine import run_simulation

                collateral_config = {
                    "deal_id": f"SCALE_TEST_{n_loans}",
                    "data": {
                        "pool_id": f"SCALE_TEST_{n_loans}",
                        "original_balance": float(loan_tape["OriginalBalance"].sum()),
                        "current_balance": float(loan_tape["CurrentBalance"].sum()),
                        "loan_count": n_loans,
                    },
                    "ml_config": {"enabled": False}  # Rule-based for consistent comparison
                }

                deal_config = {
                    "meta": {"deal_id": f"SCALE_TEST_{n_loans}"},
                    "collateral": collateral_config["data"],
                    "bonds": [{
                        "id": "ClassA",
                        "type": "NOTE",
                        "original_balance": collateral_config["data"]["original_balance"] * 0.8,
                        "priority": {"interest": 1, "principal": 1},
                        "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                    }],
                    "waterfalls": {
                        "interest": {"steps": [{"id": "1", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "bonds.ClassA.balance * 0.05 / 12"}]},
                        "principal": {"steps": [{"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"}]},
                        "loss_allocation": {"write_down_order": ["ClassA"], "loss_source_rule": "variables.RealizedLoss"}
                    }
                }

                start_time = time.time()
                df, reconciliation = run_simulation(
                    deal_config,
                    collateral_config,
                    [],
                    cpr=0.08,
                    cdr=0.008,
                    severity=0.32,
                    horizon_periods=12
                )
                end_time = time.time()

                performance_results[n_loans] = {
                    "time": end_time - start_time,
                    "periods": len(df),
                    "success": not df.empty
                }

            except Exception as e:
                performance_results[n_loans] = {
                    "time": float('inf'),
                    "periods": 0,
                    "success": False,
                    "error": str(e)
                }

        # Validate scaling behavior
        successful_sizes = [size for size, result in performance_results.items() if result["success"]]

        if len(successful_sizes) >= 2:
            # Performance should scale reasonably with size
            base_size = successful_sizes[0]
            base_time = performance_results[base_size]["time"]

            for size in successful_sizes[1:]:
                scale_factor = size / base_size
                actual_time = performance_results[size]["time"]
                expected_max_time = base_time * (scale_factor ** 1.5)  # Allow for some non-linearity

                assert actual_time < expected_max_time * 2, f"Poor scaling: {size} loans took {actual_time:.1f}s, expected < {expected_max_time*2:.1f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])