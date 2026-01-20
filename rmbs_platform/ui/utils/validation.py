"""
Validation Utilities
===================

Functions for validating user inputs and data formats.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


def validate_deal_json(deal_spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate deal specification JSON structure.

    Parameters
    ----------
    deal_spec : dict
        Deal specification to validate

    Returns
    -------
    tuple of (bool, list)
        (is_valid, error_messages)
    """
    errors = []

    # Required top-level keys
    required_keys = ["meta", "bonds", "waterfalls"]
    for key in required_keys:
        if key not in deal_spec:
            errors.append(f"Missing required key: '{key}'")

    # Meta validation
    if "meta" in deal_spec:
        meta = deal_spec["meta"]
        if not isinstance(meta, dict):
            errors.append("'meta' must be a dictionary")
        elif "deal_id" not in meta:
            errors.append("'meta.deal_id' is required")

    # Bonds validation
    if "bonds" in deal_spec:
        bonds = deal_spec["bonds"]
        if not isinstance(bonds, list):
            errors.append("'bonds' must be a list")
        elif len(bonds) == 0:
            errors.append("'bonds' list cannot be empty")
        else:
            for i, bond in enumerate(bonds):
                if not isinstance(bond, dict):
                    errors.append(f"bonds[{i}] must be a dictionary")
                elif "id" not in bond:
                    errors.append(f"bonds[{i}] missing 'id' field")

    # Waterfalls validation
    if "waterfalls" in deal_spec:
        waterfalls = deal_spec["waterfalls"]
        if not isinstance(waterfalls, dict):
            errors.append("'waterfalls' must be a dictionary")
        else:
            required_waterfalls = ["interest", "principal"]
            for wf_type in required_waterfalls:
                if wf_type not in waterfalls:
                    errors.append(f"Missing waterfall type: '{wf_type}'")

    return len(errors) == 0, errors


def validate_performance_csv(csv_content: str) -> Tuple[bool, List[str]]:
    """
    Validate performance data CSV format.

    Parameters
    ----------
    csv_content : str
        CSV content as string

    Returns
    -------
    tuple of (bool, list)
        (is_valid, error_messages)
    """
    errors = []

    try:
        # Parse CSV
        lines = csv_content.strip().split('\n')
        if len(lines) < 2:
            errors.append("CSV must have at least a header row and one data row")
            return False, errors

        # Check header
        header = lines[0].split(',')
        required_columns = ['Period', 'InterestCollected', 'PrincipalCollected']
        missing_columns = [col for col in required_columns if col not in header]

        if missing_columns:
            errors.append(f"Missing required columns: {', '.join(missing_columns)}")

        # Check data rows
        if len(lines) > 1:
            data_line = lines[1].split(',')
            if len(data_line) != len(header):
                errors.append("Data rows must have same number of columns as header")

            # Check Period is numeric
            try:
                int(data_line[header.index('Period')])
            except (ValueError, IndexError):
                errors.append("'Period' column must contain numeric values")

    except Exception as e:
        errors.append(f"CSV parsing error: {e}")

    return len(errors) == 0, errors


def validate_simulation_params(params: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate simulation parameters.

    Parameters
    ----------
    params : dict
        Simulation parameters to validate

    Returns
    -------
    tuple of (bool, list)
        (is_valid, error_messages)
    """
    errors = []

    # CPR validation
    cpr = params.get("cpr")
    if cpr is None:
        errors.append("CPR (prepayment rate) is required")
    elif not isinstance(cpr, (int, float)) or not (0.0 <= cpr <= 1.0):
        errors.append("CPR must be a number between 0.0 and 1.0")

    # CDR validation
    cdr = params.get("cdr")
    if cdr is None:
        errors.append("CDR (default rate) is required")
    elif not isinstance(cdr, (int, float)) or not (0.0 <= cdr <= 1.0):
        errors.append("CDR must be a number between 0.0 and 1.0")

    # Severity validation
    severity = params.get("severity")
    if severity is None:
        errors.append("Loss severity is required")
    elif not isinstance(severity, (int, float)) or not (0.0 <= severity <= 1.0):
        errors.append("Loss severity must be a number between 0.0 and 1.0")

    return len(errors) == 0, errors


def create_validation_ui(validator_func, data, title: str) -> bool:
    """
    Create a Streamlit UI for validation with expandable error display.

    Parameters
    ----------
    validator_func : callable
        Validation function that returns (is_valid, errors)
    data : any
        Data to validate
    title : str
        Validation section title

    Returns
    -------
    bool
        True if validation passes
    """
    is_valid, errors = validator_func(data)

    if is_valid:
        st.success(f"✅ {title} validation passed")
        return True
    else:
        with st.expander(f"❌ {title} validation failed ({len(errors)} issues)", expanded=True):
            for error in errors:
                st.error(error)
        return False