"""
Test Caching Infrastructure
============================

This script demonstrates the performance benefits of caching
frequently-called financial calculations.
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))

from engine.cache_utils import (
    amortization_factor,
    discount_factor,
    cpr_to_smm,
    smm_to_cpr,
    get_cache_info,
    clear_all_caches
)


def main():
    """Run caching performance test."""
    print("=" * 80)
    print("CACHING INFRASTRUCTURE TEST")
    print("=" * 80)
    print()
    
    # Clear caches
    clear_all_caches()
    
    print("TEST SCENARIO: Calculating 10,000 amortization factors")
    print("-" * 80)
    print()
    
    # Common loan parameters (these will repeat often in a pool)
    common_rates = [0.03/12, 0.04/12, 0.05/12, 0.06/12, 0.07/12]
    common_terms = [360, 300, 240, 180, 120]
    
    # First pass: Cold cache
    print("Pass 1: Cold cache (no caching benefits yet)")
    start = time.time()
    for _ in range(2000):
        for rate in common_rates:
            for term in common_terms:
                _ = amortization_factor(rate, term)
    cold_time = time.time() - start
    print(f"  Time: {cold_time:.4f} seconds")
    print(f"  Calculations: 10,000")
    print()
    
    # Second pass: Warm cache
    print("Pass 2: Warm cache (caching benefits)")
    start = time.time()
    for _ in range(2000):
        for rate in common_rates:
            for term in common_terms:
                _ = amortization_factor(rate, term)
    warm_time = time.time() - start
    print(f"  Time: {warm_time:.4f} seconds")
    print(f"  Calculations: 10,000")
    print()
    
    # Calculate speedup
    speedup = cold_time / warm_time if warm_time > 0 else float('inf')
    
    print("PERFORMANCE IMPROVEMENT")
    print("-" * 80)
    print(f"Cold cache: {cold_time:.4f} seconds")
    print(f"Warm cache: {warm_time:.4f} seconds")
    print(f"Speedup: {speedup:.1f}x faster")
    print()
    
    # Show cache statistics
    print("CACHE STATISTICS")
    print("-" * 80)
    cache_stats = get_cache_info()
    for func_name, stats in cache_stats.items():
        if stats['hits'] > 0 or stats['misses'] > 0:
            hit_rate = stats['hits'] / (stats['hits'] + stats['misses']) * 100
            print(f"{func_name}:")
            print(f"  Hits: {stats['hits']:,}")
            print(f"  Misses: {stats['misses']:,}")
            print(f"  Hit Rate: {hit_rate:.1f}%")
            print(f"  Cache Size: {stats['currsize']}")
            print()
    
    # Test other cached functions
    print("TESTING OTHER CACHED FUNCTIONS")
    print("-" * 80)
    
    cpr = 0.06
    smm = cpr_to_smm(cpr)
    cpr_back = smm_to_cpr(smm)
    
    print(f"CPR to SMM conversion:")
    print(f"  Input CPR: {cpr:.2%}")
    print(f"  Calculated SMM: {smm:.4%}")
    print(f"  Back to CPR: {cpr_back:.2%}")
    print(f"  ✅ Round-trip accurate: {abs(cpr - cpr_back) < 0.0001}")
    print()
    
    # Discount factor test
    rate = 0.05 / 12
    periods = 360
    df = discount_factor(rate, periods)
    print(f"Discount Factor:")
    print(f"  Rate: {rate*12:.2%} annual")
    print(f"  Periods: {periods} months")
    print(f"  Discount Factor: {df:.6f}")
    print(f"  PV of $100: ${100 * df:.2f}")
    print()
    
    # Show final cache stats
    final_stats = get_cache_info()
    total_hits = sum(s['hits'] for s in final_stats.values())
    total_misses = sum(s['misses'] for s in final_stats.values())
    
    print("SUMMARY")
    print("-" * 80)
    print(f"Total cache hits: {total_hits:,}")
    print(f"Total cache misses: {total_misses:,}")
    print(f"Overall hit rate: {total_hits / (total_hits + total_misses) * 100:.1f}%")
    print()
    
    if speedup > 2:
        print(f"✅ Caching provides {speedup:.1f}x speedup for repeated calculations")
    else:
        print(f"⚠️  Caching provides {speedup:.1f}x speedup (may vary based on system)")
    
    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
