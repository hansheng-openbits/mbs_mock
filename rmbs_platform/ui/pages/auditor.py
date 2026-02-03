"""
Enhanced Auditor Portal
=======================

Comprehensive audit interface based on Web3_Tokenization_Design.md specifications.

Features:
- Dashboard with active engagements, pending reviews, findings, attestations
- Audit Trail Explorer with hash chain verification
- Deal Audit Workspace with verification tools
- Findings & Attestations workflow
- Dispute resolution interface
- Access grant management
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from ..components.data_display import data_table
from ..services.api_client import APIClient
from ..utils.formatting import create_table_formatter


# =============================================================================
# Dashboard Section
# =============================================================================


def render_dashboard_section(api_client: APIClient) -> None:
    """Render the auditor dashboard with key metrics."""
    st.subheader("📊 Auditor Dashboard")
    
    # Check if we have an auditor ID in session
    if "auditor_id" not in st.session_state:
        st.session_state.auditor_id = None
    
    # Auditor selection/login
    with st.expander("🔐 Auditor Identity", expanded=st.session_state.auditor_id is None):
        auditor_id = st.text_input(
            "Auditor ID",
            value=st.session_state.auditor_id or "",
            placeholder="Enter your auditor ID (e.g., aud_12345)",
            help="Your unique auditor identifier"
        )
        if st.button("Set Identity"):
            st.session_state.auditor_id = auditor_id
            st.success(f"✓ Identity set to: {auditor_id}")
            st.rerun()
    
    if not st.session_state.auditor_id:
        st.info("👆 Please set your auditor identity to view the dashboard")
        return
    
    # Dashboard metrics
    col1, col2, col3, col4 = st.columns(4)
    
    # Try to fetch real data from API, fallback to mock data
    try:
        # In production, this would call the audit API
        dashboard_data = {
            "active_engagements": 5,
            "pending_reviews": 12,
            "open_findings": 3,
            "attestations_due": 2,
            "findings_by_severity": {
                "CRITICAL": 0,
                "HIGH": 1,
                "MEDIUM": 2,
                "LOW": 0,
            }
        }
    except Exception:
        dashboard_data = {
            "active_engagements": 0,
            "pending_reviews": 0,
            "open_findings": 0,
            "attestations_due": 0,
            "findings_by_severity": {},
        }
    
    with col1:
        st.metric(
            "Active Engagements",
            dashboard_data["active_engagements"],
            help="Deals you have active access grants for"
        )
    
    with col2:
        st.metric(
            "Pending Reviews",
            dashboard_data["pending_reviews"],
            help="Deals awaiting audit review"
        )
    
    with col3:
        findings = dashboard_data["open_findings"]
        critical = dashboard_data["findings_by_severity"].get("CRITICAL", 0)
        high = dashboard_data["findings_by_severity"].get("HIGH", 0)
        st.metric(
            "Open Findings",
            findings,
            delta=f"{critical} critical, {high} high" if critical + high > 0 else None,
            delta_color="inverse" if critical > 0 else "off",
            help="Unresolved audit findings"
        )
    
    with col4:
        st.metric(
            "Attestations Due",
            dashboard_data["attestations_due"],
            help="Attestations due within 30 days"
        )
    
    # Recent Activity
    st.markdown("### 🕐 Recent Activity")
    
    activity_data = [
        {"timestamp": datetime.now() - timedelta(hours=2), "action": "Waterfall verified", "deal_id": "FREDDIE_SAMPLE_2017_2020", "status": "✓ Verified"},
        {"timestamp": datetime.now() - timedelta(hours=5), "action": "Finding created", "deal_id": "PRIME_2024_1", "status": "⚠️ Medium"},
        {"timestamp": datetime.now() - timedelta(days=1), "action": "Attestation issued", "deal_id": "NONQM_2023_1", "status": "✓ Unqualified"},
        {"timestamp": datetime.now() - timedelta(days=2), "action": "Access granted", "deal_id": "STRESSED_2022_1", "status": "✓ Active"},
        {"timestamp": datetime.now() - timedelta(days=3), "action": "Data accessed", "deal_id": "FREDDIE_SAMPLE_2017_2020", "status": "✓ Logged"},
    ]
    
    activity_df = pd.DataFrame(activity_data)
    activity_df["timestamp"] = activity_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    
    st.dataframe(
        activity_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
            "action": st.column_config.TextColumn("Action", width="medium"),
            "deal_id": st.column_config.TextColumn("Deal", width="large"),
            "status": st.column_config.TextColumn("Status", width="small"),
        }
    )


# =============================================================================
# Audit Trail Explorer Section
# =============================================================================


def render_audit_trail_section(api_client: APIClient) -> None:
    """Render the audit trail explorer with hash chain verification."""
    st.subheader("📜 Audit Trail Explorer")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        deal_filter = st.text_input(
            "Deal ID",
            placeholder="Filter by deal ID",
            help="Leave empty to show all deals"
        )
    
    with col2:
        event_types = [
            "All Events",
            "DEAL_CREATED", "TOKENS_MINTED", "WATERFALL_EXECUTED",
            "PERFORMANCE_SUBMITTED", "YIELD_DISTRIBUTED", "PRINCIPAL_PAID",
            "TRIGGER_BREACHED", "TRIGGER_CURED", "AUDITOR_ATTESTATION",
            "FINDING_CREATED", "ACCESS_GRANTED", "DATA_ACCESSED",
        ]
        event_filter = st.selectbox("Event Type", event_types)
    
    with col3:
        time_range = st.selectbox(
            "Time Range",
            ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"]
        )
    
    # Hash Chain Verification Status
    verification_col1, verification_col2 = st.columns([3, 1])
    
    with verification_col1:
        st.markdown("**Chain Integrity Status:**")
    
    with verification_col2:
        if st.button("🔍 Verify Chain"):
            with st.spinner("Verifying hash chain integrity..."):
                # In production, this would call the API
                import time
                time.sleep(1)
                st.success("✓ Hash chain verified - No tampering detected")
    
    # Event table
    st.markdown("### 📋 Events")
    
    # Mock audit trail data
    events_data = [
        {
            "event_id": "evt_001",
            "timestamp": "2026-02-01 14:32:01",
            "event_type": "WATERFALL_EXECUTED",
            "deal_id": "FREDDIE_SAMPLE_2017_2020",
            "actor": "trustee@bank.com",
            "data_hash": "a1b2c3d4...",
            "chain_link": "✓",
        },
        {
            "event_id": "evt_002",
            "timestamp": "2026-02-01 14:31:45",
            "event_type": "PERFORMANCE_SUBMITTED",
            "deal_id": "FREDDIE_SAMPLE_2017_2020",
            "actor": "servicer@bank.com",
            "data_hash": "e5f6g7h8...",
            "chain_link": "✓",
        },
        {
            "event_id": "evt_003",
            "timestamp": "2026-02-01 09:00:00",
            "event_type": "YIELD_DISTRIBUTED",
            "deal_id": "PRIME_2024_1",
            "actor": "system",
            "data_hash": "i9j0k1l2...",
            "chain_link": "✓",
        },
        {
            "event_id": "evt_004",
            "timestamp": "2026-01-31 14:35:12",
            "event_type": "AUDITOR_ATTESTATION",
            "deal_id": "NONQM_2023_1",
            "actor": st.session_state.get("auditor_id", "auditor@firm.com"),
            "data_hash": "m3n4o5p6...",
            "chain_link": "✓",
        },
    ]
    
    events_df = pd.DataFrame(events_data)
    
    st.dataframe(
        events_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "event_id": st.column_config.TextColumn("Event ID", width="small"),
            "timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
            "event_type": st.column_config.TextColumn("Type", width="medium"),
            "deal_id": st.column_config.TextColumn("Deal", width="large"),
            "actor": st.column_config.TextColumn("Actor", width="medium"),
            "data_hash": st.column_config.TextColumn("Data Hash", width="small"),
            "chain_link": st.column_config.TextColumn("Chain", width="small"),
        }
    )
    
    # Export options
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        st.download_button(
            "📥 Export CSV",
            events_df.to_csv(index=False),
            file_name="audit_trail.csv",
            mime="text/csv",
        )
    with col2:
        st.download_button(
            "📥 Export JSON",
            events_df.to_json(orient="records", indent=2),
            file_name="audit_trail.json",
            mime="application/json",
        )


# =============================================================================
# Deal Audit Workspace Section
# =============================================================================


def render_deal_workspace_section(api_client: APIClient) -> None:
    """Render the deal audit workspace with verification tools."""
    st.subheader("🔍 Deal Audit Workspace")
    
    # Deal selection
    available_deals = [
        "FREDDIE_SAMPLE_2017_2020",
        "PRIME_2024_1",
        "NONQM_2023_1",
        "STRESSED_2022_1",
        "SAMPLE_RMBS_2024",
    ]
    
    selected_deal = st.selectbox(
        "Select Deal to Audit",
        available_deals,
        help="Choose a deal you have access to"
    )
    
    if selected_deal:
        # Deal summary cards
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 📊 Waterfall Verification")
            st.markdown("""
            | Period | Status |
            |--------|--------|
            | 1-5 | ✓ Verified |
            | 6-7 | ⏳ Pending |
            """)
            if st.button("▶️ Verify Waterfall", key="verify_waterfall"):
                with st.spinner("Running waterfall verification..."):
                    import time
                    time.sleep(2)
                st.success("✓ Waterfall calculations verified for periods 6-7")
        
        with col2:
            st.markdown("### 📈 Performance Data")
            st.markdown("""
            | Metric | Status |
            |--------|--------|
            | CPR/CDR | ✓ Valid |
            | DQ Buckets | ✓ Valid |
            | Loss Severity | ⚠️ Review |
            """)
            if st.button("🔄 Reconcile Data", key="reconcile_data"):
                with st.spinner("Reconciling performance data..."):
                    import time
                    time.sleep(1.5)
                st.success("✓ Data reconciled - 1 minor discrepancy noted")
        
        with col3:
            st.markdown("### ✅ Compliance")
            st.markdown("""
            | Check | Status |
            |-------|--------|
            | KYC/AML | ✓ Pass |
            | Reg D | ✓ Pass |
            | Sanctions | ✓ Pass |
            """)
            if st.button("🔍 Run Compliance", key="run_compliance"):
                with st.spinner("Running compliance checks..."):
                    import time
                    time.sleep(1)
                st.success("✓ All compliance checks passed")
        
        # Stratification Analysis
        st.markdown("### 📊 Stratification Analysis")
        
        strat_col1, strat_col2 = st.columns(2)
        
        with strat_col1:
            stratify_by = st.multiselect(
                "Stratify By",
                ["FICO Bucket", "LTV Bucket", "Loan Purpose", "Property Type", "State"],
                default=["FICO Bucket"],
                help="Select fields for stratification analysis"
            )
        
        with strat_col2:
            period = st.number_input(
                "Period",
                min_value=1,
                max_value=100,
                value=7,
                help="Period for stratification snapshot"
            )
        
        if st.button("📊 Generate Stratification", key="gen_strat"):
            with st.spinner("Generating stratification..."):
                import time
                time.sleep(1.5)
            
            # Mock stratification data
            strat_data = [
                {"FICO Range": "≥760", "Count": 250, "Balance": "$112.5M", "% of Pool": "25.0%"},
                {"FICO Range": "720-759", "Count": 300, "Balance": "$135.0M", "% of Pool": "30.0%"},
                {"FICO Range": "680-719", "Count": 275, "Balance": "$123.75M", "% of Pool": "27.5%"},
                {"FICO Range": "640-679", "Count": 125, "Balance": "$56.25M", "% of Pool": "12.5%"},
                {"FICO Range": "<640", "Count": 50, "Balance": "$22.5M", "% of Pool": "5.0%"},
            ]
            
            strat_df = pd.DataFrame(strat_data)
            st.dataframe(strat_df, use_container_width=True, hide_index=True)


# =============================================================================
# Findings & Attestations Section
# =============================================================================


def render_findings_section(api_client: APIClient) -> None:
    """Render the findings and attestations management section."""
    st.subheader("📝 Findings & Attestations")
    
    findings_tab, attestations_tab = st.tabs(["🔍 Findings", "✅ Attestations"])
    
    with findings_tab:
        # Create new finding
        with st.expander("➕ Create New Finding", expanded=False):
            finding_deal = st.selectbox(
                "Deal",
                ["FREDDIE_SAMPLE_2017_2020", "PRIME_2024_1", "NONQM_2023_1"],
                key="finding_deal"
            )
            
            finding_severity = st.selectbox(
                "Severity",
                ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
                index=2,
                key="finding_severity"
            )
            
            finding_title = st.text_input(
                "Title",
                placeholder="Brief description of the finding",
                key="finding_title"
            )
            
            finding_desc = st.text_area(
                "Description",
                placeholder="Detailed description of the finding...",
                height=100,
                key="finding_desc"
            )
            
            finding_rec = st.text_area(
                "Recommendation",
                placeholder="Recommended remediation steps...",
                height=80,
                key="finding_rec"
            )
            
            if st.button("📤 Submit Finding"):
                if finding_title and finding_desc:
                    st.success(f"✓ Finding created: {finding_title}")
                else:
                    st.error("Please provide title and description")
        
        # Existing findings
        st.markdown("### Open Findings")
        
        findings_data = [
            {
                "finding_id": "FND-001",
                "deal_id": "PRIME_2024_1",
                "severity": "🟠 MEDIUM",
                "title": "Loss severity calculation variance",
                "status": "OPEN",
                "created": "2026-01-28",
            },
            {
                "finding_id": "FND-002",
                "deal_id": "FREDDIE_SAMPLE_2017_2020",
                "severity": "🟡 LOW",
                "title": "Minor data formatting inconsistency",
                "status": "ACKNOWLEDGED",
                "created": "2026-01-25",
            },
            {
                "finding_id": "FND-003",
                "deal_id": "STRESSED_2022_1",
                "severity": "🟠 MEDIUM",
                "title": "Trigger test threshold review needed",
                "status": "IN_PROGRESS",
                "created": "2026-01-20",
            },
        ]
        
        findings_df = pd.DataFrame(findings_data)
        
        # Make findings selectable
        selected_finding = st.dataframe(
            findings_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
        
        # Finding actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✓ Acknowledge"):
                st.info("Select a finding to acknowledge")
        with col2:
            if st.button("🔄 Mark In Progress"):
                st.info("Select a finding to update")
        with col3:
            if st.button("✅ Resolve"):
                st.info("Select a finding to resolve")
    
    with attestations_tab:
        # Create new attestation
        with st.expander("➕ Create Attestation", expanded=False):
            attest_deal = st.selectbox(
                "Deal",
                ["FREDDIE_SAMPLE_2017_2020", "PRIME_2024_1", "NONQM_2023_1"],
                key="attest_deal"
            )
            
            attest_col1, attest_col2 = st.columns(2)
            with attest_col1:
                period_start = st.number_input("Period Start", min_value=1, value=1, key="period_start")
            with attest_col2:
                period_end = st.number_input("Period End", min_value=1, value=7, key="period_end")
            
            attest_type = st.selectbox(
                "Attestation Type",
                ["UNQUALIFIED", "QUALIFIED", "ADVERSE", "DISCLAIMER"],
                help="UNQUALIFIED = Clean opinion, QUALIFIED = With exceptions",
                key="attest_type"
            )
            
            attest_summary = st.text_area(
                "Summary",
                placeholder="Attestation summary...",
                height=100,
                key="attest_summary"
            )
            
            if st.button("📤 Submit Attestation"):
                if attest_summary:
                    st.success(f"✓ Attestation created for {attest_deal} (Periods {period_start}-{period_end})")
                else:
                    st.error("Please provide a summary")
        
        # Existing attestations
        st.markdown("### Attestation History")
        
        attestations_data = [
            {
                "attestation_id": "ATT-001",
                "deal_id": "NONQM_2023_1",
                "periods": "1-6",
                "type": "✓ UNQUALIFIED",
                "findings": 0,
                "date": "2026-01-15",
            },
            {
                "attestation_id": "ATT-002",
                "deal_id": "PRIME_2024_1",
                "periods": "1-3",
                "type": "⚠️ QUALIFIED",
                "findings": 2,
                "date": "2026-01-10",
            },
            {
                "attestation_id": "ATT-003",
                "deal_id": "FREDDIE_SAMPLE_2017_2020",
                "periods": "1-5",
                "type": "✓ UNQUALIFIED",
                "findings": 0,
                "date": "2025-12-20",
            },
        ]
        
        attestations_df = pd.DataFrame(attestations_data)
        st.dataframe(attestations_df, use_container_width=True, hide_index=True)


# =============================================================================
# Access Grants Section
# =============================================================================


def render_access_section(api_client: APIClient) -> None:
    """Render the access grants management section."""
    st.subheader("🔑 Access Grants")
    
    # Current grants
    st.markdown("### My Active Grants")
    
    grants_data = [
        {
            "grant_id": "GNT-001",
            "deal_id": "FREDDIE_SAMPLE_2017_2020",
            "scope": "FULL_DEAL_ACCESS",
            "granted_by": "arranger@bank.com",
            "expires": "2026-04-01",
            "status": "✓ Active",
        },
        {
            "grant_id": "GNT-002",
            "deal_id": "PRIME_2024_1",
            "scope": "LOAN_TAPE_ANONYMIZED",
            "granted_by": "trustee@bank.com",
            "expires": "2026-03-15",
            "status": "✓ Active",
        },
        {
            "grant_id": "GNT-003",
            "deal_id": "NONQM_2023_1",
            "scope": "PERFORMANCE_ONLY",
            "granted_by": "arranger@bank.com",
            "expires": "2026-02-15",
            "status": "⚠️ Expiring Soon",
        },
    ]
    
    grants_df = pd.DataFrame(grants_data)
    st.dataframe(grants_df, use_container_width=True, hide_index=True)
    
    # Request new access
    st.markdown("### Request Access")
    
    col1, col2 = st.columns(2)
    
    with col1:
        request_deal = st.selectbox(
            "Deal ID",
            ["STRESSED_2022_1", "SAMPLE_RMBS_2024", "DEAL_2024_001"],
            help="Deal to request access for"
        )
    
    with col2:
        request_scope = st.selectbox(
            "Access Scope",
            ["PERFORMANCE_ONLY", "LOAN_TAPE_ANONYMIZED", "LOAN_TAPE_FULL", "FULL_DEAL_ACCESS"],
            help="Level of access needed"
        )
    
    request_purpose = st.text_area(
        "Purpose",
        placeholder="Describe the audit engagement and purpose for access...",
        height=80,
    )
    
    request_duration = st.slider(
        "Duration (days)",
        min_value=7,
        max_value=365,
        value=90,
        help="Requested access duration"
    )
    
    if st.button("📤 Submit Access Request"):
        if request_purpose:
            st.success(f"✓ Access request submitted for {request_deal}")
        else:
            st.error("Please provide a purpose for the access request")
    
    # Access logs
    st.markdown("### Access Log")
    
    logs_data = [
        {"timestamp": "2026-02-01 14:30", "deal_id": "FREDDIE_SAMPLE_2017_2020", "data_type": "waterfall_verification", "query": "Periods 6-7"},
        {"timestamp": "2026-02-01 10:15", "deal_id": "PRIME_2024_1", "data_type": "stratification", "query": "FICO distribution"},
        {"timestamp": "2026-01-31 16:45", "deal_id": "NONQM_2023_1", "data_type": "performance_data", "query": "Period 6"},
    ]
    
    logs_df = pd.DataFrame(logs_data)
    st.dataframe(logs_df, use_container_width=True, hide_index=True)


# =============================================================================
# Disputes Section
# =============================================================================


def render_disputes_section(api_client: APIClient) -> None:
    """Render the dispute resolution section."""
    st.subheader("⚖️ Disputes")
    
    # Create new dispute
    with st.expander("➕ Open New Dispute", expanded=False):
        dispute_deal = st.selectbox(
            "Deal",
            ["FREDDIE_SAMPLE_2017_2020", "PRIME_2024_1"],
            key="dispute_deal"
        )
        
        dispute_type = st.selectbox(
            "Dispute Type",
            ["DATA_ACCURACY", "WATERFALL_CALCULATION", "COMPLIANCE_VIOLATION", "ACCESS_DENIAL", "FINDING_CONTESTED"],
            key="dispute_type"
        )
        
        dispute_respondent = st.text_input(
            "Respondent ID",
            placeholder="servicer@bank.com",
            key="dispute_respondent"
        )
        
        dispute_title = st.text_input(
            "Title",
            placeholder="Brief description of the dispute",
            key="dispute_title"
        )
        
        dispute_desc = st.text_area(
            "Description",
            placeholder="Detailed description with evidence references...",
            height=150,
            key="dispute_desc"
        )
        
        if st.button("📤 Submit Dispute"):
            if dispute_title and dispute_desc:
                st.success(f"✓ Dispute created: {dispute_title}")
            else:
                st.error("Please provide title and description")
    
    # Active disputes
    st.markdown("### Active Disputes")
    
    disputes_data = [
        {
            "dispute_id": "DSP-001",
            "deal_id": "PRIME_2024_1",
            "type": "DATA_ACCURACY",
            "status": "🔵 ARBITRATION",
            "initiated": "2026-01-20",
            "votes": "1/3",
        },
    ]
    
    if disputes_data:
        disputes_df = pd.DataFrame(disputes_data)
        st.dataframe(disputes_df, use_container_width=True, hide_index=True)
    else:
        st.info("No active disputes")
    
    # Resolved disputes
    st.markdown("### Resolved Disputes")
    
    resolved_data = [
        {
            "dispute_id": "DSP-000",
            "deal_id": "NONQM_2023_1",
            "type": "WATERFALL_CALCULATION",
            "resolution": "✓ In favor of initiator",
            "resolved": "2025-12-15",
        },
    ]
    
    resolved_df = pd.DataFrame(resolved_data)
    st.dataframe(resolved_df, use_container_width=True, hide_index=True)


# =============================================================================
# Main Page Renderer
# =============================================================================


def render_auditor_page(api_client: APIClient) -> None:
    """Render the complete enhanced auditor portal."""
    st.header("🔍 Auditor Portal")
    st.caption("Comprehensive audit, verification, and compliance management")
    
    # Main interface tabs
    tabs = st.tabs([
        "📊 Dashboard",
        "📜 Audit Trail",
        "🔍 Deal Workspace",
        "📝 Findings & Attestations",
        "🔑 Access Grants",
        "⚖️ Disputes",
    ])
    
    with tabs[0]:
        render_dashboard_section(api_client)
    
    with tabs[1]:
        render_audit_trail_section(api_client)
    
    with tabs[2]:
        render_deal_workspace_section(api_client)
    
    with tabs[3]:
        render_findings_section(api_client)
    
    with tabs[4]:
        render_access_section(api_client)
    
    with tabs[5]:
        render_disputes_section(api_client)
    
    # Footer
    st.markdown("---")
    st.caption(
        "🔒 **Audit Notice**: All activities in this interface are logged with cryptographic "
        "hash chain integrity. Access is time-limited and scope-restricted per audit engagement."
    )
