"""
Data Display Components
======================

Components for displaying data including metrics, KPIs, tables, and charts.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional, Union
import numpy as np

from ..utils.formatting import format_currency, format_percentage


def metric_card(
    title: str,
    value: Union[str, float, int],
    delta: Optional[Union[str, float]] = None,
    help_text: Optional[str] = None,
    format_type: str = "auto"
) -> None:
    """
    Display a metric in a card format.

    Parameters
    ----------
    title : str
        Metric title
    value : str, float, or int
        Metric value
    delta : str, float, optional
        Change indicator
    help_text : str, optional
        Help tooltip text
    format_type : str
        Formatting type ('currency', 'percentage', 'auto')
    """
    if format_type == "currency" and isinstance(value, (int, float)):
        display_value = format_currency(value)
    elif format_type == "percentage" and isinstance(value, (int, float)):
        display_value = format_percentage(value)
    else:
        display_value = str(value)

    st.metric(
        label=title,
        value=display_value,
        delta=str(delta) if delta is not None else None,
        help=help_text
    )


def kpi_dashboard(
    data: pd.DataFrame,
    metrics: List[Dict[str, Any]],
    title: Optional[str] = None
) -> None:
    """
    Display a dashboard of key performance indicators.

    Parameters
    ----------
    data : pd.DataFrame
        Data containing the metrics
    metrics : list of dict
        Metric definitions with keys:
        - 'column': DataFrame column name
        - 'title': Display title
        - 'aggregation': 'sum', 'mean', 'last', etc.
        - 'format': 'currency', 'percentage', 'auto'
        - 'help': Optional help text
    title : str, optional
        Dashboard title
    """
    if title:
        st.subheader(title)

    if data.empty:
        st.info("No data available for KPI dashboard")
        return

    # Calculate number of columns (max 4 per row)
    num_metrics = len(metrics)
    cols_per_row = min(4, num_metrics)
    rows_needed = (num_metrics + cols_per_row - 1) // cols_per_row

    metric_idx = 0
    for row in range(rows_needed):
        cols = st.columns(cols_per_row)

        for col_idx in range(cols_per_row):
            if metric_idx >= num_metrics:
                break

            metric_def = metrics[metric_idx]
            with cols[col_idx]:
                try:
                    # Support either a single column name or a list of candidate columns.
                    column = metric_def.get("column")
                    candidates = metric_def.get("columns")
                    if candidates is None and isinstance(column, (list, tuple)):
                        candidates = list(column)
                        column = None

                    if candidates:
                        resolved = next((c for c in candidates if c in data.columns), None)
                        if resolved is None:
                            st.warning(f"None of the columns {candidates} were found in data")
                            metric_idx += 1
                            continue
                        column = resolved
                    elif not column or column not in data.columns:
                        st.warning(f"Column '{column}' not found in data")
                        metric_idx += 1
                        continue

                    # Calculate value based on aggregation
                    aggregation = metric_def.get('aggregation', 'last')
                    if aggregation == 'sum':
                        value = data[column].sum()
                    elif aggregation == 'mean':
                        value = data[column].mean()
                    elif aggregation == 'last':
                        value = data[column].iloc[-1] if not data.empty else 0
                    elif aggregation == 'max':
                        value = data[column].max()
                    elif aggregation == 'min':
                        value = data[column].min()
                    else:
                        value = data[column].iloc[-1] if not data.empty else 0

                    # Handle delta calculation
                    delta = None
                    if 'delta_column' in metric_def:
                        delta_col = metric_def['delta_column']
                        if delta_col in data.columns:
                            if aggregation == 'last':
                                delta = data[delta_col].iloc[-1]
                            else:
                                delta = data[delta_col].sum()

                    metric_card(
                        title=metric_def['title'],
                        value=value,
                        delta=delta,
                        help_text=metric_def.get('help'),
                        format_type=metric_def.get('format', 'auto')
                    )

                except Exception as e:
                    st.error(f"Error calculating metric '{metric_def.get('title', 'Unknown')}': {e}")

            metric_idx += 1


def data_table(
    df: pd.DataFrame,
    title: Optional[str] = None,
    formatters: Optional[Dict[str, callable]] = None,
    max_rows: Optional[int] = None,
    searchable: bool = False,
    downloadable: bool = True
) -> None:
    """
    Display a formatted data table with optional features.

    Parameters
    ----------
    df : pd.DataFrame
        Data to display
    title : str, optional
        Table title
    formatters : dict, optional
        Column formatters {column_name: formatter_function}
    max_rows : int, optional
        Maximum rows to display (shows scroll for more)
    searchable : bool
        Whether to add search/filter functionality
    downloadable : bool
        Whether to add download button
    """
    if title:
        st.subheader(title)

    if df.empty:
        st.info("No data available")
        return

    # Apply formatters
    display_df = df.copy()
    if formatters:
        for col, formatter in formatters.items():
            if col in display_df.columns:
                try:
                    display_df[col] = display_df[col].apply(formatter)
                except Exception as e:
                    st.warning(f"Error formatting column '{col}': {e}")

    # Limit rows if specified
    if max_rows and len(display_df) > max_rows:
        st.info(f"Showing first {max_rows} of {len(display_df)} rows")
        display_df = display_df.head(max_rows)

    # Display table
    st.dataframe(display_df, use_container_width=True)

    # Download button
    if downloadable:
        csv_data = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"{title.lower().replace(' ', '_') if title else 'data'}.csv",
            mime="text/csv"
        )


def chart_container(
    chart_func: callable,
    title: str,
    height: Optional[int] = None,
    **kwargs
) -> None:
    """
    Container for charts with consistent styling.

    Parameters
    ----------
    chart_func : callable
        Function that returns a plotly figure
    title : str
        Chart title
    height : int, optional
        Chart height in pixels
    **kwargs
        Additional arguments passed to chart_func
    """
    try:
        fig = chart_func(**kwargs)

        if height:
            fig.update_layout(height=height)

        # Add consistent styling
        fig.update_layout(
            template="plotly_white",
            font=dict(size=12),
            margin=dict(l=20, r=20, t=40, b=20)
        )

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Error creating chart '{title}': {e}")


def cashflow_waterfall_chart(
    df: pd.DataFrame,
    bond_columns: Optional[List[str]] = None,
    title: str = "Bond Balance Evolution"
) -> go.Figure:
    """
    Create a cashflow waterfall chart showing bond balance evolution.

    Parameters
    ----------
    df : pd.DataFrame
        Cashflow data with Period column
    bond_columns : list of str, optional
        Bond balance columns to include (auto-detected if None)
    title : str
        Chart title

    Returns
    -------
    plotly.graph_objects.Figure
        Waterfall chart figure
    """
    if 'Period' not in df.columns:
        raise ValueError("DataFrame must contain 'Period' column")

    if bond_columns is None:
        bond_columns = [c for c in df.columns if 'Bond.' in c and 'Balance' in c]

    if not bond_columns:
        raise ValueError("No bond balance columns found")

    fig = go.Figure()

    # Color palette for multiple bonds
    colors = px.colors.qualitative.Set1

    for i, col in enumerate(bond_columns):
        bond_name = col.split('.')[1] if '.' in col else col
        color = colors[i % len(colors)]

        fig.add_trace(go.Scatter(
            x=df['Period'],
            y=df[col],
            mode='lines+markers',
            name=bond_name,
            line=dict(color=color, width=2),
            marker=dict(size=4),
            hovertemplate=f'{bond_name}: $%{{y:,.0f}}<extra></extra>'
        ))

    fig.update_layout(
        title=title,
        xaxis_title="Period",
        yaxis_title="Balance ($)",
        hovermode="x unified",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    return fig


def prepayment_curve_chart(
    df: pd.DataFrame,
    prepay_column: str = "Var.CPR",
    title: str = "Prepayment Rate Evolution"
) -> go.Figure:
    """
    Create a prepayment rate curve chart.

    Parameters
    ----------
    df : pd.DataFrame
        Data with prepayment rates
    prepay_column : str
        Column containing prepayment rates
    title : str
        Chart title

    Returns
    -------
    plotly.graph_objects.Figure
        Prepayment curve figure
    """
    if 'Period' not in df.columns or prepay_column not in df.columns:
        raise ValueError(f"DataFrame must contain 'Period' and '{prepay_column}' columns")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['Period'],
        y=df[prepay_column] * 100,  # Convert to percentage
        mode='lines+markers',
        name='Prepayment Rate',
        line=dict(color='orange', width=2),
        fill='tozeroy',
        hovertemplate='Period %{x}<br>CPR: %{y:.2f}%<extra></extra>'
    ))

    # Add average line
    avg_rate = df[prepay_column].mean() * 100
    fig.add_hline(
        y=avg_rate,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Avg: {avg_rate:.1f}%",
        annotation_position="top right"
    )

    fig.update_layout(
        title=title,
        xaxis_title="Period",
        yaxis_title="CPR (%)",
        hovermode="x unified"
    )

    return fig


def loss_distribution_chart(
    df: pd.DataFrame,
    loss_column: str = "RealizedLoss",
    title: str = "Cumulative Loss Distribution"
) -> go.Figure:
    """
    Create a cumulative loss distribution chart.

    Parameters
    ----------
    df : pd.DataFrame
        Data with loss information
    loss_column : str
        Column containing loss amounts
    title : str
        Chart title

    Returns
    -------
    plotly.graph_objects.Figure
        Loss distribution figure
    """
    if 'Period' not in df.columns or loss_column not in df.columns:
        raise ValueError(f"DataFrame must contain 'Period' and '{loss_column}' columns")

    # Calculate cumulative losses
    cumulative_losses = df[loss_column].cumsum()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['Period'],
        y=cumulative_losses,
        mode='lines+markers',
        name='Cumulative Losses',
        line=dict(color='red', width=2),
        fill='tozeroy',
        hovertemplate='Period %{x}<br>Cumulative Loss: $%{y:,.0f}<extra></extra>'
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Period",
        yaxis_title="Cumulative Loss ($)",
        hovermode="x unified"
    )

    return fig