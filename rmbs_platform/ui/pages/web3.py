"""
Web3 Tokenization Page
======================

Enhanced Streamlit page for Web3 tokenization workflows with
modern dashboard design, step-by-step wizards, and comprehensive
contract management.

Features:
- Dashboard with tokenization status and health monitoring
- Step-by-step deal tokenization wizard
- Contract registry with deployment status
- Token distribution management
- Oracle data publishing and waterfall execution
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from ..services.api_client import APIClient, APIError


# =============================================================================
# STYLING & CONSTANTS
# =============================================================================

WORKFLOW_STEPS = [
    {"id": "register", "label": "1. Register Deal", "icon": "📋"},
    {"id": "deploy", "label": "2. Deploy Tranches", "icon": "🏗️"},
    {"id": "mint_loans", "label": "3. Mint Loan NFTs", "icon": "🪙"},
    {"id": "issue", "label": "4. Issue Tokens", "icon": "💎"},
    {"id": "publish", "label": "5. Publish Waterfall", "icon": "🌊"},
]

STATUS_COLORS = {
    "deployed": "#10B981",    # Green
    "pending": "#F59E0B",     # Amber
    "not_started": "#6B7280", # Gray
    "error": "#EF4444",       # Red
    "healthy": "#10B981",     # Green
    "degraded": "#F59E0B",    # Amber
    "offline": "#EF4444",     # Red
}


def _format_address(address: str, truncate: bool = True) -> str:
    """Format Ethereum address with optional truncation."""
    if not address or address == "0x...":
        return "Not Set"
    if truncate and len(address) > 14:
        return f"{address[:8]}...{address[-6:]}"
    return address


def _format_currency(value: float) -> str:
    """Format value as currency."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.1f}K"
    else:
        return f"${value:,.0f}"


def _rerun() -> None:
    """Version-safe Streamlit rerun."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def _get_status_badge(status: str) -> str:
    """Generate HTML badge for status."""
    color = STATUS_COLORS.get(status, "#6B7280")
    return f'<span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{status.upper()}</span>'


# =============================================================================
# DATA LOADING HELPERS
# =============================================================================

def _load_deployment_info(api_client: APIClient) -> Dict[str, Any]:
    """Load deployment information for all deals."""
    deployments = {}
    
    try:
        # Get all deals
        deals = api_client.get_deals()
        
        for deal in deals:
            deal_id = deal.get("deal_id", "")
            if not deal_id:
                continue
            
            deployment = {
                "deal_id": deal_id,
                "deal_name": deal.get("deal_name", deal_id),
                "status": "not_started",
                "tranches_deployed": 0,
                "total_tranches": 0,
                "tranche_addresses": {},
                "tokens_issued": False,
                "waterfall_published": False,
            }
            
            # Get deal spec for tranche count
            try:
                deal_response = api_client.get_deal(deal_id)
                spec = deal_response.get("spec", {})
                bonds = spec.get("bonds", [])
                deployment["total_tranches"] = len(bonds)
                deployment["bonds"] = bonds
            except Exception:
                pass
            
            # Get tranche registry
            try:
                registry = api_client.get_tranche_registry(deal_id)
                tranches = registry.get("tranches", {})
                deployment["tranche_addresses"] = tranches
                deployment["tranches_deployed"] = len(tranches)
                
                if tranches:
                    deployment["status"] = "deployed"
            except Exception:
                pass
            
            deployments[deal_id] = deployment
    
    except Exception as e:
        st.error(f"Failed to load deployments: {e}")
    
    return deployments


def _load_token_holders(api_client: APIClient) -> List[Dict[str, Any]]:
    """Load all token holders."""
    try:
        return api_client.get_token_holders()
    except Exception:
        return []


# =============================================================================
# DASHBOARD TAB
# =============================================================================

def render_dashboard(api_client: APIClient) -> None:
    """Render the main Web3 dashboard with status overview."""
    
    # Header with Web3 Health Check
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("### 🌐 Tokenization Overview")
        st.caption("Monitor deal tokenization status and blockchain health")
    
    with col2:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_dashboard"):
            _rerun()
    
    # Web3 Health Status
    st.markdown("---")
    
    health_col1, health_col2, health_col3, health_col4 = st.columns(4)
    
    try:
        health = api_client.web3_health()
        web3_status = "healthy" if health.get("connected", False) else "offline"
        network = health.get("network", "Unknown")
        block = health.get("block_number", "N/A")
        gas_price = health.get("gas_price_gwei", "N/A")
    except Exception:
        web3_status = "offline"
        network = "Disconnected"
        block = "N/A"
        gas_price = "N/A"
    
    with health_col1:
        status_icon = "🟢" if web3_status == "healthy" else "🔴"
        st.metric("Blockchain Status", f"{status_icon} {web3_status.title()}")
    
    with health_col2:
        st.metric("Network", network)
    
    with health_col3:
        st.metric("Latest Block", str(block))
    
    with health_col4:
        st.metric("Gas Price", f"{gas_price} Gwei" if isinstance(gas_price, (int, float)) else gas_price)
    
    st.markdown("---")
    
    # Load deployment data
    deployments = _load_deployment_info(api_client)
    
    # Summary Cards
    st.markdown("### 📊 Tokenization Summary")
    
    total_deals = len(deployments)
    deployed_deals = sum(1 for d in deployments.values() if d["status"] == "deployed")
    total_tranches_deployed = sum(d["tranches_deployed"] for d in deployments.values())
    
    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    
    with sum_col1:
        st.metric(
            "Total Deals",
            total_deals,
            help="Total number of deals in the platform"
        )
    
    with sum_col2:
        st.metric(
            "Tokenized Deals",
            deployed_deals,
            delta=f"{(deployed_deals / total_deals * 100):.0f}%" if total_deals > 0 else "0%",
            help="Deals with deployed tranche contracts"
        )
    
    with sum_col3:
        st.metric(
            "Deployed Tranches",
            total_tranches_deployed,
            help="Total tranche contracts deployed on-chain"
        )
    
    with sum_col4:
        # Count token holders
        holders = _load_token_holders(api_client)
        active_holders = len([h for h in holders if h.get("holdings")])
        st.metric(
            "Active Investors",
            active_holders,
            help="Investors with token holdings"
        )
    
    st.markdown("---")
    
    # Deal Status Grid
    st.markdown("### 📋 Deal Tokenization Status")
    
    if not deployments:
        st.info("📭 No deals found. Create a deal in the Arranger screen first.")
        return
    
    for deal_id, deployment in deployments.items():
        with st.expander(
            f"{'✅' if deployment['status'] == 'deployed' else '⏳'} {deployment['deal_name']} ({deal_id})",
            expanded=deployment["status"] == "deployed"
        ):
            # Progress indicator
            total_steps = 5
            completed_steps = 0
            if deployment["total_tranches"] > 0:
                completed_steps += 1  # Deal registered
            if deployment["tranches_deployed"] > 0:
                completed_steps += 2  # Tranches deployed
            if deployment.get("tokens_issued"):
                completed_steps += 1  # Tokens issued
            if deployment.get("waterfall_published"):
                completed_steps += 1  # Waterfall published
            
            progress = completed_steps / total_steps
            st.progress(progress, text=f"Tokenization Progress: {completed_steps}/{total_steps} steps")
            
            # Status details
            detail_col1, detail_col2, detail_col3 = st.columns(3)
            
            with detail_col1:
                st.markdown("**Tranche Deployment**")
                st.write(f"Deployed: {deployment['tranches_deployed']} / {deployment['total_tranches']}")
                
                if deployment["tranche_addresses"]:
                    for tranche_id, address in deployment["tranche_addresses"].items():
                        st.code(f"{tranche_id}: {_format_address(address)}", language=None)
            
            with detail_col2:
                st.markdown("**Token Issuance**")
                if deployment.get("tokens_issued"):
                    st.success("✅ Tokens Issued")
                else:
                    st.warning("⏳ Pending")
            
            with detail_col3:
                st.markdown("**Quick Actions**")
                if deployment["status"] != "deployed":
                    if st.button("🚀 Start Tokenization", key=f"start_{deal_id}", use_container_width=True):
                        st.session_state["tokenize_deal_id"] = deal_id
                        st.session_state["active_tab"] = 1  # Switch to Tokenize tab
                        _rerun()
                else:
                    if st.button("📤 Issue Tokens", key=f"issue_{deal_id}", use_container_width=True):
                        st.session_state["issue_deal_id"] = deal_id
                        st.session_state["active_tab"] = 2  # Switch to Issue tab
                        _rerun()


# =============================================================================
# TOKENIZE DEAL TAB
# =============================================================================

def render_tokenize_deal(api_client: APIClient) -> None:
    """Render the deal tokenization wizard."""
    
    st.markdown("### 🏗️ Tokenize Deal")
    st.caption("Step-by-step workflow to deploy smart contracts for a deal")
    
    # Deal selector
    deals = api_client.get_deals()
    
    if not deals:
        st.warning("⚠️ No deals available. Please create a deal first in the Arranger screen.")
        return
    
    deal_options = {f"{d.get('deal_id')} - {d.get('deal_name', 'Unknown')}": d.get("deal_id") for d in deals}
    
    # Pre-select deal if set from dashboard
    default_idx = 0
    if "tokenize_deal_id" in st.session_state:
        target_deal = st.session_state["tokenize_deal_id"]
        for idx, (label, deal_id) in enumerate(deal_options.items()):
            if deal_id == target_deal:
                default_idx = idx
                break
    
    selected_label = st.selectbox(
        "Select Deal to Tokenize",
        options=list(deal_options.keys()),
        index=default_idx,
        key="tokenize_deal_select"
    )
    
    deal_id = deal_options.get(selected_label, "")
    
    if not deal_id:
        return
    
    # Load deal details
    try:
        deal_response = api_client.get_deal(deal_id)
        deal_spec = deal_response.get("spec", {})
        bonds = deal_spec.get("bonds", [])
        parties = deal_spec.get("parties", {})
    except Exception as e:
        st.error(f"Failed to load deal: {e}")
        return
    
    # Check current deployment status
    try:
        registry = api_client.get_tranche_registry(deal_id)
        deployed_tranches = registry.get("tranches", {})
    except Exception:
        deployed_tranches = {}
    
    st.markdown("---")
    
    # Workflow Steps with Status
    st.markdown("#### Tokenization Workflow")
    
    step_cols = st.columns(len(WORKFLOW_STEPS))
    
    for idx, (step, col) in enumerate(zip(WORKFLOW_STEPS, step_cols)):
        with col:
            # Determine step status
            if step["id"] == "register":
                status = "complete" if bonds else "pending"
            elif step["id"] == "deploy":
                status = "complete" if deployed_tranches else "pending"
            elif step["id"] == "issue":
                status = "pending"  # Would check token balances
            else:
                status = "pending"
            
            icon = "✅" if status == "complete" else step["icon"]
            st.markdown(f"**{icon}**")
            st.caption(step["label"])
    
    st.markdown("---")
    
    # Step 1: Deal Info (Read-only from deal spec)
    with st.expander("📋 Step 1: Deal Information", expanded=not deployed_tranches):
        st.markdown("**Deal Details** (from deal specification)")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.write(f"**Deal ID:** {deal_id}")
            st.write(f"**Deal Name:** {deal_spec.get('meta', {}).get('deal_name', 'N/A')}")
            st.write(f"**Asset Type:** {deal_spec.get('meta', {}).get('asset_type', 'N/A')}")
        
        with info_col2:
            dates = deal_spec.get("dates", {})
            st.write(f"**Closing Date:** {dates.get('closing_date', 'N/A')}")
            st.write(f"**Maturity Date:** {dates.get('maturity_date', 'N/A')}")
            st.write(f"**Payment Frequency:** {dates.get('payment_frequency', 'N/A')}")
        
        st.markdown("**Tranches to Deploy:**")
        
        tranche_data = []
        for bond in bonds:
            coupon = bond.get("coupon", {})
            coupon_type = coupon.get("kind", "FIXED")
            if coupon_type == "FIXED":
                rate = f"{coupon.get('fixed_rate', 0) * 100:.2f}%"
            elif coupon_type == "FLOAT":
                rate = f"SOFR + {coupon.get('margin', 0) * 100:.2f}%"
            else:
                rate = "N/A"
            
            deployed_addr = deployed_tranches.get(bond.get("id"), "")
            
            tranche_data.append({
                "Tranche": bond.get("id", ""),
                "Balance": _format_currency(bond.get("original_balance", 0)),
                "Type": coupon_type,
                "Rate": rate,
                "Priority": bond.get("priority", {}).get("interest", 0),
                "Status": "✅ Deployed" if deployed_addr else "⏳ Pending",
                "Contract": _format_address(deployed_addr) if deployed_addr else "—",
            })
        
        import pandas as pd
        st.dataframe(pd.DataFrame(tranche_data), use_container_width=True, hide_index=True)
    
    # Step 2: Deploy Tranche Contracts
    with st.expander("🏗️ Step 2: Deploy Tranche Contracts", expanded=not deployed_tranches):
        
        if deployed_tranches:
            st.success(f"✅ {len(deployed_tranches)} tranche contracts already deployed!")
            
            st.markdown("**Deployed Contracts:**")
            for tranche_id, address in deployed_tranches.items():
                st.code(f"{tranche_id}: {address}", language=None)
            
            if st.button("🔄 Re-deploy All Tranches", type="secondary", key="redeploy_tranches"):
                st.warning("⚠️ Re-deploying will create new contracts. Existing contracts will remain on-chain.")
        else:
            st.info("💡 This will deploy ERC-20 contracts for each tranche on the blockchain.")
        
        st.markdown("**Deployment Configuration:**")
        
        deploy_col1, deploy_col2 = st.columns(2)
        
        with deploy_col1:
            payment_token = st.text_input(
                "Payment Token Address",
                value="0x0000000000000000000000000000000000000000",
                help="Address of USDC/USDT/stablecoin for payments (0x0 for native ETH)",
                key="deploy_payment_token"
            )
            
            admin_address = st.text_input(
                "Admin Address",
                value=parties.get("administrator", {}).get("address", "0x0000000000000000000000000000000000000001"),
                help="Address with admin privileges on the contracts",
                key="deploy_admin"
            )
        
        with deploy_col2:
            trustee_address = st.text_input(
                "Trustee Address",
                value=parties.get("trustee", {}).get("address", "0x0000000000000000000000000000000000000002"),
                help="Trustee address for payment distributions",
                key="deploy_trustee"
            )
            
            servicer_address = st.text_input(
                "Servicer Address",
                value=parties.get("servicer", {}).get("address", "0x0000000000000000000000000000000000000003"),
                help="Servicer address for performance reporting",
                key="deploy_servicer"
            )
        
        if st.button("🚀 Deploy Tranche Contracts", type="primary", use_container_width=True, key="deploy_tranches"):
            with st.spinner("Deploying contracts to blockchain..."):
                try:
                    result = api_client.deploy_tranches(
                        deal_id=deal_id,
                        payment_token=payment_token,
                        admin=admin_address
                    )
                    
                    st.success(f"✅ Successfully deployed {len(result.get('tranches', {}))} tranche contracts!")
                    
                    # Show deployed addresses
                    for tranche_id, address in result.get("tranches", {}).items():
                        st.code(f"{tranche_id}: {address}", language=None)
                    
                    if result.get("tx_hashes"):
                        with st.expander("Transaction Hashes"):
                            for tx_hash in result.get("tx_hashes", []):
                                st.code(tx_hash, language=None)
                    
                    _rerun()
                    
                except APIError as e:
                    st.error(f"❌ Deployment failed: {e}")
    
    # Step 3: Mint Loan NFTs
    with st.expander("🪙 Step 3: Mint Loan NFTs (Optional)", expanded=False):
        
        st.info("💡 Mint NFTs representing individual loans in the collateral pool. This enables loan-level tracking on-chain.")
        
        mint_col1, mint_col2 = st.columns(2)
        
        with mint_col1:
            nft_recipient = st.text_input(
                "NFT Recipient Address",
                value=parties.get("sponsor", {}).get("address", "0x0000000000000000000000000000000000000001"),
                help="Address to receive the loan NFTs (typically the trust or sponsor)",
                key="mint_nft_recipient"
            )
        
        with mint_col2:
            loan_nft_contract = st.text_input(
                "LoanNFT Contract Address",
                value="0x...",
                help="Address of the LoanNFT contract (deploy via Hardhat first)",
                key="mint_nft_contract"
            )
        
        if st.button("🪙 Mint Loan NFTs", type="secondary", use_container_width=True, key="mint_loan_nfts"):
            with st.spinner("Minting loan NFTs..."):
                try:
                    result = api_client.mint_loan_nfts(
                        deal_id=deal_id,
                        recipient_address=nft_recipient,
                        loan_nft_contract=loan_nft_contract
                    )
                    
                    st.success(f"✅ Minted {result.get('loans_minted', 0)} loan NFTs!")
                    
                    if result.get("tx_hash"):
                        st.code(f"Transaction: {result.get('tx_hash')}", language=None)
                    
                except APIError as e:
                    st.error(f"❌ Minting failed: {e}")


# =============================================================================
# ISSUE TOKENS TAB
# =============================================================================

def render_issue_tokens(api_client: APIClient) -> None:
    """Render the token issuance interface."""
    
    st.markdown("### 💎 Issue Tranche Tokens")
    st.caption("Issue tokens to investors for deployed tranches")
    
    # Deal selector
    deals = api_client.get_deals()
    deployed_deals = []
    
    for deal in deals:
        deal_id = deal.get("deal_id", "")
        try:
            registry = api_client.get_tranche_registry(deal_id)
            if registry.get("tranches"):
                deployed_deals.append(deal)
        except Exception:
            pass
    
    if not deployed_deals:
        st.warning("⚠️ No deals have deployed tranche contracts yet. Please deploy tranches first.")
        return
    
    deal_options = {f"{d.get('deal_id')} - {d.get('deal_name', 'Unknown')}": d.get("deal_id") for d in deployed_deals}
    
    # Pre-select deal if set
    default_idx = 0
    if "issue_deal_id" in st.session_state:
        target_deal = st.session_state["issue_deal_id"]
        for idx, (label, deal_id) in enumerate(deal_options.items()):
            if deal_id == target_deal:
                default_idx = idx
                break
    
    selected_label = st.selectbox(
        "Select Deal",
        options=list(deal_options.keys()),
        index=default_idx,
        key="issue_deal_select"
    )
    
    deal_id = deal_options.get(selected_label, "")
    
    if not deal_id:
        return
    
    # Load deal and registry
    try:
        deal_response = api_client.get_deal(deal_id)
        deal_spec = deal_response.get("spec", {})
        bonds = deal_spec.get("bonds", [])
        
        registry = api_client.get_tranche_registry(deal_id)
        deployed_tranches = registry.get("tranches", {})
    except Exception as e:
        st.error(f"Failed to load deal: {e}")
        return
    
    st.markdown("---")
    
    # Issuance Mode Selection
    issuance_mode = st.radio(
        "Issuance Mode",
        options=["🎯 Single Tranche", "📦 All Tranches (Pro-Rata)"],
        horizontal=True,
        key="issuance_mode"
    )
    
    st.markdown("---")
    
    if issuance_mode == "🎯 Single Tranche":
        render_single_tranche_issuance(api_client, deal_id, bonds, deployed_tranches)
    else:
        render_bulk_issuance(api_client, deal_id, bonds, deployed_tranches)


def render_single_tranche_issuance(
    api_client: APIClient,
    deal_id: str,
    bonds: List[Dict],
    deployed_tranches: Dict[str, str]
) -> None:
    """Render single tranche token issuance form."""
    
    # Tranche selector
    tranche_options = [b.get("id") for b in bonds if b.get("id") in deployed_tranches]
    
    if not tranche_options:
        st.warning("No deployed tranches available for issuance.")
        return
    
    selected_tranche = st.selectbox(
        "Select Tranche",
        options=tranche_options,
        key="single_tranche_select"
    )
    
    # Get tranche details
    tranche_bond = next((b for b in bonds if b.get("id") == selected_tranche), {})
    original_balance = tranche_bond.get("original_balance", 0)
    
    st.info(f"💰 {selected_tranche} Original Balance: {_format_currency(original_balance)}")
    
    # Investor inputs
    st.markdown("**Investor Allocations:**")
    
    num_investors = st.number_input(
        "Number of Investors",
        min_value=1,
        max_value=10,
        value=1,
        key="num_investors_single"
    )
    
    investors = []
    
    for i in range(int(num_investors)):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            address = st.text_input(
                f"Investor {i+1} Address",
                value=f"0x{'0' * 39}{i+1}",
                key=f"investor_addr_{i}"
            )
        
        with col2:
            amount = st.number_input(
                f"Amount",
                min_value=0.0,
                max_value=float(original_balance),
                value=float(original_balance / num_investors),
                format="%.2f",
                key=f"investor_amount_{i}"
            )
        
        investors.append({"address": address, "amount": amount})
    
    # Validate total
    total_allocated = sum(inv["amount"] for inv in investors)
    
    if total_allocated > original_balance:
        st.error(f"❌ Total allocation ({_format_currency(total_allocated)}) exceeds tranche balance ({_format_currency(original_balance)})")
    elif total_allocated < original_balance:
        st.warning(f"⚠️ {_format_currency(original_balance - total_allocated)} remaining unallocated")
    else:
        st.success("✅ Full tranche allocated")
    
    if st.button("💎 Issue Tokens", type="primary", use_container_width=True, key="issue_single"):
        if total_allocated > original_balance:
            st.error("Cannot issue more than tranche balance")
            return
        
        with st.spinner(f"Issuing {selected_tranche} tokens..."):
            try:
                result = api_client.issue_tranche_tokens(
                    deal_id=deal_id,
                    tranche_id=selected_tranche,
                    token_holders=[inv["address"] for inv in investors],
                    token_amounts=[int(inv["amount"]) for inv in investors]
                )
                
                st.success(f"✅ Successfully issued {selected_tranche} tokens to {len(investors)} investor(s)!")
                
                if result.get("tx_hash"):
                    st.code(f"Transaction: {result.get('tx_hash')}", language=None)
                
                st.balloons()
                
            except APIError as e:
                st.error(f"❌ Issuance failed: {e}")


def render_bulk_issuance(
    api_client: APIClient,
    deal_id: str,
    bonds: List[Dict],
    deployed_tranches: Dict[str, str]
) -> None:
    """Render bulk token issuance form for all tranches."""
    
    st.markdown("**Issue tokens for ALL tranches proportionally to investors.**")
    
    # Calculate total deal size
    total_deal_size = sum(b.get("original_balance", 0) for b in bonds if b.get("id") in deployed_tranches)
    
    st.info(f"💰 Total Deal Size (Deployed Tranches): {_format_currency(total_deal_size)}")
    
    # Investor inputs with pro-rata allocation
    st.markdown("**Investors (will receive pro-rata allocation across all tranches):**")
    
    num_investors = st.number_input(
        "Number of Investors",
        min_value=1,
        max_value=10,
        value=1,
        key="num_investors_bulk"
    )
    
    investors = []
    
    for i in range(int(num_investors)):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            address = st.text_input(
                f"Investor {i+1} Address",
                value=f"0x{'0' * 39}{i+1}",
                key=f"bulk_investor_addr_{i}"
            )
        
        with col2:
            pct = st.slider(
                f"Share (%)",
                min_value=0,
                max_value=100,
                value=int(100 / num_investors),
                key=f"bulk_investor_pct_{i}"
            )
        
        investors.append({"address": address, "percentage": pct})
    
    # Validate total percentage
    total_pct = sum(inv["percentage"] for inv in investors)
    
    if total_pct > 100:
        st.error(f"❌ Total allocation ({total_pct}%) exceeds 100%")
    elif total_pct < 100:
        st.warning(f"⚠️ {100 - total_pct}% remaining unallocated")
    else:
        st.success("✅ 100% allocated")
    
    # Preview allocation
    with st.expander("📊 Allocation Preview", expanded=True):
        import pandas as pd
        
        preview_data = []
        for bond in bonds:
            if bond.get("id") not in deployed_tranches:
                continue
            
            tranche_id = bond.get("id")
            balance = bond.get("original_balance", 0)
            
            for inv in investors:
                allocation = balance * inv["percentage"] / 100
                preview_data.append({
                    "Tranche": tranche_id,
                    "Investor": _format_address(inv["address"]),
                    "Share": f"{inv['percentage']}%",
                    "Allocation": _format_currency(allocation),
                })
        
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)
    
    if st.button("💎 Issue All Tokens", type="primary", use_container_width=True, key="issue_bulk"):
        if total_pct > 100:
            st.error("Cannot allocate more than 100%")
            return
        
        with st.spinner("Issuing tokens for all tranches..."):
            try:
                # Calculate allocations per tranche
                token_allocations = {}
                
                for bond in bonds:
                    if bond.get("id") not in deployed_tranches:
                        continue
                    
                    tranche_id = bond.get("id")
                    balance = bond.get("original_balance", 0)
                    
                    allocations = [int(balance * inv["percentage"] / 100) for inv in investors]
                    token_allocations[tranche_id] = allocations
                
                result = api_client.issue_all_tranche_tokens(
                    deal_id=deal_id,
                    token_holders=[inv["address"] for inv in investors],
                    token_allocations=token_allocations
                )
                
                st.success(f"✅ Successfully issued tokens for {len(token_allocations)} tranches!")
                
                if result.get("summary"):
                    for tranche_id, summary in result.get("summary", {}).items():
                        st.write(f"  • {tranche_id}: {summary}")
                
                st.balloons()
                
            except APIError as e:
                st.error(f"❌ Issuance failed: {e}")


# =============================================================================
# DISTRIBUTIONS TAB
# =============================================================================

def render_distributions(api_client: APIClient) -> None:
    """Render the distributions management interface."""
    
    st.markdown("### 🌊 Distribution Management")
    st.caption("Execute waterfall distributions and manage oracle data")
    
    # Deal selector
    deals = api_client.get_deals()
    
    if not deals:
        st.warning("No deals available.")
        return
    
    deal_options = {f"{d.get('deal_id')} - {d.get('deal_name', 'Unknown')}": d.get("deal_id") for d in deals}
    
    selected_label = st.selectbox(
        "Select Deal",
        options=list(deal_options.keys()),
        key="dist_deal_select"
    )
    
    deal_id = deal_options.get(selected_label, "")
    
    if not deal_id:
        return
    
    st.markdown("---")
    
    # Subtabs for distribution actions
    dist_tabs = st.tabs(["📊 Distribution Cycles", "🛰️ Oracle Publishing", "⚙️ Waterfall Config"])
    
    # Distribution Cycles Tab
    with dist_tabs[0]:
        render_distribution_cycles(api_client, deal_id)
    
    # Oracle Publishing Tab
    with dist_tabs[1]:
        render_oracle_publishing(api_client, deal_id)
    
    # Waterfall Config Tab
    with dist_tabs[2]:
        render_waterfall_config(api_client, deal_id)


def render_distribution_cycles(api_client: APIClient, deal_id: str) -> None:
    """Render distribution cycles management."""
    
    st.markdown("#### 📊 Distribution Cycles")
    
    # Load distribution periods
    try:
        dist_data = api_client.get_distribution_periods(deal_id)
        periods = dist_data.get("periods", [])
    except Exception:
        periods = []
    
    if not periods:
        st.info("📭 No distribution periods yet. Upload servicer tape to create one.")
        return
    
    # Pending distributions
    pending = [p for p in periods if p.get("status") == "pending"]
    distributed = [p for p in periods if p.get("status") == "distributed"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Pending Distributions", len(pending))
    
    with col2:
        st.metric("Completed Distributions", len(distributed))
    
    st.markdown("---")
    
    # Show pending distributions first
    if pending:
        st.markdown("**⏳ Pending Distributions**")
        
        for period in sorted(pending, key=lambda x: x.get("period_number", 0)):
            period_num = period.get("period_number", 0)
            collections = period.get("total_collections", 0)
            
            with st.container():
                p_col1, p_col2, p_col3 = st.columns([2, 2, 1])
                
                with p_col1:
                    st.write(f"**Period {period_num}**")
                    st.caption(f"Collections: {_format_currency(collections)}")
                
                with p_col2:
                    st.write(f"Interest: {_format_currency(period.get('interest_collected', 0))}")
                    st.write(f"Principal: {_format_currency(period.get('principal_collected', 0))}")
                
                with p_col3:
                    if st.button("▶️ Execute", key=f"exec_dist_{period_num}", use_container_width=True):
                        with st.spinner(f"Executing Period {period_num} distribution..."):
                            try:
                                result = api_client.execute_distribution(deal_id, period_num)
                                st.success(f"✅ Period {period_num} distributed!")
                                _rerun()
                            except APIError as e:
                                st.error(f"❌ Distribution failed: {e}")
    
    # Show completed distributions
    if distributed:
        with st.expander(f"✅ Completed Distributions ({len(distributed)})", expanded=False):
            import pandas as pd
            
            dist_df = pd.DataFrame([
                {
                    "Period": p.get("period_number"),
                    "Date": p.get("distribution_date", "")[:10] if p.get("distribution_date") else "N/A",
                    "Collections": _format_currency(p.get("total_collections", 0)),
                    "Interest Paid": _format_currency(p.get("total_interest_distributed", 0)),
                    "Principal Paid": _format_currency(p.get("total_principal_distributed", 0)),
                    "TX Hash": _format_address(p.get("waterfall_tx_hash", "")) if p.get("waterfall_tx_hash") else "—",
                }
                for p in sorted(distributed, key=lambda x: x.get("period_number", 0), reverse=True)
            ])
            
            st.dataframe(dist_df, use_container_width=True, hide_index=True)


def render_oracle_publishing(api_client: APIClient, deal_id: str) -> None:
    """Render oracle data publishing interface."""
    
    st.markdown("#### 🛰️ Oracle Data Publishing")
    st.caption("Publish performance data to the on-chain oracle")
    
    publish_mode = st.radio(
        "Publishing Mode",
        options=["📍 Single Period", "📊 Period Range"],
        horizontal=True,
        key="oracle_publish_mode"
    )
    
    if publish_mode == "📍 Single Period":
        period = st.number_input(
            "Period Number",
            min_value=1,
            value=1,
            step=1,
            key="oracle_single_period"
        )
        
        if st.button("📤 Publish Period", type="primary", use_container_width=True, key="publish_single_period"):
            with st.spinner(f"Publishing Period {period} to oracle..."):
                try:
                    result = api_client.web3_oracle_publish_period(deal_id, int(period))
                    st.success(f"✅ Period {period} published!")
                    
                    if result.get("tx_hash"):
                        st.code(f"Transaction: {result.get('tx_hash')}", language=None)
                    
                except APIError as e:
                    st.error(f"❌ Publishing failed: {e}")
    
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            start_period = st.number_input(
                "Start Period",
                min_value=1,
                value=1,
                step=1,
                key="oracle_start_period"
            )
        
        with col2:
            end_period = st.number_input(
                "End Period",
                min_value=1,
                value=12,
                step=1,
                key="oracle_end_period"
            )
        
        if st.button("📤 Publish Range", type="primary", use_container_width=True, key="publish_range"):
            with st.spinner(f"Publishing Periods {start_period}-{end_period}..."):
                try:
                    result = api_client.web3_oracle_publish_range(
                        deal_id,
                        {"start_period": int(start_period), "end_period": int(end_period)}
                    )
                    st.success(f"✅ Periods {start_period}-{end_period} published!")
                    
                except APIError as e:
                    st.error(f"❌ Publishing failed: {e}")


def render_waterfall_config(api_client: APIClient, deal_id: str) -> None:
    """Render waterfall configuration interface."""
    
    st.markdown("#### ⚙️ Waterfall Configuration")
    st.caption("Configure and publish the on-chain waterfall contract")
    
    # Load deal spec for default values
    try:
        deal_response = api_client.get_deal(deal_id)
        deal_spec = deal_response.get("spec", {})
        parties = deal_spec.get("parties", {})
        servicing = deal_spec.get("servicing", {})
        
        registry = api_client.get_tranche_registry(deal_id)
        deployed_tranches = registry.get("tranches", {})
    except Exception as e:
        st.error(f"Failed to load deal: {e}")
        return
    
    if not deployed_tranches:
        st.warning("⚠️ No tranches deployed. Deploy tranches first before publishing waterfall.")
        return
    
    # Configuration form
    col1, col2 = st.columns(2)
    
    with col1:
        payment_token = st.text_input(
            "Payment Token",
            value="0x0000000000000000000000000000000000000000",
            help="Stablecoin address for payments",
            key="wf_payment_token"
        )
        
        trustee_address = st.text_input(
            "Trustee Address",
            value=parties.get("trustee", {}).get("address", "0x0000000000000000000000000000000000000002"),
            key="wf_trustee"
        )
        
        trustee_fee_bps = st.number_input(
            "Trustee Fee (bps)",
            min_value=0,
            max_value=100,
            value=10,
            key="wf_trustee_fee"
        )
    
    with col2:
        servicer_address = st.text_input(
            "Servicer Address",
            value=parties.get("servicer", {}).get("address", "0x0000000000000000000000000000000000000003"),
            key="wf_servicer"
        )
        
        servicer_fee_bps = st.number_input(
            "Servicer Fee (bps)",
            min_value=0,
            max_value=100,
            value=int(servicing.get("servicing_fee", {}).get("rate_bps", 25)),
            key="wf_servicer_fee"
        )
        
        sequential_principal = st.checkbox(
            "Sequential Principal",
            value=True,
            help="If checked, principal pays sequentially. If unchecked, pro-rata.",
            key="wf_sequential"
        )
    
    # Tranche order preview
    st.markdown("**Tranche Payment Order:**")
    
    tranche_list = list(deployed_tranches.keys())
    st.write(" → ".join(tranche_list))
    
    if st.button("🌊 Publish Waterfall Contract", type="primary", use_container_width=True, key="publish_waterfall"):
        with st.spinner("Publishing waterfall contract..."):
            try:
                payload = {
                    "payment_token": payment_token,
                    "tranches": list(deployed_tranches.values()),
                    "trustee_address": trustee_address,
                    "servicer_address": servicer_address,
                    "trustee_fees_bps": int(trustee_fee_bps),
                    "servicer_fees_bps": int(servicer_fee_bps),
                    "principal_sequential": sequential_principal,
                }
                
                result = api_client.web3_publish_waterfall(deal_id, payload)
                st.success("✅ Waterfall contract published!")
                
                if result.get("waterfall_address"):
                    st.code(f"Waterfall Contract: {result.get('waterfall_address')}", language=None)
                
                if result.get("tx_hash"):
                    st.code(f"Transaction: {result.get('tx_hash')}", language=None)
                
            except APIError as e:
                st.error(f"❌ Publishing failed: {e}")


# =============================================================================
# CONTRACT REGISTRY TAB
# =============================================================================

def render_contract_registry(api_client: APIClient) -> None:
    """Render the contract registry and explorer."""
    
    st.markdown("### 📜 Contract Registry")
    st.caption("View all deployed smart contracts")
    
    # Load all deployments
    deployments = _load_deployment_info(api_client)
    
    if not deployments:
        st.info("📭 No contracts deployed yet.")
        return
    
    # Contract summary
    all_contracts = []
    
    for deal_id, deployment in deployments.items():
        for tranche_id, address in deployment.get("tranche_addresses", {}).items():
            all_contracts.append({
                "Deal": deal_id,
                "Tranche": tranche_id,
                "Contract Address": address,
                "Type": "TrancheToken",
                "Status": "✅ Deployed",
            })
    
    if all_contracts:
        import pandas as pd
        
        st.metric("Total Contracts", len(all_contracts))
        
        st.markdown("---")
        
        # Filter by deal
        deal_filter = st.multiselect(
            "Filter by Deal",
            options=list(deployments.keys()),
            default=list(deployments.keys()),
            key="contract_deal_filter"
        )
        
        filtered_contracts = [c for c in all_contracts if c["Deal"] in deal_filter]
        
        st.dataframe(
            pd.DataFrame(filtered_contracts),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Contract Address": st.column_config.TextColumn(
                    "Contract Address",
                    width="large",
                    help="Click to copy"
                ),
            }
        )
        
        # Export option
        if st.button("📥 Export Registry", key="export_registry"):
            registry_json = json.dumps(
                {
                    d_id: {
                        "tranches": d_info.get("tranche_addresses", {})
                    }
                    for d_id, d_info in deployments.items()
                },
                indent=2
            )
            st.download_button(
                "Download JSON",
                data=registry_json,
                file_name="contract_registry.json",
                mime="application/json"
            )
    else:
        st.info("📭 No tranche contracts deployed yet.")


# =============================================================================
# MAIN PAGE RENDERER
# =============================================================================

def render_web3_page(api_client: APIClient) -> None:
    """Render the complete Web3 Tokenization page."""
    
    st.header("🔗 Web3 Tokenization")
    st.caption("Deploy smart contracts, issue tokens, and manage on-chain distributions")
    
    # Main navigation tabs
    tab_labels = [
        "📊 Dashboard",
        "🏗️ Tokenize Deal",
        "💎 Issue Tokens",
        "🌊 Distributions",
        "📜 Contract Registry",
    ]
    
    tabs = st.tabs(tab_labels)
    
    with tabs[0]:
        render_dashboard(api_client)
    
    with tabs[1]:
        render_tokenize_deal(api_client)
    
    with tabs[2]:
        render_issue_tokens(api_client)
    
    with tabs[3]:
        render_distributions(api_client)
    
    with tabs[4]:
        render_contract_registry(api_client)
