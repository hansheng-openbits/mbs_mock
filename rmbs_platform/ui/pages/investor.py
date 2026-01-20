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


def render_simulation_controls(api_client: APIClient) -> Dict[str, Any]:
    """
    Render simulation parameter controls with improved UX.

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
            st.info("ℹ️ ML models require origination tape to be configured in collateral data")

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

    def _on_scenario_select_change() -> None:
        sid = st.session_state.get("scenario_id_select")
        if not sid or sid == "__manual__":
            st.session_state["scenario_selected_id"] = None
            return
        selected = st.session_state.get("_scenario_by_id", {}).get(sid, {})
        st.session_state["scenario_selected_id"] = sid
        name = selected.get("name")
        if name:
            st.session_state["scenario_name"] = name

    def _apply_selected_scenario_params() -> None:
        sid = st.session_state.get("scenario_selected_id")
        if not sid:
            return
        selected = st.session_state.get("_scenario_by_id", {}).get(sid, {})
        params = selected.get("params") or {}
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
        if "name" in selected:
            st.session_state["scenario_name"] = selected.get("name", "")

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

    return {
        "cpr": cpr,
        "cdr": cdr,
        "severity": severity,
        "use_ml": use_ml,
        "prepay_model_key": prepay_model_key,
        "default_model_key": default_model_key,
        "scenario_id": st.session_state.get("scenario_selected_id"),
        "scenario_name": scenario_name,
        "horizon_months": horizon_months
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


def render_investor_page(api_client: APIClient) -> None:
    """
    Render the complete investor analytics dashboard.

    Parameters
    ----------
    api_client : APIClient
        Configured API client instance
    """
    st.header("📊 Risk & Valuation Dashboard")
    st.caption("Advanced RMBS analytics and scenario modeling platform")

    # Deal Selection
    selected_deal = render_deal_selector(api_client)

    if not selected_deal:
        st.info("👆 Please select a deal to begin analysis")
        return

    # Simulation Controls
    sim_params = render_simulation_controls(api_client)

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