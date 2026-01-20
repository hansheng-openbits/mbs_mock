"""
Servicer Page
============

Performance data management and reconciliation interface for servicers.
"""

from ..services.api_client import APIClient
from ..components.status import success_message, error_message, loading_spinner
from ..components.data_display import data_table
from ..utils.formatting import create_table_formatter
from ..utils.validation import validate_performance_csv
import streamlit as st
import pandas as pd
from io import StringIO


def render_performance_upload_section(api_client: APIClient) -> None:
    """Render the performance data upload section."""
    st.subheader("📤 Servicer Tape Upload")

    # Deal selection
    deals = api_client.get_deals()
    if not deals:
        st.warning("⚠️ No deals available. Please ask an arranger to create deal specifications first.")
        return

    deal_options = [f"{d.get('deal_id')} - {d.get('deal_name', 'Unknown')}" for d in deals]
    deal_id_map = {opt: d.get('deal_id') for opt, d in zip(deal_options, deals)}

    selected_option = st.selectbox(
        "Select Deal for Performance Upload",
        options=deal_options,
        help="Choose the deal to upload performance data for"
    )

    selected_deal_id = deal_id_map.get(selected_option)

    if selected_deal_id:
        st.caption(f"Uploading performance data for deal: **{selected_deal_id}**")

        # File upload
        uploaded_file = st.file_uploader(
            "Upload Servicer Tape (CSV)",
            type=["csv"],
            help="Upload a servicer performance tape in CSV format"
        )

        if uploaded_file is not None:
            try:
                # Read and preview CSV
                csv_content = StringIO(uploaded_file.getvalue().decode("utf-8"))
                df = pd.read_csv(csv_content)

                st.success(f"✅ CSV loaded successfully: {len(df)} rows, {len(df.columns)} columns")

                # Show preview
                st.subheader("📋 Data Preview")
                st.dataframe(df.head(10), use_container_width=True)

                # Basic validation
                required_cols = ['Period', 'InterestCollected', 'PrincipalCollected']
                missing_cols = [col for col in required_cols if col not in df.columns]

                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                else:
                    st.info("✅ Required columns present")

                # Additional stats (best-effort)
                if "Period" in df.columns:
                    try:
                        periods = sorted(df["Period"].unique())
                        st.write(f"**Periods covered:** {len(periods)} periods ({min(periods)} to {max(periods)})")
                    except Exception:
                        pass

                # Validate button
                if st.button("🔍 Validate Data", help="Run validation checks on the uploaded servicer tape"):
                    csv_string = uploaded_file.getvalue().decode("utf-8")
                    is_valid, errors = validate_performance_csv(csv_string)

                    if is_valid:
                        st.success("✅ Servicer tape passed validation")
                    else:
                        with st.expander(f"❌ CSV validation failed ({len(errors)} issues)", expanded=True):
                            for error in errors:
                                st.write(f"• {error}")

                st.markdown("---")
                st.caption("If your tape uses different column names, either rename them to match the required schema or upload with override.")

                allow_override = st.checkbox(
                    "Allow upload even if required columns are missing",
                    value=False,
                    help="Use only if you know the backend can interpret your tape schema. Recommended: fix column names instead."
                )

                col1, col2 = st.columns([3, 1])

                with col1:
                    created_by = st.text_input(
                        "Created By",
                        value="Servicer Team",
                        help="Name or identifier of who is uploading this data"
                    )

                can_upload = bool(created_by.strip()) and (not missing_cols or allow_override)
                upload_help = (
                    "Upload the servicer tape to the backend."
                    if can_upload
                    else (
                        "Enter Created By and ensure required columns are present "
                        "(or enable override) before uploading."
                    )
                )

                with col2:
                    if st.button(
                        "📤 Upload Servicer Tape",
                        type="primary",
                        use_container_width=True,
                        disabled=not can_upload,
                        help=upload_help,
                    ):
                        try:
                            with loading_spinner("Uploading servicer tape..."):
                                csv_payload = uploaded_file.getvalue().decode("utf-8")
                                result = api_client.upload_performance(
                                    selected_deal_id,
                                    csv_payload,
                                    uploaded_file.name,
                                    created_by.strip()
                                )

                                success_message(
                                    f"Servicer tape for '{selected_deal_id}' uploaded successfully! 📊",
                                    celebration=True
                                )

                                st.info(f"Processed {result.get('rows', 0)} performance records")

                        except Exception as e:
                            error_message(
                                f"Failed to upload servicer tape: {e}",
                                details=str(e),
                                show_retry=True
                            )

            except Exception as e:
                st.error(f"❌ Failed to process CSV file: {e}")


def render_performance_management_section(api_client: APIClient) -> None:
    """Render the performance data management section."""
    st.subheader("📋 Performance Data Management")

    # Deal selection
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available")
        return

    deal_options = [d.get('deal_id') for d in deals]
    selected_deal_id = st.selectbox(
        "Select Deal",
        options=deal_options,
        key="servicer_deal_select",
        help="Choose a deal to manage performance data for"
    )

    if selected_deal_id:
        # Version history
        st.markdown("### 📚 Version History")
        if st.button(f"Load Versions for {selected_deal_id}", help="Refresh version list"):
            try:
                versions = api_client.get_versions(f"/performance/{selected_deal_id}/versions")
                if versions:
                    version_df = pd.DataFrame(versions)
                    # Format timestamps
                    if 'created_at' in version_df.columns:
                        version_df['created_at'] = pd.to_datetime(version_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')

                    formatters = create_table_formatter(version_df)
                    data_table(
                        version_df,
                        f"Performance Versions - {selected_deal_id}",
                        formatters=formatters,
                        downloadable=True
                    )
                else:
                    st.info("No performance data uploaded yet for this deal")

            except Exception as e:
                st.error(f"Failed to load version history: {e}")

        # Data validation
        st.markdown("### 🔍 Data Validation")
        if st.button(f"Validate Latest Data for {selected_deal_id}"):
            try:
                # Get latest performance data
                # This would need an endpoint to retrieve performance data
                st.info("Data validation feature coming soon - will check for completeness and consistency")
            except Exception as e:
                st.error(f"Validation failed: {e}")


def render_reconciliation_section(api_client: APIClient) -> None:
    """Render the reconciliation dashboard section."""
    st.subheader("⚖️ Reconciliation Dashboard")

    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available for reconciliation")
        return

    # Filter deals that have performance data
    deals_with_perf = [d for d in deals if d.get('latest_performance_period')]

    if not deals_with_perf:
        st.info("No deals have performance data uploaded yet")
        return

    deal_options = [f"{d.get('deal_id')} (latest: period {d.get('latest_performance_period')})"
                   for d in deals_with_perf]

    selected_option = st.selectbox(
        "Select Deal for Reconciliation",
        options=deal_options,
        help="Choose a deal to view reconciliation status"
    )

    if selected_option:
        selected_deal_id = selected_option.split(' ')[0]  # Extract deal ID

        st.info("Reconciliation dashboard coming soon - will show:")
        st.write("• Period completeness checks")
        st.write("• Balance reconciliation")
        st.write("• Data quality metrics")
        st.write("• Exception tracking and resolution")

        # Placeholder for reconciliation metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Periods Loaded", "12", help="Number of performance periods uploaded")
        with col2:
            st.metric("Reconciliation Rate", "98.5%", help="Percentage of records matching expectations")
        with col3:
            st.metric("Open Exceptions", "2", help="Number of unresolved data issues")
        with col4:
            st.metric("Last Updated", "2024-01-15", help="When performance data was last updated")


def render_servicer_page(api_client: APIClient) -> None:
    """Render the complete servicer performance management interface."""
    st.header("📊 Servicer Performance Management")
    st.caption("Upload, validate, and reconcile servicer performance data")

    # Main interface tabs
    tabs = st.tabs(["📤 Upload Performance", "📋 Data Management", "⚖️ Reconciliation"])

    with tabs[0]:
        render_performance_upload_section(api_client)

    with tabs[1]:
        render_performance_management_section(api_client)

    with tabs[2]:
        render_reconciliation_section(api_client)

    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Upload performance data regularly to maintain accurate deal cashflows and trigger monitoring.")