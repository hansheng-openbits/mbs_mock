"""
Standard RMBS Reporting Templates
=================================

This module provides industry-standard reporting templates for RMBS deals:

1. **Factor Report**: Monthly pool and bond factors for price/yield analysis.
2. **Distribution Report**: Detailed breakdown of cashflows to each tranche.
3. **Collateral Performance Report**: Delinquency, prepayment, and loss metrics.
4. **Trustee Report**: Official monthly report format.

These reports follow conventions established by:
- Fannie Mae/Freddie Mac (Agency MBS)
- SIFMA (Securities Industry standards)
- Bloomberg (Data feed specifications)

Classes
-------
FactorReport
    Generates monthly factor and balance information.
DistributionReport
    Generates detailed distribution statements.
CollateralPerformanceReport
    Generates collateral-level performance metrics.
TrusteeReport
    Generates comprehensive trustee report.

Example
-------
>>> from rmbs_platform.engine.reports import FactorReport, DistributionReport
>>> factor_report = FactorReport.from_simulation(simulation_results)
>>> print(factor_report.to_dataframe())
>>> distribution_report = DistributionReport.from_simulation(simulation_results)
>>> html = distribution_report.to_html()

See Also
--------
reporting.ReportGenerator : Base reporting utilities.
state.Snapshot : Period-by-period deal snapshots.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import numpy as np

logger = logging.getLogger("RMBS.Reports")


@dataclass
class BondFactorRecord:
    """
    Factor record for a single bond in a single period.

    Attributes
    ----------
    period : int
        Period number.
    bond_id : str
        Bond identifier (CUSIP or internal ID).
    original_balance : float
        Original face value.
    beginning_balance : float
        Balance at start of period.
    ending_balance : float
        Balance at end of period.
    factor : float
        Current factor (ending_balance / original_balance).
    principal_paid : float
        Principal distributed this period.
    interest_paid : float
        Interest distributed this period.
    losses_allocated : float
        Losses written down this period.
    """

    period: int
    bond_id: str
    original_balance: float
    beginning_balance: float
    ending_balance: float
    factor: float
    principal_paid: float
    interest_paid: float
    losses_allocated: float = 0.0


@dataclass
class PoolFactorRecord:
    """
    Factor record for the collateral pool.

    Attributes
    ----------
    period : int
        Period number.
    original_balance : float
        Original pool balance.
    beginning_balance : float
        Balance at start of period.
    ending_balance : float
        Balance at end of period.
    factor : float
        Pool factor (ending / original).
    scheduled_principal : float
        Scheduled (amortization) principal.
    prepayments : float
        Voluntary prepayments.
    defaults : float
        Default amounts.
    losses : float
        Realized losses.
    recoveries : float
        Recoveries from liquidations.
    cpr : float
        Constant prepayment rate (annualized).
    cdr : float
        Constant default rate (annualized).
    severity : float
        Loss severity rate.
    """

    period: int
    original_balance: float
    beginning_balance: float
    ending_balance: float
    factor: float
    scheduled_principal: float
    prepayments: float
    defaults: float
    losses: float
    recoveries: float
    cpr: float = 0.0
    cdr: float = 0.0
    severity: float = 0.0


class FactorReport:
    """
    Generate monthly factor reports for bonds and collateral.

    Factor reports are essential for:
    - Price/yield calculations
    - Portfolio valuation
    - Risk analytics
    - Regulatory reporting

    Parameters
    ----------
    deal_id : str
        Deal identifier.
    as_of_date : date
        Report date.
    periods : list
        Period records to include.

    Attributes
    ----------
    deal_id : str
        Deal identifier.
    as_of_date : date
        Report generation date.
    bond_factors : list of BondFactorRecord
        Bond-level factors.
    pool_factors : list of PoolFactorRecord
        Pool-level factors.

    Example
    -------
    >>> report = FactorReport("DEAL_2024_001", date.today())
    >>> report.add_bond_factor(BondFactorRecord(...))
    >>> df = report.to_dataframe()
    """

    def __init__(
        self,
        deal_id: str,
        as_of_date: Optional[date] = None,
    ) -> None:
        """Initialize factor report."""
        self.deal_id = deal_id
        self.as_of_date = as_of_date or date.today()
        self.bond_factors: List[BondFactorRecord] = []
        self.pool_factors: List[PoolFactorRecord] = []
        self._metadata: Dict[str, Any] = {}

    @classmethod
    def from_simulation(
        cls,
        simulation_results: Dict[str, Any],
        deal_id: Optional[str] = None,
    ) -> "FactorReport":
        """
        Create factor report from simulation results.

        Parameters
        ----------
        simulation_results : dict
            Results from run_simulation() containing detailed_tape.
        deal_id : str, optional
            Deal identifier.

        Returns
        -------
        FactorReport
            Populated factor report.
        """
        deal_id = deal_id or simulation_results.get("deal_id", "UNKNOWN")
        report = cls(deal_id)

        detailed_tape = simulation_results.get("detailed_tape", [])

        # Track original balances
        bond_originals: Dict[str, float] = {}
        pool_original: float = 0.0

        for row in detailed_tape:
            period = int(row.get("Period", 0))

            # Pool factors
            if period == 1:
                pool_original = float(row.get("BeginBalance", row.get("EndBalance", 0)))

            pool_record = PoolFactorRecord(
                period=period,
                original_balance=pool_original,
                beginning_balance=float(row.get("BeginBalance", 0)),
                ending_balance=float(row.get("EndBalance", 0)),
                factor=float(row.get("EndBalance", 0)) / pool_original if pool_original > 0 else 0,
                scheduled_principal=float(row.get("ScheduledPrincipal", 0)),
                prepayments=float(row.get("Prepayment", 0)),
                defaults=float(row.get("DefaultAmount", 0)),
                losses=float(row.get("RealizedLoss", 0)),
                recoveries=float(row.get("Recoveries", 0)),
                cpr=float(row.get("CPR", 0)),
                cdr=float(row.get("CDR", 0)),
                severity=float(row.get("Severity", 0.35)),
            )
            report.pool_factors.append(pool_record)

            # Bond factors (extract from row if available)
            for key, value in row.items():
                if key.startswith("Bond_") and key.endswith("_Balance"):
                    bond_id = key.replace("Bond_", "").replace("_Balance", "")

                    if bond_id not in bond_originals:
                        bond_originals[bond_id] = float(value)

                    bond_record = BondFactorRecord(
                        period=period,
                        bond_id=bond_id,
                        original_balance=bond_originals[bond_id],
                        beginning_balance=float(row.get(f"Bond_{bond_id}_BeginBalance", value)),
                        ending_balance=float(value),
                        factor=float(value) / bond_originals[bond_id] if bond_originals[bond_id] > 0 else 0,
                        principal_paid=float(row.get(f"Bond_{bond_id}_Principal", 0)),
                        interest_paid=float(row.get(f"Bond_{bond_id}_Interest", 0)),
                        losses_allocated=float(row.get(f"Bond_{bond_id}_Losses", 0)),
                    )
                    report.bond_factors.append(bond_record)

        return report

    def add_bond_factor(self, record: BondFactorRecord) -> None:
        """Add a bond factor record."""
        self.bond_factors.append(record)

    def add_pool_factor(self, record: PoolFactorRecord) -> None:
        """Add a pool factor record."""
        self.pool_factors.append(record)

    def to_dataframe(self, record_type: str = "pool") -> pd.DataFrame:
        """
        Convert factor records to DataFrame.

        Parameters
        ----------
        record_type : str
            "pool" for pool factors, "bond" for bond factors.

        Returns
        -------
        pd.DataFrame
            Factor records as DataFrame.
        """
        if record_type == "bond":
            if not self.bond_factors:
                return pd.DataFrame()
            return pd.DataFrame([vars(r) for r in self.bond_factors])
        else:
            if not self.pool_factors:
                return pd.DataFrame()
            return pd.DataFrame([vars(r) for r in self.pool_factors])

    def to_bloomberg_format(self) -> pd.DataFrame:
        """
        Export in Bloomberg-compatible format.

        Returns
        -------
        pd.DataFrame
            Factors in Bloomberg FTP format.
        """
        records = []
        for pf in self.pool_factors:
            records.append({
                "DEAL_ID": self.deal_id,
                "PERIOD": pf.period,
                "FACTOR": round(pf.factor, 8),
                "POOL_BALANCE": pf.ending_balance,
                "CPR": round(pf.cpr, 4),
                "CDR": round(pf.cdr, 4),
                "LOSS_SEVERITY": round(pf.severity, 4),
                "REALIZED_LOSS": pf.losses,
            })
        return pd.DataFrame(records)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics.

        Returns
        -------
        dict
            Summary metrics.
        """
        if not self.pool_factors:
            return {}

        latest = self.pool_factors[-1]
        total_principal = sum(pf.scheduled_principal + pf.prepayments for pf in self.pool_factors)
        total_prepay = sum(pf.prepayments for pf in self.pool_factors)
        total_defaults = sum(pf.defaults for pf in self.pool_factors)
        total_losses = sum(pf.losses for pf in self.pool_factors)

        return {
            "deal_id": self.deal_id,
            "as_of_date": self.as_of_date.isoformat(),
            "periods_reported": len(self.pool_factors),
            "current_factor": latest.factor,
            "current_balance": latest.ending_balance,
            "original_balance": latest.original_balance,
            "cumulative_principal": total_principal,
            "cumulative_prepayments": total_prepay,
            "cumulative_defaults": total_defaults,
            "cumulative_losses": total_losses,
            "avg_cpr": np.mean([pf.cpr for pf in self.pool_factors]),
            "avg_cdr": np.mean([pf.cdr for pf in self.pool_factors]),
            "avg_severity": np.mean([pf.severity for pf in self.pool_factors if pf.severity > 0]),
        }


@dataclass
class DistributionRecord:
    """
    Distribution record for a single bond in a single period.

    Attributes
    ----------
    period : int
        Period number.
    payment_date : date
        Distribution date.
    bond_id : str
        Bond identifier.
    coupon_rate : float
        Current coupon rate.
    beginning_balance : float
        Balance at start of period.
    interest_due : float
        Interest amount due.
    interest_paid : float
        Interest actually paid.
    interest_shortfall : float
        Unpaid interest carried forward.
    principal_paid : float
        Principal distributed.
    ending_balance : float
        Balance after distribution.
    total_distribution : float
        Total cash distributed (interest + principal).
    """

    period: int
    payment_date: date
    bond_id: str
    coupon_rate: float
    beginning_balance: float
    interest_due: float
    interest_paid: float
    interest_shortfall: float
    principal_paid: float
    ending_balance: float
    total_distribution: float


class DistributionReport:
    """
    Generate monthly distribution reports for bondholders.

    Distribution reports detail exactly how cashflows are allocated
    to each tranche, including:
    - Interest payments
    - Principal payments
    - Any shortfalls or deferrals

    Parameters
    ----------
    deal_id : str
        Deal identifier.
    distribution_date : date
        Payment date.

    Example
    -------
    >>> report = DistributionReport("DEAL_2024", date(2024, 3, 25))
    >>> report.add_distribution(DistributionRecord(...))
    >>> statement = report.generate_statement()
    """

    def __init__(
        self,
        deal_id: str,
        distribution_date: Optional[date] = None,
    ) -> None:
        """Initialize distribution report."""
        self.deal_id = deal_id
        self.distribution_date = distribution_date or date.today()
        self.distributions: List[DistributionRecord] = []
        self.fee_payments: Dict[str, float] = {}
        self.swap_payments: Dict[str, float] = {}
        self._sources: Dict[str, float] = {}

    def add_distribution(self, record: DistributionRecord) -> None:
        """Add a distribution record."""
        self.distributions.append(record)

    def add_fee_payment(self, fee_id: str, amount: float) -> None:
        """Record a fee payment."""
        self.fee_payments[fee_id] = amount

    def add_swap_payment(self, swap_id: str, amount: float) -> None:
        """Record a swap settlement."""
        self.swap_payments[swap_id] = amount

    def set_sources(
        self,
        interest_collected: float,
        principal_collected: float,
        recoveries: float = 0.0,
        servicer_advances: float = 0.0,
        swap_receipts: float = 0.0,
    ) -> None:
        """Set source of funds for the distribution."""
        self._sources = {
            "interest_collected": interest_collected,
            "principal_collected": principal_collected,
            "recoveries": recoveries,
            "servicer_advances": servicer_advances,
            "swap_receipts": swap_receipts,
            "total_available": (
                interest_collected + principal_collected + recoveries +
                servicer_advances + swap_receipts
            ),
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert distributions to DataFrame."""
        if not self.distributions:
            return pd.DataFrame()
        return pd.DataFrame([vars(r) for r in self.distributions])

    def generate_statement(self) -> Dict[str, Any]:
        """
        Generate a complete distribution statement.

        Returns
        -------
        dict
            Statement with sources, uses, and per-bond details.
        """
        # Calculate totals
        total_interest = sum(d.interest_paid for d in self.distributions)
        total_principal = sum(d.principal_paid for d in self.distributions)
        total_shortfall = sum(d.interest_shortfall for d in self.distributions)
        total_fees = sum(self.fee_payments.values())
        total_swaps = sum(self.swap_payments.values())

        # Group by bond
        by_bond: Dict[str, Dict[str, float]] = {}
        for d in self.distributions:
            if d.bond_id not in by_bond:
                by_bond[d.bond_id] = {
                    "interest_paid": 0.0,
                    "principal_paid": 0.0,
                    "total": 0.0,
                }
            by_bond[d.bond_id]["interest_paid"] += d.interest_paid
            by_bond[d.bond_id]["principal_paid"] += d.principal_paid
            by_bond[d.bond_id]["total"] += d.total_distribution

        return {
            "deal_id": self.deal_id,
            "distribution_date": self.distribution_date.isoformat(),
            "sources": self._sources,
            "uses": {
                "total_interest": total_interest,
                "total_principal": total_principal,
                "total_fees": total_fees,
                "total_swaps": total_swaps,
                "total_distributed": total_interest + total_principal + total_fees + total_swaps,
            },
            "shortfalls": {
                "interest_shortfall": total_shortfall,
            },
            "by_bond": by_bond,
            "fee_details": self.fee_payments,
            "swap_details": self.swap_payments,
        }

    def to_html(self) -> str:
        """
        Generate HTML distribution statement.

        Returns
        -------
        str
            HTML-formatted statement.
        """
        statement = self.generate_statement()

        html = f"""
        <html>
        <head>
            <title>Distribution Report - {self.deal_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 10px; text-align: right; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .total {{ font-weight: bold; background-color: #ecf0f1; }}
                .header {{ text-align: left; }}
            </style>
        </head>
        <body>
            <h1>Monthly Distribution Report</h1>
            <p><strong>Deal:</strong> {self.deal_id}</p>
            <p><strong>Distribution Date:</strong> {self.distribution_date}</p>

            <h2>Sources of Funds</h2>
            <table>
                <tr><th class="header">Source</th><th>Amount</th></tr>
        """

        for source, amount in statement.get("sources", {}).items():
            html += f'<tr><td class="header">{source.replace("_", " ").title()}</td>'
            html += f'<td>${amount:,.2f}</td></tr>'

        html += """
            </table>

            <h2>Uses of Funds</h2>
            <table>
                <tr><th class="header">Use</th><th>Amount</th></tr>
        """

        for use, amount in statement.get("uses", {}).items():
            css_class = "total" if "total" in use else ""
            html += f'<tr class="{css_class}"><td class="header">{use.replace("_", " ").title()}</td>'
            html += f'<td>${amount:,.2f}</td></tr>'

        html += """
            </table>

            <h2>Distribution by Bond</h2>
            <table>
                <tr>
                    <th class="header">Bond</th>
                    <th>Interest</th>
                    <th>Principal</th>
                    <th>Total</th>
                </tr>
        """

        for bond_id, amounts in statement.get("by_bond", {}).items():
            html += f'<tr><td class="header">{bond_id}</td>'
            html += f'<td>${amounts["interest_paid"]:,.2f}</td>'
            html += f'<td>${amounts["principal_paid"]:,.2f}</td>'
            html += f'<td>${amounts["total"]:,.2f}</td></tr>'

        html += """
            </table>
        </body>
        </html>
        """

        return html


class CollateralPerformanceReport:
    """
    Generate collateral performance reports.

    Tracks key metrics over time:
    - Delinquency rates (30/60/90+ days)
    - Prepayment speeds (CPR, SMM)
    - Default and loss rates
    - Modification and forbearance activity

    Parameters
    ----------
    deal_id : str
        Deal identifier.

    Example
    -------
    >>> report = CollateralPerformanceReport("DEAL_2024")
    >>> report.add_period_metrics(period=6, metrics={...})
    >>> summary = report.get_trend_analysis()
    """

    def __init__(self, deal_id: str) -> None:
        """Initialize performance report."""
        self.deal_id = deal_id
        self.period_metrics: List[Dict[str, Any]] = []

    def add_period_metrics(self, period: int, metrics: Dict[str, Any]) -> None:
        """
        Add performance metrics for a period.

        Parameters
        ----------
        period : int
            Period number.
        metrics : dict
            Performance metrics including:
            - delinq_30: 30-day delinquency rate
            - delinq_60: 60-day delinquency rate
            - delinq_90plus: 90+ day delinquency rate
            - cpr: Conditional prepayment rate
            - cdr: Conditional default rate
            - severity: Loss severity
            - loan_count: Current loan count
            - current_balance: Current pool balance
        """
        metrics["period"] = period
        self.period_metrics.append(metrics)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert metrics to DataFrame."""
        return pd.DataFrame(self.period_metrics)

    def get_trend_analysis(self) -> Dict[str, Any]:
        """
        Analyze performance trends.

        Returns
        -------
        dict
            Trend analysis including:
            - Recent vs. historical comparison
            - Rolling averages
            - Acceleration/deceleration indicators
        """
        if len(self.period_metrics) < 3:
            return {"insufficient_data": True}

        df = self.to_dataframe()

        # Calculate rolling averages
        for col in ["cpr", "cdr", "severity"]:
            if col in df.columns:
                df[f"{col}_3m_avg"] = df[col].rolling(3).mean()
                df[f"{col}_6m_avg"] = df[col].rolling(6).mean()

        latest = df.iloc[-1].to_dict()
        prior_3m = df.iloc[-4:-1].mean().to_dict() if len(df) > 3 else {}

        # Trend indicators
        trends = {}
        for metric in ["cpr", "cdr"]:
            if metric in latest and metric in prior_3m:
                change = latest[metric] - prior_3m.get(metric, latest[metric])
                if abs(change) < 0.001:
                    trends[metric] = "stable"
                elif change > 0:
                    trends[metric] = "increasing"
                else:
                    trends[metric] = "decreasing"

        return {
            "deal_id": self.deal_id,
            "periods_analyzed": len(self.period_metrics),
            "latest_metrics": latest,
            "prior_3m_average": prior_3m,
            "trends": trends,
            "cumulative_defaults": df["defaults"].sum() if "defaults" in df.columns else 0,
            "cumulative_losses": df["losses"].sum() if "losses" in df.columns else 0,
        }


class TrusteeReport:
    """
    Generate comprehensive trustee report.

    The trustee report combines all standard reports into a single
    document for regulatory and investor reporting.

    Parameters
    ----------
    deal_id : str
        Deal identifier.
    report_date : date
        Report date.

    Example
    -------
    >>> trustee = TrusteeReport("DEAL_2024", date(2024, 3, 31))
    >>> trustee.set_factor_report(factor_report)
    >>> trustee.set_distribution_report(dist_report)
    >>> full_report = trustee.generate()
    """

    def __init__(self, deal_id: str, report_date: Optional[date] = None) -> None:
        """Initialize trustee report."""
        self.deal_id = deal_id
        self.report_date = report_date or date.today()
        self.factor_report: Optional[FactorReport] = None
        self.distribution_report: Optional[DistributionReport] = None
        self.performance_report: Optional[CollateralPerformanceReport] = None
        self._deal_info: Dict[str, Any] = {}
        self._notes: List[str] = []

    def set_deal_info(self, info: Dict[str, Any]) -> None:
        """Set deal information."""
        self._deal_info = info

    def set_factor_report(self, report: FactorReport) -> None:
        """Set factor report."""
        self.factor_report = report

    def set_distribution_report(self, report: DistributionReport) -> None:
        """Set distribution report."""
        self.distribution_report = report

    def set_performance_report(self, report: CollateralPerformanceReport) -> None:
        """Set performance report."""
        self.performance_report = report

    def add_note(self, note: str) -> None:
        """Add a note to the report."""
        self._notes.append(note)

    def generate(self) -> Dict[str, Any]:
        """
        Generate the complete trustee report.

        Returns
        -------
        dict
            Complete report with all sections.
        """
        return {
            "report_type": "Monthly Trustee Report",
            "deal_id": self.deal_id,
            "report_date": self.report_date.isoformat(),
            "generated_at": datetime.now().isoformat(),
            "deal_information": self._deal_info,
            "factor_summary": self.factor_report.get_summary() if self.factor_report else None,
            "distribution_statement": (
                self.distribution_report.generate_statement()
                if self.distribution_report else None
            ),
            "performance_trends": (
                self.performance_report.get_trend_analysis()
                if self.performance_report else None
            ),
            "notes": self._notes,
        }

    def to_json(self) -> str:
        """Export report as JSON string."""
        import json
        return json.dumps(self.generate(), indent=2, default=str)
