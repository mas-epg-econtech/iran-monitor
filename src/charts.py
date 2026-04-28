from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Dark theme palette
# ---------------------------------------------------------------------------
_BG = "rgba(0,0,0,0)"       # transparent so the CSS glass card shows through
_GRID = "rgba(224, 230, 239, 0.08)"
_TEXT = "#c9d4e3"
_TEXT_MUTED = "rgba(224, 230, 239, 0.5)"
_HOVER_BG = "rgba(13, 27, 42, 0.92)"
_HOVER_BORDER = "rgba(194, 154, 81, 0.35)"
_TITLE_COLOR = "#f0d08a"

# Curated series palette — works well on dark backgrounds
_SERIES_COLORS = [
    "#60a5fa",   # sky blue
    "#f0d08a",   # gold
    "#34d399",   # emerald
    "#f87171",   # rose
    "#a78bfa",   # violet
    "#fb923c",   # orange
    "#22d3ee",   # cyan
    "#e879f9",   # fuchsia
    "#fbbf24",   # amber
    "#4ade80",   # green
]


def make_y_label(unit: str) -> str:
    if unit == "%":
        return "Percent (%)"
    if unit:
        return unit
    return "Value"


def make_date_formats(frequency: str, df: pd.DataFrame) -> tuple[str, str]:
    frequency_text = str(frequency).lower()
    if not frequency_text and "frequency" in df.columns:
        normalized_frequencies = {
            str(value).lower() for value in df["frequency"].dropna().unique() if str(value).strip()
        }
        if len(normalized_frequencies) == 1:
            frequency_text = normalized_frequencies.pop()

    if "month" in frequency_text:
        return "%b %Y", "%b %Y"
    return "%d %b %Y", "%b %Y"


def _apply_dark_layout(fig, chart_title: str, tick_date_format: str, hover_date_format: str,
                       y_title: str, margin_top: int | None = None):
    """Shared dark-theme layout settings."""
    resolved = str(chart_title).strip()
    top = margin_top if margin_top is not None else (70 if resolved else 24)

    fig.update_layout(
        template=None,
        height=450,
        font=dict(color=_TEXT, size=13, family="Inter, -apple-system, sans-serif"),
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        hovermode="x unified",
        margin=dict(l=70, r=20, t=top, b=60),
        legend=dict(
            title=None,
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(color=_TEXT, size=12),
        ),
        hoverlabel=dict(
            bgcolor=_HOVER_BG,
            bordercolor=_HOVER_BORDER,
            font=dict(color="#e0e6ef", size=13),
        ),
        colorway=_SERIES_COLORS,
    )
    if resolved:
        fig.update_layout(title=dict(
            text=resolved,
            font=dict(color=_TITLE_COLOR, size=18, family="Inter, sans-serif"),
            x=0.02,
            xanchor="left",
        ))
    else:
        fig.update_layout(title=None)

    fig.update_xaxes(
        showgrid=True,
        gridcolor=_GRID,
        linecolor="rgba(224, 230, 239, 0.12)",
        tickfont=dict(color=_TEXT_MUTED),
        title_text="",
        tickformat=tick_date_format,
        hoverformat=hover_date_format,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=_GRID,
        zeroline=False,
        linecolor="rgba(224, 230, 239, 0.12)",
        tickfont=dict(color=_TEXT_MUTED),
        title_font=dict(color=_TEXT_MUTED, size=11),
        title_text=y_title,
        title_standoff=10,
    )


def build_line_chart(df: pd.DataFrame, chart_title: str, unit: str, frequency: str):
    hover_date_format, tick_date_format = make_date_formats(frequency, df)

    fig = px.line(
        df,
        x="date",
        y="value",
        color="series_name",
        title=chart_title or None,
    )

    fig.update_traces(
        line=dict(width=2.5),
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            f"Date: %{{x|{hover_date_format}}}<br>"
            "Value: %{y}<extra></extra>"
        ),
    )

    _apply_dark_layout(fig, chart_title, tick_date_format, hover_date_format, make_y_label(unit))
    return fig


def build_dual_axis_chart(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    chart_title: str,
    left_unit: str,
    right_unit: str,
    frequency: str,
):
    combined_df = pd.concat([left_df, right_df], ignore_index=True)
    hover_date_format, tick_date_format = make_date_formats(frequency, combined_df)

    fig = go.Figure()

    color_idx = 0
    for series_name in left_df["series_name"].dropna().unique():
        series_df = left_df[left_df["series_name"] == series_name]
        legend_name = f"{series_name} (LHS)"
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df["value"],
                mode="lines",
                name=legend_name,
                line=dict(width=2.5, color=_SERIES_COLORS[color_idx % len(_SERIES_COLORS)]),
                hovertemplate=(
                    f"<b>{series_name}</b><br>"
                    f"Date: %{{x|{hover_date_format}}}<br>"
                    "Value: %{y}<extra></extra>"
                ),
                yaxis="y",
            )
        )
        color_idx += 1

    for series_name in right_df["series_name"].dropna().unique():
        series_df = right_df[right_df["series_name"] == series_name]
        legend_name = f"{series_name} (RHS)"
        fig.add_trace(
            go.Scatter(
                x=series_df["date"],
                y=series_df["value"],
                mode="lines",
                name=legend_name,
                line=dict(width=2.5, dash="dot",
                          color=_SERIES_COLORS[color_idx % len(_SERIES_COLORS)]),
                hovertemplate=(
                    f"<b>{series_name}</b><br>"
                    f"Date: %{{x|{hover_date_format}}}<br>"
                    "Value: %{y}<extra></extra>"
                ),
                yaxis="y2",
            )
        )
        color_idx += 1

    _apply_dark_layout(fig, chart_title, tick_date_format, hover_date_format, make_y_label(left_unit),
                       margin_top=70)

    fig.update_layout(
        margin=dict(l=70, r=70, t=70, b=60),
        yaxis2=dict(
            title=make_y_label(right_unit),
            title_standoff=10,
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            linecolor="rgba(224, 230, 239, 0.12)",
            tickfont=dict(color=_TEXT_MUTED),
            title_font=dict(color=_TEXT_MUTED, size=11),
        ),
    )

    return fig
