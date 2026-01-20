"""
Portfolio Comparison Tools for RMBS Engine.
============================================

This module provides comprehensive tools for comparing RMBS portfolios
and deals, including:

- Side-by-side deal comparison
- Stratification analysis comparison
- Performance cohort analysis
- Vintage comparison
- Scenario outcome comparison
- Attribution analysis

Industry Context
----------------
Portfolio comparison is essential for:

1. **Investment Selection**: Comparing competing deals
2. **Relative Value Analysis**: Identifying mispricing
3. **Performance Benchmarking**: Against peers and indices
4. **Manager Evaluation**: Comparing servicer/originator performance
5. **Risk Assessment**: Understanding portfolio differences

Standard comparison dimensions:
- Credit quality (FICO, LTV distributions)
- Geographic concentration
- Product mix (fixed vs. ARM)
- Vintage and seasoning
- Performance metrics (CPR, CDR, severity)

References
----------
- Moody's ABS Performance Metrics
- S&P Global Ratings Analytics
- Bloomberg PORT Analytics

Examples
--------
>>> from rmbs_platform.engine.comparison import (
...     PortfolioComparator, ComparisonReport, DealComparer
... )
>>> 
>>> # Compare two portfolios
>>> comparator = PortfolioComparator()
>>> result = comparator.compare(portfolio_a, portfolio_b)
>>> print(result.summary())
>>> 
>>> # Generate comparison report
>>> report = comparator.generate_report(format='html')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


# =============================================================================
# Enums and Types
# =============================================================================

class ComparisonDimension(str, Enum):
    """
    Dimensions for portfolio comparison.
    """
    
    CREDIT_QUALITY = "Credit Quality"
    GEOGRAPHIC = "Geographic Distribution"
    PRODUCT_MIX = "Product Mix"
    VINTAGE = "Vintage/Seasoning"
    PERFORMANCE = "Historical Performance"
    STRUCTURE = "Deal Structure"
    PRICING = "Pricing/Spread"
    COLLATERAL = "Collateral Characteristics"


class MetricType(str, Enum):
    """
    Types of comparison metrics.
    """
    
    ABSOLUTE = "Absolute"
    RELATIVE = "Relative"
    PERCENTILE = "Percentile"
    Z_SCORE = "Z-Score"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PortfolioCharacteristics:
    """
    Summary characteristics of a loan portfolio.
    
    Parameters
    ----------
    portfolio_id : str
        Unique portfolio identifier
    as_of_date : date
        Date of the characteristics
    loan_count : int
        Number of loans
    total_balance : float
        Total current balance
    wac : float
        Weighted average coupon
    wam : float
        Weighted average maturity (months)
    avg_fico : float
        Average FICO score
    avg_ltv : float
        Average LTV ratio
    avg_loan_size : float
        Average loan balance
    """
    
    portfolio_id: str
    as_of_date: date
    
    # Size metrics
    loan_count: int = 0
    total_balance: float = 0.0
    original_balance: float = 0.0
    
    # Weighted averages
    wac: float = 0.0  # Weighted Average Coupon
    wam: float = 0.0  # Weighted Average Maturity
    wala: float = 0.0  # Weighted Average Loan Age
    
    # Credit metrics
    avg_fico: float = 0.0
    avg_ltv: float = 0.0
    avg_dti: float = 0.0
    avg_loan_size: float = 0.0
    
    # Distributions (as dicts)
    fico_distribution: Dict[str, float] = field(default_factory=dict)
    ltv_distribution: Dict[str, float] = field(default_factory=dict)
    state_distribution: Dict[str, float] = field(default_factory=dict)
    property_type_distribution: Dict[str, float] = field(default_factory=dict)
    loan_purpose_distribution: Dict[str, float] = field(default_factory=dict)
    
    # Performance
    current_cpr: float = 0.0
    current_cdr: float = 0.0
    lifetime_cpr: float = 0.0
    lifetime_cdr: float = 0.0
    delinquency_30_plus: float = 0.0
    delinquency_60_plus: float = 0.0
    delinquency_90_plus: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ComparisonMetric:
    """
    A single comparison metric between portfolios.
    
    Parameters
    ----------
    name : str
        Metric name
    dimension : ComparisonDimension
        Comparison dimension
    portfolio_a_value : float
        Value for portfolio A
    portfolio_b_value : float
        Value for portfolio B
    difference : float
        Absolute difference (B - A)
    difference_pct : float
        Percentage difference
    """
    
    name: str
    dimension: ComparisonDimension
    portfolio_a_value: Any
    portfolio_b_value: Any
    difference: float = 0.0
    difference_pct: float = 0.0
    significance: str = "neutral"  # favorable, unfavorable, neutral
    description: str = ""
    
    def __post_init__(self):
        if isinstance(self.portfolio_a_value, (int, float)) and isinstance(self.portfolio_b_value, (int, float)):
            self.difference = self.portfolio_b_value - self.portfolio_a_value
            if self.portfolio_a_value != 0:
                self.difference_pct = self.difference / abs(self.portfolio_a_value) * 100


@dataclass
class StratificationComparison:
    """
    Comparison of stratification buckets between portfolios.
    
    Parameters
    ----------
    dimension : str
        Stratification dimension (e.g., 'FICO', 'LTV')
    buckets : List[str]
        Bucket labels
    portfolio_a : Dict[str, float]
        Distribution for portfolio A
    portfolio_b : Dict[str, float]
        Distribution for portfolio B
    """
    
    dimension: str
    buckets: List[str]
    portfolio_a: Dict[str, float]
    portfolio_b: Dict[str, float]
    
    @property
    def differences(self) -> Dict[str, float]:
        """Calculate bucket-level differences."""
        return {
            bucket: self.portfolio_b.get(bucket, 0) - self.portfolio_a.get(bucket, 0)
            for bucket in self.buckets
        }
    
    @property
    def max_deviation(self) -> Tuple[str, float]:
        """Find bucket with maximum deviation."""
        diffs = self.differences
        max_bucket = max(diffs, key=lambda x: abs(diffs[x]))
        return max_bucket, diffs[max_bucket]
    
    def chi_square_test(self) -> Dict[str, float]:
        """Perform chi-square test for distribution similarity."""
        from scipy import stats
        
        observed = np.array([self.portfolio_b.get(b, 0) for b in self.buckets])
        expected = np.array([self.portfolio_a.get(b, 0) for b in self.buckets])
        
        # Normalize to same total
        if observed.sum() > 0 and expected.sum() > 0:
            expected = expected * (observed.sum() / expected.sum())
            
            # Avoid division by zero
            mask = expected > 0
            if mask.any():
                chi2, p_value = stats.chisquare(observed[mask], expected[mask])
                return {"chi_square": chi2, "p_value": p_value}
        
        return {"chi_square": 0.0, "p_value": 1.0}


@dataclass  
class ComparisonResult:
    """
    Complete comparison result between two portfolios.
    
    Parameters
    ----------
    portfolio_a_id : str
        First portfolio identifier
    portfolio_b_id : str
        Second portfolio identifier
    comparison_date : date
        Date of comparison
    metrics : List[ComparisonMetric]
        Individual metric comparisons
    stratifications : List[StratificationComparison]
        Stratification comparisons
    """
    
    portfolio_a_id: str
    portfolio_b_id: str
    comparison_date: date
    portfolio_a_chars: Optional[PortfolioCharacteristics] = None
    portfolio_b_chars: Optional[PortfolioCharacteristics] = None
    metrics: List[ComparisonMetric] = field(default_factory=list)
    stratifications: List[StratificationComparison] = field(default_factory=list)
    summary_text: str = ""
    
    def get_metrics_by_dimension(self, dimension: ComparisonDimension) -> List[ComparisonMetric]:
        """Get metrics for a specific dimension."""
        return [m for m in self.metrics if m.dimension == dimension]
    
    def get_favorable_metrics(self, for_portfolio: str = "B") -> List[ComparisonMetric]:
        """Get metrics where specified portfolio is favorable."""
        return [m for m in self.metrics if m.significance == "favorable"]
    
    def get_unfavorable_metrics(self) -> List[ComparisonMetric]:
        """Get metrics marked as unfavorable."""
        return [m for m in self.metrics if m.significance == "unfavorable"]
    
    def summary(self) -> str:
        """Generate text summary of comparison."""
        lines = [
            f"Portfolio Comparison: {self.portfolio_a_id} vs {self.portfolio_b_id}",
            f"As of: {self.comparison_date}",
            "-" * 60,
        ]
        
        # Group by dimension
        for dim in ComparisonDimension:
            dim_metrics = self.get_metrics_by_dimension(dim)
            if dim_metrics:
                lines.append(f"\n{dim.value}:")
                for m in dim_metrics:
                    diff_str = f"{m.difference:+.2f}" if isinstance(m.difference, float) else str(m.difference)
                    lines.append(f"  {m.name}: {m.portfolio_a_value} vs {m.portfolio_b_value} ({diff_str})")
        
        return "\n".join(lines)
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert metrics to DataFrame."""
        records = []
        for m in self.metrics:
            records.append({
                "Dimension": m.dimension.value,
                "Metric": m.name,
                f"{self.portfolio_a_id}": m.portfolio_a_value,
                f"{self.portfolio_b_id}": m.portfolio_b_value,
                "Difference": m.difference,
                "Diff %": m.difference_pct,
                "Significance": m.significance,
            })
        return pd.DataFrame(records)


# =============================================================================
# Portfolio Comparator
# =============================================================================

class PortfolioComparator:
    """
    Compare two loan portfolios across multiple dimensions.
    
    Provides comprehensive comparison including credit quality,
    geographic distribution, performance metrics, and more.
    
    Parameters
    ----------
    benchmark_id : Optional[str]
        Identifier for benchmark/reference portfolio
    custom_metrics : Optional[Dict[str, Callable]]
        Custom metric calculation functions
    
    Examples
    --------
    >>> comparator = PortfolioComparator()
    >>> 
    >>> # Compare DataFrames directly
    >>> result = comparator.compare_dataframes(df_a, df_b)
    >>> 
    >>> # Compare portfolio characteristics
    >>> result = comparator.compare_characteristics(chars_a, chars_b)
    >>> 
    >>> # Generate comparison report
    >>> html_report = comparator.generate_html_report(result)
    """
    
    def __init__(
        self,
        benchmark_id: Optional[str] = None,
        custom_metrics: Optional[Dict[str, Callable]] = None,
        significance_thresholds: Optional[Dict[str, float]] = None,
    ) -> None:
        self.benchmark_id = benchmark_id
        self.custom_metrics = custom_metrics or {}
        
        # Thresholds for determining significance
        self.thresholds = significance_thresholds or {
            "fico": 20,  # 20 point difference is significant
            "ltv": 5,    # 5% LTV difference
            "wac": 0.25, # 25 bps coupon difference
            "delinquency": 1.0,  # 1% delinquency difference
            "concentration": 5.0,  # 5% geographic concentration
        }
    
    def calculate_characteristics(
        self,
        loans_df: pd.DataFrame,
        portfolio_id: str,
        as_of_date: Optional[date] = None,
    ) -> PortfolioCharacteristics:
        """
        Calculate portfolio characteristics from loan data.
        
        Parameters
        ----------
        loans_df : pd.DataFrame
            Loan-level data
        portfolio_id : str
            Portfolio identifier
        as_of_date : Optional[date]
            As-of date for characteristics
            
        Returns
        -------
        PortfolioCharacteristics
            Calculated characteristics
        """
        df = loans_df.copy()
        as_of = as_of_date or date.today()
        
        # Standardize column names
        col_map = {
            'Current_Balance': 'current_balance',
            'Original_Balance': 'original_balance',
            'Interest_Rate': 'interest_rate',
            'Remaining_Term': 'remaining_term',
            'Loan_Age': 'loan_age',
            'FICO': 'fico',
            'LTV': 'ltv',
            'DTI': 'dti',
            'State': 'state',
            'Property_Type': 'property_type',
            'Loan_Purpose': 'loan_purpose',
        }
        
        for old, new in col_map.items():
            if old in df.columns and new not in df.columns:
                df[new] = df[old]
        
        # Calculate metrics
        total_balance = df['current_balance'].sum() if 'current_balance' in df else 0
        
        chars = PortfolioCharacteristics(
            portfolio_id=portfolio_id,
            as_of_date=as_of,
            loan_count=len(df),
            total_balance=total_balance,
            original_balance=df['original_balance'].sum() if 'original_balance' in df else total_balance,
            avg_loan_size=total_balance / len(df) if len(df) > 0 else 0,
        )
        
        # Weighted averages
        if total_balance > 0 and 'current_balance' in df:
            weights = df['current_balance'] / total_balance
            
            if 'interest_rate' in df:
                chars.wac = (df['interest_rate'] * weights).sum()
            
            if 'remaining_term' in df:
                chars.wam = (df['remaining_term'] * weights).sum()
            
            if 'loan_age' in df:
                chars.wala = (df['loan_age'] * weights).sum()
            
            if 'fico' in df:
                chars.avg_fico = (df['fico'] * weights).sum()
            
            if 'ltv' in df:
                chars.avg_ltv = (df['ltv'] * weights).sum()
            
            if 'dti' in df:
                chars.avg_dti = (df['dti'] * weights).sum()
        
        # Distributions
        if 'fico' in df:
            chars.fico_distribution = self._calculate_fico_distribution(df)
        
        if 'ltv' in df:
            chars.ltv_distribution = self._calculate_ltv_distribution(df)
        
        if 'state' in df:
            chars.state_distribution = self._calculate_concentration(df, 'state')
        
        if 'property_type' in df:
            chars.property_type_distribution = self._calculate_concentration(df, 'property_type')
        
        return chars
    
    def _calculate_fico_distribution(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate FICO score distribution by bucket."""
        bins = [0, 620, 660, 700, 740, 780, 900]
        labels = ['<620', '620-659', '660-699', '700-739', '740-779', '780+']
        
        df['fico_bucket'] = pd.cut(df['fico'], bins=bins, labels=labels, right=False)
        
        if 'current_balance' in df:
            dist = df.groupby('fico_bucket', observed=True)['current_balance'].sum()
            total = dist.sum()
            if total > 0:
                return (dist / total * 100).to_dict()
        
        dist = df['fico_bucket'].value_counts(normalize=True) * 100
        return dist.to_dict()
    
    def _calculate_ltv_distribution(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate LTV distribution by bucket."""
        bins = [0, 60, 70, 80, 90, 100, 200]
        labels = ['<60%', '60-69%', '70-79%', '80-89%', '90-100%', '>100%']
        
        df['ltv_bucket'] = pd.cut(df['ltv'], bins=bins, labels=labels, right=False)
        
        if 'current_balance' in df:
            dist = df.groupby('ltv_bucket', observed=True)['current_balance'].sum()
            total = dist.sum()
            if total > 0:
                return (dist / total * 100).to_dict()
        
        dist = df['ltv_bucket'].value_counts(normalize=True) * 100
        return dist.to_dict()
    
    def _calculate_concentration(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """Calculate concentration by categorical field."""
        if 'current_balance' in df:
            dist = df.groupby(column)['current_balance'].sum()
            total = dist.sum()
            if total > 0:
                return (dist / total * 100).to_dict()
        
        return df[column].value_counts(normalize=True).to_dict()
    
    def compare_dataframes(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        portfolio_a_id: str = "Portfolio A",
        portfolio_b_id: str = "Portfolio B",
        as_of_date: Optional[date] = None,
    ) -> ComparisonResult:
        """
        Compare two loan portfolios from DataFrames.
        
        Parameters
        ----------
        df_a : pd.DataFrame
            First portfolio loan data
        df_b : pd.DataFrame
            Second portfolio loan data
        portfolio_a_id : str
            First portfolio identifier
        portfolio_b_id : str
            Second portfolio identifier
        as_of_date : Optional[date]
            Comparison date
            
        Returns
        -------
        ComparisonResult
            Complete comparison result
        """
        as_of = as_of_date or date.today()
        
        # Calculate characteristics
        chars_a = self.calculate_characteristics(df_a, portfolio_a_id, as_of)
        chars_b = self.calculate_characteristics(df_b, portfolio_b_id, as_of)
        
        return self.compare_characteristics(chars_a, chars_b)
    
    def compare_characteristics(
        self,
        chars_a: PortfolioCharacteristics,
        chars_b: PortfolioCharacteristics,
    ) -> ComparisonResult:
        """
        Compare two portfolio characteristics objects.
        
        Parameters
        ----------
        chars_a : PortfolioCharacteristics
            First portfolio characteristics
        chars_b : PortfolioCharacteristics
            Second portfolio characteristics
            
        Returns
        -------
        ComparisonResult
            Comparison result
        """
        result = ComparisonResult(
            portfolio_a_id=chars_a.portfolio_id,
            portfolio_b_id=chars_b.portfolio_id,
            comparison_date=max(chars_a.as_of_date, chars_b.as_of_date),
            portfolio_a_chars=chars_a,
            portfolio_b_chars=chars_b,
        )
        
        # Credit Quality Metrics
        result.metrics.extend([
            ComparisonMetric(
                name="Weighted Avg FICO",
                dimension=ComparisonDimension.CREDIT_QUALITY,
                portfolio_a_value=round(chars_a.avg_fico, 0),
                portfolio_b_value=round(chars_b.avg_fico, 0),
                significance=self._assess_significance("fico", chars_b.avg_fico - chars_a.avg_fico, higher_better=True),
            ),
            ComparisonMetric(
                name="Weighted Avg LTV",
                dimension=ComparisonDimension.CREDIT_QUALITY,
                portfolio_a_value=round(chars_a.avg_ltv, 1),
                portfolio_b_value=round(chars_b.avg_ltv, 1),
                significance=self._assess_significance("ltv", chars_b.avg_ltv - chars_a.avg_ltv, higher_better=False),
            ),
            ComparisonMetric(
                name="Weighted Avg DTI",
                dimension=ComparisonDimension.CREDIT_QUALITY,
                portfolio_a_value=round(chars_a.avg_dti, 1),
                portfolio_b_value=round(chars_b.avg_dti, 1),
                significance=self._assess_significance("ltv", chars_b.avg_dti - chars_a.avg_dti, higher_better=False),
            ),
        ])
        
        # Collateral Characteristics
        result.metrics.extend([
            ComparisonMetric(
                name="Loan Count",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=chars_a.loan_count,
                portfolio_b_value=chars_b.loan_count,
            ),
            ComparisonMetric(
                name="Total Balance ($M)",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=round(chars_a.total_balance / 1_000_000, 1),
                portfolio_b_value=round(chars_b.total_balance / 1_000_000, 1),
            ),
            ComparisonMetric(
                name="Avg Loan Size ($K)",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=round(chars_a.avg_loan_size / 1_000, 1),
                portfolio_b_value=round(chars_b.avg_loan_size / 1_000, 1),
            ),
            ComparisonMetric(
                name="WAC",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=round(chars_a.wac * 100, 3),
                portfolio_b_value=round(chars_b.wac * 100, 3),
                significance=self._assess_significance("wac", (chars_b.wac - chars_a.wac) * 100, higher_better=True),
            ),
            ComparisonMetric(
                name="WAM (months)",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=round(chars_a.wam, 0),
                portfolio_b_value=round(chars_b.wam, 0),
            ),
            ComparisonMetric(
                name="WALA (months)",
                dimension=ComparisonDimension.COLLATERAL,
                portfolio_a_value=round(chars_a.wala, 0),
                portfolio_b_value=round(chars_b.wala, 0),
            ),
        ])
        
        # Performance Metrics
        result.metrics.extend([
            ComparisonMetric(
                name="Current CPR",
                dimension=ComparisonDimension.PERFORMANCE,
                portfolio_a_value=round(chars_a.current_cpr, 2),
                portfolio_b_value=round(chars_b.current_cpr, 2),
            ),
            ComparisonMetric(
                name="Current CDR",
                dimension=ComparisonDimension.PERFORMANCE,
                portfolio_a_value=round(chars_a.current_cdr, 2),
                portfolio_b_value=round(chars_b.current_cdr, 2),
                significance=self._assess_significance("delinquency", chars_b.current_cdr - chars_a.current_cdr, higher_better=False),
            ),
            ComparisonMetric(
                name="30+ DQ %",
                dimension=ComparisonDimension.PERFORMANCE,
                portfolio_a_value=round(chars_a.delinquency_30_plus, 2),
                portfolio_b_value=round(chars_b.delinquency_30_plus, 2),
                significance=self._assess_significance("delinquency", chars_b.delinquency_30_plus - chars_a.delinquency_30_plus, higher_better=False),
            ),
            ComparisonMetric(
                name="60+ DQ %",
                dimension=ComparisonDimension.PERFORMANCE,
                portfolio_a_value=round(chars_a.delinquency_60_plus, 2),
                portfolio_b_value=round(chars_b.delinquency_60_plus, 2),
                significance=self._assess_significance("delinquency", chars_b.delinquency_60_plus - chars_a.delinquency_60_plus, higher_better=False),
            ),
            ComparisonMetric(
                name="90+ DQ %",
                dimension=ComparisonDimension.PERFORMANCE,
                portfolio_a_value=round(chars_a.delinquency_90_plus, 2),
                portfolio_b_value=round(chars_b.delinquency_90_plus, 2),
                significance=self._assess_significance("delinquency", chars_b.delinquency_90_plus - chars_a.delinquency_90_plus, higher_better=False),
            ),
        ])
        
        # Stratification comparisons
        if chars_a.fico_distribution and chars_b.fico_distribution:
            all_buckets = list(set(chars_a.fico_distribution.keys()) | set(chars_b.fico_distribution.keys()))
            result.stratifications.append(StratificationComparison(
                dimension="FICO Score",
                buckets=sorted(all_buckets),
                portfolio_a=chars_a.fico_distribution,
                portfolio_b=chars_b.fico_distribution,
            ))
        
        if chars_a.ltv_distribution and chars_b.ltv_distribution:
            all_buckets = list(set(chars_a.ltv_distribution.keys()) | set(chars_b.ltv_distribution.keys()))
            result.stratifications.append(StratificationComparison(
                dimension="LTV",
                buckets=sorted(all_buckets),
                portfolio_a=chars_a.ltv_distribution,
                portfolio_b=chars_b.ltv_distribution,
            ))
        
        if chars_a.state_distribution and chars_b.state_distribution:
            # Top 10 states
            top_states = sorted(
                set(chars_a.state_distribution.keys()) | set(chars_b.state_distribution.keys()),
                key=lambda s: chars_a.state_distribution.get(s, 0) + chars_b.state_distribution.get(s, 0),
                reverse=True
            )[:10]
            result.stratifications.append(StratificationComparison(
                dimension="Geographic (Top 10)",
                buckets=top_states,
                portfolio_a={s: chars_a.state_distribution.get(s, 0) for s in top_states},
                portfolio_b={s: chars_b.state_distribution.get(s, 0) for s in top_states},
            ))
        
        # Generate summary
        result.summary_text = self._generate_summary_text(result)
        
        return result
    
    def _assess_significance(
        self,
        metric_type: str,
        difference: float,
        higher_better: bool = True,
    ) -> str:
        """Assess significance of a metric difference."""
        threshold = self.thresholds.get(metric_type, 0)
        
        if abs(difference) < threshold:
            return "neutral"
        
        if higher_better:
            return "favorable" if difference > 0 else "unfavorable"
        else:
            return "favorable" if difference < 0 else "unfavorable"
    
    def _generate_summary_text(self, result: ComparisonResult) -> str:
        """Generate natural language summary of comparison."""
        lines = []
        
        favorable = result.get_favorable_metrics()
        unfavorable = result.get_unfavorable_metrics()
        
        if favorable:
            lines.append(f"Portfolio {result.portfolio_b_id} shows favorable characteristics in:")
            for m in favorable[:5]:
                lines.append(f"  - {m.name}: {m.difference:+.2f} ({m.difference_pct:+.1f}%)")
        
        if unfavorable:
            lines.append(f"\nPortfolio {result.portfolio_b_id} shows weaker characteristics in:")
            for m in unfavorable[:5]:
                lines.append(f"  - {m.name}: {m.difference:+.2f} ({m.difference_pct:+.1f}%)")
        
        return "\n".join(lines) if lines else "Portfolios are comparable across major metrics."
    
    def generate_html_report(self, result: ComparisonResult) -> str:
        """
        Generate HTML comparison report.
        
        Parameters
        ----------
        result : ComparisonResult
            Comparison result to format
            
        Returns
        -------
        str
            HTML report content
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Comparison: {result.portfolio_a_id} vs {result.portfolio_b_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .favorable {{ color: green; }}
        .unfavorable {{ color: red; }}
        .neutral {{ color: #666; }}
        .summary {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Portfolio Comparison Report</h1>
    <p>Generated: {result.comparison_date}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <pre>{result.summary_text}</pre>
    </div>
    
    <h2>Detailed Metrics</h2>
    <table>
        <tr>
            <th>Dimension</th>
            <th>Metric</th>
            <th>{result.portfolio_a_id}</th>
            <th>{result.portfolio_b_id}</th>
            <th>Difference</th>
            <th>Diff %</th>
        </tr>
"""
        for m in result.metrics:
            sig_class = m.significance
            html += f"""
        <tr class="{sig_class}">
            <td style="text-align:left">{m.dimension.value}</td>
            <td style="text-align:left">{m.name}</td>
            <td>{m.portfolio_a_value}</td>
            <td>{m.portfolio_b_value}</td>
            <td>{m.difference:+.2f}</td>
            <td>{m.difference_pct:+.1f}%</td>
        </tr>
"""
        
        html += """
    </table>
</body>
</html>
"""
        return html


# =============================================================================
# Deal Structure Comparator
# =============================================================================

class DealStructureComparator:
    """
    Compare deal structures (waterfall, tranches, triggers).
    
    Parameters
    ----------
    include_cashflow_analysis : bool
        Include projected cashflow comparison
    
    Examples
    --------
    >>> comparator = DealStructureComparator()
    >>> result = comparator.compare_deals(deal_a, deal_b)
    """
    
    def __init__(
        self,
        include_cashflow_analysis: bool = True,
    ) -> None:
        self.include_cashflow_analysis = include_cashflow_analysis
    
    def compare_deals(
        self,
        deal_a: Dict[str, Any],
        deal_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare two deal structures.
        
        Parameters
        ----------
        deal_a : Dict[str, Any]
            First deal specification
        deal_b : Dict[str, Any]
            Second deal specification
            
        Returns
        -------
        Dict[str, Any]
            Structure comparison
        """
        comparison = {
            "deal_a_id": deal_a.get("deal_id", "Deal A"),
            "deal_b_id": deal_b.get("deal_id", "Deal B"),
            "comparison_date": date.today().isoformat(),
            "tranche_comparison": self._compare_tranches(deal_a, deal_b),
            "waterfall_comparison": self._compare_waterfalls(deal_a, deal_b),
            "trigger_comparison": self._compare_triggers(deal_a, deal_b),
            "account_comparison": self._compare_accounts(deal_a, deal_b),
        }
        
        return comparison
    
    def _compare_tranches(
        self,
        deal_a: Dict[str, Any],
        deal_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare tranche structures."""
        tranches_a = deal_a.get("bonds", [])
        tranches_b = deal_b.get("bonds", [])
        
        # Convert to comparable format
        def normalize_tranches(tranches):
            result = {}
            for t in tranches:
                if isinstance(t, dict):
                    tid = t.get("id", t.get("bond_id", "Unknown"))
                    result[tid] = t
            return result
        
        norm_a = normalize_tranches(tranches_a)
        norm_b = normalize_tranches(tranches_b)
        
        all_ids = set(norm_a.keys()) | set(norm_b.keys())
        
        tranche_diffs = []
        for tid in all_ids:
            ta = norm_a.get(tid, {})
            tb = norm_b.get(tid, {})
            
            diff = {
                "tranche_id": tid,
                "in_deal_a": tid in norm_a,
                "in_deal_b": tid in norm_b,
                "balance_a": ta.get("original_balance", ta.get("balance", 0)),
                "balance_b": tb.get("original_balance", tb.get("balance", 0)),
                "coupon_a": ta.get("coupon_rate", ta.get("rate", 0)),
                "coupon_b": tb.get("coupon_rate", tb.get("rate", 0)),
            }
            tranche_diffs.append(diff)
        
        return {
            "count_a": len(norm_a),
            "count_b": len(norm_b),
            "total_balance_a": sum(t.get("original_balance", t.get("balance", 0)) for t in norm_a.values()),
            "total_balance_b": sum(t.get("original_balance", t.get("balance", 0)) for t in norm_b.values()),
            "tranches": tranche_diffs,
        }
    
    def _compare_waterfalls(
        self,
        deal_a: Dict[str, Any],
        deal_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare waterfall structures."""
        wf_a = deal_a.get("waterfall", {})
        wf_b = deal_b.get("waterfall", {})
        
        return {
            "interest_waterfall_a": wf_a.get("interest", []),
            "interest_waterfall_b": wf_b.get("interest", []),
            "principal_waterfall_a": wf_a.get("principal", []),
            "principal_waterfall_b": wf_b.get("principal", []),
            "step_count_a": len(wf_a.get("interest", [])) + len(wf_a.get("principal", [])),
            "step_count_b": len(wf_b.get("interest", [])) + len(wf_b.get("principal", [])),
        }
    
    def _compare_triggers(
        self,
        deal_a: Dict[str, Any],
        deal_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare deal triggers."""
        triggers_a = deal_a.get("triggers", [])
        triggers_b = deal_b.get("triggers", [])
        
        return {
            "trigger_count_a": len(triggers_a),
            "trigger_count_b": len(triggers_b),
            "triggers_a": triggers_a,
            "triggers_b": triggers_b,
        }
    
    def _compare_accounts(
        self,
        deal_a: Dict[str, Any],
        deal_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare account structures."""
        accounts_a = deal_a.get("accounts", [])
        accounts_b = deal_b.get("accounts", [])
        
        return {
            "account_count_a": len(accounts_a),
            "account_count_b": len(accounts_b),
            "accounts_a": accounts_a,
            "accounts_b": accounts_b,
        }


# =============================================================================
# Vintage Comparator
# =============================================================================

class VintageComparator:
    """
    Compare loan performance by origination vintage.
    
    Analyzes how different origination cohorts perform over time.
    
    Examples
    --------
    >>> comparator = VintageComparator()
    >>> vintage_analysis = comparator.analyze_vintages(performance_df)
    """
    
    def __init__(self) -> None:
        pass
    
    def analyze_vintages(
        self,
        performance_df: pd.DataFrame,
        vintage_column: str = "origination_date",
        balance_column: str = "current_balance",
        original_balance_column: str = "original_balance",
    ) -> pd.DataFrame:
        """
        Analyze performance by vintage.
        
        Parameters
        ----------
        performance_df : pd.DataFrame
            Loan performance data
        vintage_column : str
            Column containing origination date
        balance_column : str
            Column with current balance
        original_balance_column : str
            Column with original balance
            
        Returns
        -------
        pd.DataFrame
            Vintage performance summary
        """
        df = performance_df.copy()
        
        # Extract vintage year-quarter
        df['vintage'] = pd.to_datetime(df[vintage_column]).dt.to_period('Q')
        
        # Aggregate by vintage
        vintage_summary = df.groupby('vintage').agg({
            balance_column: ['sum', 'count'],
            original_balance_column: 'sum',
        }).round(2)
        
        vintage_summary.columns = ['current_balance', 'loan_count', 'original_balance']
        vintage_summary['pool_factor'] = vintage_summary['current_balance'] / vintage_summary['original_balance']
        
        return vintage_summary.reset_index()
    
    def compare_vintage_performance(
        self,
        performance_df: pd.DataFrame,
        vintage_a: str,
        vintage_b: str,
    ) -> Dict[str, Any]:
        """
        Compare performance between two specific vintages.
        
        Parameters
        ----------
        performance_df : pd.DataFrame
            Performance data
        vintage_a : str
            First vintage (e.g., '2020Q1')
        vintage_b : str
            Second vintage (e.g., '2021Q1')
            
        Returns
        -------
        Dict[str, Any]
            Comparison results
        """
        vintage_data = self.analyze_vintages(performance_df)
        
        row_a = vintage_data[vintage_data['vintage'].astype(str) == vintage_a]
        row_b = vintage_data[vintage_data['vintage'].astype(str) == vintage_b]
        
        if row_a.empty or row_b.empty:
            return {"error": "One or both vintages not found"}
        
        return {
            "vintage_a": vintage_a,
            "vintage_b": vintage_b,
            "loan_count_a": row_a['loan_count'].iloc[0],
            "loan_count_b": row_b['loan_count'].iloc[0],
            "pool_factor_a": row_a['pool_factor'].iloc[0],
            "pool_factor_b": row_b['pool_factor'].iloc[0],
            "factor_difference": row_b['pool_factor'].iloc[0] - row_a['pool_factor'].iloc[0],
        }
