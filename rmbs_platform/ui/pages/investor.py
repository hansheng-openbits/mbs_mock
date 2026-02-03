"""
Investor Page
============

Analytics dashboard for investors with modern UX patterns and interactive visualizations.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Any, Dict, List, Optional

from ..services.api_client import APIClient
from ..components.status import (
    loading_spinner, success_message, error_message, progress_bar
)
from ..components.data_display import (
    kpi_dashboard, data_table, chart_container,
    cashflow_waterfall_chart, prepayment_curve_chart, loss_distribution_chart
)
from ..utils.formatting import create_table_formatter


def _rerun() -> None:
    """Version-safe Streamlit rerun (supports both old/new Streamlit APIs)."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def render_simulation_controls(api_client: APIClient, selected_deal_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Render simulation parameter controls with improved UX.

    Parameters
    ----------
    api_client : APIClient
        API client instance
    selected_deal_id : str, optional
        Currently selected deal ID for checking origination tape availability

    Returns
    -------
    dict
        Simulation parameters
    """
    st.subheader("🎯 Simulation Parameters")

    # Create responsive columns for parameters
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Prepayment & Default**")
        cpr_pct = st.slider(
            "CPR (Prepayment, %)",
            min_value=0.0,
            max_value=50.0,
            value=float(st.session_state.get("cpr_pct", st.session_state.get("cpr", 0.08) * 100.0)),
            step=0.1,
            format="%.1f%%",
            key="cpr_pct",
            help="Constant Prepayment Rate (annual). Slider is in percentage points; engine uses a decimal (e.g. 8.0% → 0.08)."
        )
        cpr = cpr_pct / 100.0

        cdr_pct = st.slider(
            "CDR (Default, %)",
            min_value=0.0,
            max_value=20.0,
            value=float(st.session_state.get("cdr_pct", st.session_state.get("cdr", 0.005) * 100.0)),
            step=0.05,
            format="%.2f%%",
            key="cdr_pct",
            help="Constant Default Rate (annual). Slider is in percentage points; engine uses a decimal (e.g. 0.50% → 0.005)."
        )
        cdr = cdr_pct / 100.0

    with col2:
        st.markdown("**Loss Assumptions**")
        severity_pct = st.slider(
            "Loss Severity (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state.get("severity_pct", st.session_state.get("severity", 0.32) * 100.0)),
            step=1.0,
            format="%.0f%%",
            key="severity_pct",
            help="Percent of defaulted balance lost. Slider is in percentage points; engine uses a decimal (e.g. 32% → 0.32)."
        )
        severity = severity_pct / 100.0

        horizon_months = st.slider(
            "Projection Horizon",
            min_value=12,
            max_value=360,
            value=st.session_state.get("horizon_months", 60),
            step=12,
            format="%d months",
            key="horizon_months",
            help="Number of months to project cashflows forward"
        )

    with col3:
        st.markdown("**Advanced Options**")
        use_ml = st.checkbox(
            "🔬 Use ML Models",
            value=st.session_state.get("use_ml", False),
            key="use_ml",
            help="Enable machine learning models for prepayment and default predictions"
        )

        if use_ml:
            # Check if origination tape is configured for the selected deal
            has_origination_tape = False

            if selected_deal_id:
                try:
                    collateral_response = api_client.get_collateral(selected_deal_id)
                    collateral_data = collateral_response.get("collateral", {})
                    loan_data = collateral_data.get("loan_data", {})
                    schema_ref = loan_data.get("schema_ref", {})
                    ml_config = collateral_data.get("ml_config", {})

                    source_uri = schema_ref.get("source_uri") or ml_config.get("origination_source_uri")
                    has_origination_tape = bool(source_uri)
                except:
                    pass

            if not has_origination_tape:
                st.warning("⚠️ ML models require origination tape to be configured in collateral data. Please upload loan tape data in the Arranger screen.")
            else:
                st.success("✅ Origination tape configured for ML models")

            registry = api_client.get_model_registry()
            model_keys = sorted(list(registry.keys())) if registry else []
            if not model_keys:
                st.warning("No models found in registry. Check `models/model_registry.json` and API `/models/registry`.")
                prepay_model_key = None
                default_model_key = None
            else:
                opts = ["(use deal defaults)"] + model_keys
                prepay_choice = st.selectbox(
                    "Prepayment model",
                    options=opts,
                    index=0,
                    key="prepay_model_choice",
                    help="Select which prepayment model to use (or use deal defaults).",
                )
                default_choice = st.selectbox(
                    "Default model",
                    options=opts,
                    index=0,
                    key="default_model_choice",
                    help="Select which default model to use (or use deal defaults).",
                )
                prepay_model_key = None if prepay_choice == "(use deal defaults)" else prepay_choice
                default_model_key = None if default_choice == "(use deal defaults)" else default_choice
        else:
            prepay_model_key = None
            default_model_key = None

    # Scenario selection
    st.markdown("**📊 Scenario Analysis**")
    scenario_col1, scenario_col2 = st.columns(2)

    scenarios = api_client.get_scenarios(include_archived=False)
    scenario_by_id = {
        s.get("scenario_id"): s for s in scenarios
        if isinstance(s, dict) and s.get("scenario_id")
    }
    st.session_state["_scenario_by_id"] = scenario_by_id

    def _apply_scenario_params(scenario: Dict[str, Any]) -> None:
        """Apply scenario parameters to session state (updates sliders)."""
        params = scenario.get("params") or {}
        if not isinstance(params, dict):
            return

        def _to_pct(x: float) -> float:
            # Allow both decimal (0-1) and percentage (0-100) inputs.
            return float(x) * 100.0 if float(x) <= 1.0 else float(x)

        if "cpr" in params:
            st.session_state["cpr_pct"] = _to_pct(params["cpr"])
        if "cdr" in params:
            st.session_state["cdr_pct"] = _to_pct(params["cdr"])
        if "severity" in params:
            st.session_state["severity_pct"] = _to_pct(params["severity"])
        if "horizon_periods" in params:
            st.session_state["horizon_months"] = int(params["horizon_periods"])
        if "name" in scenario:
            st.session_state["scenario_name"] = scenario.get("name", "")

    def _on_scenario_select_change() -> None:
        sid = st.session_state.get("scenario_id_select")
        if not sid or sid == "__manual__":
            st.session_state["scenario_selected_id"] = None
            st.session_state["_scenario_applied"] = False
            return
        selected = st.session_state.get("_scenario_by_id", {}).get(sid, {})
        st.session_state["scenario_selected_id"] = sid
        name = selected.get("name")
        if name:
            st.session_state["scenario_name"] = name
        
        # AUTO-APPLY scenario parameters when selected (not just on button click)
        _apply_scenario_params(selected)
        st.session_state["_scenario_applied"] = True

    def _apply_selected_scenario_params() -> None:
        sid = st.session_state.get("scenario_selected_id")
        if not sid:
            return
        selected = st.session_state.get("_scenario_by_id", {}).get(sid, {})
        _apply_scenario_params(selected)

    with scenario_col1:
        scenario_ids = ["__manual__"] + sorted([sid for sid in scenario_by_id.keys() if sid])

        def _fmt_scenario(sid: str) -> str:
            if sid == "__manual__":
                return "Manual / ad-hoc"
            s = scenario_by_id.get(sid, {})
            name = s.get("name", sid)
            status = s.get("status")
            return f"{name}" if not status else f"{name} ({status})"

        selected_sid = st.selectbox(
            "Scenario",
            options=scenario_ids,
            format_func=_fmt_scenario,
            key="scenario_id_select",
            on_change=_on_scenario_select_change,
            help="Pick a saved scenario, or choose Manual for ad-hoc inputs.",
        )

        selected_scenario_id = None if selected_sid == "__manual__" else selected_sid

        scenario_name = st.text_input(
            "Scenario Name",
            value=st.session_state.get("scenario_name", ""),
            placeholder="e.g., Base Case, Stress Test",
            key="scenario_name",
            disabled=bool(selected_scenario_id),
            help="Manual only. If you choose a saved scenario above, this will be auto-filled.",
        )

        st.button(
            "Apply selected scenario parameters",
            disabled=not bool(selected_scenario_id),
            on_click=_apply_selected_scenario_params,
            help="Sets CPR/CDR/Severity/Horizon to the selected scenario's parameters.",
        )

    with scenario_col2:
        if st.button("💾 Save Scenario", type="secondary"):
            if scenario_name.strip():
                # Save scenario logic would go here
                success_message(f"Scenario '{scenario_name}' saved!", celebration=True)
            else:
                error_message("Please enter a scenario name")
    
    # Show notification when scenario is applied
    if st.session_state.get("_scenario_applied") and selected_scenario_id:
        selected = scenario_by_id.get(selected_scenario_id, {})
        params = selected.get("params", {})
        if params:
            st.success(f"✅ Scenario '{selected.get('name', selected_scenario_id)}' applied: "
                      f"CPR={params.get('cpr', 'N/A')}, CDR={params.get('cdr', 'N/A')}, "
                      f"Severity={params.get('severity', 'N/A')}")
        st.session_state["_scenario_applied"] = False

    # Read FINAL values from session state (in case scenario was just applied)
    # This ensures we use scenario values even on the render cycle when they were set
    final_cpr = st.session_state.get("cpr_pct", cpr * 100.0) / 100.0
    final_cdr = st.session_state.get("cdr_pct", cdr * 100.0) / 100.0
    final_severity = st.session_state.get("severity_pct", severity * 100.0) / 100.0
    final_horizon = st.session_state.get("horizon_months", horizon_months)

    return {
        "cpr": final_cpr,
        "cdr": final_cdr,
        "severity": final_severity,
        "use_ml": use_ml,
        "prepay_model_key": prepay_model_key,
        "default_model_key": default_model_key,
        "scenario_id": st.session_state.get("scenario_selected_id"),
        "scenario_name": scenario_name,
        "horizon_months": final_horizon
    }


def render_deal_selector(api_client: APIClient) -> Optional[str]:
    """
    Render deal selection interface with improved UX.

    Parameters
    ----------
    api_client : APIClient
        API client instance

    Returns
    -------
    str or None
        Selected deal ID
    """
    st.subheader("📋 Deal Selection")

    # Deal list with refresh capability
    col1, col2 = st.columns([4, 1])

    with col1:
        deals = api_client.get_deals()

        if not deals:
            st.info("No deals available. Please ask an arranger to upload deal specifications.")
            return None

        # Create readable deal options
        deal_options = []
        deal_id_map = {}

        for deal in deals:
            deal_id = deal.get("deal_id", "")
            deal_name = deal.get("deal_name", "Unknown Deal")
            asset_type = deal.get("asset_type", "Unknown")
            has_collateral = "✅" if deal.get("has_collateral") else "❌"

            display_name = f"{deal_id} - {deal_name} ({asset_type}) {has_collateral}"
            deal_options.append(display_name)
            deal_id_map[display_name] = deal_id

        selected_display = st.selectbox(
            "Select Deal for Analysis",
            options=deal_options,
            help="Choose a deal to run cashflow analysis on"
        )

        selected_deal_id = deal_id_map.get(selected_display)

        # Store selected deal ID in session state for ML check
        if selected_deal_id:
            st.session_state["investor_selected_deal_id"] = selected_deal_id

    with col2:
        if st.button("🔄 Refresh", help="Refresh deal list"):
            _rerun()

    if selected_deal_id:
        # Show deal summary
        selected_deal = next((d for d in deals if d.get("deal_id") == selected_deal_id), {})
        if selected_deal:
            with st.expander("📊 Deal Summary", expanded=False):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Deal ID", selected_deal_id)
                    st.metric("Asset Type", selected_deal.get("asset_type", "N/A"))
                with col_b:
                    st.metric("Deal Name", selected_deal.get("deal_name", "N/A"))
                with col_c:
                    collateral_status = "✅ Available" if selected_deal.get("has_collateral") else "❌ Missing"
                    st.metric("Collateral", collateral_status)

    return selected_deal_id


def render_simulation_execution(
    api_client: APIClient,
    deal_id: str,
    params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Execute simulation with progress tracking and improved UX.

    Parameters
    ----------
    api_client : APIClient
        API client instance
    deal_id : str
        Deal ID to simulate
    params : dict
        Simulation parameters

    Returns
    -------
    dict or None
        Simulation results if successful
    """
    st.subheader("🚀 Simulation Execution")

    # Simulation button with validation
    can_simulate = deal_id and params.get("cpr") is not None

    if not can_simulate:
        st.warning("⚠️ Please select a deal and configure parameters before running simulation")
        return None

    # Display parameter summary
    with st.expander("📋 Simulation Summary", expanded=False):
        summary_col1, summary_col2, summary_col3 = st.columns(3)

        with summary_col1:
            st.markdown(f"**Deal:** {deal_id}")
            st.markdown(f"**CPR:** {params['cpr']:.1%}")
            st.markdown(f"**CDR:** {params['cdr']:.1%}")

        with summary_col2:
            st.markdown(f"**Severity:** {params['severity']:.0%}")
            st.markdown(f"**ML Models:** {'✅ Enabled' if params['use_ml'] else '❌ Disabled'}")
            st.markdown(f"**Horizon:** {params['horizon_months']} months")

        with summary_col3:
            job_id_summary_placeholder = st.empty()

            def _render_job_id_in_summary(job_id: Optional[str]) -> None:
                if job_id:
                    job_id_summary_placeholder.markdown("**Job ID:**")
                    job_id_summary_placeholder.code(job_id)
                else:
                    job_id_summary_placeholder.markdown("**Job ID:** _Not submitted yet_")

            _render_job_id_in_summary(st.session_state.get("last_job_id"))

            if params.get('scenario_name'):
                st.markdown(f"**Scenario:** {params['scenario_name']}")
            else:
                st.markdown("*No scenario name*")

    # Execute simulation
    if st.button("🚀 Run Cashflow Simulation", type="primary", use_container_width=True):
        try:
            with loading_spinner("Running RMBS cashflow engine..."):
                # Create progress callback
                progress_placeholder = st.empty()

                def progress_callback(progress_val: float, message: str = ""):
                    with progress_placeholder.container():
                        progress_bar(progress_val, message)

                def job_id_callback(job_id: str) -> None:
                    st.session_state["last_job_id"] = job_id
                    # Update the Job ID inside the Simulation Summary (in-place)
                    _render_job_id_in_summary(job_id)
                    # Also show an explicit callout below the button for copy/paste
                    st.info("✅ Simulation submitted. Use this Job ID in the Auditor screen:")
                    st.code(job_id)

                # Run simulation
                results = api_client.simulate_deal(
                    deal_id=deal_id,
                    cpr=params["cpr"],
                    cdr=params["cdr"],
                    severity=params["severity"],
                    horizon_periods=int(params.get("horizon_months", 60)),
                    scenario_id=params.get("scenario_id"),
                    prepay_model_key=params.get("prepay_model_key"),
                    default_model_key=params.get("default_model_key"),
                    use_ml=params["use_ml"],
                    progress_callback=progress_callback,
                    job_id_callback=job_id_callback,
                )

                # Clear progress indicator
                progress_placeholder.empty()

                # Success animation
                success_message("Simulation completed successfully! 🎉", celebration=True)

                # Store results in session state for comparison
                st.session_state["last_simulation"] = {
                    "deal_id": deal_id,
                    "params": params,
                    "results": results
                }

                return results

        except Exception as e:
            error_message(
                f"Simulation failed: {e}",
                details=str(e),
                show_retry=True,
                retry_callback=_rerun
            )

    return None


def render_results_dashboard(results: Dict[str, Any]) -> None:
    """
    Render comprehensive results dashboard with KPIs and visualizations.

    Parameters
    ----------
    results : dict
        Simulation results from API
    """
    st.subheader("📊 Results Dashboard")

    # Extract data
    data = results.get("data", [])
    if not data:
        st.warning("No simulation data available")
        return

    df = pd.DataFrame(data)

    # KPI Dashboard
    summary_data = results.get("simulated_summary", [])
    if summary_data:
        kpi_metrics = [
            {
                "columns": ["PrincipalCollected", "Var.InputPrincipalCollected", "PrincipalPaid"],
                "title": "Total Principal Collected",
                "aggregation": "sum",
                "format": "currency",
                "help": "Cumulative principal collected from the collateral during the projection period"
            },
            {
                "columns": ["InterestCollected", "Var.InputInterestCollected", "InterestPaid"],
                "title": "Total Interest Collected",
                "aggregation": "sum",
                "format": "currency",
                "help": "Cumulative interest collected from the collateral during the projection period"
            },
            {
                "columns": ["EndBalance", "EndingBalance", "Var.InputEndBalance"],
                "title": "Final Pool Balance",
                "aggregation": "last",
                "format": "currency",
                "help": "Remaining pool balance at simulation end"
            },
            {
                "columns": ["RealizedLoss", "Var.InputRealizedLoss"],
                "title": "Cumulative Realized Loss",
                "aggregation": "sum",
                "format": "currency",
                "help": "Total realized losses during the projection period"
            }
        ]

        kpi_dashboard(pd.DataFrame(summary_data), kpi_metrics, "🎯 Key Performance Indicators")

    # Visualizations
    st.subheader("📈 Cashflow Analysis")

    viz_tabs = st.tabs(["Bond Balances", "Prepayment Rates", "Loss Distribution"])

    with viz_tabs[0]:
        try:
            chart_container(
                cashflow_waterfall_chart,
                "Bond Balance Evolution Over Time",
                df=df,
                height=400
            )
        except Exception as e:
            st.error(f"Error creating bond balance chart: {e}")

    with viz_tabs[1]:
        if "Var.CPR" in df.columns:
            try:
                chart_container(
                    prepayment_curve_chart,
                    "Prepayment Rate (CPR) Evolution",
                    df=df,
                    height=400
                )
            except Exception as e:
                st.error(f"Error creating prepayment chart: {e}")
        else:
            st.info("Prepayment rate data not available in simulation results")

    with viz_tabs[2]:
        try:
            chart_container(
                loss_distribution_chart,
                "Cumulative Realized Losses",
                df=df,
                loss_column="Var.RealizedLoss",
                height=400
            )
        except Exception as e:
            st.error(f"Error creating loss distribution chart: {e}")

    # Detailed Data Tables
    st.subheader("📋 Detailed Results")

    table_tabs = st.tabs(["Cashflow Tape", "Period Summary", "Reconciliation"])

    with table_tabs[0]:
        formatters = create_table_formatter(df)
        data_table(
            df,
            "Complete Cashflow Tape",
            formatters=formatters,
            max_rows=100,
            downloadable=True
        )

    with table_tabs[1]:
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            formatters = create_table_formatter(summary_df)
            data_table(
                summary_df,
                "Period-by-Period Summary",
                formatters=formatters,
                downloadable=True
            )

    with table_tabs[2]:
        reconciliation = results.get("reconciliation", [])
        if reconciliation:
            recon_df = pd.DataFrame(reconciliation)
            data_table(
                recon_df,
                "Model vs. Servicer Reconciliation",
                downloadable=True
            )
        else:
            st.info("No reconciliation issues detected")

    # Warnings and Diagnostics
    warnings = results.get("warnings", [])
    if warnings:
        st.subheader("⚠️ Data Quality Warnings")
        for warning in warnings:
            st.warning(warning.get("message", "Warning detected"))

    # ML Diagnostics
    model_info = results.get("model_info")
    if model_info:
        with st.expander("🔬 Model Information", expanded=False):
            st.json(model_info)


def _format_currency(value: float) -> str:
    """Format value as currency."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:,.0f}"


def _get_investor_holdings(api_client: APIClient, investor_address: str) -> List[Dict[str, Any]]:
    """
    Get token holdings for an investor address.
    
    Queries the backend portfolio API for actual token holdings issued to this address.
    Falls back to empty list if no holdings or API error.
    """
    try:
        # Try to get actual holdings from the portfolio API
        portfolio = api_client.get_investor_portfolio(investor_address)
        holdings = portfolio.get("holdings", [])
        
        if holdings:
            return holdings
            
    except Exception as e:
        # API error - portfolio not available
        pass
    
    # No actual holdings - return empty list
    return []


def _get_all_available_deals_summary(api_client: APIClient) -> List[Dict[str, Any]]:
    """
    Get summary of all available deals with deployed tranches for display.
    
    This shows what deals/tranches are available for investment.
    """
    available = []
    
    try:
        deals = api_client.get_deals()
        
        for deal in deals:
            deal_id = deal.get("deal_id")
            
            # Try to get tranche registry for this deal
            try:
                registry = api_client.get_tranche_registry(deal_id)
                tranches = registry.get("tranches", {})
                
                if not tranches:
                    continue
                
                # Get deal details for tranche info
                deal_response = api_client.get_deal(deal_id)
                deal_spec = deal_response.get("spec", {})
                bonds = deal_spec.get("bonds", [])
                
                for bond in bonds:
                    bond_id = bond.get("id")
                    if bond_id not in tranches:
                        continue
                    
                    original_balance = bond.get("original_balance", 0)
                    
                    # Get coupon info
                    coupon = bond.get("coupon", {})
                    coupon_kind = coupon.get("kind", "FIXED")
                    if coupon_kind == "FIXED":
                        ytm = coupon.get("fixed_rate", 0.05)
                    elif coupon_kind == "FLOAT":
                        ytm = 0.052 + coupon.get("margin", 0.0175)
                    else:
                        ytm = 0.06
                    
                    # Calculate OAS (spread over risk-free)
                    oas_bps = int((ytm - 0.045) * 10000)
                    
                    available.append({
                        "deal_id": deal_id,
                        "tranche_id": bond_id,
                        "token_symbol": f"{deal_id[:8]}-{bond_id}",
                        "original_balance": original_balance,
                        "ytm": ytm,
                        "oas_bps": max(0, oas_bps),
                        "contract_address": tranches.get(bond_id, ""),
                        "coupon_type": coupon_kind,
                    })
                    
            except Exception:
                continue
                
    except Exception:
        pass
    
    return available


def _calculate_pending_yields(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate pending yield claims for holdings."""
    total_pending = 0
    claims = []
    
    for holding in holdings:
        # Use current_value if available, otherwise balance
        value = holding.get("current_value", holding.get("balance", 0))
        ytm = holding.get("ytm", 0.05)
        
        # Simulate one month of accrued interest
        monthly_yield = value * ytm / 12
        if monthly_yield > 0:
            total_pending += monthly_yield
            claims.append({
                "token": holding.get("token_symbol", "Unknown"),
                "amount": monthly_yield,
                "period": "Jan 2026",
            })
    
    return {
        "total_pending": total_pending,
        "claims_count": len(claims),
        "claims": claims[:5],  # Top 5
    }


def render_portfolio_dashboard(api_client: APIClient) -> None:
    """Render the investor portfolio dashboard."""
    st.subheader("💼 My Portfolio")
    
    # Investor address input (in production, would connect to wallet)
    investor_address = st.text_input(
        "Investor Wallet Address",
        value="0x0000000000000000000000000000000000000001",
        help="Enter your wallet address to view holdings",
        key="investor_wallet"
    )
    
    # Key Pricing Inputs Section
    st.markdown("### 📊 Pricing Assumptions")
    
    # Mode selector for pricing assumptions
    pricing_mode = st.radio(
        "Assumption Source",
        options=["📝 Manual", "📈 Model-Driven", "🎯 Scenario-Based"],
        horizontal=True,
        key="pricing_mode",
        help="Choose how CPR/CDR/Severity are determined"
    )
    
    # Model-driven estimation (uses pool characteristics)
    if pricing_mode == "📈 Model-Driven":
        st.markdown("**Model-Driven Mode**: Estimates CPR/CDR/Severity using ML models trained on historical loan data.")
        
        # Pool Characteristics Section
        with st.expander("🏠 Pool Characteristics", expanded=True):
            pool_col1, pool_col2, pool_col3, pool_col4 = st.columns(4)
            
            with pool_col1:
                wa_fico = st.number_input(
                    "WA FICO",
                    min_value=500,
                    max_value=850,
                    value=int(st.session_state.get("model_wa_fico", 720)),
                    step=10,
                    key="model_wa_fico",
                    help="Weighted-average credit score of the pool"
                )
            
            with pool_col2:
                wa_ltv = st.number_input(
                    "WA LTV (%)",
                    min_value=20.0,
                    max_value=100.0,
                    value=float(st.session_state.get("model_wa_ltv", 75.0)),
                    step=5.0,
                    key="model_wa_ltv",
                    help="Weighted-average loan-to-value ratio"
                )
            
            with pool_col3:
                wa_dti = st.number_input(
                    "WA DTI (%)",
                    min_value=10.0,
                    max_value=60.0,
                    value=float(st.session_state.get("model_wa_dti", 36.0)),
                    step=2.0,
                    key="model_wa_dti",
                    help="Weighted-average debt-to-income ratio"
                )
            
            with pool_col4:
                wa_coupon = st.number_input(
                    "WA Coupon (%)",
                    min_value=2.0,
                    max_value=12.0,
                    value=float(st.session_state.get("model_wa_coupon", 5.0)),
                    step=0.25,
                    key="model_wa_coupon",
                    help="Weighted-average coupon rate"
                ) / 100.0
            
            pool_col5, pool_col6, pool_col7, pool_col8 = st.columns(4)
            
            with pool_col5:
                wa_seasoning = st.number_input(
                    "Seasoning (months)",
                    min_value=0,
                    max_value=360,
                    value=int(st.session_state.get("model_wa_seasoning", 12)),
                    step=6,
                    key="model_wa_seasoning",
                    help="Average loan age in months"
                )
            
            with pool_col6:
                pct_high_ltv = st.slider(
                    "% High LTV (>80%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(st.session_state.get("model_pct_high_ltv", 20.0)),
                    step=5.0,
                    key="model_pct_high_ltv",
                    help="Percentage of loans with LTV > 80%"
                ) / 100.0
            
            with pool_col7:
                pct_condo = st.slider(
                    "% Condo/Co-op",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(st.session_state.get("model_pct_condo", 10.0)),
                    step=5.0,
                    key="model_pct_condo",
                    help="Percentage of condos/co-ops in pool"
                ) / 100.0
            
            with pool_col8:
                pct_judicial = st.slider(
                    "% Judicial States",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(st.session_state.get("model_pct_judicial", 30.0)),
                    step=5.0,
                    key="model_pct_judicial",
                    help="Percentage in judicial foreclosure states"
                ) / 100.0
        
        # Market Conditions Section
        with st.expander("📊 Market Conditions", expanded=True):
            mkt_col1, mkt_col2, mkt_col3 = st.columns(3)
            
            with mkt_col1:
                current_market_rate = st.number_input(
                    "Current Mortgage Rate (%)",
                    min_value=2.0,
                    max_value=12.0,
                    value=float(st.session_state.get("model_market_rate", 6.5)),
                    step=0.25,
                    key="model_market_rate",
                    help="Current 30-year mortgage rate"
                ) / 100.0
            
            with mkt_col2:
                rate_scenario = st.selectbox(
                    "Rate Scenario",
                    options=["base", "rally", "selloff"],
                    format_func=lambda x: {"base": "🟡 Base Case", "rally": "🟢 Rally (Rates Down)", "selloff": "🔴 Sell-off (Rates Up)"}[x],
                    key="model_rate_scenario",
                    help="Expected direction of interest rates"
                )
            
            with mkt_col3:
                economic_scenario = st.selectbox(
                    "Economic Scenario",
                    options=["expansion", "stable", "mild_recession", "severe_recession"],
                    format_func=lambda x: {
                        "expansion": "📈 Expansion",
                        "stable": "🟡 Stable",
                        "mild_recession": "📉 Mild Recession",
                        "severe_recession": "🔴 Severe Recession"
                    }[x],
                    index=1,  # Default to stable
                    key="model_economic_scenario",
                    help="Economic outlook affects default rates and severity"
                )
        
        # Call API to get model estimates
        try:
            model_result = api_client.get_model_estimates(
                wa_fico=float(wa_fico),
                wa_ltv=float(wa_ltv),
                wa_dti=float(wa_dti),
                wa_coupon=wa_coupon,
                wa_seasoning=wa_seasoning,
                current_market_rate=current_market_rate,
                rate_scenario=rate_scenario,
                economic_scenario=economic_scenario,
                pct_high_ltv=pct_high_ltv,
                pct_condo=pct_condo,
                pct_judicial_states=pct_judicial,
            )
            
            model_cpr = model_result.get("cpr", 0.10) * 100
            model_cdr = model_result.get("cdr", 0.02) * 100
            model_severity = model_result.get("severity", 0.35) * 100
            
            cpr_range = model_result.get("cpr_range", (0.05, 0.15))
            cdr_range = model_result.get("cdr_range", (0.01, 0.04))
            severity_range = model_result.get("severity_range", (0.25, 0.45))
            
            components = model_result.get("components", {})
            
        except Exception as e:
            st.warning(f"⚠️ Could not fetch model estimates: {e}. Using fallback values.")
            model_cpr, model_cdr, model_severity = 10.0, 2.0, 35.0
            cpr_range, cdr_range, severity_range = (0.05, 0.15), (0.01, 0.04), (0.25, 0.45)
            components = {}
        
        # Display model estimates with confidence intervals
        st.markdown("### 📊 Model Estimates")
        est_col1, est_col2, est_col3 = st.columns(3)
        
        with est_col1:
            st.metric(
                "CPR (Prepay)",
                f"{model_cpr:.1f}%",
                delta=f"Range: {cpr_range[0]*100:.1f}% - {cpr_range[1]*100:.1f}%",
                delta_color="off",
                help="Constant Prepayment Rate from prepayment model"
            )
        
        with est_col2:
            st.metric(
                "CDR (Default)",
                f"{model_cdr:.2f}%",
                delta=f"Range: {cdr_range[0]*100:.2f}% - {cdr_range[1]*100:.2f}%",
                delta_color="off",
                help="Constant Default Rate from default model"
            )
        
        with est_col3:
            st.metric(
                "Loss Severity",
                f"{model_severity:.1f}%",
                delta=f"Range: {severity_range[0]*100:.1f}% - {severity_range[1]*100:.1f}%",
                delta_color="off",
                help="Loss Given Default from severity model"
            )
        
        cpr = model_cpr / 100.0
        cdr = model_cdr / 100.0
        severity = model_severity / 100.0
        
        # Component breakdown
        with st.expander("🔬 Model Component Breakdown", expanded=False):
            if components:
                comp_col1, comp_col2, comp_col3 = st.columns(3)
                
                with comp_col1:
                    st.markdown("**CPR Components**")
                    cpr_comps = components.get("cpr", {})
                    for key, val in cpr_comps.items():
                        if key not in ["baseline", "smm", "cpr"]:
                            st.write(f"• {key.replace('_', ' ').title()}: {val:+.4f}")
                    st.write(f"**Baseline SMM:** {cpr_comps.get('baseline', 0.06)*100:.2f}%")
                    st.write(f"**Final SMM:** {cpr_comps.get('smm', 0)*100:.3f}%")
                
                with comp_col2:
                    st.markdown("**CDR Components**")
                    cdr_comps = components.get("cdr", {})
                    for key, val in cdr_comps.items():
                        if key not in ["baseline", "mdr", "cdr"]:
                            st.write(f"• {key.replace('_', ' ').title()}: {val:+.4f}")
                    st.write(f"**Baseline MDR:** {cdr_comps.get('baseline', 0.005)*100:.3f}%")
                    st.write(f"**Final MDR:** {cdr_comps.get('mdr', 0)*100:.4f}%")
                
                with comp_col3:
                    st.markdown("**Severity Components**")
                    sev_comps = components.get("severity", {})
                    for key, val in sev_comps.items():
                        if key != "severity":
                            st.write(f"• {key.replace('_', ' ').title()}: {val:+.2%}")
            else:
                st.info("Component details not available.")
        
        # Sensitivity Analysis
        with st.expander("📈 Sensitivity Analysis", expanded=False):
            sens_param = st.selectbox(
                "Vary Parameter",
                options=["wa_fico", "wa_ltv", "current_market_rate"],
                format_func=lambda x: {
                    "wa_fico": "FICO Score",
                    "wa_ltv": "LTV Ratio",
                    "current_market_rate": "Market Rate"
                }[x],
                key="sensitivity_param"
            )
            
            if st.button("Run Sensitivity Analysis", key="run_sensitivity"):
                if sens_param == "wa_fico":
                    vary_values = [640, 680, 700, 720, 740, 760, 780]
                elif sens_param == "wa_ltv":
                    vary_values = [60, 70, 75, 80, 85, 90, 95]
                else:  # current_market_rate
                    vary_values = [0.04, 0.05, 0.055, 0.06, 0.065, 0.07, 0.075]
                
                try:
                    sens_result = api_client.run_sensitivity_analysis(
                        vary_param=sens_param,
                        vary_values=vary_values,
                    )
                    
                    sens_data = sens_result.get("results", [])
                    if sens_data:
                        # pd is already imported at module level
                        sens_df = pd.DataFrame(sens_data)
                        
                        # Format values
                        if sens_param == "current_market_rate":
                            sens_df[sens_param] = sens_df[sens_param] * 100
                            x_label = "Market Rate (%)"
                        elif sens_param == "wa_fico":
                            x_label = "FICO Score"
                        else:
                            x_label = "LTV (%)"
                        
                        sens_df["cpr"] = sens_df["cpr"] * 100
                        sens_df["cdr"] = sens_df["cdr"] * 100
                        sens_df["severity"] = sens_df["severity"] * 100
                        
                        st.markdown("**CPR vs " + x_label + "**")
                        st.line_chart(sens_df.set_index(sens_param)["cpr"])
                        
                        st.markdown("**CDR vs " + x_label + "**")
                        st.line_chart(sens_df.set_index(sens_param)["cdr"])
                        
                        st.markdown("**Severity vs " + x_label + "**")
                        st.line_chart(sens_df.set_index(sens_param)["severity"])
                    
                except Exception as e:
                    st.error(f"Sensitivity analysis failed: {e}")
        
        # Model methodology
        with st.expander("📚 Model Methodology", expanded=False):
            st.markdown("""
            **Prepayment Model (CPR)**  
            Uses a survival analysis approach based on:
            - **Rate Incentive**: Current mortgage rate vs. pool WAC (coef: 0.1511)
            - **Burnout Effect**: Cumulative incentive exposure reduces prepay (coef: -0.0902)
            - **Credit Score**: Higher FICO → slightly higher prepay (coef: 0.0001)
            - **LTV**: Higher LTV → lower prepay capacity (coef: -0.0009)
            - **Seasoning Ramp**: Prepays ramp up over first 30 months (PSA-style)
            
            **Default Model (CDR)**  
            Estimates probability of default based on:
            - **SATO**: Spread at origination indicates credit risk (coef: 0.5538)
            - **High LTV Flag**: LTV > 80% indicates higher default risk (coef: 0.3920)
            - **FICO Bucket**: Credit tier classification (coef: 0.0276)
            - **Credit Score**: Inverse relationship with default (coef: -0.0020)
            - **Economic Multiplier**: Adjusts for macro conditions
            
            **Severity Model**  
            Loss-given-default estimated from:
            - **Base Severity**: 35% (industry average)
            - **LTV Adjustment**: +0.4% per point above 80% LTV
            - **FICO Adjustment**: -0.02% per point above 700 FICO
            - **Property Type**: Condos +5%, manufactured housing +10%
            - **Judicial States**: +5% for longer foreclosure timelines
            - **HPI Sensitivity**: Home price depreciation increases severity
            """)
    
    elif pricing_mode == "🎯 Scenario-Based":
        st.info(
            "**Scenario-Based Mode**: Select a predefined scenario from the Analytics tab. "
            "CPR/CDR/Severity will be loaded from the scenario parameters."
        )
        
        # Show current scenario values
        scenario_cpr = st.session_state.get("cpr_pct", 10.0)
        scenario_cdr = st.session_state.get("cdr_pct", 2.0)
        scenario_severity = st.session_state.get("severity_pct", 35.0)
        scenario_name = st.session_state.get("scenario_name", "No scenario selected")
        
        st.write(f"**Active Scenario:** {scenario_name}")
        
        scn_col1, scn_col2, scn_col3 = st.columns(3)
        with scn_col1:
            st.metric("Scenario CPR", f"{scenario_cpr:.1f}%")
        with scn_col2:
            st.metric("Scenario CDR", f"{scenario_cdr:.1f}%")
        with scn_col3:
            st.metric("Scenario Severity", f"{scenario_severity:.1f}%")
        
        cpr = scenario_cpr / 100.0
        cdr = scenario_cdr / 100.0
        severity = scenario_severity / 100.0
        
        st.caption("💡 Go to the **Analytics** tab to select or modify scenarios.")
    
    else:  # Manual mode
        st.caption("Manually adjust parameters to see how portfolio valuation changes")
        
        pricing_col1, pricing_col2, pricing_col3, pricing_col4 = st.columns(4)
        
        with pricing_col1:
            cpr = st.slider(
                "CPR (%)",
                min_value=0.0,
                max_value=50.0,
                value=st.session_state.get("portfolio_cpr", 10.0),
                step=1.0,
                key="portfolio_cpr",
                help="Constant Prepayment Rate - Annual rate at which loans prepay voluntarily"
            ) / 100.0
        
        with pricing_col2:
            cdr = st.slider(
                "CDR (%)",
                min_value=0.0,
                max_value=20.0,
                value=st.session_state.get("portfolio_cdr", 2.0),
                step=0.5,
                key="portfolio_cdr",
                help="Constant Default Rate - Annual rate at which loans default"
            ) / 100.0
        
        with pricing_col3:
            severity = st.slider(
                "Loss Severity (%)",
                min_value=0.0,
                max_value=100.0,
                value=st.session_state.get("portfolio_severity", 35.0),
                step=5.0,
                key="portfolio_severity",
                help="Loss Given Default - Percentage of loan balance lost when a loan defaults"
            ) / 100.0
        
        with pricing_col4:
            use_full_pricing = st.toggle(
                "Full Pricing Engine",
                value=True,
                key="use_full_pricing_toggle",
                help="Use full cashflow projection with yield curve. Disable for faster simplified pricing."
            )
    
    # For non-manual modes, add pricing engine toggle outside columns
    if pricing_mode != "📝 Manual":
        use_full_pricing = st.toggle(
            "Full Pricing Engine",
            value=True,
            key="use_full_pricing_toggle_alt",
            help="Use full cashflow projection with yield curve. Disable for faster simplified pricing."
        )
    
    # Show current yield curve assumptions
    with st.expander("🏦 Market Data & Yield Curve", expanded=False):
        st.markdown("""
        **Treasury Curve (as of Feb 2026):**
        | Tenor | Rate |
        |-------|------|
        | 3-month | 4.80% |
        | 6-month | 4.75% |
        | 1-year | 4.65% |
        | 2-year | 4.48% |
        | 5-year | 4.25% |
        | 10-year | 4.45% |
        | 30-year | 4.65% |
        
        **SOFR Rate:** 5.20% (for floating-rate tranches)
        
        **Credit Spreads by Rating:**
        - AAA: +25 bps | AA: +50 bps | A: +85 bps | BBB: +150 bps
        """)
    
    st.markdown("---")
    
    # Fetch full portfolio data from API with scenario parameters
    portfolio_data = None
    try:
        portfolio_data = api_client.get_investor_portfolio(
            investor_address,
            cpr=cpr,
            cdr=cdr,
            severity=severity,
            use_full_pricing=use_full_pricing,
        )
    except Exception as e:
        st.error(f"❌ Could not fetch portfolio: {e}")
        st.info("💡 Check that the API server is running and the pricing engine is available.")
    
    holdings = portfolio_data.get("holdings", []) if portfolio_data else []
    cash_balance = portfolio_data.get("cash_balance", 0.0) if portfolio_data else 0.0
    pending_yields = portfolio_data.get("pending_yields", []) if portfolio_data else []
    total_pending = portfolio_data.get("total_pending_yields", 0.0) if portfolio_data else 0.0
    
    if not holdings:
        st.info("📭 No token holdings found for this address.")
        st.caption("💡 To see holdings: Go to Issuer screen → Deploy Tranches → Issue Tokens to this address")
        
        # Show cash balance and deposit/withdraw even without holdings
        st.markdown("---")
        st.markdown("### 💰 Cash Management")
        
        cash_col1, cash_col2, cash_col3, cash_col4 = st.columns([1, 2, 1, 1])
        
        with cash_col1:
            st.metric("💵 Cash Balance", _format_currency(cash_balance))
        
        with cash_col2:
            deposit_amount_empty = st.number_input(
                "Amount (USD)",
                min_value=0.0,
                value=10000.0,
                step=1000.0,
                format="%.2f",
                key="cash_amount_empty",
                help="Enter amount to deposit or withdraw"
            )
        
        with cash_col3:
            if st.button("⬆️ Deposit", type="primary", use_container_width=True, key="deposit_btn_empty"):
                if deposit_amount_empty > 0:
                    with loading_spinner("Processing deposit..."):
                        try:
                            result = api_client.deposit_cash(investor_address, deposit_amount_empty)
                            success_message(
                                f"✅ Deposited {_format_currency(result['deposited_amount'])}! "
                                f"New balance: {_format_currency(result['new_balance'])}",
                                celebration=True
                            )
                            _rerun()
                        except Exception as e:
                            error_message(f"Deposit failed: {e}")
                else:
                    error_message("Please enter an amount greater than 0")
        
        with cash_col4:
            if st.button("⬇️ Withdraw", use_container_width=True, key="withdraw_btn_empty"):
                if deposit_amount_empty > 0:
                    if deposit_amount_empty > cash_balance:
                        error_message(f"Insufficient balance. Available: {_format_currency(cash_balance)}")
                    else:
                        with loading_spinner("Processing withdrawal..."):
                            try:
                                result = api_client.withdraw_cash(investor_address, deposit_amount_empty)
                                success_message(
                                    f"✅ Withdrew {_format_currency(result['withdrawn_amount'])}! "
                                    f"New balance: {_format_currency(result['new_balance'])}",
                                    celebration=True
                                )
                                _rerun()
                            except Exception as e:
                                error_message(f"Withdrawal failed: {e}")
        
        # Show available deals for investment
        available_deals = _get_all_available_deals_summary(api_client)
        if available_deals:
            st.markdown("---")
            st.markdown("### 📋 Available Deals for Investment")
            st.caption("These tranches have been deployed and are available for token issuance.")
            
            avail_df = pd.DataFrame([
                {
                    "Token": d.get("token_symbol", ""),
                    "Original Balance": _format_currency(d.get("original_balance", 0)),
                    "Est. YTM": f"{d.get('ytm', 0):.2%}",
                    "OAS": f"{d.get('oas_bps', 0)}bps",
                    "Type": d.get("coupon_type", ""),
                }
                for d in available_deals
            ])
            st.dataframe(avail_df, use_container_width=True, hide_index=True)
        return
    
    # Calculate portfolio metrics - handle API response field names
    total_value = sum(h.get("current_value", h.get("balance", 0)) for h in holdings)
    total_balance = sum(h.get("balance", 0) for h in holdings)
    
    # Factor calculation - use provided factor or calculate from balance/initial
    def get_factor(h):
        if "factor" in h:
            return h["factor"]
        initial = h.get("initial_balance", h.get("balance", 1))
        return h.get("balance", 0) / initial if initial > 0 else 1.0
    
    avg_factor = sum(get_factor(h) * h.get("balance", 0) for h in holdings) / total_balance if total_balance > 0 else 0
    
    # Use portfolio-level weighted metrics from API if available
    weighted_ytm = portfolio_data.get("weighted_ytm", 0.0)
    weighted_duration = portfolio_data.get("weighted_duration", 0.0)
    weighted_oas = portfolio_data.get("weighted_oas_bps", 0)
    pricing_assumptions = portfolio_data.get("pricing_assumptions", {})
    
    # Fallback calculations if not provided by API
    if weighted_ytm == 0 and holdings:
        weighted_ytm = sum(h.get("ytm", 0.05) * h.get("current_value", h.get("balance", 0)) for h in holdings) / total_value if total_value > 0 else 0
    if weighted_duration == 0 and holdings:
        weighted_duration = sum(h.get("duration", 0) * h.get("current_value", h.get("balance", 0)) for h in holdings) / total_value if total_value > 0 else 0
    if weighted_oas == 0 and holdings:
        weighted_oas = sum(h.get("oas_bps", 0) * h.get("current_value", h.get("balance", 0)) for h in holdings) / total_value if total_value > 0 else 0
    
    # Portfolio Summary Cards - Row 1: Values and Cash
    st.markdown("### Portfolio Summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "💵 Cash Balance",
            _format_currency(cash_balance),
            help="Available cash from claimed yields"
        )
    
    with col2:
        st.metric(
            "📈 Portfolio Value",
            _format_currency(total_value),
            help="Current market value of all holdings"
        )
    
    with col3:
        st.metric(
            "📊 Avg Factor",
            f"{avg_factor:.1%}",
            help="Weighted average pool factor across holdings"
        )
    
    with col4:
        st.metric(
            "💹 Avg YTM",
            f"{weighted_ytm:.2%}",
            help="Yield to maturity weighted by position size"
        )
    
    with col5:
        st.metric(
            "🎁 Pending Yields",
            _format_currency(total_pending),
            delta=f"{len(pending_yields)} claims" if pending_yields else None,
            help="Unclaimed yield distributions"
        )
    
    # Row 2: Risk Metrics
    st.markdown("### Risk Analytics")
    risk_col1, risk_col2, risk_col3, risk_col4 = st.columns(4)
    
    with risk_col1:
        st.metric(
            "📉 Wtd Duration",
            f"{weighted_duration:.2f} yrs",
            help="Weighted average modified duration (interest rate sensitivity)"
        )
    
    with risk_col2:
        st.metric(
            "📊 Wtd OAS",
            f"{int(weighted_oas)} bps",
            help="Weighted average Option-Adjusted Spread over risk-free curve"
        )
    
    with risk_col3:
        use_full_pricing = pricing_assumptions.get("use_full_pricing", False)
        st.metric(
            "🔬 Pricing Mode",
            "Full Engine" if use_full_pricing else "Simplified",
            help="Full Engine: Uses cashflow projection with CPR/CDR scenarios. Simplified: Coupon-based approximation."
        )
    
    with risk_col4:
        curve_date = pricing_assumptions.get("curve_date", "N/A")
        st.metric(
            "📅 Curve Date",
            curve_date if curve_date else "N/A",
            help="Date of yield curve used for pricing"
        )
    
    # Show pricing assumptions
    with st.expander("📋 Pricing Assumptions", expanded=False):
        assumption_col1, assumption_col2, assumption_col3 = st.columns(3)
        with assumption_col1:
            st.write(f"**CPR:** {pricing_assumptions.get('cpr', cpr) * 100:.1f}%")
        with assumption_col2:
            st.write(f"**CDR:** {pricing_assumptions.get('cdr', cdr) * 100:.1f}%")
        with assumption_col3:
            st.write(f"**Severity:** {pricing_assumptions.get('severity', severity) * 100:.1f}%")
        
        st.caption("💡 Tip: Adjust scenario parameters in the **Analytics** tab to see how pricing changes under different assumptions.")
    
    # Cash Management Section
    st.markdown("### 💰 Cash Management")
    cash_col1, cash_col2, cash_col3 = st.columns([2, 1, 1])
    
    with cash_col1:
        deposit_amount = st.number_input(
            "Amount (USD)",
            min_value=0.0,
            value=10000.0,
            step=1000.0,
            format="%.2f",
            key="cash_amount_input",
            help="Enter amount to deposit or withdraw"
        )
    
    with cash_col2:
        if st.button("⬆️ Deposit", type="primary", use_container_width=True, key="deposit_btn"):
            if deposit_amount > 0:
                with loading_spinner("Processing deposit..."):
                    try:
                        result = api_client.deposit_cash(investor_address, deposit_amount)
                        success_message(
                            f"✅ Deposited {_format_currency(result['deposited_amount'])}! "
                            f"New balance: {_format_currency(result['new_balance'])}",
                            celebration=True
                        )
                        _rerun()
                    except Exception as e:
                        error_message(f"Deposit failed: {e}")
            else:
                error_message("Please enter an amount greater than 0")
    
    with cash_col3:
        if st.button("⬇️ Withdraw", use_container_width=True, key="withdraw_btn"):
            if deposit_amount > 0:
                if deposit_amount > cash_balance:
                    error_message(f"Insufficient balance. Available: {_format_currency(cash_balance)}")
                else:
                    with loading_spinner("Processing withdrawal..."):
                        try:
                            result = api_client.withdraw_cash(investor_address, deposit_amount)
                            success_message(
                                f"✅ Withdrew {_format_currency(result['withdrawn_amount'])}! "
                                f"New balance: {_format_currency(result['new_balance'])}",
                                celebration=True
                            )
                            _rerun()
                        except Exception as e:
                            error_message(f"Withdrawal failed: {e}")
            else:
                error_message("Please enter an amount greater than 0")
    
    st.markdown("---")
    
    # Claim Yields Button - now actually works
    if total_pending > 0:
        col_claim1, col_claim2 = st.columns([3, 1])
        with col_claim1:
            st.info(f"💰 You have **{_format_currency(total_pending)}** in pending yields from {len(pending_yields)} token(s) ready to claim!")
        with col_claim2:
            if st.button("💰 Claim All Yields", type="primary", use_container_width=True, key="claim_yields_btn"):
                with loading_spinner("Processing yield claims on blockchain..."):
                    try:
                        result = api_client.claim_yields(investor_address, claim_all=True)
                        success_message(
                            f"✅ Successfully claimed {_format_currency(result['total_claimed'])}! "
                            f"New cash balance: {_format_currency(result['new_cash_balance'])} 🎉",
                            celebration=True
                        )
                        # Trigger rerun to refresh balances
                        _rerun()
                    except Exception as e:
                        error_message(f"Failed to claim yields: {e}")
    
    st.markdown("---")
    
    # Show yield claim history if available
    with st.expander("📜 Yield Claim History", expanded=False):
        try:
            history = api_client.get_yield_history(investor_address, limit=10)
            if history:
                history_df = pd.DataFrame([
                    {
                        "Date": h.get("claimed_at", "")[:19].replace("T", " "),
                        "Amount Claimed": _format_currency(h.get("total_amount", 0)),
                        "New Balance": _format_currency(h.get("new_balance", 0)),
                        "Claims": h.get("claims", []),
                    }
                    for h in history
                ])
                st.dataframe(history_df[["Date", "Amount Claimed", "New Balance"]], use_container_width=True, hide_index=True)
            else:
                st.info("No yield claims yet. Claim your pending yields above!")
        except Exception:
            st.info("Yield history not available.")
    
    # Distribution History Section
    st.markdown("### 📊 Distribution History")
    st.caption("Monthly distributions processed by the Trustee")
    
    # Get unique deal IDs from holdings
    deal_ids = list(set(h.get("deal_id") for h in holdings if h.get("deal_id")))
    
    if deal_ids:
        for deal_id in deal_ids:
            try:
                dist_data = api_client.get_distribution_periods(deal_id)
                periods = dist_data.get("periods", [])
                
                if periods:
                    with st.expander(f"📁 {deal_id} - {len(periods)} period(s)", expanded=False):
                        dist_df = pd.DataFrame([
                            {
                                "Period": p.get("period_number"),
                                "Status": p.get("status", "").upper(),
                                "Collections": _format_currency(p.get("total_collections", 0)),
                                "Interest Dist.": _format_currency(p.get("total_interest_distributed", 0)),
                                "Principal Dist.": _format_currency(p.get("total_principal_distributed", 0)),
                                "Date": p.get("distribution_date", p.get("collection_date", ""))[:10] if p.get("distribution_date") or p.get("collection_date") else "N/A",
                            }
                            for p in sorted(periods, key=lambda x: x.get("period_number", 0), reverse=True)
                        ])
                        st.dataframe(dist_df, use_container_width=True, hide_index=True)
                        
                        # Show pending periods alert
                        pending = [p for p in periods if p.get("status") == "pending"]
                        if pending:
                            st.warning(f"⏳ {len(pending)} period(s) pending Trustee distribution")
                else:
                    st.info(f"📭 No distributions yet for {deal_id}")
            except Exception as e:
                st.caption(f"Could not load distributions for {deal_id}")
    else:
        st.info("📭 Distribution history will appear here once you hold tokens")
    
    st.markdown("---")
    
    # Holdings Table
    st.markdown("### Token Holdings")
    
    holdings_df = pd.DataFrame([
        {
            "Token": h.get("token_symbol", f"{h.get('deal_id', '')[:8]}-{h.get('tranche_id', '')}"),
            "Face Value": _format_currency(h.get("balance", 0)),
            "Factor": f"{get_factor(h):.1%}",
            "YTM": f"{h.get('ytm', 0.05):.2%}",
            "OAS": f"{h.get('oas_bps', 0)} bps",
            "Z-Spread": f"{h.get('z_spread_bps', 0)} bps",
            "Duration": f"{h.get('duration', 0):.2f}",
            "Rating": h.get("rating", "NR"),
            "Type": h.get("coupon_type", "N/A"),
            "Cashflows": h.get("cashflow_count", 0),
        }
        for h in holdings
    ])
    
    st.dataframe(
        holdings_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Token": st.column_config.TextColumn("Token", width="medium"),
            "Face Value": st.column_config.TextColumn("Face Value", width="small"),
            "Factor": st.column_config.TextColumn("Factor", width="small"),
            "YTM": st.column_config.TextColumn("YTM", width="small"),
            "OAS": st.column_config.TextColumn("OAS", width="small"),
            "Z-Spread": st.column_config.TextColumn("Z-Spd", width="small"),
            "Duration": st.column_config.TextColumn("Dur", width="small"),
            "Rating": st.column_config.TextColumn("Rating", width="small"),
            "Type": st.column_config.TextColumn("Type", width="small"),
            "Cashflows": st.column_config.NumberColumn("Cashflows", width="small", help="Number of cashflows projected"),
        }
    )
    
    # Pricing methodology details for selected holding
    with st.expander("📈 Pricing Methodology Details", expanded=False):
        for h in holdings:
            token = h.get("token_symbol", f"{h.get('deal_id', '')[:8]}-{h.get('tranche_id', '')}")
            methodology = h.get("pricing_methodology", "N/A")
            st.markdown(f"**{token}:** {methodology}")
    
    st.markdown("---")
    
    # Deal Performance for Selected Holding
    st.markdown("### Deal Performance")
    
    # Generate token symbols for selection
    token_options = [
        h.get("token_symbol", f"{h.get('deal_id', '')[:8]}-{h.get('tranche_id', '')}")
        for h in holdings
    ]
    
    selected_holding = st.selectbox(
        "Select Token for Details",
        options=token_options,
        key="selected_holding"
    )
    
    if selected_holding:
        # Find the holding by matching token_symbol or constructing it
        holding = next(
            (h for h in holdings if h.get("token_symbol") == selected_holding or 
             f"{h.get('deal_id', '')[:8]}-{h.get('tranche_id', '')}" == selected_holding),
            None
        )
        if holding:
            deal_id = holding.get("deal_id", "")
            factor = get_factor(holding)
            
            # Performance metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Pool Factor", f"{factor:.1%}")
            with col2:
                # Simulated CPR
                import random
                random.seed(hash(deal_id))
                cpr = random.uniform(0.08, 0.15)
                st.metric("CPR", f"{cpr:.1%}")
            with col3:
                cdr = random.uniform(0.005, 0.02)
                st.metric("CDR", f"{cdr:.2%}")
            with col4:
                dq60 = random.uniform(0.01, 0.04)
                st.metric("DQ 60+", f"{dq60:.1%}")
            
            # Issuance info
            if holding.get("issued_at"):
                st.caption(f"🕐 Issued: {holding.get('issued_at', 'N/A')}")
            if holding.get("last_tx_hash"):
                st.caption(f"🔗 Last TX: {holding.get('last_tx_hash', '')[:20]}...")
            
            # Actions
            st.markdown("### Actions")
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                if st.button("📄 View Deal Documents", use_container_width=True, key="btn_docs"):
                    st.info("Document viewer would open here (PSA, Prospectus, etc.)")
            
            with action_col2:
                if st.button("📊 View Audit Trail", use_container_width=True, key="btn_audit"):
                    st.info("Blockchain audit trail would display here")
            
            with action_col3:
                if st.button("💹 Request Trade Quote", use_container_width=True, key="btn_trade"):
                    st.info("Trading interface would open here")


def render_investor_page(api_client: APIClient) -> None:
    """
    Render the complete investor analytics dashboard.

    Parameters
    ----------
    api_client : APIClient
        Configured API client instance
    """
    st.header("📊 Investor Portal")
    st.caption("Portfolio management, risk analytics, and scenario modeling")
    
    # Main tabs for investor functionality
    main_tabs = st.tabs(["💼 Portfolio", "📈 Analytics & Simulation"])
    
    # Portfolio Tab
    with main_tabs[0]:
        render_portfolio_dashboard(api_client)
    
    # Analytics Tab (existing functionality)
    with main_tabs[1]:
        st.subheader("📈 Risk & Valuation Analytics")
        
        # Deal Selection
        selected_deal = render_deal_selector(api_client)

        if not selected_deal:
            st.info("👆 Please select a deal to begin analysis")
            return

        # Simulation Controls
        sim_params = render_simulation_controls(api_client, selected_deal)

        # Simulation Execution
        simulation_results = render_simulation_execution(api_client, selected_deal, sim_params)

        # Results Dashboard
        if simulation_results:
            render_results_dashboard(simulation_results)

        # Scenario Comparison (if previous results exist)
        if "last_simulation" in st.session_state:
            last_sim = st.session_state["last_simulation"]
            if last_sim["deal_id"] == selected_deal:
                st.subheader("🔄 Scenario Comparison")

                if st.button("📊 Compare with Previous Run"):
                    # Comparison logic would go here
                    st.info("Scenario comparison feature coming soon!")