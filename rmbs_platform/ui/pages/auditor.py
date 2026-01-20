"""
Auditor Page
===========

Audit and evidence review interface for auditors with read-only access.
"""

from ..services.api_client import APIClient
from ..components.data_display import data_table
from ..utils.formatting import create_table_formatter
import streamlit as st
import pandas as pd


def render_simulation_audit_section(api_client: APIClient) -> None:
    """Render the simulation audit and review section."""
    st.subheader("🔬 Simulation Audit")

    # Job ID input for specific audit
    col1, col2 = st.columns([3, 1])

    with col1:
        job_id = st.text_input(
            "Simulation Job ID",
            placeholder="Enter job ID to review (e.g., sim_20240115_143022_abc123)",
            help="Enter a specific simulation job ID to review its audit trail"
        )

    with col2:
        audit_mode = st.selectbox(
            "Audit Scope",
            options=["Job Details", "Full History"],
            help="Choose what to audit"
        )

    if job_id and st.button("🔍 Load Audit Trail", help="Retrieve audit information for this job"):
        try:
            # In a real implementation, this would call an audit endpoint
            # For now, show placeholder audit information
            st.success(f"✅ Audit trail loaded for job {job_id}")

            # Mock audit data
            audit_data = {
                "job_id": job_id,
                "status": "completed",
                "submitted_by": "investor@bank.com",
                "submitted_at": "2024-01-15T14:30:22Z",
                "deal_id": "PRIME_2024_1",
                "parameters": {
                    "cpr": 0.08,
                    "cdr": 0.005,
                    "severity": 0.32
                },
                "execution_time_seconds": 45.2,
                "model_version": "v2.1.0",
                "data_hash": "a1b2c3d4e5f6...",
                "validation_status": "passed"
            }

            # Display audit information
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Job Status", audit_data["status"].upper())
                st.metric("Deal ID", audit_data["deal_id"])
                st.metric("Execution Time", f"{audit_data['execution_time_seconds']:.1f}s")

            with col2:
                st.metric("Submitted By", audit_data["submitted_by"])
                st.metric("Model Version", audit_data["model_version"])
                st.metric("Validation", audit_data["validation_status"].upper())

            # Detailed audit log
            st.subheader("📋 Audit Details")
            audit_df = pd.DataFrame([audit_data])
            formatters = create_table_formatter(audit_df)
            data_table(audit_df, "Audit Trail Details", formatters=formatters)

        except Exception as e:
            st.error(f"❌ Failed to load audit trail: {e}")


def render_system_overview_section(api_client: APIClient) -> None:
    """Render the system overview and statistics section."""
    st.subheader("📊 System Overview")

    # System metrics (mock data for now)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Deals", "8", help="Number of deals in the system")
    with col2:
        st.metric("Active Simulations", "12", help="Currently running simulations")
    with col3:
        st.metric("Data Quality Score", "98.5%", help="Overall data quality percentage")
    with col4:
        st.metric("System Uptime", "99.9%", help="Platform availability")

    # Recent activity
    st.subheader("🕐 Recent Activity")

    # Mock recent activity data
    activity_data = [
        {"timestamp": "2024-01-15 14:30", "action": "Simulation completed", "deal_id": "PRIME_2024_1", "user": "investor@bank.com"},
        {"timestamp": "2024-01-15 14:25", "action": "Performance uploaded", "deal_id": "NONQM_2023_1", "user": "servicer@bank.com"},
        {"timestamp": "2024-01-15 14:20", "action": "Deal updated", "deal_id": "STRESSED_2022_1", "user": "arranger@bank.com"},
        {"timestamp": "2024-01-15 14:15", "action": "Scenario created", "deal_id": "PRIME_2024_1", "user": "investor@bank.com"},
        {"timestamp": "2024-01-15 14:10", "action": "Collateral validated", "deal_id": "SAMPLE_RMBS_2024", "user": "arranger@bank.com"}
    ]

    activity_df = pd.DataFrame(activity_data)
    formatters = {
        "timestamp": lambda x: f"`{x}`"
    }
    data_table(activity_df, "Recent System Activity", formatters=formatters)


def render_compliance_section(api_client: APIClient) -> None:
    """Render the compliance and validation section."""
    st.subheader("⚖️ Compliance & Validation")

    # Compliance checks overview
    st.markdown("### 📋 Compliance Status")

    compliance_data = [
        {"check": "Data Encryption", "status": "✅ Passed", "last_checked": "2024-01-15"},
        {"check": "Access Controls", "status": "✅ Passed", "last_checked": "2024-01-15"},
        {"check": "Data Validation", "status": "✅ Passed", "last_checked": "2024-01-15"},
        {"check": "Audit Logging", "status": "✅ Passed", "last_checked": "2024-01-15"},
        {"check": "Backup Integrity", "status": "✅ Passed", "last_checked": "2024-01-14"},
        {"check": "Performance Monitoring", "status": "✅ Passed", "last_checked": "2024-01-15"}
    ]

    compliance_df = pd.DataFrame(compliance_data)
    formatters = {
        "status": lambda x: "✅" if "Passed" in x else "❌"
    }
    data_table(compliance_df, "Compliance Check Results", formatters=formatters)

    # Data quality metrics
    st.markdown("### 📊 Data Quality Metrics")

    quality_col1, quality_col2, quality_col3 = st.columns(3)

    with quality_col1:
        st.metric("Data Completeness", "99.2%", help="Percentage of required data fields populated")
    with quality_col2:
        st.metric("Data Accuracy", "98.7%", help="Percentage of data passing validation rules")
    with quality_col3:
        st.metric("Timeliness", "97.8%", help="Percentage of data uploaded on time")

    # Validation rules summary
    st.markdown("### 🔍 Validation Rules")
    rules_data = [
        {"rule": "Deal Structure Schema", "violations": 0, "status": "✅ Compliant"},
        {"rule": "Performance Data Format", "violations": 2, "status": "⚠️ Minor Issues"},
        {"rule": "Collateral Completeness", "violations": 0, "status": "✅ Compliant"},
        {"rule": "Trigger Definitions", "violations": 1, "status": "⚠️ Minor Issues"},
        {"rule": "Cashflow Calculations", "violations": 0, "status": "✅ Compliant"}
    ]

    rules_df = pd.DataFrame(rules_data)
    data_table(rules_df, "Validation Rule Summary")


def render_auditor_page(api_client: APIClient) -> None:
    """Render the complete auditor review interface."""
    st.header("🔍 Audit & Evidence Review")
    st.caption("Independent validation and compliance monitoring")

    # Main interface tabs
    tabs = st.tabs(["🔬 Simulation Audit", "📊 System Overview", "⚖️ Compliance"])

    with tabs[0]:
        render_simulation_audit_section(api_client)

    with tabs[1]:
        render_system_overview_section(api_client)

    with tabs[2]:
        render_compliance_section(api_client)

    # Footer with audit disclaimer
    st.markdown("---")
    st.caption("🔒 **Audit Notice**: All activities in this interface are logged for compliance purposes. This is a read-only interface for independent review and validation.")