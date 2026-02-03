"""
Golden File Testing Framework
==============================

This module provides automated comparison of simulation results against
industry-standard outputs (Intex, Bloomberg, Moody's).

Golden file tests build confidence in model accuracy by validating that
our calculations match accepted benchmarks within specified tolerances.

Usage
-----
>>> from tests.test_golden_files import GoldenFileTest
>>> test = GoldenFileTest("tests/golden_files/FREDDIE_SAMPLE_001")
>>> result = test.run()
>>> print(f"Pass rate: {result.pass_rate:.1%}")
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.loader import DealLoader
from engine.state import DealState
from engine.waterfall import WaterfallRunner
from engine.compute import ExpressionEngine


@dataclass
class Tolerance:
    """Tolerance specification for value comparison."""
    absolute: float
    relative: float
    description: str
    
    def is_within_tolerance(self, expected: float, actual: float) -> Tuple[bool, float]:
        """
        Check if actual value is within tolerance of expected.
        
        Parameters
        ----------
        expected : float
            Expected value (from golden file).
        actual : float
            Actual value (from our simulation).
        
        Returns
        -------
        tuple
            (is_passing, difference) where is_passing is True if within tolerance
        """
        if expected == 0 and actual == 0:
            return True, 0.0
        
        diff = abs(actual - expected)
        
        # Use larger of absolute or relative tolerance
        abs_tol = self.absolute
        rel_tol = abs(expected * self.relative) if expected != 0 else 0
        
        max_tol = max(abs_tol, rel_tol)
        
        return diff <= max_tol, diff


@dataclass
class ComparisonResult:
    """Result of comparing a single metric."""
    metric_name: str
    period: int
    expected: float
    actual: float
    difference: float
    tolerance: float
    passed: bool
    category: str = "cashflow"
    
    @property
    def relative_error(self) -> float:
        """Calculate relative error as percentage."""
        if self.expected == 0:
            return 0.0
        return (self.difference / abs(self.expected)) * 100


@dataclass
class GoldenFileTestResult:
    """Complete result of a golden file test."""
    test_name: str
    total_comparisons: int = 0
    passed_comparisons: int = 0
    failed_comparisons: int = 0
    comparisons: List[ComparisonResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as fraction."""
        if self.total_comparisons == 0:
            return 0.0
        return self.passed_comparisons / self.total_comparisons
    
    def add_comparison(self, result: ComparisonResult) -> None:
        """Add a comparison result."""
        self.comparisons.append(result)
        self.total_comparisons += 1
        if result.passed:
            self.passed_comparisons += 1
        else:
            self.failed_comparisons += 1
    
    def get_failed_comparisons(self) -> List[ComparisonResult]:
        """Get list of failed comparisons."""
        return [c for c in self.comparisons if not c.passed]
    
    def summary(self) -> str:
        """Generate summary report."""
        lines = []
        lines.append(f"Golden File Test: {self.test_name}")
        lines.append("=" * 80)
        lines.append(f"Total Comparisons: {self.total_comparisons}")
        lines.append(f"Passed: {self.passed_comparisons}")
        lines.append(f"Failed: {self.failed_comparisons}")
        lines.append(f"Pass Rate: {self.pass_rate:.1%}")
        lines.append("")
        
        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  - {error}")
            lines.append("")
        
        if self.failed_comparisons > 0:
            lines.append("FAILED COMPARISONS:")
            lines.append("-" * 80)
            for comp in self.get_failed_comparisons():
                lines.append(f"Period {comp.period} - {comp.metric_name}:")
                lines.append(f"  Expected: ${comp.expected:,.2f}")
                lines.append(f"  Actual:   ${comp.actual:,.2f}")
                lines.append(f"  Diff:     ${comp.difference:,.2f} ({comp.relative_error:.2f}%)")
                lines.append(f"  Tolerance: ${comp.tolerance:,.2f}")
                lines.append("")
        
        return "\n".join(lines)


class GoldenFileTest:
    """
    Golden file test runner.
    
    Loads expected outputs and compares against simulation results.
    
    Parameters
    ----------
    test_dir : Path or str
        Directory containing test inputs and expected outputs.
    tolerance_file : Path or str, optional
        Path to tolerance configuration. Defaults to tests/golden_files/tolerance.json.
    
    Example
    -------
    >>> test = GoldenFileTest("tests/golden_files/FREDDIE_SAMPLE_001")
    >>> result = test.run()
    >>> if result.pass_rate >= 0.95:
    ...     print("✅ Test passed")
    """
    
    def __init__(self, test_dir: Path, tolerance_file: Optional[Path] = None):
        self.test_dir = Path(test_dir)
        self.test_name = self.test_dir.name
        
        # Load tolerance configuration
        if tolerance_file is None:
            tolerance_file = self.test_dir.parent / "tolerance.json"
        
        with open(tolerance_file) as f:
            tol_config = json.load(f)
        
        self.tolerances = {
            name: Tolerance(**spec)
            for name, spec in tol_config["tolerances"].items()
        }
    
    def run(self) -> GoldenFileTestResult:
        """
        Run the golden file test.
        
        Returns
        -------
        GoldenFileTestResult
            Complete test results with comparisons.
        """
        result = GoldenFileTestResult(test_name=self.test_name)
        
        try:
            # Load inputs
            deal_spec = self._load_deal_spec()
            expected_cashflows = self._load_expected_cashflows()
            expected_balances = self._load_expected_balances()
            
            # Run simulation
            actual_results = self._run_simulation(deal_spec)
            
            # Compare cashflows
            if expected_cashflows is not None:
                self._compare_cashflows(expected_cashflows, actual_results, result)
            
            # Compare balances
            if expected_balances is not None:
                self._compare_balances(expected_balances, actual_results, result)
            
        except Exception as e:
            result.errors.append(f"Test execution error: {str(e)}")
        
        return result
    
    def _load_deal_spec(self) -> Dict:
        """Load deal specification from input file."""
        spec_file = self.test_dir / "input_spec.json"
        if not spec_file.exists():
            raise FileNotFoundError(f"Deal spec not found: {spec_file}")
        
        with open(spec_file) as f:
            return json.load(f)
    
    def _load_expected_cashflows(self) -> Optional[pd.DataFrame]:
        """Load expected cashflows from golden file."""
        cf_file = self.test_dir / "expected_cashflows.csv"
        if not cf_file.exists():
            return None
        
        return pd.read_csv(cf_file)
    
    def _load_expected_balances(self) -> Optional[pd.DataFrame]:
        """Load expected balances from golden file."""
        bal_file = self.test_dir / "expected_balances.csv"
        if not bal_file.exists():
            return None
        
        return pd.read_csv(bal_file)
    
    def _run_simulation(self, deal_spec: Dict) -> Dict:
        """
        Run simulation and return results.
        
        Returns dict with keys:
        - snapshots: List of period snapshots
        - cashflows: DataFrame of cashflows by period
        - balances: DataFrame of balances by period
        """
        # Load deal
        loader = DealLoader()
        deal_def = loader.load_from_json(deal_spec)
        state = DealState(deal_def)
        
        # Initialize collateral
        collateral = deal_def.collateral
        state.collateral["current_balance"] = collateral.get("original_balance", 300000000)
        state.collateral["original_balance"] = collateral.get("original_balance", 300000000)
        state.collateral["wac"] = collateral.get("wac", 0.055)
        
        # Create runner
        engine = ExpressionEngine()
        runner = WaterfallRunner(engine, use_iterative_solver=True)
        
        # Run simulation (for demo, run 12 periods)
        for period in range(12):
            # Simplified cashflow generation
            coll_balance = state.collateral.get("current_balance", 300000000)
            coll_wac = state.collateral.get("wac", 0.055)
            gross_interest = coll_balance * coll_wac / 12
            
            state.deposit_funds("IAF", gross_interest)
            state.deposit_funds("PAF", 0)  # No principal for demo
            
            runner.run_period(state)
        
        # Extract results
        return {
            "snapshots": state.history,
            "cashflows": self._extract_cashflows(state),
            "balances": self._extract_balances(state)
        }
    
    def _extract_cashflows(self, state: DealState) -> pd.DataFrame:
        """Extract cashflows from simulation results."""
        # Simplified extraction for demo
        data = []
        for snap in state.history:
            data.append({
                "Period": snap.period,
                "Interest": snap.funds.get("IAF", 0),
                "Principal": snap.funds.get("PAF", 0),
            })
        return pd.DataFrame(data)
    
    def _extract_balances(self, state: DealState) -> pd.DataFrame:
        """Extract balances from simulation results."""
        # Simplified extraction for demo
        data = []
        for snap in state.history:
            row = {"Period": snap.period}
            row.update(snap.bond_balances)
            data.append(row)
        return pd.DataFrame(data)
    
    def _compare_cashflows(self, expected: pd.DataFrame, actual: Dict, result: GoldenFileTestResult) -> None:
        """Compare expected vs actual cashflows."""
        actual_df = actual["cashflows"]
        tolerance = self.tolerances["cashflows"]
        
        # Compare each metric in each period
        for _, exp_row in expected.iterrows():
            period = int(exp_row.get("Period", 0))
            
            # Find matching period in actual
            act_rows = actual_df[actual_df["Period"] == period]
            if len(act_rows) == 0:
                result.errors.append(f"Period {period} not found in simulation results")
                continue
            
            act_row = act_rows.iloc[0]
            
            # Compare each column (except Period)
            for col in expected.columns:
                if col == "Period":
                    continue
                
                if col not in act_row.index:
                    result.errors.append(f"Metric '{col}' not found in period {period}")
                    continue
                
                exp_val = float(exp_row[col])
                act_val = float(act_row[col])
                
                passed, diff = tolerance.is_within_tolerance(exp_val, act_val)
                
                comp = ComparisonResult(
                    metric_name=col,
                    period=period,
                    expected=exp_val,
                    actual=act_val,
                    difference=diff,
                    tolerance=max(tolerance.absolute, abs(exp_val * tolerance.relative)),
                    passed=passed,
                    category="cashflow"
                )
                result.add_comparison(comp)
    
    def _compare_balances(self, expected: pd.DataFrame, actual: Dict, result: GoldenFileTestResult) -> None:
        """Compare expected vs actual balances."""
        actual_df = actual["balances"]
        tolerance = self.tolerances["balances"]
        
        # Compare each metric in each period
        for _, exp_row in expected.iterrows():
            period = int(exp_row.get("Period", 0))
            
            # Find matching period in actual
            act_rows = actual_df[actual_df["Period"] == period]
            if len(act_rows) == 0:
                result.errors.append(f"Period {period} not found in simulation results")
                continue
            
            act_row = act_rows.iloc[0]
            
            # Compare each column (except Period)
            for col in expected.columns:
                if col == "Period":
                    continue
                
                if col not in act_row.index:
                    result.errors.append(f"Balance '{col}' not found in period {period}")
                    continue
                
                exp_val = float(exp_row[col])
                act_val = float(act_row[col])
                
                passed, diff = tolerance.is_within_tolerance(exp_val, act_val)
                
                comp = ComparisonResult(
                    metric_name=col,
                    period=period,
                    expected=exp_val,
                    actual=act_val,
                    difference=diff,
                    tolerance=max(tolerance.absolute, abs(exp_val * tolerance.relative)),
                    passed=passed,
                    category="balance"
                )
                result.add_comparison(comp)


def run_all_golden_tests(golden_dir: Path = None) -> List[GoldenFileTestResult]:
    """
    Run all golden file tests in the directory.
    
    Parameters
    ----------
    golden_dir : Path, optional
        Directory containing golden file test directories.
        Defaults to tests/golden_files/.
    
    Returns
    -------
    list
        List of test results.
    """
    if golden_dir is None:
        golden_dir = Path(__file__).parent / "golden_files"
    
    results = []
    
    # Find all test directories (subdirectories with input_spec.json)
    for test_dir in golden_dir.iterdir():
        if not test_dir.is_dir():
            continue
        
        if not (test_dir / "input_spec.json").exists():
            continue
        
        print(f"Running golden file test: {test_dir.name}")
        test = GoldenFileTest(test_dir)
        result = test.run()
        results.append(result)
        print(f"  Pass rate: {result.pass_rate:.1%} ({result.passed_comparisons}/{result.total_comparisons})")
        print()
    
    return results


if __name__ == "__main__":
    # Run all golden file tests
    print("=" * 80)
    print("GOLDEN FILE TEST SUITE")
    print("=" * 80)
    print()
    
    results = run_all_golden_tests()
    
    if not results:
        print("⚠️  No golden file tests found.")
        print("   Create test directories in tests/golden_files/ with:")
        print("   - input_spec.json")
        print("   - expected_cashflows.csv")
        print("   - expected_balances.csv")
    else:
        # Summary
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.pass_rate >= 0.95)
        
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed (≥95%): {passed_tests}")
        print(f"Failed (<95%): {total_tests - passed_tests}")
        print()
        
        # Show detailed results for failed tests
        for result in results:
            if result.pass_rate < 0.95:
                print(result.summary())
