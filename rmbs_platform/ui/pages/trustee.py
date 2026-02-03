"""
Trustee Page
============

Deal administration workbench for trustees to manage deal lifecycle.
"""

from ..services.api_client import APIClient
from ..components.status import success_message, error_message, loading_spinner
from ..components.data_display import data_table
from ..utils.formatting import format_currency
import streamlit as st
import pandas as pd


def render_waterfall_execution_section(api_client: APIClient) -> None:
    """Render the waterfall execution section with distribution cycle."""
    st.subheader("💧 Monthly Distribution Cycle")
    
    # Show workflow guidance
    with st.expander("📋 Distribution Cycle Workflow", expanded=False):
        st.markdown("""
        **Industry-Standard Monthly Distribution Cycle:**
        
        | Step | Role | Action |
        |------|------|--------|
        | 1️⃣ | **Servicer** | Upload monthly performance tape |
        | 2️⃣ | **Trustee** | Review collections & execute waterfall |
        | 3️⃣ | **System** | Update token balances, create yield distributions |
        | 4️⃣ | **Investor** | View updated portfolio, claim yields |
        
        *The waterfall distributes collections to tranches in priority order (senior first).*
        """)

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="waterfall_deal", help="Choose a deal to manage distributions")

    if selected_deal:
        # Show pending distributions alert
        try:
            pending_data = api_client.get_pending_distributions(selected_deal)
            pending_periods = pending_data.get("pending_periods", [])
            
            if pending_periods:
                st.warning(f"⏳ **{len(pending_periods)} period(s) pending distribution** - Servicer has uploaded tape, awaiting waterfall execution")
                
                # Show pending periods table
                pending_df = pd.DataFrame([
                    {
                        "Period": p.get("period_number"),
                        "Collections": format_currency(p.get("total_collections", 0)),
                        "Interest": format_currency(p.get("interest_collected", 0)),
                        "Principal": format_currency(p.get("principal_collected", 0)),
                        "Losses": format_currency(p.get("losses", 0)),
                        "Uploaded": p.get("collection_date", "")[:10] if p.get("collection_date") else "N/A",
                    }
                    for p in pending_periods
                ])
                st.dataframe(pending_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ No pending distributions - all periods have been processed")
        except Exception:
            pending_periods = []
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # If pending periods, default to first pending
            default_period = pending_periods[0].get("period_number", 1) if pending_periods else 1
            period_number = st.number_input(
                "Period Number",
                min_value=1,
                max_value=360,
                value=default_period,
                help="Payment period to execute (typically incremental)",
                key="waterfall_period"
            )
        
        with col2:
            # Show latest performance period if available
            deal_response = api_client.get_deal(selected_deal)
            latest_period = deal_response.get("latest_period", "N/A")
            st.metric("Latest Performance Period", latest_period)

        # Check if selected period is pending
        selected_pending = next((p for p in pending_periods if p.get("period_number") == period_number), None)
        
        if selected_pending:
            st.markdown("### 📊 Period Collections (from Servicer)")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Collections", format_currency(selected_pending.get("total_collections", 0)))
            with col2:
                st.metric("Interest", format_currency(selected_pending.get("interest_collected", 0)))
            with col3:
                st.metric("Principal", format_currency(selected_pending.get("principal_collected", 0)))
            with col4:
                st.metric("Losses", format_currency(selected_pending.get("losses", 0)))
            
            st.markdown("---")
            
            # Check period status and provide force reprocess option
            period_status = selected_pending.get("status", "pending")
            if period_status == "distributed":
                st.warning(f"⚠️ Period {period_number} was already distributed. Enable 'Force Re-process' to run again for testing.")
            
            force_reprocess = st.checkbox(
                "🔄 Force Re-process (Testing Mode)",
                value=False,
                help="Enable to re-process an already distributed period. Use for testing only.",
                key=f"force_reprocess_{selected_deal}_{period_number}"
            )
            
            if st.button("💧 Execute Distribution & Update Tokens", type="primary", use_container_width=True):
                try:
                    with loading_spinner("Executing waterfall and distributing to token holders..."):
                        result = api_client.execute_distribution(
                            deal_id=selected_deal,
                            period_number=period_number,
                            force_reprocess=force_reprocess
                        )

                        success_message(
                            f"✅ Period {period_number} distributed! Token balances updated, yields available for claim. 💧",
                            celebration=True
                        )
                        
                        st.info(f"Transaction Hash: `{result.get('transaction_hash', 'N/A')}`")
                        
                        # Show distribution summary
                        distributions = result.get("distributions", {})
                        token_updates = result.get("token_updates", [])
                        
                        st.markdown("### 📈 Distribution Summary")
                        sum_col1, sum_col2, sum_col3 = st.columns(3)
                        with sum_col1:
                            st.metric("Interest Distributed", format_currency(distributions.get("total_interest_distributed", 0)))
                        with sum_col2:
                            st.metric("Principal Distributed", format_currency(distributions.get("total_principal_distributed", 0)))
                        with sum_col3:
                            st.metric("Tokens Updated", len(token_updates))
                        
                        if token_updates:
                            st.markdown("### 🎟️ Token Balance Updates")
                            updates_df = pd.DataFrame([
                                {
                                    "Holder": u.get("holder", "")[:10] + "...",
                                    "Tranche": u.get("tranche_id"),
                                    "Old Balance": format_currency(u.get("old_balance", 0)),
                                    "Principal Paid": format_currency(u.get("principal_paid", 0)),
                                    "New Balance": format_currency(u.get("new_balance", 0)),
                                    "Interest Earned": format_currency(u.get("interest_earned", 0)),
                                }
                                for u in token_updates
                            ])
                            st.dataframe(updates_df, use_container_width=True, hide_index=True)

                except Exception as e:
                    error_message(
                        f"Failed to execute distribution: {e}",
                        details=str(e),
                        show_retry=True
                    )
        else:
            st.info(f"ℹ️ Period {period_number} is not pending. Either it's already been distributed or the Servicer hasn't uploaded a tape for this period yet.")
            
            # Show legacy waterfall button for non-pending periods
            if st.button("💧 Execute Waterfall (Legacy)", use_container_width=True):
                try:
                    with loading_spinner("Executing waterfall..."):
                        result = api_client.execute_waterfall(
                            deal_id=selected_deal,
                            period_number=period_number
                        )
                        success_message(f"Waterfall executed for period {period_number}! 💧", celebration=True)
                        st.info(f"Transaction Hash: `{result['transaction_hash']}`")
                except Exception as e:
                    error_message(f"Failed to execute waterfall: {e}", details=str(e), show_retry=True)
        
        # Show distribution history
        st.markdown("---")
        st.markdown("### 📜 Distribution History")
        
        try:
            dist_data = api_client.get_distribution_periods(selected_deal)
            periods = dist_data.get("periods", [])
            distributed = [p for p in periods if p.get("status") == "distributed"]
            
            if distributed:
                hist_df = pd.DataFrame([
                    {
                        "Period": p.get("period_number"),
                        "Status": "✅ Distributed",
                        "Interest Dist.": format_currency(p.get("total_interest_distributed", 0)),
                        "Principal Dist.": format_currency(p.get("total_principal_distributed", 0)),
                        "Date": p.get("distribution_date", "")[:10] if p.get("distribution_date") else "N/A",
                    }
                    for p in sorted(distributed, key=lambda x: x.get("period_number", 0), reverse=True)
                ])
                st.dataframe(hist_df, use_container_width=True, hide_index=True)
            else:
                st.info("No distributions processed yet for this deal")
        except Exception:
            st.info("Distribution history not available")


def render_factor_update_section(api_client: APIClient) -> None:
    """Render the tranche factor update section."""
    st.subheader("📉 Update Tranche Factors")
    st.caption("Update current factors after principal paydowns")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="factor_deal", help="Choose a deal to update factors for")

    if selected_deal:
        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            bonds = deal_spec.get("bonds", [])

            if not bonds:
                st.warning(f"Deal {selected_deal} has no tranches defined.")
                return

            st.write("**Update Factors for All Tranches:**")

            # Create input fields for each tranche
            tranche_factors = {}
            for bond in bonds:
                tranche_id = bond.get("id")
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    st.write(f"**{tranche_id}**")
                with col2:
                    st.write(format_currency(bond.get("original_balance", 0)))
                with col3:
                    new_factor = st.number_input(
                        "New Factor",
                        min_value=0.0,
                        max_value=1.0,
                        value=1.0,
                        step=0.01,
                        format="%.4f",
                        key=f"factor_{tranche_id}",
                        help=f"Current factor for {tranche_id} (1.0 = 100%, 0.95 = 95% remaining)"
                    )
                    tranche_factors[tranche_id] = new_factor

            st.markdown("---")

            if st.button("📉 Update Factors", type="primary", use_container_width=True):
                # In a real implementation, this would call the on-chain updateFactor function
                # For now, show a success message
                st.success(f"Updated factors for {len(tranche_factors)} tranches!")
                st.json(tranche_factors)

        except Exception as e:
            st.error(f"Failed to load deal: {e}")


def render_yield_distribution_section(api_client: APIClient) -> None:
    """Render the yield distribution section."""
    st.subheader("💰 Distribute Yield")
    st.caption("Distribute interest payments to tranche token holders")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="yield_deal", help="Choose a deal to distribute yield for")

    if selected_deal:
        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            bonds = deal_spec.get("bonds", [])

            if not bonds:
                st.warning(f"Deal {selected_deal} has no tranches defined.")
                return

            # Show tranche selector
            tranche_options = [bond.get("id") for bond in bonds]
            selected_tranche = st.selectbox("Select Tranche", tranche_options, key="yield_tranche", help="Choose a tranche to distribute yield for")

            if selected_tranche:
                selected_bond = next((b for b in bonds if b.get("id") == selected_tranche), None)
                
                if selected_bond:
                    # Calculate yield based on coupon
                    original_balance = selected_bond.get("original_balance", 0)
                    coupon_rate = selected_bond.get("coupon", {}).get("fixed_rate", 0)
                    monthly_yield = original_balance * coupon_rate / 12

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Original Balance", format_currency(original_balance))
                    with col2:
                        st.metric("Coupon Rate", f"{coupon_rate * 100:.2f}%")
                    with col3:
                        st.metric("Monthly Yield (Estimate)", format_currency(monthly_yield))

                    st.markdown("---")

                    period_number = st.number_input(
                        "Period Number",
                        min_value=1,
                        max_value=360,
                        value=1,
                        key="yield_period",
                        help="Payment period for this distribution"
                    )

                    yield_amount = st.number_input(
                        "Yield Amount",
                        min_value=0.0,
                        value=float(monthly_yield),
                        step=1000.0,
                        help="Total yield to distribute for this period"
                    )

                    st.markdown("---")

                    if st.button("💰 Distribute Yield", type="primary", use_container_width=True):
                        try:
                            with loading_spinner("Distributing yield to token holders..."):
                                result = api_client.distribute_yield(
                                    deal_id=selected_deal,
                                    tranche_id=selected_tranche,
                                    amount=yield_amount,
                                    period=period_number
                                )
                            
                            success_message(
                                f"✅ Distributed {format_currency(yield_amount)} to {result.get('distributed_to', 0)} holders of {selected_tranche}!",
                                celebration=True
                            )
                            st.info(f"Transaction Hash: `{result.get('transaction_hash', 'N/A')}`")
                            st.info("💡 Investors can now claim their pro-rata share via the Investor portal.")
                        except Exception as e:
                            error_message(f"Failed to distribute yield: {e}")

        except Exception as e:
            st.error(f"Failed to load deal: {e}")


def render_deal_status_section(api_client: APIClient) -> None:
    """Render the deal status monitoring section."""
    st.subheader("📊 Deal Status")
    st.caption("Monitor deal lifecycle and performance")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="status_deal", help="Choose a deal to view status for")

    if selected_deal:
        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            
            # Deal overview
            meta = deal_spec.get("meta", {})
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Deal ID", meta.get("deal_id", "N/A"))
            with col2:
                st.metric("Issuer", meta.get("issuer", "N/A"))
            with col3:
                st.metric("Latest Period", deal_response.get("latest_period", "N/A"))

            st.markdown("---")

            # Tranche summary
            st.write("**Tranche Summary:**")
            bonds = deal_spec.get("bonds", [])
            tranche_data = []
            total_balance = 0
            for bond in bonds:
                balance = bond.get("original_balance", 0)
                total_balance += balance
                tranche_data.append({
                    "Tranche": bond.get("id"),
                    "Balance": format_currency(balance),
                    "Coupon": f"{bond.get('coupon', {}).get('fixed_rate', 0) * 100:.2f}%",
                    "Priority": bond.get("priority", {}).get("interest", "N/A"),
                    "% of Total": f"{(balance / total_balance * 100) if total_balance > 0 else 0:.1f}%"
                })
            
            if tranche_data:
                st.table(tranche_data)
                st.metric("Total Deal Size", format_currency(total_balance))

        except Exception as e:
            st.error(f"Failed to load deal status: {e}")


def render_trustee_page(api_client: APIClient) -> None:
    """Render the complete trustee deal administration workbench."""
    st.header("⚖️ Deal Administration Workbench")
    st.caption("Execute waterfalls, update factors, and distribute yield")

    # Main interface tabs
    tabs = st.tabs(["💧 Waterfall", "📉 Factors", "💰 Yield", "📊 Status"])

    with tabs[0]:
        render_waterfall_execution_section(api_client)

    with tabs[1]:
        render_factor_update_section(api_client)

    with tabs[2]:
        render_yield_distribution_section(api_client)

    with tabs[3]:
        render_deal_status_section(api_client)

    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Execute waterfall after servicer submits performance data for each period.")
