"""
Formatting Utilities
===================

Functions for formatting data display (currency, percentages, etc.).
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Any, Union
import locale

# Try to set locale for better number formatting
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    # Fallback if locale not available
    pass


def format_currency(
    value: Union[int, float, pd.Series, np.ndarray],
    currency_symbol: str = "$",
    decimals: int = 0,
    compact: bool = False
) -> Union[str, pd.Series]:
    """
    Format numeric value as currency.

    Parameters
    ----------
    value : int, float, pd.Series, or np.ndarray
        Value(s) to format
    currency_symbol : str
        Currency symbol to prepend
    decimals : int
        Number of decimal places
    compact : bool
        Whether to use compact notation (K, M, B)

    Returns
    -------
    str or pd.Series
        Formatted currency string(s)

    Examples
    --------
    >>> format_currency(1234567.89)
    '$1,234,568'
    >>> format_currency(1234567.89, decimals=2)
    '$1,234,567.89'
    >>> format_currency(1500000, compact=True)
    '$1.5M'
    """
    if isinstance(value, (pd.Series, np.ndarray)):
        return value.apply(lambda x: format_currency(x, currency_symbol, decimals, compact))

    if pd.isna(value) or value is None:
        return "N/A"

    try:
        numeric_value = float(value)

        if compact:
            if abs(numeric_value) >= 1e9:
                return f"{currency_symbol}{numeric_value/1e9:.1f}B"
            elif abs(numeric_value) >= 1e6:
                return f"{currency_symbol}{numeric_value/1e6:.1f}M"
            elif abs(numeric_value) >= 1e3:
                return f"{currency_symbol}{numeric_value/1e3:.1f}K"

        # Standard formatting
        formatted = f"{numeric_value:,.{decimals}f}"
        return f"{currency_symbol}{formatted}"

    except (ValueError, TypeError):
        return str(value)


def format_percentage(
    value: Union[float, int, pd.Series, np.ndarray],
    decimals: int = 1,
    multiply_by_100: bool = True,
    show_symbol: bool = True
) -> Union[str, pd.Series]:
    """
    Format numeric value as percentage.

    Parameters
    ----------
    value : float, int, pd.Series, or np.ndarray
        Value(s) to format
    decimals : int
        Number of decimal places
    multiply_by_100 : bool
        Whether to multiply by 100 (for decimal rates)
    show_symbol : bool
        Whether to append % symbol

    Returns
    -------
    str or pd.Series
        Formatted percentage string(s)

    Examples
    --------
    >>> format_percentage(0.123)
    '12.3%'
    >>> format_percentage(12.3, multiply_by_100=False)
    '12.3%'
    """
    if isinstance(value, (pd.Series, np.ndarray)):
        return value.apply(lambda x: format_percentage(x, decimals, multiply_by_100, show_symbol))

    if pd.isna(value) or value is None:
        return "N/A"

    try:
        numeric_value = float(value)

        if multiply_by_100:
            numeric_value *= 100

        formatted = f"{numeric_value:.{decimals}f}"
        return f"{formatted}%" if show_symbol else formatted

    except (ValueError, TypeError):
        return str(value)


def format_number(
    value: Union[int, float, pd.Series, np.ndarray],
    decimals: int = 2,
    compact: bool = False,
    separator: bool = True
) -> Union[str, pd.Series]:
    """
    Format numeric value with optional thousands separator.

    Parameters
    ----------
    value : int, float, pd.Series, or np.ndarray
        Value(s) to format
    decimals : int
        Number of decimal places
    compact : bool
        Whether to use compact notation
    separator : bool
        Whether to include thousands separator

    Returns
    -------
    str or pd.Series
        Formatted number string(s)
    """
    if isinstance(value, (pd.Series, np.ndarray)):
        return value.apply(lambda x: format_number(x, decimals, compact, separator))

    if pd.isna(value) or value is None:
        return "N/A"

    try:
        numeric_value = float(value)

        if compact:
            if abs(numeric_value) >= 1e9:
                return f"{numeric_value/1e9:.1f}B"
            elif abs(numeric_value) >= 1e6:
                return f"{numeric_value/1e6:.1f}M"
            elif abs(numeric_value) >= 1e3:
                return f"{numeric_value/1e3:.1f}K"

        if separator:
            return f"{numeric_value:,.{decimals}f}"
        else:
            return f"{numeric_value:.{decimals}f}"

    except (ValueError, TypeError):
        return str(value)


def format_date(
    value: Union[str, pd.Timestamp, pd.Series],
    format_str: str = "%Y-%m-%d"
) -> Union[str, pd.Series]:
    """
    Format date/datetime value.

    Parameters
    ----------
    value : str, pd.Timestamp, or pd.Series
        Date value(s) to format
    format_str : str
        Date format string

    Returns
    -------
    str or pd.Series
        Formatted date string(s)
    """
    if isinstance(value, pd.Series):
        return value.apply(lambda x: format_date(x, format_str))

    if pd.isna(value) or value is None:
        return "N/A"

    try:
        if isinstance(value, str):
            # Try to parse string date
            parsed_date = pd.to_datetime(value)
            return parsed_date.strftime(format_str)
        elif hasattr(value, 'strftime'):
            # Already a datetime-like object
            return value.strftime(format_str)
        else:
            return str(value)
    except Exception:
        return str(value)


def create_table_formatter(
    df: pd.DataFrame,
    currency_columns: Optional[list] = None,
    percentage_columns: Optional[list] = None,
    date_columns: Optional[list] = None,
    number_columns: Optional[list] = None
) -> dict:
    """
    Create a formatter dictionary for styling a DataFrame table.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to create formatters for
    currency_columns : list, optional
        Columns to format as currency
    percentage_columns : list, optional
        Columns to format as percentages
    date_columns : list, optional
        Columns to format as dates
    number_columns : list, optional
        Columns to format as numbers

    Returns
    -------
    dict
        Formatter functions for each column
    """
    formatters = {}

    # Auto-detect column types if not specified
    if currency_columns is None:
        currency_columns = [c for c in df.columns if any(term in c.lower() for term in
                        ['balance', 'paid', 'loss', 'principal', 'interest', 'amount'])]

    if percentage_columns is None:
        percentage_columns = [c for c in df.columns if any(term in c.lower() for term in
                          ['rate', 'ratio', 'cpr', 'cdr', 'severity', 'return', 'yield'])]

    if date_columns is None:
        date_columns = [c for c in df.columns if 'date' in c.lower()]

    # Apply formatters
    for col in currency_columns:
        if col in df.columns:
            formatters[col] = lambda x, col=col: format_currency(x, decimals=0)

    for col in percentage_columns:
        if col in df.columns:
            # Check if values are already percentages ( > 1) or decimals ( < 1)
            sample_values = df[col].dropna().head(5)
            # Only apply numeric heuristics when we actually have numeric samples.
            numeric_samples = []
            for v in sample_values:
                try:
                    # Handle numpy/pandas scalars, ints/floats, and numeric strings.
                    fv = float(v)
                    if fv == fv:  # not NaN
                        numeric_samples.append(fv)
                except (TypeError, ValueError):
                    continue

            if len(numeric_samples) > 0 and all(v <= 1 for v in numeric_samples):
                # Values are decimals, multiply by 100
                formatters[col] = lambda x, col=col: format_percentage(x, decimals=1, multiply_by_100=True)
            else:
                # Values are already percentages
                formatters[col] = lambda x, col=col: format_percentage(x, decimals=1, multiply_by_100=False)

    for col in date_columns:
        if col in df.columns:
            formatters[col] = lambda x, col=col: format_date(x)

    for col in (number_columns or []):
        if col in df.columns:
            formatters[col] = lambda x, col=col: format_number(x, decimals=2)

    return formatters