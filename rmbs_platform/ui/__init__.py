"""
RMBS Platform UI - Modular Streamlit Application
===============================================

This package provides a modular, maintainable UI for the RMBS platform
with persona-based workflows and modern UX patterns.

Structure:
- components/: Reusable UI components (charts, forms, status indicators)
- pages/: Persona-specific page implementations
- services/: API integration and data processing
- utils/: Helper functions and utilities
"""

# Only import main when streamlit is available
try:
    from .app import main
    __all__ = ["main"]
except ImportError:
    # Streamlit not available - provide utilities only
    __all__ = []

__version__ = "1.0.0"