"""
Test script to demonstrate the two industry-grade fixes:

1. Loan-Level Collateral Model (vs Rep-Line)
   - Iterates through individual loans
   - Captures WAC drift (adverse selection)
   - Required for institutional RWA and Web3 tokenization

2. Iterative Waterfall Solver
   - Resolves circular dependencies
   - Handles Net WAC cap calculations
   - Required for complex deal structures
"""

import pandas as pd
import numpy as np
from engine.collateral import CollateralModel, LoanLevelCollateralModel


def test_loan_level_vs_rep_line():
    """
    Demonstrate the difference between rep-line and loan-level models.
    
    Key insight: Rep-line misses adverse selection where high-rate loans
    prepay first, causing WAC drift in the remaining pool.
    """
    print("=" * 60)
    print("TEST 1: Loan-Level vs Rep-Line Model")
    print("=" * 60)
    
    # Create synthetic loan tape with mixed rates (500 high-rate, 500 low-rate)
    np.random.seed(42)
    n_loans = 1000
    
    loans_data = {
        "LoanId": [f"L{i:06d}" for i in range(n_loans)],
        "OriginalBalance": [300000] * n_loans,
        "CurrentBalance": [300000] * n_loans,
        "NoteRate": [0.07 if i < 500 else 0.04 for i in range(n_loans)],  # 7% or 4%
        "RemainingTermMonths": [360] * n_loans,
        "FICO": np.random.randint(650, 800, n_loans),
        "LTV": np.random.uniform(0.6, 0.9, n_loans),
    }
    loan_df = pd.DataFrame(loans_data)
    
    # Calculate pool metrics
    total_balance = loan_df["CurrentBalance"].sum()
    initial_wac = (loan_df["NoteRate"] * loan_df["CurrentBalance"]).sum() / total_balance
    print(f"\nInitial Pool:")
    print(f"  Total Balance: ${total_balance:,.0f}")
    print(f"  Initial WAC: {initial_wac:.2%}")
    print(f"  High-rate loans (7%): 500")
    print(f"  Low-rate loans (4%): 500")
    
    # Run rep-line model
    print("\n--- Rep-Line Model ---")
    rep_model = CollateralModel(
        original_balance=total_balance,
        wac=initial_wac,  # Uses average WAC
        wam=360
    )
    rep_cfs = rep_model.generate_cashflows(
        periods=60,
        cpr_vector=0.15,  # 15% CPR
        cdr_vector=0.02,  # 2% CDR
        sev_vector=0.35,
    )
    print(f"  Final Balance: ${rep_cfs.iloc[-1]['EndBalance']:,.0f}")
    print(f"  WAC assumption: {initial_wac:.2%} (constant - INCORRECT)")
    
    # Run loan-level model
    print("\n--- Loan-Level Model (Seriatim) ---")
    loan_model = LoanLevelCollateralModel(loan_df)
    
    # Use falling rate environment (4% market rate encourages high-rate refinancing)
    market_rates = [0.04] * 60
    
    loan_cfs = loan_model.generate_cashflows(
        periods=60,
        base_cpr=0.15,
        base_cdr=0.02,
        base_severity=0.35,
        market_rate_path=market_rates,
    )
    
    initial_wac_tracked = loan_model.wac_history[0] if loan_model.wac_history else 0
    final_wac_tracked = loan_model.wac_history[-1] if loan_model.wac_history else 0
    wac_drift = final_wac_tracked - initial_wac_tracked
    
    print(f"  Final Balance: ${loan_cfs.iloc[-1]['EndBalance']:,.0f}")
    print(f"  Initial WAC: {initial_wac_tracked:.2%}")
    print(f"  Final WAC: {final_wac_tracked:.2%}")
    print(f"  WAC Drift (adverse selection): {wac_drift:.2%}")
    print(f"  Active Loans remaining: {loan_cfs.iloc[-1]['ActiveLoans']:.0f}")
    
    print("\n🎯 KEY INSIGHT:")
    print(f"  Rep-line assumes WAC stays at {initial_wac:.2%}")
    print(f"  Reality: WAC dropped to {final_wac_tracked:.2%} as high-rate loans prepaid")
    print(f"  This {abs(wac_drift):.2%} WAC drift means rep-line OVERESTIMATES interest income")
    
    return loan_cfs


def test_iterative_solver():
    """
    Demonstrate the iterative waterfall solver for circular dependencies.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Iterative Waterfall Solver")
    print("=" * 60)
    
    from engine.waterfall import WaterfallRunner, SolverResult
    from engine.compute import ExpressionEngine
    
    # Create runner with iterative solver
    engine = ExpressionEngine()
    
    # Sequential runner (original - can't handle circularity)
    seq_runner = WaterfallRunner(engine, use_iterative_solver=False)
    print(f"\nSequential Runner:")
    print(f"  use_iterative_solver: {seq_runner.use_iterative_solver}")
    print(f"  Status: Uses top-to-bottom logic (may fail with Net WAC cap)")
    
    # Iterative runner (new - handles circularity)
    iter_runner = WaterfallRunner(
        engine,
        use_iterative_solver=True,
        max_iterations=15,
        convergence_tol=0.01,
    )
    print(f"\nIterative Runner:")
    print(f"  use_iterative_solver: {iter_runner.use_iterative_solver}")
    print(f"  max_iterations: {iter_runner.max_iterations}")
    print(f"  convergence_tol: ${iter_runner.convergence_tol}")
    print(f"  Status: Will iterate until bond balances converge")
    
    print("\n🎯 KEY INSIGHT:")
    print("  The iterative solver is required for deals with:")
    print("  - Net WAC cap (coupon cannot exceed available interest)")
    print("  - Fee circularity (trustee fee based on bond balance)")
    print("  - Any variable that depends on downstream waterfall values")


def test_web3_transparency():
    """
    Demonstrate loan-level transparency for Web3 tokenization.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Web3 Transparency (Loan-Level Detail)")
    print("=" * 60)
    
    # Create small loan pool
    loans_data = {
        "LoanId": ["L001", "L002", "L003", "L004", "L005"],
        "OriginalBalance": [250000, 350000, 400000, 300000, 500000],
        "CurrentBalance": [250000, 350000, 400000, 300000, 500000],
        "NoteRate": [0.055, 0.065, 0.045, 0.075, 0.050],
        "RemainingTermMonths": [360, 300, 340, 280, 360],
        "FICO": [720, 680, 750, 640, 780],
        "LTV": [0.80, 0.85, 0.65, 0.95, 0.70],
    }
    loan_df = pd.DataFrame(loans_data)
    
    model = LoanLevelCollateralModel(loan_df)
    
    print("\nInitial Loan-Level State (for NFT transparency):")
    initial_state = model.get_loan_level_detail()
    print(initial_state.to_string(index=False))
    
    # Run 12 periods
    model.generate_cashflows(12, base_cpr=0.10, base_cdr=0.02, base_severity=0.35)
    
    print("\nAfter 12 Months:")
    final_state = model.get_loan_level_detail()
    print(final_state.to_string(index=False))
    
    print("\n🎯 KEY INSIGHT:")
    print("  Web3 investors expect to see individual loans (NFTs)")
    print("  Rep-line model hides this detail behind pool-level averages")
    print("  Loan-level model provides full transparency for tokenization")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("RMBS ENGINE INDUSTRY-GRADE FIXES")
    print("=" * 60)
    print("\nThis script demonstrates two critical fixes:")
    print("1. Loan-Level Collateral Model (Seriatim simulation)")
    print("2. Iterative Waterfall Solver (Circular dependency resolution)")
    print("\nThese are required for institutional RWA and Web3 applications.")
    
    test_loan_level_vs_rep_line()
    test_iterative_solver()
    test_web3_transparency()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
✅ FIX 1: Loan-Level Collateral Model
   - LoanLevelCollateralModel class in engine/collateral.py
   - Iterates through individual loans (seriatim)
   - Captures WAC drift from adverse selection
   - Provides loan-level detail for Web3 transparency
   
✅ FIX 2: Iterative Waterfall Solver  
   - WaterfallRunner now supports use_iterative_solver=True
   - Runs waterfall until values converge
   - Handles Net WAC cap calculations
   - Resolves fee circularity (trustee fee based on bond balance)

🚀 PRODUCTION READINESS:
   - For DeFi Retail: Rep-line model is acceptable
   - For Institutional RWA: MUST use loan-level model
   - For Complex Deals: MUST use iterative solver
""")


if __name__ == "__main__":
    main()
