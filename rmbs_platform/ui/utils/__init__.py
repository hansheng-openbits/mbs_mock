"""
UI Utilities Package
===================

Helper functions for formatting, validation, and common operations.
"""

from .formatting import (
    format_currency,
    format_percentage,
    format_number,
    format_date
)

# Import validation functions, handling streamlit dependency
try:
    from .validation import (
        validate_deal_json,
        validate_performance_csv,
        validate_simulation_params
    )
except ImportError:
    # Streamlit not available - validation functions require streamlit
    validate_deal_json = None
    validate_performance_csv = None
    validate_simulation_params = None

__all__ = [
    "format_currency", "format_percentage", "format_number", "format_date",
    "validate_deal_json", "validate_performance_csv", "validate_simulation_params"
]