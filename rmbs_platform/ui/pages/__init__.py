"""
UI Pages Package
===============

Persona-specific page implementations for the RMBS platform.
"""

from .arranger import render_arranger_page
from .issuer import render_issuer_page
from .trustee import render_trustee_page
from .servicer import render_servicer_page
from .investor import render_investor_page
from .auditor import render_auditor_page
from .web3 import render_web3_page

__all__ = [
    "render_arranger_page",
    "render_issuer_page",
    "render_trustee_page",
    "render_servicer_page",
    "render_investor_page",
    "render_auditor_page",
    "render_web3_page",
]