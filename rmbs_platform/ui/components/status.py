"""
Status Components
================

UI components for displaying status indicators, loading states,
and user feedback messages.
"""

from __future__ import annotations

import streamlit as st
from typing import Any, Optional, Union
from contextlib import contextmanager
import time


@contextmanager
def loading_spinner(message: str = "Loading...", delay: float = 0.1):
    """
    Context manager for loading spinner.

    Parameters
    ----------
    message : str
        Message to display during loading
    delay : float
        Delay before showing spinner (prevents flash for fast operations)
    """
    start_time = time.time()
    time.sleep(delay)

    with st.spinner(message):
        try:
            yield
        finally:
            # Ensure minimum display time for UX
            elapsed = time.time() - start_time
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)


def success_message(message: str, icon: str = "✅", celebration: bool = False) -> None:
    """
    Display success message with optional celebration.

    Parameters
    ----------
    message : str
        Success message to display
    icon : str
        Icon to prepend to message
    celebration : bool
        Whether to show celebration animation
    """
    st.success(f"{icon} {message}")
    if celebration:
        st.balloons()


def error_message(
    message: str,
    details: Optional[str] = None,
    show_retry: bool = False,
    retry_callback: Optional[callable] = None
) -> bool:
    """
    Display error message with optional retry functionality.

    Parameters
    ----------
    message : str
        Error message to display
    details : str, optional
        Additional error details
    show_retry : bool
        Whether to show retry button
    retry_callback : callable, optional
        Function to call when retry is clicked

    Returns
    -------
    bool
        True if retry was clicked, False otherwise
    """
    with st.expander(f"❌ {message}", expanded=True):
        st.error(message)
        if details:
            st.code(details, language="text")

        if show_retry and retry_callback:
            return st.button("🔄 Retry Operation", on_click=retry_callback)

    return False


def warning_message(message: str, details: Optional[str] = None) -> None:
    """
    Display warning message.

    Parameters
    ----------
    message : str
        Warning message
    details : str, optional
        Additional warning details
    """
    with st.expander(f"⚠️ {message}", expanded=False):
        st.warning(message)
        if details:
            st.info(details)


def progress_bar(
    progress: float,
    message: str = "",
    show_percentage: bool = True
) -> None:
    """
    Display progress bar with message.

    Parameters
    ----------
    progress : float
        Progress value between 0.0 and 1.0
    message : str
        Message to display with progress
    show_percentage : bool
        Whether to show percentage in message
    """
    # Ensure progress is between 0 and 1
    progress = max(0.0, min(1.0, progress))

    if show_percentage and message:
        display_message = f"{message} ({progress:.1%})"
    elif show_percentage:
        display_message = f"{progress:.1%}"
    else:
        display_message = message

    st.progress(progress, text=display_message)


def status_indicator(
    status: str,
    message: Optional[str] = None,
    details: Optional[str] = None
) -> None:
    """
    Display status indicator with appropriate styling.

    Parameters
    ----------
    status : str
        Status type ('success', 'error', 'warning', 'info', 'loading')
    message : str, optional
        Status message
    details : str, optional
        Additional status details
    """
    status = status.lower()

    if status == "success":
        icon = "✅"
        color_func = st.success
    elif status == "error":
        icon = "❌"
        color_func = st.error
    elif status == "warning":
        icon = "⚠️"
        color_func = st.warning
    elif status == "info":
        icon = "ℹ️"
        color_func = st.info
    elif status == "loading":
        icon = "⏳"
        with st.spinner(message or "Loading..."):
            time.sleep(0.1)
        return
    else:
        icon = "❓"
        color_func = st.info

    display_message = f"{icon} {message}" if message else icon

    if details:
        with st.expander(display_message, expanded=(status == "error")):
            color_func(display_message)
            st.write(details)
    else:
        color_func(display_message)


def simulation_progress_tracker(job_id: str, api_client):
    """
    Track simulation progress with real-time updates.

    Parameters
    ----------
    job_id : str
        Simulation job ID to track
    api_client : APIClient
        API client instance

    Yields
    ------
    dict
        Current status information
    """
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    while True:
        try:
            # This would be replaced with actual API call in real implementation
            # For now, just simulate progress
            import random
            progress = min(0.95, random.random())

            with progress_placeholder.container():
                progress_bar(progress, "Simulation Progress")

            with status_placeholder.container():
                if progress > 0.9:
                    st.success("Simulation nearly complete...")
                elif progress > 0.5:
                    st.info("Processing waterfall calculations...")
                else:
                    st.info("Initializing simulation...")

            if progress > 0.95:  # Simulate completion
                yield {"status": "completed", "progress": 1.0}
                break

            time.sleep(2)  # Update every 2 seconds

        except Exception as e:
            with status_placeholder.container():
                error_message(f"Progress tracking failed: {e}")
            break