"""
Issuer Page
===========

Token issuance workbench for issuers to deploy tranches and issue tokens.
"""

from ..services.api_client import APIClient
from ..components.status import success_message, error_message, loading_spinner
from ..components.data_display import data_table
from ..utils.formatting import format_currency
import streamlit as st
import json


def render_tranche_deployment_section(api_client: APIClient) -> None:
    """Render the tranche deployment section."""
    st.subheader("🚀 Deploy Tranche Contracts")
    st.caption("Deploy ERC-1400 security token contracts for each tranche (required before issuing tokens)")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="deploy_deal", help="Choose a deal to deploy tranches for")

    if selected_deal:
        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            bonds = deal_spec.get("bonds", [])

            if not bonds:
                st.warning(f"Deal {selected_deal} has no tranches defined.")
                return

            # Check if already deployed
            try:
                registry_response = api_client.get_tranche_registry(selected_deal)
                existing_tranches = registry_response.get("tranches", {})
            except:
                existing_tranches = {}

            if existing_tranches:
                st.success(f"✅ Tranches already deployed for {selected_deal}")
                st.write("**Deployed Tranche Contracts:**")
                tranche_data = []
                for tranche_id, address in existing_tranches.items():
                    tranche_data.append({
                        "Tranche": tranche_id,
                        "Contract Address": address[:20] + "..." if len(address) > 20 else address
                    })
                st.table(tranche_data)
                st.info("💡 You can now proceed to issue tokens in the 'Issue Tokens' tab.")
                return

            # Show tranches to deploy
            st.write("**Tranches to Deploy:**")
            tranche_data = []
            total_face_value = 0
            for bond in bonds:
                balance = bond.get("original_balance", 0)
                total_face_value += balance
                coupon = bond.get("coupon", {})
                coupon_kind = coupon.get("kind", "FIXED")
                if coupon_kind == "FIXED":
                    coupon_display = f"{coupon.get('fixed_rate', 0) * 100:.2f}%"
                elif coupon_kind == "FLOAT":
                    coupon_display = f"{coupon.get('index', 'SOFR')} + {coupon.get('margin', 0) * 100:.2f}%"
                elif coupon_kind == "VARIABLE":
                    coupon_display = f"Variable ({coupon.get('variable_cap', 'NetWAC')})"
                elif coupon_kind == "WAC":
                    coupon_display = "WAC"
                else:
                    coupon_display = coupon_kind
                tranche_data.append({
                    "Tranche": bond.get("id"),
                    "Original Balance": format_currency(balance),
                    "Coupon": coupon_display,
                    "Priority": bond.get("priority", {}).get("interest", "N/A")
                })
            
            st.table(tranche_data)
            st.metric("Total Face Value", format_currency(total_face_value))

            st.markdown("---")

            # Configuration
            col1, col2 = st.columns(2)
            with col1:
                payment_token = st.text_input(
                    "Payment Token Address",
                    value="0x0000000000000000000000000000000000000000",
                    help="Address of the payment token (e.g., USDC)"
                )
            with col2:
                admin_address = st.text_input(
                    "Admin/Issuer Address",
                    value="0x0000000000000000000000000000000000000001",
                    help="Address that will control the tranche contracts"
                )

            if st.button("🚀 Deploy Tranche Contracts", type="primary", use_container_width=True):
                try:
                    with loading_spinner(f"Deploying {len(bonds)} tranche contracts..."):
                        result = api_client.deploy_tranches(
                            deal_id=selected_deal,
                            payment_token=payment_token,
                            admin=admin_address
                        )

                        success_message(
                            f"Deployed {result['count']} tranche contracts! 🚀",
                            celebration=True
                        )

                        st.write("**Deployed Contracts:**")
                        for tranche_id, address in result.get("tranches", {}).items():
                            st.code(f"{tranche_id}: {address}")

                except Exception as e:
                    error_message(
                        f"Failed to deploy tranches: {e}",
                        details=str(e),
                        show_retry=True
                    )

        except Exception as e:
            st.error(f"Failed to load deal: {e}")


def render_tranche_token_issuance_section(api_client: APIClient) -> None:
    """Render the tranche token issuance section."""
    st.subheader("💎 Issue Tranche Tokens")
    st.caption("Mint and distribute tranche tokens to investors")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="tranche_deal", help="Choose a deal to issue tranche tokens for")

    if selected_deal:
        # Check if tranches are deployed
        try:
            registry_response = api_client.get_tranche_registry(selected_deal)
            deployed_tranches = registry_response.get("tranches", {})
        except:
            deployed_tranches = {}

        if not deployed_tranches:
            st.warning(f"⚠️ No tranches deployed for {selected_deal}. Deploy tranches first in the 'Deploy Tranches' tab.")
            return

        # Get deal spec to show available tranches
        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            bonds = deal_spec.get("bonds", [])

            if not bonds:
                st.warning(f"Deal {selected_deal} has no tranches defined.")
                return

            # Show tranche selector
            tranche_options = [bond.get("id") for bond in bonds]
            selected_tranche = st.selectbox("Select Tranche", tranche_options, help="Choose a tranche to issue tokens for")

            if selected_tranche:
                # Find the selected bond
                selected_bond = next((b for b in bonds if b.get("id") == selected_tranche), None)
                
                if selected_bond:
                    # Show tranche details
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Original Balance", format_currency(selected_bond.get("original_balance", 0)))
                    with col2:
                        coupon = selected_bond.get("coupon", {})
                        coupon_kind = coupon.get("kind", "FIXED")
                        if coupon_kind == "FIXED":
                            coupon_display = f"{coupon.get('fixed_rate', 0) * 100:.2f}%"
                        elif coupon_kind == "FLOAT":
                            index = coupon.get("index", "SOFR")
                            margin = coupon.get("margin", 0) * 100
                            coupon_display = f"{index} + {margin:.2f}%"
                        elif coupon_kind == "VARIABLE":
                            cap = coupon.get("variable_cap", "NetWAC")
                            coupon_display = f"Variable ({cap})"
                        elif coupon_kind == "WAC":
                            coupon_display = "WAC"
                        else:
                            coupon_display = coupon_kind
                        st.metric("Coupon", coupon_display)
                    with col3:
                        st.metric("Priority", selected_bond.get("priority", {}).get("interest", "N/A"))

                    st.markdown("---")

                    # Token holder configuration
                    st.write("**Token Distribution**")
                    
                    num_holders = st.number_input(
                        "Number of Token Holders",
                        min_value=1,
                        max_value=100,
                        value=1,
                        help="Number of investors receiving tokens"
                    )

                    token_holders = []
                    token_amounts = []

                    for i in range(int(num_holders)):
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            holder = st.text_input(
                                f"Holder {i+1} Address",
                                value=f"0x{'0'*39}{i+1}",
                                key=f"holder_{selected_deal}_{selected_tranche}_{i}"
                            )
                            token_holders.append(holder)
                        with col2:
                            amount = st.number_input(
                                f"Amount",
                                min_value=0,
                                value=int(selected_bond.get("original_balance", 0)) if i == 0 else 0,
                                key=f"amount_{selected_deal}_{selected_tranche}_{i}",
                                help="Token amount (face value)"
                            )
                            token_amounts.append(amount)

                    total_to_issue = sum(token_amounts)
                    original_balance = selected_bond.get("original_balance", 0)
                    
                    if total_to_issue != original_balance:
                        st.warning(f"⚠️ Total to issue ({format_currency(total_to_issue)}) does not match original balance ({format_currency(original_balance)})")

                    st.markdown("---")

                    if st.button("💎 Issue Tranche Tokens", type="primary", use_container_width=True):
                        try:
                            with loading_spinner("Issuing tranche tokens..."):
                                result = api_client.issue_tranche_tokens(
                                    deal_id=selected_deal,
                                    tranche_id=selected_tranche,
                                    token_holders=token_holders,
                                    token_amounts=token_amounts
                                )

                                success_message(
                                    f"Issued {format_currency(total_to_issue)} of tranche {selected_tranche} tokens! 💎",
                                    celebration=True
                                )

                                st.info(f"Transaction Hash: `{result['transaction_hash']}`")

                        except Exception as e:
                            error_message(
                                f"Failed to issue tranche tokens: {e}",
                                details=str(e),
                                show_retry=True
                            )

        except Exception as e:
            st.error(f"Failed to load deal: {e}")


def render_batch_issuance_section(api_client: APIClient) -> None:
    """Render the batch issuance section for all tranches."""
    st.subheader("🎯 Batch Issue All Tranches")
    st.caption("Issue tokens for all tranches at once (deal closing)")

    # Get available deals
    deals = api_client.get_deals()
    if not deals:
        st.info("No deals available. Upload a deal as Arranger first.")
        return

    deal_ids = [d.get("deal_id") for d in deals]
    selected_deal = st.selectbox("Select Deal", deal_ids, key="batch_deal", help="Choose a deal to issue all tranches for")

    if selected_deal:
        # Check if tranches are deployed
        try:
            registry_response = api_client.get_tranche_registry(selected_deal)
            deployed_tranches = registry_response.get("tranches", {})
        except:
            deployed_tranches = {}

        if not deployed_tranches:
            st.warning(f"⚠️ No tranches deployed for {selected_deal}. Deploy tranches first in the 'Deploy Tranches' tab.")
            return

        try:
            deal_response = api_client.get_deal(selected_deal)
            deal_spec = deal_response.get("spec", {})
            bonds = deal_spec.get("bonds", [])

            if not bonds:
                st.warning(f"Deal {selected_deal} has no tranches defined.")
                return

            # Show summary of all tranches
            st.write("**Tranches to Issue:**")
            tranche_data = []
            for bond in bonds:
                coupon = bond.get("coupon", {})
                coupon_kind = coupon.get("kind", "FIXED")
                if coupon_kind == "FIXED":
                    coupon_display = f"{coupon.get('fixed_rate', 0) * 100:.2f}%"
                elif coupon_kind == "FLOAT":
                    coupon_display = f"{coupon.get('index', 'SOFR')} + {coupon.get('margin', 0) * 100:.2f}%"
                elif coupon_kind == "VARIABLE":
                    coupon_display = f"Variable ({coupon.get('variable_cap', 'NetWAC')})"
                elif coupon_kind == "WAC":
                    coupon_display = "WAC"
                else:
                    coupon_display = coupon_kind
                tranche_data.append({
                    "Tranche": bond.get("id"),
                    "Original Balance": format_currency(bond.get("original_balance", 0)),
                    "Coupon": coupon_display,
                    "Priority": bond.get("priority", {}).get("interest", "N/A")
                })
            
            st.table(tranche_data)

            st.markdown("---")

            # Primary holder configuration
            primary_holder = st.text_input(
                "Primary Token Holder",
                value="0x0000000000000000000000000000000000000001",
                help="Address to receive all tranche tokens (can be distributed later)"
            )

            if st.button("🚀 Issue All Tranches", type="primary", use_container_width=True):
                try:
                    with loading_spinner("Issuing all tranche tokens..."):
                        result = api_client.issue_all_tranche_tokens(
                            deal_id=selected_deal,
                            token_holders=[primary_holder]
                        )

                        success_message(
                            f"Issued tokens for {result['count']} tranches! 🚀",
                            celebration=True
                        )

                        st.json({
                            "transactions": result["transactions"],
                            "count": result["count"]
                        })

                except Exception as e:
                    error_message(
                        f"Failed to issue tranche tokens: {e}",
                        details=str(e),
                        show_retry=True
                    )

        except Exception as e:
            st.error(f"Failed to load deal: {e}")


def render_issuer_page(api_client: APIClient) -> None:
    """Render the complete issuer token issuance workbench."""
    st.header("💎 Token Issuance Workbench")
    st.caption("Deploy tranche contracts and issue security tokens to investors")

    # Info banner
    st.info("""ℹ️ **Issuer Workflow**:
1. **Deploy Tranches** - Deploy ERC-1400 contracts for each tranche (one-time)
2. **Issue Tokens** - Mint and distribute tokens to investors
    
*Loan NFTs are minted by the Arranger during collateral pool formation.*""")

    # Main interface tabs
    tabs = st.tabs(["🚀 Deploy Tranches", "💎 Issue Tokens", "🎯 Batch Issuance"])

    with tabs[0]:
        render_tranche_deployment_section(api_client)

    with tabs[1]:
        render_tranche_token_issuance_section(api_client)

    with tabs[2]:
        render_batch_issuance_section(api_client)

    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Deploy tranches first, then issue tokens. Verify allocations match deal structure before batch issuance.")
