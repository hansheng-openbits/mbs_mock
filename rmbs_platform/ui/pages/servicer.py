"""
Servicer Page
============

Performance data management and reconciliation interface for servicers.
Includes Web3 loan NFT status updates for monthly performance synchronization.
"""

import json
from io import StringIO
from typing import Optional, Dict

import pandas as pd
import streamlit as st

from ..services.api_client import APIClient
from ..components.status import success_message, error_message, loading_spinner
from ..components.data_display import data_table
from ..utils.formatting import create_table_formatter
from ..utils.validation import validate_performance_csv


def render_performance_upload_section(api_client: APIClient) -> None:
    """Render the performance data upload section."""
    st.subheader("📤 Monthly Servicer Tape Upload")
    
    # Workflow guidance
    with st.expander("📋 Monthly Distribution Cycle - Step 1 of 4", expanded=False):
        st.markdown("""
        **You are at Step 1: Servicer uploads monthly performance tape**
        
        | Step | Role | Status |
        |------|------|--------|
        | **1️⃣** | **Servicer** | ◀️ **YOU ARE HERE** - Upload monthly collections |
        | 2️⃣ | Trustee | Execute waterfall distribution |
        | 3️⃣ | System | Update token balances |
        | 4️⃣ | Investor | Claim yields |
        
        After you upload, a **pending distribution period** is created for the Trustee to process.
        """)

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
                
                # Web3 NFT Auto-Update Section
                st.markdown("---")
                st.markdown("#### 🔗 Web3 Integration (Optional)")
                
                update_nfts = st.checkbox(
                    "Auto-update loan NFT statuses on blockchain",
                    value=False,
                    help="Automatically sync loan statuses to on-chain NFTs after upload. "
                         "Requires loan_token_mapping.json in the deal's datasets folder."
                )
                
                loan_nft_contract: Optional[str] = None
                if update_nfts:
                    loan_nft_contract = st.text_input(
                        "LoanNFT Contract Address (optional)",
                        placeholder="0x... (uses config default if empty)",
                        help="LoanNFT contract address. Leave empty to use RMBS_WEB3_LOAN_NFT config."
                    )
                    st.caption("⚠️ Ensure `loan_token_mapping.json` exists in `datasets/{deal_id}/`")

                can_upload = bool(created_by.strip()) and (not missing_cols or allow_override)
                upload_help = (
                    "Upload the servicer tape to the backend."
                    if can_upload
                    else (
                        "Enter Created By and ensure required columns are present "
                        "(or enable override) before uploading."
                    )
                )

                st.markdown("---")
                
                with col2:
                    pass  # Moved button below
                
                if st.button(
                    "📤 Upload Servicer Tape" + (" & Update NFTs" if update_nfts else ""),
                    type="primary",
                    use_container_width=True,
                    disabled=not can_upload,
                    help=upload_help,
                ):
                    try:
                        spinner_msg = "Uploading servicer tape..."
                        if update_nfts:
                            spinner_msg = "Uploading servicer tape and updating NFT statuses..."
                        
                        with loading_spinner(spinner_msg):
                            csv_payload = uploaded_file.getvalue().decode("utf-8")
                            result = api_client.upload_performance(
                                selected_deal_id,
                                csv_payload,
                                uploaded_file.name,
                                created_by.strip(),
                                update_nfts=update_nfts,
                                loan_nft_contract=loan_nft_contract if loan_nft_contract else None,
                            )

                            success_message(
                                f"Servicer tape for '{selected_deal_id}' uploaded successfully! 📊",
                                celebration=True
                            )
                            
                            # Show upload summary with both new and total rows
                            rows_new = result.get('rows_new', result.get('rows', 0))
                            rows_total = result.get('rows_total', result.get('rows', 0))
                            
                            if rows_new != rows_total:
                                st.info(f"📤 **Uploaded:** {rows_new:,} records | 📚 **Total in database:** {rows_total:,} records")
                            else:
                                st.info(f"📤 Uploaded {rows_new:,} performance records")
                            
                            # Show local NFT records update (always happens if records exist)
                            nft_records_result = result.get("nft_records_updated")
                            if nft_records_result and nft_records_result.get("updated"):
                                st.success(
                                    f"📝 Local NFT records updated: {nft_records_result.get('loans_updated', 0)} loans "
                                    f"(period {nft_records_result.get('period', 'N/A')})"
                                )
                                
                                # Show status summary
                                status_summary = nft_records_result.get("status_summary", {})
                                if status_summary:
                                    with st.expander("📊 Loan Status Distribution"):
                                        for status, count in sorted(status_summary.items()):
                                            st.write(f"• **{status}**: {count} loans")
                            
                            # Show NFT update results if enabled
                            nft_result = result.get("nft_update")
                            if nft_result:
                                if nft_result.get("success"):
                                    st.success(
                                        f"✅ NFT statuses updated: {nft_result.get('loans_updated', 0)} loans "
                                        f"({len(nft_result.get('tx_hashes', []))} transactions)"
                                    )
                                    
                                    # Show status summary
                                    status_summary = nft_result.get("status_summary", {})
                                    if status_summary:
                                        with st.expander("📊 Status Distribution"):
                                            for status, count in status_summary.items():
                                                st.write(f"• **{status}**: {count} loans")
                                    
                                    # Show transaction hashes
                                    tx_hashes = nft_result.get("tx_hashes", [])
                                    if tx_hashes:
                                        with st.expander("🔗 Transaction Hashes"):
                                            for tx_hash in tx_hashes:
                                                st.code(tx_hash, language=None)
                                else:
                                    # Show errors if NFT update failed
                                    errors = nft_result.get("errors", [])
                                    if errors:
                                        st.warning("⚠️ NFT update had issues:")
                                        for error in errors:
                                            st.write(f"• {error}")
                            
                            # Show distribution period created (for trustee workflow)
                            dist_period = result.get("distribution_period")
                            if dist_period:
                                st.markdown("---")
                                st.markdown("### 📋 Distribution Period Created")
                                st.info(
                                    f"**Period {dist_period.get('period_number')}** is now **pending** distribution.\n\n"
                                    f"💰 Total Collections: ${dist_period.get('total_collections', 0):,.2f}\n\n"
                                    f"**Next Step:** Trustee must execute waterfall to distribute to token holders."
                                )
                                st.caption("👉 Go to **Trustee** screen → **Execute Distribution** to complete the cycle")

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

    # Filter deals that have performance data (API returns 'latest_period')
    deals_with_perf = [d for d in deals if d.get('latest_period')]

    if not deals_with_perf:
        st.info("No deals have performance data uploaded yet")
        return

    deal_options = [f"{d.get('deal_id')} (latest: period {d.get('latest_period')})"
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


def render_nft_status_update_section(api_client: APIClient) -> None:
    """Render the NFT status update section for syncing loan statuses on-chain."""
    st.subheader("🔗 Loan NFT Status Updates")
    st.caption("View and sync loan NFT statuses with blockchain")
    
    # Deal selection
    deals = api_client.get_deals()
    if not deals:
        st.warning("⚠️ No deals available.")
        return
    
    # Filter deals that have performance data (API returns 'latest_period')
    deals_with_perf = [d for d in deals if d.get('latest_period')]
    
    if not deals_with_perf:
        st.warning("⚠️ No deals have performance data uploaded yet. Upload performance data first.")
        return
    
    deal_options = [d.get('deal_id') for d in deals_with_perf]
    selected_deal_id = st.selectbox(
        "Select Deal",
        options=deal_options,
        key="nft_update_deal_select",
        help="Choose a deal with uploaded performance data"
    )
    
    if not selected_deal_id:
        return
    
    # Show deal info
    deal_info = next((d for d in deals_with_perf if d.get('deal_id') == selected_deal_id), {})
    latest_period = deal_info.get('latest_period', 'N/A')
    
    st.markdown("---")
    
    # =========================================================================
    # CURRENT NFT RECORDS STATUS
    # =========================================================================
    st.markdown("### 📊 Current NFT Records Status")
    
    # Try to load the NFT records file
    import os
    from pathlib import Path
    
    # Get the datasets path (this is a bit hacky but works for now)
    base_path = Path(__file__).resolve().parents[2]  # Go up to rmbs_platform root
    records_path = base_path / "datasets" / selected_deal_id / "loan_nft_records.json"
    
    if records_path.exists():
        try:
            with open(records_path, "r") as f:
                nft_records = json.load(f)
            
            # Display summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            total_loans = nft_records.get("total_loans", 0)
            last_update = nft_records.get("last_status_update", nft_records.get("minted_at", "N/A"))
            last_period = nft_records.get("last_period_updated", "N/A")
            contract = nft_records.get("contract_address", "N/A")
            
            with col1:
                st.metric("Total Loan NFTs", f"{total_loans:,}")
            with col2:
                st.metric("Last Period Updated", str(last_period))
            with col3:
                st.metric("Performance Period", str(latest_period))
            with col4:
                # Check if up to date
                is_current = str(last_period) == str(latest_period)
                status_icon = "✅" if is_current else "⚠️"
                st.metric("Sync Status", f"{status_icon} {'Current' if is_current else 'Outdated'}")
            
            # Show last update time
            if last_update != "N/A":
                st.caption(f"📅 Last updated: {last_update}")
            
            # Show contract address (truncated)
            if contract and contract != "N/A":
                display_contract = f"{contract[:10]}...{contract[-8:]}" if len(contract) > 20 else contract
                st.caption(f"📋 Contract: `{display_contract}`")
            
            # Status distribution
            loans_data = nft_records.get("loans", {})
            if loans_data:
                status_counts: Dict[str, int] = {}
                total_balance = 0.0
                
                for loan in loans_data.values():
                    status = loan.get("status", "Unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1
                    total_balance += float(loan.get("current_balance", 0))
                
                # Display status distribution
                with st.expander("📈 Status Distribution", expanded=True):
                    status_df = pd.DataFrame([
                        {"Status": k, "Count": v, "Percentage": f"{v/len(loans_data)*100:.1f}%"} 
                        for k, v in sorted(status_counts.items(), key=lambda x: -x[1])
                    ])
                    st.dataframe(status_df, use_container_width=True, hide_index=True)
                    
                    st.metric("Total Current Balance", f"${total_balance:,.2f}")
                
                # Sample loan records
                with st.expander("🔍 Sample Loan Records (First 5)"):
                    sample_loans = list(loans_data.values())[:5]
                    for loan in sample_loans:
                        st.markdown(f"""
                        **Token #{loan.get('token_id')}** - Loan `{loan.get('loan_id')}`
                        - Status: **{loan.get('status')}** | Balance: **${loan.get('current_balance', 0):,.2f}**
                        - Rate: {loan.get('note_rate_percent', 'N/A')}% | Originated: {loan.get('origination_date', 'N/A')}
                        - Last Updated: {loan.get('last_updated', 'N/A')}
                        """)
                        st.divider()
            
        except Exception as e:
            st.error(f"Failed to load NFT records: {e}")
    else:
        st.warning(f"⚠️ No NFT records found for {selected_deal_id}. Mint loan NFTs first (Arranger role).")
        st.info("Go to **Arranger → Loan NFTs** tab to mint loan NFTs for this deal.")
    
    st.markdown("---")
    
    # =========================================================================
    # MANUAL BLOCKCHAIN SYNC SECTION
    # =========================================================================
    st.markdown("### 🔄 Sync to Blockchain")
    
    # Information box
    with st.expander("ℹ️ How Blockchain Sync Works"):
        st.markdown("""
        **Automatic Updates** (Recommended):
        - Enable "Auto-update NFT statuses" when uploading servicer tape
        - NFTs are automatically synced to blockchain
        
        **Manual Sync** (This Section):
        - Use when automatic update was skipped
        - Or to re-sync after fixing data issues
        
        **Status Mapping:**
        | Performance Data | NFT Status |
        |-----------------|------------|
        | DPD 0-29 | Current |
        | DPD 30-59 | 30+ DPD |
        | DPD 60-89 | 60+ DPD |
        | DPD 90+ | 90+ DPD |
        | Default/Foreclosure | Default |
        | Paid/Full | Paid Off |
        | Prepaid | Prepaid |
        """)
    
    st.markdown("---")
    
    # NFT contract configuration (for blockchain sync - optional)
    st.markdown("### 🔧 Blockchain Sync Configuration *(Optional)*")
    
    # Add info box explaining this is optional
    st.info(
        "💡 **This section is optional for demo/development mode.**\n\n"
        "Local NFT records (`loan_nft_records.json`) are already updated automatically "
        "when you upload the servicer tape above. This section is only needed if you want to "
        "sync statuses to a **real blockchain** with a deployed LoanNFT smart contract."
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        loan_nft_contract = st.text_input(
            "LoanNFT Contract Address",
            placeholder="0x...",
            help="Address of the LoanNFT contract on the blockchain"
        )
    
    with col2:
        period_to_update = st.number_input(
            "Period to Update",
            min_value=1,
            value=int(latest_period) if latest_period != 'N/A' else 1,
            help="Period number from performance data to sync (defaults to latest)"
        )
    
    # Loan ID to Token ID mapping
    st.markdown("### 📋 Loan-to-Token Mapping")
    st.caption("The system needs to know which token ID corresponds to each loan ID")
    
    mapping_option = st.radio(
        "Mapping Source",
        options=["Auto-load from file", "Upload mapping JSON"],
        help="Choose how to provide the loan ID to token ID mapping"
    )
    
    loan_id_to_token_map = None
    
    if mapping_option == "Upload mapping JSON":
        mapping_file = st.file_uploader(
            "Upload Mapping JSON",
            type=["json"],
            help='JSON file with format: {"LOAN001": 1, "LOAN002": 2, ...}'
        )
        
        if mapping_file:
            try:
                loan_id_to_token_map = json.load(mapping_file)
                st.success(f"✅ Loaded mapping for {len(loan_id_to_token_map)} loans")
            except Exception as e:
                st.error(f"❌ Failed to parse mapping JSON: {e}")
    else:
        st.info(f"Will attempt to load mapping from `datasets/{selected_deal_id}/loan_token_mapping.json`")
    
    st.markdown("---")
    
    # Validation
    can_update = bool(loan_nft_contract and loan_nft_contract.startswith("0x") and len(loan_nft_contract) == 42)
    
    if not can_update:
        st.warning("⚠️ Enter a valid LoanNFT contract address (0x... with 42 characters)")
    
    # Update button
    col1, col2, col3 = st.columns([2, 1, 2])
    
    with col2:
        if st.button(
            "🔗 Sync to Blockchain",
            type="primary",
            use_container_width=True,
            disabled=not can_update
        ):
            try:
                with loading_spinner("Updating loan NFT statuses on blockchain..."):
                    result = api_client.update_loan_nft_statuses(
                        deal_id=selected_deal_id,
                        loan_nft_contract=loan_nft_contract,
                        period=period_to_update,
                        loan_id_to_token_map=loan_id_to_token_map
                    )
                    
                    success_message(
                        f"Successfully updated {result.get('loans_updated', 0)} loan NFTs!",
                        celebration=True
                    )
                    
                    # Show results
                    st.markdown("### 📊 Update Results")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric("Loans Updated", result.get('loans_updated', 0))
                        st.metric("Period", result.get('period', 'N/A'))
                    
                    with col2:
                        tx_hashes = result.get('tx_hashes', [])
                        st.metric("Transactions", len(tx_hashes))
                    
                    # Status summary
                    status_summary = result.get('status_summary', {})
                    if status_summary:
                        st.markdown("#### Status Distribution")
                        summary_df = pd.DataFrame([
                            {"Status": k, "Count": v} for k, v in status_summary.items()
                        ])
                        st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    
                    # Transaction hashes
                    if tx_hashes:
                        with st.expander("🔗 Transaction Hashes"):
                            for i, tx_hash in enumerate(tx_hashes, 1):
                                st.code(tx_hash, language=None)
                    
                    # Errors
                    errors = result.get('errors', [])
                    if errors:
                        with st.expander(f"⚠️ Errors ({len(errors)})", expanded=True):
                            for error in errors:
                                st.warning(error)
                    
            except Exception as e:
                error_message(
                    f"Failed to update NFT statuses: {e}",
                    details=str(e),
                    show_retry=True
                )


def render_servicer_page(api_client: APIClient) -> None:
    """Render the complete servicer performance management interface."""
    st.header("📊 Servicer Performance Management")
    st.caption("Upload, validate, reconcile servicer performance data, and sync NFT statuses")

    # Main interface tabs
    tabs = st.tabs([
        "📤 Upload Performance",
        "📋 Data Management",
        "⚖️ Reconciliation",
        "🔗 NFT Status Updates"
    ])

    with tabs[0]:
        render_performance_upload_section(api_client)

    with tabs[1]:
        render_performance_management_section(api_client)

    with tabs[2]:
        render_reconciliation_section(api_client)

    with tabs[3]:
        render_nft_status_update_section(api_client)

    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Upload performance data regularly and sync NFT statuses monthly to keep blockchain records accurate.")