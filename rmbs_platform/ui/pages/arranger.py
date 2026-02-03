"""
Arranger Page
============

Deal structuring workbench for arrangers with comprehensive deal management.
"""

from pathlib import Path
from ..services.api_client import APIClient
from ..components.status import success_message, error_message, loading_spinner
from ..components.data_display import data_table
from ..utils.formatting import create_table_formatter
from ..utils.validation import validate_deal_json
import streamlit as st
import json
import pandas as pd


def _rerun() -> None:
    """Version-safe Streamlit rerun (supports both old/new Streamlit APIs)."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def render_deal_upload_section(api_client: APIClient) -> None:
    """Render the deal specification upload and editing section."""
    st.subheader("📝 Deal Specification")

    def _set_arranger_deal_id(new_deal_id: str) -> None:
        """
        Safely update the Deal ID text input via Streamlit callback.

        Streamlit allows updating `st.session_state` for a widget key inside an
        `on_click` / `on_change` callback (callbacks run before the next script
        execution where widgets are instantiated).
        """
        st.session_state["arranger_deal_id"] = new_deal_id

    def _on_deal_file_change() -> None:
        """
        Handle deal JSON uploads and auto-capture `meta.deal_id`.

        We do this in an `on_change` callback so Streamlit allows updating
        the `arranger_deal_id` widget state safely.
        """
        uploaded = st.session_state.get("arranger_deal_file")
        if uploaded is None:
            st.session_state.pop("arranger_deal_spec", None)
            st.session_state.pop("arranger_uploaded_deal_id", None)
            return

        try:
            parsed = json.loads(uploaded.getvalue().decode("utf-8"))
        except Exception:
            # Keep UI robust: parsing errors are shown in the main render path.
            st.session_state.pop("arranger_deal_spec", None)
            st.session_state.pop("arranger_uploaded_deal_id", None)
            return

        st.session_state["arranger_deal_spec"] = parsed
        uploaded_deal_id = (
            parsed.get("meta", {}).get("deal_id")
            if isinstance(parsed, dict)
            else None
        )
        st.session_state["arranger_uploaded_deal_id"] = uploaded_deal_id

        # Default behavior: if the JSON has a deal_id and the user hasn't opted to override,
        # keep the Deal ID field synced to the uploaded JSON to avoid accidental mismatches.
        if uploaded_deal_id and not st.session_state.get("arranger_override_deal_id", False):
            st.session_state["arranger_deal_id"] = uploaded_deal_id

    # Deal ID input
    st.checkbox(
        "Override Deal ID",
        key="arranger_override_deal_id",
        help=(
            "By default, the Deal ID is taken from the uploaded JSON (`meta.deal_id`) to prevent "
            "accidental uploads under the wrong ID. Enable override only if you intentionally want "
            "to upload under a different Deal ID (e.g., cloning a deal)."
        ),
    )

    _uploaded_deal_id = st.session_state.get("arranger_uploaded_deal_id")
    deal_id_input = st.text_input(
        "Deal ID",
        value=st.session_state.get("arranger_deal_id", "DEAL_2024_001"),
        key="arranger_deal_id",
        help="Unique identifier for the deal",
        disabled=bool(_uploaded_deal_id) and not st.session_state.get("arranger_override_deal_id", False),
    )

    # File upload or JSON editor tabs
    upload_tab, editor_tab = st.tabs(["📁 Upload JSON", "✏️ JSON Editor"])

    deal_spec = st.session_state.get("arranger_deal_spec")
    uploaded_file = None

    with upload_tab:
        uploaded_file = st.file_uploader(
            "Upload deal specification JSON",
            key="arranger_deal_file",
            on_change=_on_deal_file_change,
            type=["json"],
            help="Upload a deal specification JSON file"
        )

        if uploaded_file is not None:
            try:
                # Prefer the parsed copy from session_state (set by on_change).
                if deal_spec is None:
                    deal_spec = json.load(uploaded_file)
                    st.session_state["arranger_deal_spec"] = deal_spec

                uploaded_meta = deal_spec.get("meta", {}) if isinstance(deal_spec, dict) else {}
                uploaded_deal_id = uploaded_meta.get("deal_id")
                st.session_state["arranger_uploaded_deal_id"] = uploaded_deal_id

                st.success(f"✅ Loaded deal specification: {uploaded_deal_id or 'Unknown'}")

                # Show basic info
                if 'meta' in deal_spec:
                    meta = deal_spec['meta']
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Deal ID", meta.get('deal_id', 'N/A'))
                    with col2:
                        st.metric("Asset Type", meta.get('asset_type', 'N/A'))
                    with col3:
                        st.metric("Version", meta.get('version', 'N/A'))

                # If the uploaded JSON contains a different deal_id than the input box,
                # guide the user to sync the input. This prevents accidental uploads
                # under the wrong ID.
                if uploaded_deal_id and uploaded_deal_id != deal_id_input:
                    st.warning(
                        "Deal ID mismatch: the uploaded JSON contains "
                        f"`{uploaded_deal_id}`, but the Deal ID field is `{deal_id_input}`. "
                        "Choose one to avoid uploading under the wrong ID."
                    )
                    st.button(
                        "Use uploaded Deal ID",
                        key="arranger_use_uploaded_deal_id",
                        use_container_width=True,
                        on_click=_set_arranger_deal_id,
                        args=(uploaded_deal_id,),
                        help="Sets the Deal ID field to match the uploaded JSON (safe Streamlit callback).",
                    )

            except Exception as e:
                st.error(f"❌ Failed to read JSON file: {e}")

    with editor_tab:
        # Default template
        default_json = {
            "meta": {
                "deal_id": deal_id_input,
                "deal_name": f"{deal_id_input} RMBS Trust",
                "asset_type": "NON_AGENCY_RMBS",
                "version": "1.0",
                "issuer": "Sample Issuer LLC",
                "description": "RMBS securitization trust"
            },
            "currency": "USD",
            "dates": {
                "cutoff_date": "2024-01-01",
                "closing_date": "2024-01-30",
                "first_payment_date": "2024-02-25",
                "maturity_date": "2054-01-01",
                "payment_frequency": "MONTHLY"
            },
            "bonds": [
                {
                    "id": "ClassA",
                    "type": "NOTE",
                    "original_balance": 400000000,
                    "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
                    "priority": {"interest": 1, "principal": 1}
                },
                {
                    "id": "ClassM",
                    "type": "NOTE",
                    "original_balance": 75000000,
                    "coupon": {"kind": "FIXED", "fixed_rate": 0.07},
                    "priority": {"interest": 2, "principal": 2}
                }
            ],
            "waterfalls": {
                "interest": {"steps": []},
                "principal": {"steps": []}
            }
        }

        json_input = st.text_area(
            "Deal JSON Specification",
            json.dumps(deal_spec if deal_spec is not None else default_json, indent=2),
            height=400,
            help="Edit the deal specification as JSON"
        )

        if st.button("🔍 Validate JSON", help="Validate the JSON structure"):
            try:
                parsed_json = json.loads(json_input)
                is_valid, errors = validate_deal_json(parsed_json)

                if is_valid:
                    st.success("✅ Deal specification is valid")
                    deal_spec = parsed_json
                else:
                    st.error("❌ Deal specification has validation errors:")
                    for error in errors:
                        st.write(f"• {error}")

            except json.JSONDecodeError as e:
                st.error(f"❌ Invalid JSON: {e}")

    # Upload button
    if deal_spec or uploaded_file:
        st.markdown("---")

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("📤 Upload Deal", type="primary", use_container_width=True):
                try:
                    with loading_spinner("Uploading deal specification..."):
                        # Ensure deal_id is set
                        if 'meta' not in deal_spec:
                            deal_spec['meta'] = {}
                        deal_spec['meta']['deal_id'] = deal_id_input

                        result = api_client.upload_deal(deal_id_input, deal_spec)

                        success_message(
                            f"Deal '{deal_id_input}' uploaded successfully! 🎉",
                            celebration=True
                        )

                        # Note: Form keeps the deal ID for reference

                except Exception as e:
                    error_message(
                        f"Failed to upload deal: {e}",
                        details=str(e),
                        show_retry=True
                    )

        with col2:
            if st.button("🔍 Validate Only", use_container_width=True):
                if deal_spec:
                    is_valid, errors = validate_deal_json(deal_spec)

                    if is_valid:
                        st.success("✅ Deal specification validation passed")
                    else:
                        with st.expander(f"❌ Deal validation failed ({len(errors)} issues)", expanded=True):
                            for error in errors:
                                st.write(f"• {error}")
                else:
                    st.warning("No deal specification to validate")


def render_collateral_upload_section(api_client: APIClient) -> None:
    """Render the collateral data upload section."""
    st.subheader("📊 Collateral Data")

    # Get current deal ID from session or input
    deal_id = st.session_state.get("arranger_deal_id", "")
    if not deal_id:
        deal_id = st.text_input(
            "Deal ID for Collateral",
            placeholder="Enter deal ID to associate collateral with",
            help="Must match an existing deal specification"
        )

    if deal_id:
        st.caption(f"Collateral will be uploaded for deal: **{deal_id}**")

        uploaded_collateral = st.file_uploader(
            "Upload collateral.json",
            type=["json"],
            help="Upload collateral pool characteristics"
        )

        if uploaded_collateral is not None:
            try:
                collateral_data = json.load(uploaded_collateral)

                # Show summary
                st.success("✅ Collateral data loaded")
                if 'summary_statistics' in collateral_data:
                    stats = collateral_data['summary_statistics']
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("WAC", f"{stats.get('wac', 0):.2%}")
                    with col2:
                        st.metric("WAM", f"{stats.get('wam', 0):.0f} mo")
                    with col3:
                        st.metric("FICO", f"{stats.get('avg_fico', 0):.0f}")
                    with col4:
                        st.metric("Balance", f"${collateral_data.get('current_balance', 0):,.0f}")

                # Upload button
                if st.button("📤 Upload Collateral", type="primary"):
                    try:
                        with loading_spinner("Uploading collateral data..."):
                            result = api_client.upload_collateral(deal_id, collateral_data)
                            success_message(
                                f"Collateral for '{deal_id}' uploaded successfully! 📊",
                                celebration=True
                            )

                    except Exception as e:
                        error_message(
                            f"Failed to upload collateral: {e}",
                            details=str(e),
                            show_retry=True
                        )

            except Exception as e:
                st.error(f"❌ Failed to read collateral JSON: {e}")


def render_loan_tape_upload_section(api_client: APIClient) -> None:
    """Render the origination loan tape upload section."""
    st.subheader("📋 Origination Loan Tape")

    # Get current deal ID from session or input
    deal_id = st.session_state.get("arranger_deal_id", "")
    if not deal_id:
        deal_id = st.text_input(
            "Deal ID for Loan Tape",
            placeholder="Enter deal ID to associate loan tape with",
            help="Must match an existing deal specification"
        )

    if deal_id:
        st.caption(f"Loan tape will be uploaded for deal: **{deal_id}**")

        uploaded_loan_tape = st.file_uploader(
            "Upload origination loan tape CSV",
            type=["csv"],
            help="Upload loan-level origination data for ML models"
        )

        if uploaded_loan_tape is not None:
            try:
                # Read and validate CSV
                import pandas as pd
                loan_df = pd.read_csv(uploaded_loan_tape)

                # Validate required columns for ML features
                required_cols = ["LoanId", "OriginalBalance", "CurrentBalance",
                               "NoteRate", "RemainingTermMonths", "FICO", "LTV"]
                missing_cols = [col for col in required_cols if col not in loan_df.columns]

                if missing_cols:
                    st.warning(f"⚠️ Missing required columns: {', '.join(missing_cols)}")
                    st.info("Required columns for ML models: LoanId, OriginalBalance, CurrentBalance, NoteRate, RemainingTermMonths, FICO, LTV")

                    # Show optional but recommended columns
                    recommended_cols = ["FIRST_PAYMENT_DATE", "ORIGINAL_INTEREST_RATE", "State", "PropertyType"]
                    missing_recommended = [col for col in recommended_cols if col not in loan_df.columns]
                    if missing_recommended:
                        st.info(f"💡 Recommended for ML features: {', '.join(missing_recommended)}")
                else:
                    st.success("✅ Loan tape format validated")

                    # Show summary statistics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Loans", len(loan_df))
                    with col2:
                        st.metric("Avg Balance", f"${loan_df['CurrentBalance'].mean():,.0f}")
                    with col3:
                        st.metric("Avg FICO", f"{loan_df['FICO'].mean():.0f}")
                    with col4:
                        st.metric("Avg LTV", f"{loan_df['LTV'].mean():.1%}")

                    # Upload button
                    if st.button("📤 Upload Loan Tape", type="primary"):
                        try:
                            with loading_spinner("Uploading loan tape..."):
                                result = api_client.upload_loan_tape(
                                    deal_id,
                                    uploaded_loan_tape.getvalue(),
                                    uploaded_loan_tape.name
                                )
                                success_message(
                                    f"Loan tape for '{deal_id}' uploaded successfully! 📋",
                                    celebration=True
                                )

                                # Update collateral configuration to reference the loan tape
                                _update_collateral_with_loan_tape(deal_id, api_client)

                        except Exception as e:
                            error_message(
                                f"Failed to upload loan tape: {e}",
                                details=str(e),
                                show_retry=True
                            )

            except Exception as e:
                st.error(f"❌ Failed to read CSV file: {e}")


def _update_collateral_with_loan_tape(deal_id: str, api_client: APIClient) -> None:
    """Update collateral configuration to reference the uploaded loan tape."""
    try:
        # Get current collateral
        collateral_response = api_client.get_collateral(deal_id)
        collateral_data = collateral_response.get("collateral", {})

        # Ensure loan_data section exists
        if "loan_data" not in collateral_data:
            collateral_data["loan_data"] = {}

        if "schema_ref" not in collateral_data["loan_data"]:
            collateral_data["loan_data"]["schema_ref"] = {}

        # Update the source_uri to point to the uploaded loan tape
        loan_tape_path = f"datasets/{deal_id}/loan_tape.csv"
        collateral_data["loan_data"]["schema_ref"]["source_uri"] = loan_tape_path

        # Re-upload the updated collateral
        api_client.upload_collateral(deal_id, collateral_data)
        st.info("✅ Collateral configuration updated to reference the uploaded loan tape.")

    except Exception as e:
        st.info("ℹ️ Loan tape uploaded successfully. Upload collateral data to enable ML models.")


def render_deal_management_section(api_client: APIClient) -> None:
    """Render the deal management and viewing section."""
    st.subheader("📋 Deal Management")

    # Refresh button and deals list
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Refresh", help="Refresh deal list"):
            _rerun()

    # Get deals
    deals = api_client.get_deals()

    if not deals:
        st.info("No deals available yet. Upload a deal specification to get started.")
        return

    st.success(f"Found {len(deals)} deal(s)")

    # Deals table
    deal_rows = []
    for deal in deals:
        deal_rows.append({
            "Deal ID": deal.get("deal_id", "N/A"),
            "Name": deal.get("deal_name", "N/A"),
            "Asset Type": deal.get("asset_type", "N/A"),
            "Has Collateral": "✅" if deal.get("has_collateral") else "❌",
            "Latest Period": deal.get("latest_period", "N/A")
        })

    if deal_rows:
        formatters = {
            "Deal ID": lambda x: f"`{x}`"  # Code formatting for IDs
        }
        data_table(
            pd.DataFrame(deal_rows),
            "Available Deals",
            formatters=formatters,
            downloadable=True
        )

    # Individual deal details
    st.markdown("---")
    st.subheader("📄 Deal Details")

    selected_deal_id = st.selectbox(
        "Select Deal to View",
        options=[d.get("deal_id") for d in deals],
        help="Choose a deal to view detailed information"
    )

    if selected_deal_id:
        selected_deal = next((d for d in deals if d.get("deal_id") == selected_deal_id), None)

        if selected_deal:
            # Deal overview
            meta = selected_deal.get("meta", {})

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Deal ID", selected_deal_id)
                st.metric("Asset Type", meta.get("asset_type", "N/A"))
            with col2:
                st.metric("Issuer", meta.get("issuer", "N/A"))
                st.metric("Version", meta.get("version", "N/A"))
            with col3:
                collateral_status = "✅ Available" if selected_deal.get("has_collateral") else "❌ Missing"
                st.metric("Collateral", collateral_status)

            # Version history
            st.markdown("---")
            if st.button(f"📚 View Version History for {selected_deal_id}"):
                try:
                    versions = api_client.get_versions(f"/deals/{selected_deal_id}/versions")
                    if versions:
                        version_df = pd.DataFrame(versions)
                        data_table(version_df, f"Version History - {selected_deal_id}")
                    else:
                        st.info("No version history available")
                except Exception as e:
                    st.error(f"Failed to load version history: {e}")

            # Reset Deal Data Section
            st.markdown("---")
            st.subheader("🔄 Reset Deal Data (Testing)")
            
            with st.expander("⚠️ Reset Options - USE WITH CAUTION", expanded=False):
                st.warning("**This will permanently delete data for this deal. Use only for testing purposes!**")
                
                st.info("💡 **Tip**: For a complete fresh start, keep all checkboxes checked including 'Performance Data'. "
                        "Otherwise, period numbers will continue from where the old data left off.")
                
                st.markdown("**Select data to reset:**")
                
                col1, col2 = st.columns(2)
                with col1:
                    reset_token_holders = st.checkbox(
                        "🎫 Token Holdings",
                        value=True,
                        help="Clear all token holder records for this deal",
                        key=f"reset_tokens_{selected_deal_id}"
                    )
                    reset_distributions = st.checkbox(
                        "📊 Distribution Cycles",
                        value=True,
                        help="Clear all distribution period records",
                        key=f"reset_dist_{selected_deal_id}"
                    )
                    reset_yield_distributions = st.checkbox(
                        "💰 Yield Distributions",
                        value=True,
                        help="Clear all yield distribution records",
                        key=f"reset_yields_{selected_deal_id}"
                    )
                
                with col2:
                    reset_performance = st.checkbox(
                        "📈 Performance Data",
                        value=True,  # ON by default for full reset
                        help="Clear all servicer performance data (recommended for fresh start)",
                        key=f"reset_perf_{selected_deal_id}"
                    )
                    reset_nft_records = st.checkbox(
                        "🎨 NFT Records",
                        value=False,
                        help="Clear loan NFT records and mappings",
                        key=f"reset_nft_{selected_deal_id}"
                    )
                    reset_tranche_registry = st.checkbox(
                        "📜 Tranche Registry",
                        value=False,
                        help="Clear deployed tranche contract addresses",
                        key=f"reset_tranche_{selected_deal_id}"
                    )
                
                st.markdown("---")
                
                # Confirmation
                confirm_text = st.text_input(
                    f"Type **{selected_deal_id}** to confirm reset:",
                    key=f"reset_confirm_{selected_deal_id}",
                    help="This prevents accidental data deletion"
                )
                
                reset_disabled = confirm_text != selected_deal_id
                
                if st.button(
                    "🗑️ Reset Deal Data",
                    type="primary",
                    disabled=reset_disabled,
                    use_container_width=True,
                    key=f"reset_btn_{selected_deal_id}"
                ):
                    try:
                        with loading_spinner(f"Resetting data for {selected_deal_id}..."):
                            result = api_client.reset_deal_data(
                                deal_id=selected_deal_id,
                                reset_token_holders=reset_token_holders,
                                reset_distributions=reset_distributions,
                                reset_yield_distributions=reset_yield_distributions,
                                reset_performance=reset_performance,
                                reset_nft_records=reset_nft_records,
                                reset_tranche_registry=reset_tranche_registry,
                            )
                        
                        if result.get("success"):
                            success_message(f"Successfully reset data for {selected_deal_id}! 🔄")
                            
                            # Show actions taken
                            actions = result.get("actions", [])
                            if actions:
                                st.success("**Actions performed:**")
                                for action in actions:
                                    st.write(f"  ✅ {action}")
                        else:
                            st.warning(f"Reset completed with warnings")
                        
                        # Show any warnings
                        warnings = result.get("warnings", [])
                        if warnings:
                            st.warning("**Warnings:**")
                            for warning in warnings:
                                st.write(f"  ⚠️ {warning}")
                        
                    except Exception as e:
                        error_message(f"Failed to reset deal data: {e}")
                
                if reset_disabled and confirm_text:
                    st.error(f"Confirmation text does not match. Please type exactly: {selected_deal_id}")


def render_loan_nft_minting_section(api_client: APIClient) -> None:
    """Render the loan NFT minting section."""
    st.subheader("🎨 Mint Loan NFTs")
    st.caption("Create NFT registry for collateral pool (one NFT per loan)")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal specification first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox(
        "Select Deal",
        deal_ids,
        key="nft_deal",
        help="Choose a deal to mint loan NFTs for"
    )

    if selected_deal:
        # Check if deal has loan tape
        deal_folder = Path("datasets") / selected_deal
        loan_tape_path = deal_folder / "loan_tape.csv"
        
        if loan_tape_path.exists():
            # Read loan tape to show stats
            import pandas as pd
            loan_df = pd.read_csv(loan_tape_path)
            
            st.success(f"✅ Found loan tape with {len(loan_df)} loans")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Loans", len(loan_df))
            with col2:
                st.metric("Total Balance", f"${loan_df['CurrentBalance'].sum():,.0f}")
            with col3:
                st.metric("Avg Balance", f"${loan_df['CurrentBalance'].mean():,.0f}")
            with col4:
                st.metric("Avg FICO", f"{loan_df['FICO'].mean():.0f}")
            
            st.markdown("---")
            
            st.write("**NFT Minting Configuration:**")
            
            col1, col2 = st.columns(2)
            with col1:
                recipient_address = st.text_input(
                    "Recipient Address",
                    value="0x0000000000000000000000000000000000000001",
                    help="Wallet address to receive the minted NFTs (typically issuer or trust SPV)"
                )
            
            with col2:
                loan_nft_contract = st.text_input(
                    "LoanNFT Contract",
                    value="0x0000000000000000000000000000000000000000",
                    help="Address of the deployed LoanNFT contract"
                )

            st.markdown("---")
            
            st.info("💡 **Workflow**: Minting loan NFTs creates an on-chain registry of the collateral pool. Each loan gets a unique NFT with privacy-preserving metadata.")

            if st.button("🎨 Mint Loan NFTs", type="primary", use_container_width=True):
                if recipient_address == "0x0000000000000000000000000000000000000000":
                    st.error("Please enter a valid recipient address")
                    return

                try:
                    with loading_spinner(f"Minting {len(loan_df)} loan NFTs..."):
                        result = api_client.mint_loan_nfts(
                            deal_id=selected_deal,
                            recipient_address=recipient_address,
                            loan_nft_contract=loan_nft_contract
                        )

                        success_message(
                            f"Successfully minted {result['count']} loan NFTs! 🎨",
                            celebration=True
                        )

                        st.info(f"Transaction Hash: `{result['transaction_hash']}`")
                        
                        with st.expander("View Token IDs"):
                            st.write(f"**First 10 Token IDs:**")
                            st.json(result["token_ids"][:10])
                            if result["count"] > 10:
                                st.caption(f"... and {result['count'] - 10} more")

                except Exception as e:
                    error_message(
                        f"Failed to mint loan NFTs: {e}",
                        details=str(e),
                        show_retry=True
                    )
        else:
            st.warning(f"⚠️ No loan tape found for deal {selected_deal}")
            st.info("📝 Upload a loan tape first using the 'Loan Tape' tab, then return here to mint NFTs.")


def render_arranger_page(api_client: APIClient) -> None:
    """Render the complete arranger deal structuring workbench."""
    st.header("🏗️ Deal Structuring Workbench")
    st.caption("Create, validate, and manage RMBS deal structures")

    # Main interface tabs
    tabs = st.tabs(["📝 Deal Specification", "📋 Loan Tape", "🎨 Mint Loan NFTs", "📊 Collateral Data", "📋 Deal Management"])

    with tabs[0]:
        render_deal_upload_section(api_client)

    with tabs[1]:
        render_loan_tape_upload_section(api_client)

    with tabs[2]:
        render_loan_nft_minting_section(api_client)

    with tabs[3]:
        render_collateral_upload_section(api_client)

    with tabs[4]:
        render_deal_management_section(api_client)

    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Upload deal → loan tape → mint NFTs → collateral summary. NFTs represent your collateral pool on-chain.")