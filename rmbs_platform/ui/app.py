"""
RMBS Platform UI - Main Application
===================================

Main entry point for the modular Streamlit UI application.
Provides persona-based workflows with modern UX patterns.
"""

from __future__ import annotations

import streamlit as st
from typing import Dict, Any

from .services.api_client import APIClient
from .pages import (
    render_arranger_page,
    render_issuer_page,
    render_trustee_page,
    render_servicer_page,
    render_investor_page,
    render_auditor_page,
    render_web3_page,
)
from .utils.formatting import format_currency, format_percentage


def persona_headers(persona_name: str) -> Dict[str, str]:
    """
    Return HTTP headers for the active persona.

    Maps UI persona names to API role values for RBAC enforcement.

    Parameters
    ----------
    persona_name : str
        Display name of the selected persona.

    Returns
    -------
    dict
        Headers dict with X-User-Role set appropriately.
    """
    role_map = {
        "Arranger (Structurer)": "arranger",
        "Issuer (Token Minter)": "issuer",
        "Trustee (Administrator)": "trustee",
        "Servicer (Operations)": "servicer",
        "Investor (Analytics)": "investor",
        "Auditor (Review)": "auditor",
        "Web3 (Tokenization)": "arranger",  # Legacy, maps to arranger
    }
    role = role_map.get(persona_name, "unknown")
    return {"X-User-Role": role}


def main():
    """Main application entry point."""
    # Configure page
    st.set_page_config(
        page_title="RMBS Platform",
        page_icon="🏦",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize API client
    api_client = APIClient()

    # Title and persona selection
    st.title("🏦 Enterprise RMBS Platform")
    st.caption("Securitization analytics and deal management platform")

    # Sidebar persona selection
    persona = st.sidebar.selectbox(
        "Select Persona",
        [
            "Arranger (Structurer)",
            "Issuer (Token Minter)",
            "Trustee (Administrator)",
            "Servicer (Operations)",
            "Investor (Analytics)",
            "Auditor (Review)",
            "Web3 (Tokenization)"
        ]
    )

    headers = persona_headers(persona)
    api_client.set_headers(headers)

    # Health check
    if not api_client.health_check():
        st.sidebar.error("⚠️ API server not reachable")
        st.error("The RMBS Platform API server is not available. Please start the FastAPI server.")
        return

    # Render appropriate page based on persona
    try:
        if persona == "Arranger (Structurer)":
            render_arranger_page(api_client)
        elif persona == "Issuer (Token Minter)":
            render_issuer_page(api_client)
        elif persona == "Trustee (Administrator)":
            render_trustee_page(api_client)
        elif persona == "Servicer (Operations)":
            render_servicer_page(api_client)
        elif persona == "Investor (Analytics)":
            render_investor_page(api_client)
        elif persona == "Auditor (Review)":
            render_auditor_page(api_client)
        elif persona == "Web3 (Tokenization)":
            render_web3_page(api_client)
    except Exception as e:
        st.error(f"Application error: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()