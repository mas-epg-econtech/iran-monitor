#!/usr/bin/env python3
"""
Iran Monitor — top-level dashboard builder.

Produces 4 self-contained HTML pages from the unified iran_monitor.db and the
shipping nowcast outputs:
  - index.html          (landing — narrative + 3 nav cards)
  - global_shocks.html  (Energy + Shipping tabs)
  - singapore.html      (SG domestic prices + sectoral activity + 3 placeholders)
  - regional.html       (Regional financial markets + MAS EPG report cards + 3 placeholders)

Run from the Iran Monitor root:
  python3 scripts/build_iran_monitor.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path so we can import from src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection
from src.dependency_config import DEPENDENCY_NODES
from src.page_layouts import PAGES, PAGE_NAV, LANDING_CARDS
from src.flag_svgs import get_flag
from src.illustrations import get_hero
from src.series_descriptions import lookup as series_lookup, lookup_unit_title


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SINCE_DATE = "2021-01-01"   # Filter charts to data from this date onwards
CRISIS_DATE = "2026-02-28"  # Hormuz crisis onset (a.k.a. WAR_START); used for annotation
WAR_ZOOM_START = "2026-01-01"  # War-period view zoom start (~2 months pre-war for context)
OUTPUT_DIR = ROOT

# Short page-prefix used in deterministic chart IDs (see make_chart_id below).
# Format is `<page>.<tab>.[<panel>.]<card>` so the LLM narrative system can
# cite specific charts as anchor links that survive rebuilds.
PAGE_ID_PREFIX = {
    "global_shocks": "gs",
    "singapore":     "sg",
    "regional":      "rg",
    "home":          "home",
}

# Default relevance tags for each (page, tab) combination — feeds the LLM
# narrative system so each call knows which charts bear on which of the two
# overarching questions:
#   - "energy_supply"       — how concerned should we be about supply situation?
#   - "financial_markets"   — are markets showing signs of tightening?
# Sections / cards can override by setting their own `relevant_to` field;
# tabs not listed here default to no relevance (the LLM ignores).
TAB_RELEVANCE = {
    "global_shocks.energy":              ["energy_supply"],
    "global_shocks.shipping":            ["energy_supply"],
    "singapore.prices":                  ["energy_supply"],
    "singapore.sectoral_activity":       ["energy_supply"],
    "singapore.trade":                   ["energy_supply"],
    "singapore.shipping":                ["energy_supply"],
    "singapore.financial_markets":       ["financial_markets"],
    "regional.prices":                   ["energy_supply"],
    "regional.sectoral_activity":        ["energy_supply"],
    "regional.trade":                    ["energy_supply"],
    "regional.shipping":                 ["energy_supply"],
    "regional.financial_markets":        ["financial_markets"],   # default; commodity-section
                                                                  # override below switches
                                                                  # those cards to energy_supply.
}


# ---------------------------------------------------------------------------
# Chart-ID helpers
# ---------------------------------------------------------------------------
def _slug_for_id(s: str) -> str:
    """Lowercase, alphanumeric-only, underscores. Used as one segment of a
    deterministic chart ID. Empty-string input → "x" (so we never produce
    consecutive dots)."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "x"


def make_chart_id(page_prefix: str, tab_slug: str, card_slug: str,
                  used: dict, panel_slug: str = "") -> str:
    """Build a deterministic, collision-safe chart ID of form
    `<page>.<tab>.[<panel>.]<card>`. Examples:
        sg.activity.petroleum_refining
        gs.energy.crude_oil
        rg.shipping.cn.tankers           (panel = "cn" iso2 country code)
        rg.trade.fuel.id_monthly         (panel = "fuel" view-selector key)

    The same `used` dict (typically the page-level chart_state) is consulted
    for collisions; on collision we append `_2`, `_3`, … . `panel_slug` is
    optional and only inserted when the call site passes one (country panels
    and view selectors).
    """
    parts = [page_prefix, _slug_for_id(tab_slug or "main")]
    if panel_slug:
        parts.append(_slug_for_id(panel_slug))
    parts.append(_slug_for_id(card_slug))
    base = ".".join(parts)
    cid = base
    n = 2
    while cid in used:
        cid = f"{base}_{n}"
        n += 1
    return cid


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def fetch_series_data(conn, series_id: str, since: str = SINCE_DATE):
    rows = conn.execute(
        "SELECT date, value FROM time_series WHERE series_id = ? AND date >= ? ORDER BY date",
        (series_id, since),
    ).fetchall()
    return [(r["date"], r["value"]) for r in rows if r["value"] is not None]


def fetch_series_meta(conn, series_id: str) -> dict:
    """Try indicators table first, then fall back to time_series."""
    r = conn.execute(
        "SELECT series_name, unit, frequency, source FROM indicators WHERE series_id = ?",
        (series_id,),
    ).fetchone()
    if r:
        return {"name": r["series_name"], "unit": r["unit"] or "", "frequency": r["frequency"] or "", "source": r["source"] or ""}
    r = conn.execute(
        "SELECT series_name, unit, frequency, source FROM time_series WHERE series_id = ? LIMIT 1",
        (series_id,),
    ).fetchone()
    if r:
        return {"name": r["series_name"] or series_id, "unit": r["unit"] or "", "frequency": r["frequency"] or "", "source": r["source"] or ""}
    return {"name": series_id, "unit": "", "frequency": "", "source": ""}


import re as _re_resolver  # local alias to avoid clashing with module-scope use


def _slugify_for_gsheets(name: str, max_len: int = 55) -> str:
    """Mirror update_data._gsheets_slug — must stay in sync."""
    slug = _re_resolver.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()
    return slug[:max_len].rstrip('_')


def resolve_node_to_series_ids(conn, node_id: str) -> list[str]:
    """Resolve a dependency_config node to a concrete list of series_ids in the DB.

    Bloomberg series stored under series_id 'gsheets_<slug>' (slug derived from
    the series_name via _slugify_for_gsheets, mirroring the ingestion pipeline).
    Resolver uses LIKE on a slug PREFIX so small label drift between code and
    sheet doesn't break the link.
    """
    node = DEPENDENCY_NODES.get(node_id)
    if not node:
        return []
    series_ids = list(node.get("series_ids", []))

    for partial_label in node.get("google_sheet_series", []):
        # Slugify the first 35 chars of the label for a robust prefix match.
        prefix = _slugify_for_gsheets(partial_label[:35])
        if not prefix:
            continue
        matches = conn.execute(
            "SELECT DISTINCT series_id FROM time_series WHERE series_id LIKE ?",
            (f"gsheets_{prefix}%",),
        ).fetchall()
        for m in matches:
            sid = m["series_id"]
            if sid not in series_ids:
                series_ids.append(sid)
    return series_ids


# ---------------------------------------------------------------------------
# Chart.js dataset construction
# ---------------------------------------------------------------------------
COLOR_PALETTE = [
    "#60a5fa", "#f0d08a", "#34d399", "#f87171", "#a78bfa",
    "#fb923c", "#22d3ee", "#e879f9", "#fbbf24", "#4ade80",
]


# Stable colors for partners that appear in multiple stacked-bar charts
# across the dashboard. When a series's friendly_name (or its lookup-derived
# name) matches a key here, the renderer uses this fixed color instead of
# the position-based COLOR_PALETTE rotation. This keeps e.g. Qatar always
# green across every Trade Exposure chart even when the dataset positions
# differ (because Qatar isn't always the 3rd dataset shown).
STABLE_PARTNER_COLORS = {
    # ME-spotlight (Singapore Trade Exposure tab — mineral fuel imports)
    "UAE":          "#60a5fa",   # blue
    "Saudi Arabia": "#f0d08a",   # gold
    "Qatar":        "#34d399",   # green
    "Kuwait":       "#f87171",   # red
    "Iraq":         "#a78bfa",   # purple
    "Oman":         "#fb923c",   # orange
    "Others":       "#6b7280",   # neutral gray — always the residual segment

    # Regional (Singapore Trade Exposure tab — industrial chemical exports
    # combined card). Each country gets a fixed color so the shares chart
    # (left) and the levels chart (right) share a single visual legend.
    # The first 6 countries reuse the same color sequence as the ME
    # spotlight palette above (blue → gold → green → red → purple → orange)
    # for visual consistency between the import and export cards on the
    # same tab. The remaining 4 use distinct hues.
    "China":        "#60a5fa",   # blue          (matches UAE)
    "India":        "#f0d08a",   # gold          (matches Saudi Arabia)
    "Indonesia":    "#34d399",   # green         (matches Qatar)
    "Japan":        "#f87171",   # red           (matches Kuwait)
    "Malaysia":     "#a78bfa",   # purple        (matches Iraq)
    "Philippines":  "#fb923c",   # orange        (matches Oman)
    "South Korea":  "#06b6d4",   # cyan
    "Taiwan":       "#84cc16",   # lime
    "Thailand":     "#ec4899",   # pink
    "Vietnam":      "#14b8a6",   # teal

    # Regional Financial Markets — FX and bond legend labels mapped to
    # the same per-country hues so a country reads as the same color
    # across the FX chart, bonds chart, and any other chart that uses
    # one of these strings as its dataset label. US gets a slate baseline
    # since it doesn't appear in the regional 10.
    "Indonesian Rupiah": "#34d399",   # green  (same as Indonesia)
    "Malaysian Ringgit": "#a78bfa",   # purple (Malaysia)
    "Philippine Peso":   "#fb923c",   # orange (Philippines)
    "Thai Baht":         "#ec4899",   # pink   (Thailand)
    "Vietnamese Dong":   "#14b8a6",   # teal   (Vietnam)
    "Japanese Yen":      "#f87171",   # red    (Japan)
    "Chinese Yuan":      "#60a5fa",   # blue   (China)
    "US 10Y":            "#94a3b8",   # slate  — neutral US baseline
    "Indonesia 10Y":     "#34d399",
    "Malaysia 10Y":      "#a78bfa",
    "Philippines 10Y":   "#fb923c",
    "Thailand 10Y":      "#ec4899",
    "Vietnam 10Y":       "#14b8a6",

    # Singapore Shipping tab — nowcast actual/counterfactual styling.
    # Matches the country-level chart format from the original shipping-
    # nowcast dashboard's `createInlineChart` (line 4002-4003 of the
    # upstream build_nowcast_dashboard.py): blue for actual, AMBER for
    # counterfactual (NOT the purple used in the Hormuz chart). Every
    # nowcast subchart uses this same Actual + CF pair so colors stay
    # consistent across the whole tab.
    "Actual":                   "#3b82f6",   # blue, solid (no area fill)
    "Counterfactual (Primary)": "#f59e0b",   # amber, dashed
}


def _color_for_series(series: dict, idx: int) -> str:
    """Pick a chart color for one series. Falls back to position-based
    palette if the friendly name isn't in STABLE_PARTNER_COLORS."""
    fname = (series.get("friendly_name") or "").strip()
    if fname in STABLE_PARTNER_COLORS:
        return STABLE_PARTNER_COLORS[fname]
    return COLOR_PALETTE[idx % len(COLOR_PALETTE)]


# ---------------------------------------------------------------------------
# Source attribution helpers (mirror the original Energy Dashboard's chip logic)
# ---------------------------------------------------------------------------
def source_display_name(source: str) -> str:
    s = (source or "").lower().strip()
    if s == "ceic": return "CEIC"
    if s == "singstat": return "SingStat"
    if s in ("datagov_ipi", "datagov"): return "SingStat (EDB)"
    if "google" in s or "gsheet" in s: return "Bloomberg"
    if "motorist" in s: return "Motorist"
    if s.startswith("yfinance"): return "Yahoo Finance"
    if s.startswith("adb"): return "ADB AsianBondsOnline"
    if s.startswith("investing"): return "Investing.com"
    if "manual" in s: return "Manual"
    return source or "—"


def source_chip_class(source: str) -> str:
    s = (source or "").lower().strip()
    if "ceic" in s: return "ceic"
    if "bloomberg" in s or "google" in s or "gsheet" in s: return "bloomberg"
    if "singstat" in s or "datagov" in s: return "singstat"
    if "motorist" in s: return "motorist"
    if "yfinance" in s or "yahoo" in s: return "yfinance"
    if "adb" in s: return "adb"
    if "investing" in s: return "investing"
    return "other"


def _format_through(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
    except Exception:
        return date_str


def _build_meta_line(series: dict) -> str:
    """One row of attribution detail for a single series."""
    src_raw = series.get("source", "")
    src_label = html.escape(source_display_name(src_raw))
    chip = source_chip_class(src_raw)
    name = html.escape(series["name"])
    sid = html.escape(series.get("series_id", ""))
    freq = (series.get("frequency", "") or "").strip()
    unit = (series.get("unit", "") or "").strip()
    last_date = series["data"][-1][0] if series.get("data") else ""
    last_fmt = _format_through(last_date)

    freq_unit = " · ".join(p for p in (freq, unit) if p)

    parts = [f'<span class="source-chip {chip}">{src_label}</span>']
    if sid:
        parts.append(f'<span class="meta-detail">{sid}</span>')
    parts.append('<span class="meta-sep">|</span>')
    parts.append(f'<span class="meta-name">{name}</span>')
    if freq_unit:
        parts.append('<span class="meta-sep">|</span>')
        parts.append(html.escape(freq_unit))
    if last_fmt:
        parts.append('<span class="meta-sep">|</span>')
        parts.append(f'Through {html.escape(last_fmt)}')
    return f'<div class="chart-meta-line">{" ".join(parts)}</div>'


def _build_chart_meta_block(series_list: list[dict]) -> str:
    """Per-chart meta block. ≤3 series: one line each. >3 series: a single
    collapsed summary line listing all names with shared source/freq/unit (as
    the original does). Falls back to per-series lines if metadata varies."""
    if not series_list:
        return ""
    if len(series_list) <= 3:
        return f'<div class="chart-meta">{"".join(_build_meta_line(s) for s in series_list)}</div>'

    # Try to collapse if all series share source + freq + unit
    sources = {s.get("source", "") for s in series_list}
    freqs = {(s.get("frequency", "") or "") for s in series_list}
    units = {(s.get("unit", "") or "") for s in series_list}
    if len(sources) == 1 and len(freqs) <= 1 and len(units) <= 1:
        s0 = series_list[0]
        src_raw = s0.get("source", "")
        chip = source_chip_class(src_raw)
        src_label = html.escape(source_display_name(src_raw))
        names = ", ".join(html.escape(s["name"]) for s in series_list)
        freq_unit = " · ".join(p for p in (next(iter(freqs)), next(iter(units))) if p)
        latest = max((s["data"][-1][0] for s in series_list if s.get("data")), default="")
        last_fmt = _format_through(latest)

        parts = [f'<span class="source-chip {chip}">{src_label}</span>']
        parts.append('<span class="meta-sep">|</span>')
        parts.append(f'<span class="meta-name">{names}</span>')
        if freq_unit:
            parts.append('<span class="meta-sep">|</span>')
            parts.append(html.escape(freq_unit))
        if last_fmt:
            parts.append('<span class="meta-sep">|</span>')
            parts.append(f'Through {html.escape(last_fmt)}')
        return f'<div class="chart-meta"><div class="chart-meta-line">{" ".join(parts)}</div></div>'

    # Mixed metadata — fall back to per-series lines
    return f'<div class="chart-meta">{"".join(_build_meta_line(s) for s in series_list)}</div>'


def _format_category_label(date_str: str, freq_hint: str = "") -> str:
    """Pretty label for a category-axis tick. Year for annual, 'Mon YYYY' for monthly."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    f = (freq_hint or "").lower()
    if f == "annual" or (date_str.endswith("-12-31") and not f):
        return dt.strftime("%Y")
    return dt.strftime("%b %Y")


def _forward_fill_series_data(series_list: list[dict]) -> None:
    """In-place forward-fill of every series's `data` list so they share
    a common x-axis grid (the union of dates across all series).

    Required for time-axis line charts where some series are sparse
    (e.g. PH 10Y bond auctions, ~1-2 quotes per month). Without this,
    Chart.js's tooltip in 'index' mode omits any dataset without a point
    at the exact hovered x-coordinate, even though `spanGaps: true`
    draws a continuous line. Forward-fill carries the most recent prior
    value forward so every dataset has a point at every union-date.
    Doesn't backfill — dates before a series's first observation stay
    as nulls so we don't fabricate pre-history.
    """
    if not series_list:
        return
    all_dates = sorted({d for s in series_list for d, _ in s.get("data", [])})
    for s in series_list:
        existing = dict(s.get("data", []))   # date -> value
        filled = []
        last_val: float | None = None
        for d in all_dates:
            if d in existing:
                last_val = existing[d]
            # If last_val is None, we're before this series's first
            # observation — leave as None so Chart.js shows a gap.
            filled.append((d, last_val))
        s["data"] = filled


def build_chart_config(title: str, series_list: list[dict],
                       chart_type: str = "line",
                       x_axis_type: str = "time",
                       stacked: bool = False,
                       benchmark_y: float | None = None,
                       benchmark_label: str = "",
                       apply_default_war_zoom: bool = True,
                       default_to_zoomed_in: bool = False,
                       forward_fill: bool = False) -> dict:
    """Build a Chart.js config dict.

    Parameters:
      chart_type   — "line" (default) or "bar".
      x_axis_type  — "time" (default, with war-zoom logic + WAR_START annotation)
                     or "category" (discrete labels, no time machinery, no war
                     line; needed for sparse bar charts where time positioning
                     would create misleading gaps).

    For time-axis line charts: the first paint matches applyDateRange("war") —
    xMax=today, xMin=WAR_ZOOM_START walked back through data when the war
    window has fewer than MIN_WAR_POINTS distinct timestamps. Stale-data
    charts cluster their data on the left with an empty gap on the right.

    For category-axis bar charts: each dataset's data is the raw value list
    (in the order of the chart's category labels — taken from the FIRST
    series's dates). No war-line annotation. The page-wide date-range JS
    selector skips charts whose x-axis isn't 'time'.
    """
    distinct_units = {(s.get("unit", "") or "").strip() for s in series_list}
    distinct_units.discard("")
    common_unit = next(iter(distinct_units)) if len(distinct_units) == 1 else ""

    # Forward-fill sparse series (e.g. PH 10Y bond auction quotes ~1-2/month)
    # so the Chart.js tooltip in 'index' mode shows every series at every
    # hovered x-coordinate. Only applies to time-axis charts.
    if forward_fill and x_axis_type == "time":
        _forward_fill_series_data(series_list)

    use_category = (x_axis_type == "category")

    # Build category labels from the union of dates across all series, sorted.
    # Allows multi-series bar charts where each series contributes dates.
    if use_category:
        all_dates = sorted({d for s in series_list for d, _ in s["data"]})
        # Pretty tick labels — pull a frequency hint from the first series.
        freq_hint = (series_list[0].get("frequency", "") if series_list else "").strip() if series_list else ""
        category_labels = [_format_category_label(d, freq_hint) for d in all_dates]
    else:
        all_dates = []
        category_labels = []

    datasets = []
    for i, s in enumerate(series_list):
        color = _color_for_series(s, i)
        label = s.get("friendly_name") or s["name"]
        if not common_unit and s.get("unit"):
            label = f"{label} ({s['unit']})"

        if use_category:
            # Build a {date: value} lookup so we can align this series'
            # values to the chart's union-of-dates label list (filling
            # missing dates with null so Chart.js draws no bar there).
            by_date = {d: v for d, v in s["data"]}
            data_values = [by_date.get(d, None) for d in all_dates]
            ds = {
                "label": label,
                "data": data_values,
                "backgroundColor": color + "cc",   # ~80% alpha for solid-ish bars
                "borderColor": color,
                "borderWidth": 1,
                "borderRadius": 3,
            }
        else:
            data_points = [{"x": d, "y": v} for d, v in s["data"]]
            # Detect "Counterfactual"-style series by friendly_name and apply
            # the shipping-nowcast country-chart convention: blue solid line
            # (no area fill) + amber dashed counterfactual.
            fname_check = (s.get("friendly_name") or "").lower()
            is_counterfactual = "counterfactual" in fname_check
            is_nowcast_actual = (s.get("friendly_name") or "").strip() == "Actual"
            ds = {
                "label": label,
                "data": data_points,
                "borderColor": color,
                "backgroundColor": (color + "20"),
                "borderWidth": 1.5 if (is_counterfactual or is_nowcast_actual) else 1.6,
                "pointRadius": 0,
                "tension": 0 if (is_counterfactual or is_nowcast_actual) else 0.18,
                "spanGaps": True,
                "fill": False,
                **({"borderDash": [5, 3]} if is_counterfactual else {}),
            }
        datasets.append(ds)

    # ── X scale ──────────────────────────────────────────────────────────
    if use_category:
        x_scale = {
            "type": "category",
            "ticks": {"color": "rgba(224, 230, 239, 0.5)", "font": {"size": 10}, "maxTicksLimit": 12},
            "grid": {"color": "rgba(224, 230, 239, 0.06)"},
        }
    else:
        # When all series in this chart are quarterly, switch the x-axis to
        # quarter ticks ("Q1 2025") and a quarter-grained tooltip — per
        # dashboard feedback that quarterly series should not display monthly
        # ticks. Falls back to month otherwise.
        freqs = {(s.get("frequency", "") or "").strip().lower() for s in series_list}
        all_quarterly = bool(freqs) and freqs == {"quarterly"}
        x_scale = {
            "type": "time",
            "time": (
                {"unit": "quarter",
                 "displayFormats": {"quarter": "QQQ yyyy"},
                 "tooltipFormat": "QQQ yyyy"}
                if all_quarterly
                else {"unit": "month", "tooltipFormat": "MMM d, yyyy"}
            ),
            "ticks": {"color": "rgba(224, 230, 239, 0.5)", "font": {"size": 10}, "maxTicksLimit": 8},
            "grid": {"color": "rgba(224, 230, 239, 0.06)"},
        }
        # Default to "zoomed-in" view (3 months pre-WAR_START → today)
        # for nowcast cards. Same range the per-chart "Zoom In" button
        # produces — pre-baking it here makes the chart open in that state,
        # and the user can click "Zoom Out" to widen to the full data range.
        if default_to_zoomed_in:
            war_start_dt = datetime.strptime(CRISIS_DATE, "%Y-%m-%d")
            zoom_in_min = (war_start_dt - timedelta(days=91)).strftime("%Y-%m-%d")
            x_scale["min"] = zoom_in_min
            x_scale["max"] = datetime.now().strftime("%Y-%m-%d")
        # Mirror JS applyDateRange("war") logic so first paint matches.
        # Skipped when apply_default_war_zoom=False — that's used by charts
        # with their own per-chart zoom button (e.g. shipping nowcast cards
        # on Singapore + Regional), where the page-level "war" preset would
        # otherwise pre-bake a tighter window than the user's "Zoom In"
        # button produces, making "Zoom In" look like zoom-out.
        elif apply_default_war_zoom:
            MIN_WAR_POINTS = 8
            today_iso = datetime.now().strftime("%Y-%m-%d")
            x_scale["max"] = today_iso

            distinct_in_window = {
                pt[0] for s in series_list for pt in s["data"]
                if pt[0] >= WAR_ZOOM_START
            }
            if len(distinct_in_window) >= MIN_WAR_POINTS:
                x_scale["min"] = WAR_ZOOM_START
            else:
                all_distinct = sorted({pt[0] for s in series_list for pt in s["data"]})
                if all_distinct:
                    idx = max(0, len(all_distinct) - MIN_WAR_POINTS)
                    x_scale["min"] = all_distinct[idx]
                else:
                    x_scale["min"] = WAR_ZOOM_START

    config = {
        "type": chart_type,
        "data": ({"labels": category_labels, "datasets": datasets}
                 if use_category else {"datasets": datasets}),
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {
                "legend": {
                    "position": "top",
                    "labels": {"color": "#c9d4e3", "boxWidth": 18, "padding": 10, "font": {"size": 11}},
                },
                "title": {
                    "display": True,
                    "text": title,
                    "color": "#f0d08a",
                    "font": {"size": 14, "weight": "600"},
                    "padding": {"top": 4, "bottom": 12},
                },
                "tooltip": {
                    "backgroundColor": "rgba(13, 27, 42, 0.95)",
                    "borderColor": "rgba(194, 154, 81, 0.35)",
                    "borderWidth": 1,
                    "titleColor": "#e0e6ef",
                    "bodyColor": "#c9d4e3",
                    "padding": 10,
                },
                # Annotations: war-start vertical line (only for time-axis
                # charts) plus an optional horizontal benchmark line (used
                # for "vs 2023-25 monthly average" panels).
                **(_build_annotations(use_category, benchmark_y, benchmark_label) or {}),
            },
            "scales": {
                "x": {
                    **x_scale,
                    **({"stacked": True} if stacked else {}),
                },
                "y": {
                    "ticks": {"color": "rgba(224, 230, 239, 0.6)", "font": {"size": 10}},
                    "grid": {"color": "rgba(224, 230, 239, 0.06)"},
                    # Surface the chart's unit on the Y-axis when all series
                    # share it, instead of repeating it in every legend entry.
                    **({"title": {
                        "display": True,
                        "text": common_unit,
                        "color": "rgba(224, 230, 239, 0.5)",
                        "font": {"size": 10},
                    }} if common_unit else {}),
                    "beginAtZero": True if use_category else False,
                    **({"stacked": True} if stacked else {}),
                },
            },
        },
    }
    return config


def _build_annotations(use_category: bool, benchmark_y: float | None,
                       benchmark_label: str) -> dict:
    """Compose the chartjs-plugin-annotation block.

    Two annotations are possible:
      - warLine: vertical at WAR_START (CRISIS_DATE), only for time-axis charts
      - benchmarkLine: horizontal at y=benchmark_y, applies to any chart type
        — used for the "vs 2023-2025 monthly average" reference line on the
        SG Trade tab monthly-level cards.

    Returns {} when neither annotation applies.
    """
    annotations = {}
    if not use_category:
        annotations["warLine"] = {
            "type": "line",
            "xMin": CRISIS_DATE,
            "xMax": CRISIS_DATE,
            "borderColor": "rgba(248,113,113,0.55)",
            "borderWidth": 1.4,
            "borderDash": [4, 4],
            "label": {
                "content": "War",
                "display": True,
                "position": "start",
                "color": "rgba(248,113,113,0.85)",
                "backgroundColor": "rgba(0,0,0,0)",
                "font": {"size": 9, "weight": "600"},
                "padding": 2,
                "yAdjust": -4,
            },
        }
    if benchmark_y is not None:
        label_text = benchmark_label or f"Avg: {benchmark_y:,.0f}"
        annotations["benchmarkLine"] = {
            "type": "line",
            "yMin": benchmark_y,
            "yMax": benchmark_y,
            "borderColor": "rgba(240,208,138,0.6)",   # accent gold
            "borderWidth": 1.4,
            "borderDash": [6, 4],
            "label": {
                "content": label_text,
                "display": True,
                "position": "end",
                "color": "rgba(240,208,138,0.95)",
                "backgroundColor": "rgba(0,0,0,0)",
                "font": {"size": 9, "weight": "600"},
                "padding": 2,
                "yAdjust": -8,
            },
        }
    return {"annotation": {"annotations": annotations}} if annotations else {}


def render_date_range_bar() -> str:
    """The 'War period / 1Y / All time' selector bar — one per page; controls
    every chart on the page via the JS setDateRange() function. War period is
    the default selection (and now also leftmost since it's most-used)."""
    return '''
    <div class="date-range-bar">
      <span class="dr-label">Zoom</span>
      <button class="dr-btn dr-active" data-range="war" onclick="setDateRange('war')">War period</button>
      <button class="dr-btn" data-range="1y" onclick="setDateRange('1y')">1Y</button>
      <button class="dr-btn" data-range="all" onclick="setDateRange('all')">All time</button>
    </div>'''


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def render_landing_cards() -> str:
    """Render the three landing nav cards in a single row, no arrows."""
    cards_html = ""
    for c in LANDING_CARDS:
        title_safe = html.escape(c['title'])
        desc_safe = html.escape(c['description'])
        cards_html += f'''
        <a class="nav-card" href="{c['slug']}.html">
          <div class="nav-card-hero">{get_hero(c['slug'])}</div>
          <div class="nav-card-body">
            <h3>{title_safe}</h3>
            <p>{desc_safe}</p>
          </div>
        </a>'''
    return f'<div class="nav-cards-grid">{cards_html}</div>'


_BENCHMARKS_CACHE: dict | None = None


def _get_trade_benchmarks(conn) -> dict:
    """Load the {series_id: monthly_avg_value} dict stashed in metadata by
    the Singapore Trade tab derivations. Cached for the build run.
    """
    global _BENCHMARKS_CACHE
    if _BENCHMARKS_CACHE is not None:
        return _BENCHMARKS_CACHE
    r = conn.execute(
        "SELECT value FROM metadata WHERE key = 'trade_chart_benchmarks'"
    ).fetchone()
    if not r or not r["value"]:
        _BENCHMARKS_CACHE = {}
    else:
        try:
            _BENCHMARKS_CACHE = json.loads(r["value"])
        except (TypeError, ValueError):
            _BENCHMARKS_CACHE = {}
    return _BENCHMARKS_CACHE


def render_chart_grid(section: dict, conn, chart_state: dict, data_sources_state: dict,
                      tab_slug: str | None = None,
                      page_prefix: str = "x",
                      panel_slug: str = "",
                      default_relevance: list[str] | None = None) -> str:
    """Render a chart_grid section.

    Two ways to specify the charts in this grid (can be combined in one section):
      - `nodes`: an ordered list whose items are either:
            * a string  → resolves to a dependency_config node
            * a dict    → custom series group: {"label": "...", "description": "...",
                                                "series": ["series_id", ...]}
        The order is preserved, allowing custom groups to be interleaved with nodes.
      - `series_groups`: a list of (label, [series_ids]) tuples — kept for backward
        compatibility with the Regional Financial Markets section.

    Optional section keys:
      - `chart_type`:  "line" (default) or "bar"
      - `x_axis_type`: "time" (default) or "category" (sparse bars; ignores war zoom)
      - `columns`:     int — when set, forces grid-template-columns: repeat(N, 1fr)
                       so cards pair predictably per row (e.g. annual/monthly).

    Auto-split: when a single node/group resolves to series with >1 distinct unit,
    the renderer emits one chart card per unit (titled "{label} — {unit}") so that
    incompatible scales aren't squashed onto the same y-axis. Auto-split is
    suppressed for category-axis charts (the bar layouts assume sparse single-
    series data per card and skip the split entirely).

    `tab_slug` is forwarded to each chart card so the page-bottom Data Sources
    table can filter its rows by active tab.
    """
    title = section.get("title", "")
    desc = section.get("description", "")
    chart_type = section.get("chart_type", "line")
    x_axis_type = section.get("x_axis_type", "time")
    columns = section.get("columns")
    stacked = section.get("stacked", False)
    # benchmark_y can be a constant (same for every card in the section) or
    # a per-card override via the node dict's "benchmark_y" key.
    section_benchmark_y = section.get("benchmark_y")
    section_benchmark_label = section.get("benchmark_label", "")
    # Per-chart "Zoom In/Out" toggle (mirrors the original shipping nowcast
    # dash). Used on Singapore Shipping nowcast cards where the longer
    # historical context dominates the post-war detail.
    section_zoom_button = bool(section.get("zoom_button", False))
    # Per-section overrides for Chart.js plugin title / legend visibility.
    # Defaults are None (= "auto-decide" — see _render_chart_card_for_series:
    # the chart title is auto-suppressed when the card already has an <h3>,
    # and the legend is auto-suppressed for single-series charts since the
    # series name otherwise appears 3× per card: h3, chart title, legend).
    section_hide_chart_title = section.get("hide_chart_title")
    section_hide_legend      = section.get("hide_legend")
    # Relevance for the LLM narrative pipeline. Section-level override wins
    # over the tab-level default; per-card override (in the dict-node)
    # wins over both. Charts with no relevance tag are passed through
    # to the manifest with empty list — the LLM ignores them.
    section_relevance = section.get("relevant_to") or default_relevance or []
    # Forward-fill sparse series in the chart so every dataset has a
    # value at every hovered x-coordinate. Required when one series is
    # much sparser than the others (e.g. PH 10Y auction quotes vs the
    # daily ID/MY/TH/VN sovereigns) — without this, Chart.js's tooltip
    # in 'index' mode silently drops the sparse series.
    section_forward_fill = bool(section.get("forward_fill", False))

    cards = []

    def _emit(label: str, description: str, series_ids: list[str], base_prefix: str,
              card_benchmark_y: float | None = None, card_benchmark_label: str = "",
              data_min_date: str | None = None,
              card_relevance: list[str] | None = None):
        """Resolve series_ids, split by unit if needed, and emit one or more chart cards.

        Title/description selection rules per emitted chart:
          - If the chart has exactly one series AND that series has a friendly
            name in series_descriptions, use "{label} — {friendly_name}" as the
            title and the series-specific description (overrides the node's
            generic description). This is the case the user asked for —
            "Jet Fuel — NWE FOB Barges" instead of "Jet Fuel — USD/metric tonne".
          - Otherwise, fall back to the unit suffix ("Crude Oil — USD/Barrel")
            for the multi-unit-split case, or just the node label for single-unit
            groups.
        """
        # Per-card benchmark override (falls back to section-level value).
        # If neither is set, fall back to the auto-lookup against the
        # `trade_chart_benchmarks` metadata stash — which is populated by
        # the Singapore Trade tab derivations and keyed by series_id.
        bench_y = card_benchmark_y if card_benchmark_y is not None else section_benchmark_y
        bench_label = card_benchmark_label or section_benchmark_label
        if bench_y is None and series_ids:
            benchmarks = _get_trade_benchmarks(conn)
            for sid in series_ids:
                if sid in benchmarks:
                    bench_y = benchmarks[sid]
                    if not bench_label:
                        bench_label = "2023-25 monthly avg"
                    break

        series_list = _resolve_series_list(conn, series_ids)
        # Apply data_min_date filter (e.g. transport indicators "Jan 2025"
        # truncation per dashboard feedback — clip out earlier data points
        # so the chart starts at the chosen baseline).
        if data_min_date:
            for s in series_list:
                s["data"] = [(d, v) for (d, v) in s["data"] if d >= data_min_date]
            # Drop any series that became empty after clipping
            series_list = [s for s in series_list if s["data"]]
        # Card relevance: per-card override > section override > tab default.
        relevance = card_relevance if card_relevance is not None else section_relevance
        if not series_list:
            cards.append(_render_chart_card_for_series(
                label, description, [],
                chart_state, base_prefix, data_sources_state, tab_slug,
                page_prefix=page_prefix, panel_slug=panel_slug,
                chart_type=chart_type, x_axis_type=x_axis_type,
                stacked=stacked, benchmark_y=bench_y, benchmark_label=bench_label,
                zoom_button=section_zoom_button,
                hide_chart_title=section_hide_chart_title,
                hide_legend=section_hide_legend,
                forward_fill=section_forward_fill,
                relevant_to=relevance))
            return
        # Skip auto-split-by-unit for category-axis charts — the bar layouts
        # are designed around per-card single-series sparse data.
        unit_groups = [(None, series_list)] if x_axis_type == "category" else _split_by_unit(series_list)
        for unit, sublist in unit_groups:
            # Decide title + description + prefix based on group composition
            single_friendly = (
                len(sublist) == 1 and sublist[0].get("friendly_name") and sublist[0].get("friendly_desc")
            )
            if single_friendly:
                fname = sublist[0]["friendly_name"]
                # The auto-suffix is only useful as a disambiguator when the
                # node produces multiple cards (e.g. jet_fuel emits 3 cards
                # for NWE / SG / PADD-1). If the entire node yields just one
                # card, the friendly_name suffix is just redundant repetition
                # of what the label already says.
                _fname_l = fname.lower()
                _label_l = label.lower()
                only_one_card = (len(unit_groups) == 1 and len(sublist) == 1)
                title_drops_suffix = (
                    only_one_card
                    or _fname_l == _label_l
                    or _fname_l in _label_l
                    or _label_l in _fname_l
                )
                if title_drops_suffix:
                    chart_title = label
                else:
                    chart_title = f"{label} — {fname}"
                # If the node explicitly set a description (including ""), respect
                # it — caller wants to override the auto-substituted friendly_desc.
                # The convention: an empty string means "no description, the
                # section header explains everything"; a non-empty string is
                # used as-is; a None/missing value falls back to friendly_desc.
                if description is None:
                    chart_desc = sublist[0]["friendly_desc"]
                else:
                    chart_desc = description
                # Mirror the title decision in the prefix: when the friendly_name
                # is redundant with the label (so we dropped it from the title),
                # don't append it to the chart-ID prefix either — otherwise we'd
                # produce stuttering IDs like
                # `sg.financial_markets.sora_3m_compounded_sora_3m_compounded`.
                if title_drops_suffix:
                    chart_prefix = base_prefix
                else:
                    chart_prefix = f"{base_prefix}_{_unit_slug(fname)}"
            elif unit is None:
                # Single-unit group, no split, no friendly override
                chart_title = label
                chart_desc = description
                chart_prefix = base_prefix
            else:
                # Multi-unit split — use editorial override if defined for this
                # (node, unit), otherwise fall back to the bare unit string.
                unit_override = lookup_unit_title(base_prefix, unit)
                title_suffix = unit_override if unit_override else unit
                chart_title = f"{label} — {title_suffix}"
                chart_desc = description
                chart_prefix = f"{base_prefix}_{_unit_slug(unit)}"
            cards.append(_render_chart_card_for_series(
                chart_title, chart_desc, sublist,
                chart_state, chart_prefix, data_sources_state, tab_slug,
                page_prefix=page_prefix, panel_slug=panel_slug,
                chart_type=chart_type, x_axis_type=x_axis_type,
                stacked=stacked, benchmark_y=bench_y, benchmark_label=bench_label,
                zoom_button=section_zoom_button,
                hide_chart_title=section_hide_chart_title,
                hide_legend=section_hide_legend,
                forward_fill=section_forward_fill,
                relevant_to=relevance))

    # Mode 1: ordered `nodes` list (mix of node refs and custom groups)
    for item in section.get("nodes", []):
        if isinstance(item, str):
            node = DEPENDENCY_NODES.get(item)
            if not node:
                continue
            sids = resolve_node_to_series_ids(conn, item)
            _emit(node["label"], node.get("description"), sids, base_prefix=item)
        elif isinstance(item, dict):
            base = item.get("slug") or item["label"].lower().replace(" ", "_").replace("(", "").replace(")", "")
            # New: a node with `subcharts` renders as ONE wide card containing
            # multiple side-by-side sub-plots. Used by the Singapore Trade
            # Exposure tab where each SITC's annual-shares + monthly-levels
            # share one card with one description.
            if "subcharts" in item:
                cards.append(_render_chart_card_with_subcharts(
                    item["label"], item.get("description", ""),
                    item["subcharts"], conn,
                    chart_state, base, data_sources_state, tab_slug,
                    page_prefix=page_prefix, panel_slug=panel_slug,
                    zoom_button=section_zoom_button,
                    single_legend=bool(item.get("single_legend", False)
                                       or section.get("single_legend", False)),
                    relevant_to=item.get("relevant_to") or section_relevance,
                ))
                continue
            _emit(
                item["label"],
                item.get("description"),     # None if absent → friendly_desc fallback
                item["series"],
                base_prefix=base,
                card_benchmark_y=item.get("benchmark_y"),
                card_benchmark_label=item.get("benchmark_label", ""),
                # Optional ISO date "YYYY-MM-DD" — clip data points before this
                # date out of the chart entirely (per dashboard feedback for
                # seasonal transport indicators starting Jan 2025).
                data_min_date=item.get("data_min_date"),
                # Per-card relevance override (rare — used e.g. for the regional
                # commodity-prices section's per-card overrides).
                card_relevance=item.get("relevant_to"),
            )

    # Mode 2: explicit series_groups tuples (kept for Regional Financial Markets)
    for group_label, sids in section.get("series_groups", []):
        _emit(group_label, "", sids, base_prefix=group_label.replace(" ", "_"))

    inner = "\n".join(cards)
    desc_html = f'<p class="section-desc">{desc}</p>' if desc else ""
    # Inline-style override when the section pins a column count, so cards
    # pair predictably (e.g. annual/monthly per row). Default uses the
    # auto-fill behaviour from the .chart-grid CSS class.
    grid_style = f' style="grid-template-columns: repeat({columns}, 1fr);"' if columns else ""
    # When columns==1 the card is full-width on its row; let the description
    # span the full card width too (otherwise the 64ch cap on .card-desc
    # leaves the text only spanning ~half the card).
    grid_class_extra = " chart-grid-single" if columns == 1 else ""
    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{title}</h2>
        {desc_html}
      </div>
      <div class="chart-grid{grid_class_extra}"{grid_style}>
        {inner}
      </div>
    </section>'''


def _resolve_series_list(conn, series_ids: list[str]) -> list[dict]:
    """Resolve series_ids to a list of dicts containing {series_id, name, unit,
    frequency, source, data, friendly_name, friendly_desc} — one entry per
    series with at least one data point. friendly_name/desc come from
    src/series_descriptions.py if mapped, otherwise None."""
    series_list = []
    for sid in series_ids:
        data = fetch_series_data(conn, sid)
        if not data:
            continue
        meta = fetch_series_meta(conn, sid)
        nice_name = meta["name"]
        if nice_name.startswith("gsheets_"):  # shouldn't normally hit
            nice_name = sid
        if len(nice_name) > 60:
            nice_name = nice_name[:57] + "..."
        # Try series_id first (most stable for short IDs like motorist_92 whose
        # series_name rotates with the scraped sample), then fall back to
        # series_name (handles long Bloomberg labels whose series_id is
        # truncated at 64 chars in the DB).
        info = series_lookup(sid, meta["name"])
        series_list.append({
            "series_id": sid,
            "name": nice_name,
            "unit": meta["unit"],
            "frequency": meta["frequency"],
            "source": meta["source"],
            "data": data,
            "friendly_name": info["name"] if info else None,
            "friendly_desc": info["desc"] if info else None,
        })
    return series_list


def _split_by_unit(series_list: list[dict]) -> list[tuple]:
    """Group series by unit. Returns [(unit, sublist), ...] in insertion order
    if there are >1 distinct units, otherwise [(None, series_list)] meaning
    'no split needed'. The None sentinel tells the caller to use the original
    label/prefix unchanged."""
    units_seen: list[str] = []
    by_unit: dict[str, list[dict]] = {}
    for s in series_list:
        u = (s.get("unit", "") or "").strip()
        if u not in by_unit:
            units_seen.append(u)
            by_unit[u] = []
        by_unit[u].append(s)
    if len(units_seen) <= 1:
        return [(None, series_list)]
    return [(u, by_unit[u]) for u in units_seen]


def _unit_slug(u: str) -> str:
    """Slugify a unit string for use in chart_id prefixes."""
    if not u:
        return "no_unit"
    s = "".join(c if c.isalnum() else "_" for c in u.lower()).strip("_")
    # Collapse repeated underscores
    while "__" in s:
        s = s.replace("__", "_")
    return s[:30] or "unit"


def _render_chart_card_for_series(title: str, description: str, series_list: list[dict],
                                   chart_state: dict, prefix: str, data_sources_state: dict,
                                   tab_slug: str | None = None,
                                   page_prefix: str = "x",
                                   panel_slug: str = "",
                                   chart_type: str = "line",
                                   x_axis_type: str = "time",
                                   stacked: bool = False,
                                   benchmark_y: float | None = None,
                                   benchmark_label: str = "",
                                   zoom_button: bool = False,
                                   hide_chart_title: bool | None = None,
                                   hide_legend: bool | None = None,
                                   forward_fill: bool = False,
                                   relevant_to: list[str] | None = None) -> str:
    """Render one chart card from a pre-resolved series_list (no DB I/O inside).

    Chart ID is deterministic: <page_prefix>.<tab_slug>.[<panel_slug>.]<prefix>.
    See make_chart_id() — collisions get `_2`, `_3`, … suffixes.

    `hide_chart_title` and `hide_legend` default to None ("auto-decide"):
      - chart title is suppressed whenever the card has an <h3> above the
        canvas (since the h3 already shows the same text — having both is
        redundant).
      - legend is suppressed for single-series charts (one dataset → the
        legend is just a repeat of the chart title and h3).
    Pass an explicit True/False to force one way or the other.
    """
    if not series_list:
        return f'''
        <div class="chart-card">
          <div class="chart-empty">
            <h3>{html.escape(title)}</h3>
            <p class="muted">No data available for this series.</p>
          </div>
        </div>'''

    chart_id = make_chart_id(page_prefix, tab_slug or "", prefix, chart_state,
                              panel_slug=panel_slug)
    chart_state[chart_id] = build_chart_config(title, series_list,
                                                chart_type=chart_type,
                                                x_axis_type=x_axis_type,
                                                stacked=stacked,
                                                benchmark_y=benchmark_y,
                                                benchmark_label=benchmark_label,
                                                apply_default_war_zoom=not zoom_button,
                                                default_to_zoomed_in=zoom_button,
                                                forward_fill=forward_fill)
    # Auto-decide redundancy suppression unless caller forced a value.
    has_h3 = bool((title or "").strip())
    if hide_chart_title is None:
        hide_chart_title = has_h3                  # h3 above already shows it
    if hide_legend is None:
        hide_legend = (len(series_list) <= 1)      # single dataset = redundant
    if hide_chart_title:
        chart_state[chart_id]["options"]["plugins"]["title"]["display"] = False
    if hide_legend:
        chart_state[chart_id]["options"]["plugins"]["legend"]["display"] = False

    title_safe = html.escape(title)
    desc_html = f'<p class="card-desc">{html.escape(description)}</p>' if description else ""

    # Record series metadata for the page-level Data Sources table and the
    # downstream summary-stats extractor (which is what the LLM narrative
    # system consumes).
    data_sources_state[chart_id] = {
        "title": title,
        "description": description or "",
        "series": series_list,
        "tab_slug": tab_slug,
        "page_prefix": page_prefix,
        "relevant_to": list(relevant_to or []),
    }
    # Mark charts that own their zoom so applyDateRange can skip them.
    if zoom_button:
        data_sources_state[chart_id]["_no_default_zoom"] = True

    # Cards with a per-chart zoom button open in the zoomed-in state by
    # default (button label "Zoom Out", "active" class so the user can
    # widen to full history).
    zoom_btn_html = (
        f'<div class="chart-actions"><button class="zoom-toggle-btn active" '
        f'data-target="{chart_id}" data-default-zoomed-in="true" '
        f'onclick="toggleChartZoom(this)" '
        f'title="Show the full data range">Zoom Out</button></div>'
        if zoom_button else ""
    )

    # Visible chart-ID badge — small monospace tag at the BOTTOM of the card
    # so it doesn't compete visually with the title. Lets the LLM narrative
    # cite charts by ID and the reader visually match the citation. Click
    # to copy the URL fragment to the clipboard.
    chart_id_badge = (
        f'<a class="chart-id-badge" href="#{chart_id}" '
        f'data-chart-id="{chart_id}" title="Click to copy link to this chart">'
        f'⌗ {chart_id}</a>'
    )
    badge_footer = f'<div class="chart-id-footer">{chart_id_badge}</div>'

    # Suppress the card-header div entirely when there's no title AND no
    # description (e.g., the FX/bond yields full-width single-card sections
    # where the section h2 is the only header needed).
    if title_safe or desc_html:
        header_html = (
            f'<div class="card-header">'
            + (f'<h3>{title_safe}</h3>' if title_safe else '')
            + desc_html
            + '</div>'
        )
    else:
        header_html = ""

    return f'''
    <div class="chart-card" id="card-{chart_id}">
      {header_html}
      <div class="chart-container"><canvas id="{chart_id}"></canvas></div>
      {zoom_btn_html}
      {badge_footer}
    </div>'''


def _render_chart_card_with_subcharts(
    title: str, description: str, subcharts: list[dict], conn,
    chart_state: dict, prefix: str, data_sources_state: dict,
    tab_slug: str | None = None,
    page_prefix: str = "x",
    panel_slug: str = "",
    zoom_button: bool = False,
    single_legend: bool = False,
    relevant_to: list[str] | None = None,
) -> str:
    """Render ONE wide chart card containing multiple side-by-side sub-charts.

    Used by the Singapore Trade Exposure tab — each SITC gets one card with
    two sub-charts inside (annual shares on left, monthly levels on right),
    sharing the card's title + description.

    Each subchart dict supports the same chart options as a top-level chart
    grid: subtitle (the per-subchart heading shown above its canvas), series
    (list of series_ids), chart_type, x_axis_type, stacked, benchmark_y, etc.

    `single_legend=True` suppresses each subchart's individual Chart.js
    legend and renders ONE HTML legend at the card header. Use when all
    subcharts share the same set of dataset labels (e.g. trade exposure
    cards where the left chart has 10 partners and the right has 10
    partners + Others).
    """
    title_safe = html.escape(title)
    desc_html = f'<p class="card-desc">{html.escape(description)}</p>' if description else ""

    # Auto-fill benchmarks once (shared between subcharts)
    benchmarks = _get_trade_benchmarks(conn)

    # Compute the parent card's deterministic chart-ID up front so subcharts
    # can reference it (parent_chart_id field on each subchart entry, plus
    # the parent's own data_sources_state entry registered after the loop).
    parent_chart_id_parts = [page_prefix, _slug_for_id(tab_slug or "main")]
    if panel_slug:
        parent_chart_id_parts.append(_slug_for_id(panel_slug))
    parent_chart_id_parts.append(_slug_for_id(prefix))
    parent_chart_id = ".".join(parent_chart_id_parts)

    # Collect (label, color) pairs across all subcharts for the optional
    # single shared legend at the card header. Dedupe by label, preserve
    # first-seen order — so the legend reflects the first subchart's
    # ordering plus any new labels (e.g. "Others") added in later subcharts.
    legend_seen: dict[str, str] = {}
    # Aggregate subchart-level info so we can register the PARENT card in
    # data_sources_state at the end of the loop. Without this, multi-subchart
    # cards (SG Trade SITC × 6, Shipping tankers/containers, etc.) wouldn't
    # appear in the manifest at all — only their subchart entries would,
    # and the summary-stats extractor skips entries with parent_chart_id.
    parent_series_acc: list[dict] = []
    parent_series_seen: set[str]   = set()
    subchart_meta: list[dict]      = []

    sub_html_blocks = []
    for sub_idx, sub in enumerate(subcharts):
        subtitle = sub.get("subtitle", "")
        sub_series_ids = sub.get("series", [])
        sub_chart_type = sub.get("chart_type", "bar")
        sub_x_axis = sub.get("x_axis_type", "category")
        sub_stacked = sub.get("stacked", True)
        sub_bench_y = sub.get("benchmark_y")
        sub_bench_lbl = sub.get("benchmark_label", "")

        # Auto-attach benchmark from metadata if not explicitly set.
        if sub_bench_y is None:
            for sid in sub_series_ids:
                if sid in benchmarks:
                    sub_bench_y = benchmarks[sid]
                    if not sub_bench_lbl:
                        sub_bench_lbl = "2023-25 monthly avg"
                    break

        series_list = _resolve_series_list(conn, sub_series_ids)
        if not series_list:
            sub_html_blocks.append(
                f'<div class="subchart"><h4 class="subchart-title">{html.escape(subtitle)}</h4>'
                f'<p class="muted">No data available.</p></div>'
            )
            continue

        # Subchart ID uses the parent card slug + the subchart's subtitle as
        # additional segments — stable across rebuilds.
        sub_card_slug = f"{prefix}__{_slug_for_id(subtitle) or f'sub{sub_idx}'}"
        sub_chart_id = make_chart_id(page_prefix, tab_slug or "", sub_card_slug,
                                      chart_state, panel_slug=panel_slug)
        # Don't show the Chart.js title (we use the subtitle h4 as the label)
        chart_state[sub_chart_id] = build_chart_config(
            "", series_list,
            chart_type=sub_chart_type,
            x_axis_type=sub_x_axis,
            stacked=sub_stacked,
            benchmark_y=sub_bench_y,
            benchmark_label=sub_bench_lbl,
            apply_default_war_zoom=not zoom_button,
            default_to_zoomed_in=zoom_button,
        )
        # Suppress the Chart.js title display since we render the subtitle in HTML
        chart_state[sub_chart_id]["options"]["plugins"]["title"]["display"] = False

        # Auto-suppress legend for single-series subcharts (the subtitle h4
        # already names the series — having a legend with the same label
        # would be redundant).
        if len(series_list) <= 1:
            chart_state[sub_chart_id]["options"]["plugins"]["legend"]["display"] = False

        # If the card uses a single shared legend, suppress per-subchart
        # legends and remember each dataset's (label, color) for the
        # consolidated legend rendered at the card header.
        if single_legend:
            chart_state[sub_chart_id]["options"]["plugins"]["legend"]["display"] = False
            for ds_idx, s in enumerate(series_list):
                fname = (s.get("friendly_name") or "").strip() or s.get("name") or s["series_id"]
                color = _color_for_series(s, ds_idx)
                legend_seen.setdefault(fname, color)

        # Register every subchart in data_sources_state so the
        # page-bottom Sources panel still picks up its series.
        data_sources_state[sub_chart_id] = {
            "title":       f"{title} — {subtitle}",
            "description": description or "",
            "series":      series_list,
            "tab_slug":    tab_slug,
            "page_prefix": page_prefix,
            "relevant_to": list(relevant_to or []),
            "parent_chart_id": parent_chart_id,
        }
        # Mark subcharts with their own zoom button so applyDateRange skips them.
        if zoom_button:
            data_sources_state[sub_chart_id]["_no_default_zoom"] = True

        # Accumulate subchart info for the parent's manifest entry. The
        # parent card_id is what the LLM cites; without this, multi-subchart
        # cards wouldn't appear in summary_stats.json at all (the extractor
        # filters out entries with parent_chart_id).
        for s in series_list:
            sid = s.get("series_id")
            if sid and sid not in parent_series_seen:
                parent_series_seen.add(sid)
                parent_series_acc.append(s)
        subchart_meta.append({
            "subtitle":   subtitle,
            "subchart_id": sub_chart_id,
            "series_ids": [s.get("series_id") for s in series_list if s.get("series_id")],
        })

        sub_zoom_btn = (
            f'<div class="chart-actions"><button class="zoom-toggle-btn active" '
            f'data-target="{sub_chart_id}" data-default-zoomed-in="true" '
            f'onclick="toggleChartZoom(this)" '
            f'title="Show the full data range">Zoom Out</button></div>'
            if zoom_button else ""
        )
        sub_html_blocks.append(
            f'''
            <div class="subchart">
              <h4 class="subchart-title">{html.escape(subtitle)}</h4>
              <div class="chart-container"><canvas id="{sub_chart_id}"></canvas></div>
              {sub_zoom_btn}
            </div>'''
        )

    # Inline grid-template-columns so we can flex between 2 (annual+monthly)
    # and 3 (total/imports/exports) subchart layouts per card.
    n_subs = len(subcharts)
    grid_style = f' style="grid-template-columns: repeat({n_subs}, 1fr);"'

    # One shared HTML legend for the whole card, used when single_legend=True.
    # Built from `legend_seen` which preserves first-occurrence order across
    # all subcharts (so e.g. "Others" appears at the end if it's only in the
    # right-hand monthly chart).
    legend_html = ""
    if single_legend and legend_seen:
        items = "".join(
            f'<span class="card-legend-item">'
            f'<span class="card-legend-swatch" style="background:{color}"></span>'
            f'{html.escape(label)}</span>'
            for label, color in legend_seen.items()
        )
        legend_html = f'<div class="card-legend">{items}</div>'

    parent_badge = (
        f'<a class="chart-id-badge" href="#card-{parent_chart_id}" '
        f'data-chart-id="{parent_chart_id}" title="Click to copy link to this card">'
        f'⌗ {parent_chart_id}</a>'
    )

    # Register the PARENT card as its own manifest entry — gives the LLM
    # narrative system one row to cite (e.g. `sg.trade.crude_petroleum_oils`)
    # rather than asking it to navigate from subchart canvas IDs back up
    # to the parent. The parent's series_ids is the union across subcharts;
    # `subchart_meta` lets the summary-stats extractor compute pair-aware
    # signals (e.g. nowcast actual-vs-counterfactual gaps) per subchart.
    if parent_series_acc:
        data_sources_state[parent_chart_id] = {
            "title":         title,
            "description":   description or "",
            "series":        parent_series_acc,
            "tab_slug":      tab_slug,
            "page_prefix":   page_prefix,
            "relevant_to":   list(relevant_to or []),
            "subchart_meta": subchart_meta,
        }

    return f'''
    <div class="chart-card chart-card-multi" id="card-{parent_chart_id}">
      <div class="card-header">
        <h3>{title_safe}</h3>
        {desc_html}
      </div>
      {legend_html}
      <div class="subchart-grid"{grid_style}>
        {"".join(sub_html_blocks)}
      </div>
      <div class="chart-id-footer">{parent_badge}</div>
    </div>'''


def render_tab_group(section: dict, conn, chart_state: dict, data_sources_state: dict,
                     page_prefix: str = "x", page_slug: str = "") -> str:
    tabs = section["tabs"]
    nav_html = ""
    panels_html = ""
    for i, tab in enumerate(tabs):
        active_cls = " active" if i == 0 else ""
        # Tabs whose content is all bar/category-axis charts (no time series)
        # don't need the page-wide War period / 1Y / All time selector. Mark
        # the button so the tab-switching JS can hide the .date-range-bar.
        hide_zoom_attr = ' data-hide-date-range="true"' if tab.get("hide_date_range") else ''
        nav_html += f'<button class="tab-btn{active_cls}" data-tab="{tab["slug"]}"{hide_zoom_attr} onclick="switchTab(this, \'{tab["slug"]}\')">{tab["label"]}</button>'
        # Look up default LLM-narrative relevance for this (page, tab) combo.
        # Section-level / per-card overrides will still win below.
        tab_relevance = TAB_RELEVANCE.get(f"{page_slug}.{tab['slug']}", []) if page_slug else []
        sub_inner = ""
        for sub in tab.get("subsections", []):
            t = sub["type"]
            if t == "chart_grid":
                sub_inner += render_chart_grid(sub, conn, chart_state, data_sources_state,
                                                tab_slug=tab["slug"], page_prefix=page_prefix,
                                                default_relevance=tab_relevance)
            elif t == "shipping_iframe":
                sub_inner += render_shipping_iframe(sub)
            elif t == "placeholder":
                sub_inner += render_placeholder(sub)
            elif t == "pdf_cards":
                sub_inner += render_pdf_cards(sub)
            elif t == "country_panels":
                sub_inner += render_country_panels(sub, conn, chart_state, data_sources_state,
                                                    tab_slug=tab["slug"], page_prefix=page_prefix,
                                                    default_relevance=tab_relevance)
            elif t == "country_share_comparison":
                sub_inner += render_country_share_comparison(sub, conn, chart_state, data_sources_state,
                                                              tab_slug=tab["slug"], page_prefix=page_prefix,
                                                              default_relevance=tab_relevance)
            elif t == "view_selector":
                sub_inner += render_view_selector(sub, conn, chart_state, data_sources_state,
                                                   tab_slug=tab["slug"], page_prefix=page_prefix,
                                                   default_relevance=tab_relevance)
        panels_html += f'<div class="tab-panel{active_cls}" id="tab-{tab["slug"]}">{sub_inner}</div>'
    return f'''
    <section class="page-section">
      <div class="tab-nav">{nav_html}</div>
      <div class="tab-panels">{panels_html}</div>
    </section>'''


def render_shipping_iframe(section: dict) -> str:
    title = section.get("title", "")
    desc = section.get("description", "")
    url = section["url"]
    return f'''
    <section class="page-section iframe-section">
      <div class="section-header">
        <h2>{title}</h2>
        {f'<p class="section-desc">{desc}</p>' if desc else ''}
        <p class="iframe-link"><a href="{url}" target="_blank" rel="noopener">Open the live shipping nowcast in a new tab ↗</a></p>
      </div>
      <div class="iframe-wrap">
        <iframe src="{url}" loading="lazy" title="Hormuz shipping nowcast" referrerpolicy="no-referrer"></iframe>
      </div>
    </section>'''


def _expand_country_template(template: dict, iso2: str, country_label: str) -> dict:
    """Deep-copy a subsection template and substitute {iso2} / {country}
    placeholders inside string fields and inside any nested series ID list.
    Used by render_country_panels() to produce a country-specific instance
    of a templated chart_grid subsection."""
    import copy
    out = copy.deepcopy(template)

    def _sub(s: str) -> str:
        return s.replace("{iso2}", iso2).replace("{country}", country_label)

    def _walk(obj):
        if isinstance(obj, str):
            return _sub(obj)
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        return obj

    return _walk(out)


def render_view_selector(
    section: dict, conn, chart_state: dict, data_sources_state: dict,
    tab_slug: str | None = None,
    page_prefix: str = "x",
    default_relevance: list[str] | None = None,
) -> str:
    """Render a section that wraps N "views", with a dropdown to switch
    between them. Each view contains its own list of subsections (any
    chart_grid / country_share_comparison etc.). Only the default view
    is visible on load; others have display:none.

    Section schema:
      type:        "view_selector"
      title:       section h2
      description: section paragraph
      views:       [{label, key, default?, subsections: [...]}, ...]
    """
    title = section.get("title", "")
    desc = section.get("description", "")
    views = section.get("views", [])
    if not views:
        return ""
    # Pick default view: first one with default=True, else the first one.
    default_key = next((v["key"] for v in views if v.get("default")), views[0]["key"])

    selector_id = f"view-selector-{tab_slug or 'default'}"

    option_html = "".join(
        f'<option value="{html.escape(v["key"])}"'
        f'{ " selected" if v["key"] == default_key else ""}>'
        f'{html.escape(v["label"])}</option>'
        for v in views
    )

    panels_html = ""
    for v in views:
        active = v["key"] == default_key
        # Each view becomes its own panel_slug so chart IDs include the view
        # key (e.g. rg.trade.fuel.id_monthly vs rg.trade.chem.id_monthly).
        view_panel_slug = v["key"]
        # Render the view's subsections via the same dispatcher used by tabs.
        inner = ""
        for sub in v.get("subsections", []):
            t = sub.get("type")
            if t == "chart_grid":
                inner += render_chart_grid(sub, conn, chart_state, data_sources_state,
                                            tab_slug=tab_slug, page_prefix=page_prefix,
                                            panel_slug=view_panel_slug,
                                            default_relevance=default_relevance)
            elif t == "country_share_comparison":
                inner += render_country_share_comparison(sub, conn, chart_state, data_sources_state,
                                                          tab_slug=tab_slug, page_prefix=page_prefix,
                                                          panel_slug=view_panel_slug,
                                                          default_relevance=default_relevance)
            elif t == "placeholder":
                inner += render_placeholder(sub)
        style = "" if active else ' style="display: none;"'
        panels_html += f'<div class="view-panel" data-view="{html.escape(v["key"])}"{style}>{inner}</div>'

    desc_html = f'<p class="section-desc">{html.escape(desc)}</p>' if desc else ""
    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{html.escape(title)}</h2>
        {desc_html}
        <div class="view-selector-wrap">
          <label for="{selector_id}" class="view-selector-label">View:</label>
          <select id="{selector_id}" class="view-selector"
                  onchange="switchView(this)">
            {option_html}
          </select>
        </div>
      </div>
      <div class="view-panels">{panels_html}</div>
    </section>'''


def render_country_share_comparison(
    section: dict, conn, chart_state: dict, data_sources_state: dict,
    tab_slug: str | None = None,
    page_prefix: str = "x",
    panel_slug: str = "",
    default_relevance: list[str] | None = None,
) -> str:
    """Render a single grouped-bar chart that compares one share metric
    across N countries × M time periods.

    Section schema:
      type: "country_share_comparison"
      title:        section h2
      description:  section paragraph
      categories:   [(label, key), ...]  — countries on x-axis, in display order
      year_series:  [(year_label, period_iso), ...]  — one dataset per period
      series_id_template:  e.g. "regional_chem_share_from_sg_{key}"  (key is lowercased)
      unit:         display unit on the y-axis (default "% share")

    Each dataset (year) has one bar per category. Stable colors are derived
    from STABLE_PARTNER_COLORS via the year label (or fall back to the
    palette).
    """
    title = section.get("title", "")
    desc = section.get("description", "")
    categories = section.get("categories", [])         # [(label, key), ...]
    year_series = section.get("year_series", [])        # [(year_label, period_iso), ...]
    sid_template = section.get("series_id_template", "")
    unit = section.get("unit", "% share")

    # Build datasets — one per year. Each has N bars (one per category).
    # Pull values from time_series, NULL for missing.
    datasets = []
    color_palette_year = ("#94a3b8", "#3b82f6", "#10b981", "#f59e0b", "#ef4444")
    for di, (year_label, period_iso) in enumerate(year_series):
        values = []
        for _label, key in categories:
            sid = sid_template.format(key=key.lower())
            row = conn.execute(
                "SELECT value FROM time_series WHERE series_id=? AND date=?",
                (sid, period_iso),
            ).fetchone()
            values.append(float(row[0]) if row and row[0] is not None else None)
        # Pick color: stable if year_label happens to be in STABLE_PARTNER_COLORS;
        # otherwise rotate through a year-specific palette.
        color = STABLE_PARTNER_COLORS.get(year_label,
                                         color_palette_year[di % len(color_palette_year)])
        datasets.append({
            "label":           year_label,
            "data":            values,
            "backgroundColor": color,
            "borderColor":     color,
            "borderWidth":     1,
        })

    chart_id = make_chart_id(
        page_prefix, tab_slug or "",
        section.get("slug") or "country_share_comp",
        chart_state, panel_slug=panel_slug,
    )
    chart_state[chart_id] = {
        "type": "bar",
        "data": {
            "labels": [lbl for lbl, _ in categories],
            "datasets": datasets,
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {
                "legend":  {"position": "top",
                            "labels": {"color": "#c9d4e3", "boxWidth": 18,
                                       "padding": 10, "font": {"size": 11}}},
                "title":   {"display": False, "text": title},
                "tooltip": {"callbacks": {}},
            },
            "scales": {
                "x": {"ticks": {"color": "rgba(224, 230, 239, 0.65)",
                                "font": {"size": 11}},
                       "grid":  {"color": "rgba(224, 230, 239, 0.04)"}},
                "y": {"beginAtZero": True,
                       "ticks": {"color": "rgba(224, 230, 239, 0.5)",
                                 "font": {"size": 10}},
                       "grid":  {"color": "rgba(224, 230, 239, 0.06)"},
                       "title": {"display": True, "text": unit,
                                 "color": "#9ca3af", "font": {"size": 11}}},
            },
        },
    }

    # Register a synthetic Sources entry so the page-bottom Data Sources
    # table picks this up. We pull metadata off the first underlying series.
    first_sid = sid_template.format(key=(categories[0][1].lower() if categories else ""))
    src_row = conn.execute(
        "SELECT source, frequency, unit FROM time_series WHERE series_id=? LIMIT 1",
        (first_sid,),
    ).fetchone()
    src = src_row[0] if src_row else "comtrade"
    freq = src_row[1] if src_row else "Annual"
    unit_row = src_row[2] if src_row else unit
    data_sources_state[chart_id] = {
        "title": title,
        "description": desc or "",
        "series": [
            {"series_id":   sid_template.format(key=k.lower()),
             "series_name": f"{lbl} — SG share of industrial chemical imports",
             "source":      src,
             "frequency":   freq,
             "unit":        unit_row,
             "friendly_name": lbl,
             "data":        []}
            for lbl, k in categories
        ],
        "tab_slug": tab_slug,
        "page_prefix": page_prefix,
        "relevant_to": list(section.get("relevant_to") or default_relevance or []),
    }

    desc_html = f'<p class="section-desc">{html.escape(desc)}</p>' if desc else ""
    badge = (
        f'<a class="chart-id-badge" href="#{chart_id}" data-chart-id="{chart_id}" '
        f'title="Click to copy link to this chart">⌗ {chart_id}</a>'
    )
    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{html.escape(title)}</h2>
        {desc_html}
      </div>
      <div class="chart-grid chart-grid-single" style="grid-template-columns: 1fr;">
        <div class="chart-card" id="card-{chart_id}">
          <div class="chart-container" style="height: 360px;"><canvas id="{chart_id}"></canvas></div>
          <div class="chart-id-footer">{badge}</div>
        </div>
      </div>
    </section>'''


def render_country_panels(section: dict, conn, chart_state: dict,
                          data_sources_state: dict, tab_slug: str | None = None,
                          page_prefix: str = "x",
                          default_relevance: list[str] | None = None) -> str:
    """Render a country selector + N country panels in one section.

    Each country panel contains the same set of chart_grid subsections,
    instantiated from `subsection_template` with `{iso2}` / `{country}`
    placeholders substituted per country. Only one panel is visible at a
    time, controlled by a <select> dropdown above the panels.

    Mirrors the Singapore Shipping tab's card flow — overview ➜ vessel-type
    drill-down — so users see a familiar layout for any selected country.
    """
    title = section.get("title", "")
    desc = section.get("description", "")
    countries = section.get("countries", [])  # [(iso2, label), ...]
    default_iso2 = section.get("default_country") or (countries[0][0] if countries else "")
    template_subsections = section.get("subsection_template", [])

    # Stable id per call so multiple country_panels on a single page won't
    # clash. The tab_slug + section title are unique within a page.
    selector_id = f"country-selector-{tab_slug or 'panels'}"

    # Build dropdown <option>s
    option_html = "".join(
        f'<option value="{iso2}"{ " selected" if iso2 == default_iso2 else ""}>'
        f'{html.escape(label)}</option>'
        for iso2, label in countries
    )

    # Build per-country panel content. Each country gets the same set of
    # chart_grid subsections, instantiated from the template.
    panels_html = ""
    for iso2, country_label in countries:
        active = (iso2 == default_iso2)
        # Render every subsection in the template against this country.
        per_country_inner = ""
        for tmpl in template_subsections:
            sub = _expand_country_template(tmpl, iso2, country_label)
            t = sub.get("type")
            if t == "chart_grid":
                per_country_inner += render_chart_grid(
                    sub, conn, chart_state, data_sources_state,
                    tab_slug=tab_slug, page_prefix=page_prefix, panel_slug=iso2,
                    default_relevance=default_relevance,
                )
            # (No other subsection types currently used inside country_panels —
            # add elif branches here if needed.)
        style = "" if active else ' style="display: none;"'
        panels_html += (
            f'<div class="country-panel" data-country="{iso2}"{style}>'
            f'{per_country_inner}'
            f'</div>'
        )

    # Section header + dropdown selector
    desc_html = f'<p class="section-desc">{html.escape(desc)}</p>' if desc else ""
    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{html.escape(title)}</h2>
        {desc_html}
        <div class="country-selector-wrap">
          <label for="{selector_id}" class="country-selector-label">Country:</label>
          <select id="{selector_id}" class="country-selector"
                  onchange="switchCountryPanel(this)">
            {option_html}
          </select>
        </div>
      </div>
      <div class="country-panels">
        {panels_html}
      </div>
    </section>'''


def render_placeholder(section: dict) -> str:
    title = section.get("title", "")
    items = section.get("planned_content", [])
    items_html = "".join(f"<li>{item}</li>" for item in items)
    return f'''
    <section class="page-section">
      <div class="placeholder-card">
        <div class="placeholder-badge">Coming soon</div>
        <h2>{title}</h2>
        <p class="placeholder-intro">Planned content for this section:</p>
        <ul class="planned-content">{items_html}</ul>
      </div>
    </section>'''


def render_pdf_cards(section: dict) -> str:
    title = section.get("title", "")
    desc = section.get("description", "")
    series_intro = section.get("series_intro")  # optional dict with {title, body}

    cards_html = ""
    for r in section["reports"]:
        flag_svg = get_flag(r["iso"])
        date_pretty = _format_date_pretty(r["date"])
        # onclick: preflight the URL via no-cors HEAD with timeout. If reachable,
        # opens in a new tab. If not, shows the access-warning modal instead of
        # letting the browser surface a raw "site can't be reached" error.
        # Right-click/middle-click bypass JS and open normally — keeping power-user
        # behaviour intact.
        cards_html += f'''
        <a class="pdf-card" href="{_url_escape(r['url'])}" target="_blank" rel="noopener" onclick="pdfCardClick(event, this.href)">
          <div class="pdf-flag">{flag_svg}</div>
          <div class="pdf-meta">
            <h4>{html.escape(r['title'])}</h4>
            <p class="pdf-date">{date_pretty}</p>
            <p class="pdf-country">{html.escape(r['country'])}</p>
          </div>
          <div class="pdf-arrow">↗</div>
        </a>'''

    desc_html = f'<p class="section-desc">{html.escape(desc)}</p>' if desc else ""

    intro_html = ""
    if series_intro:
        intro_title = html.escape(series_intro.get("title", ""))
        # Body may have multiple paragraphs separated by blank lines.
        body_paras = "".join(
            f'<p>{html.escape(p.strip())}</p>'
            for p in series_intro.get("body", "").split("\n\n")
            if p.strip()
        )
        intro_html = f'''
      <div class="report-series-intro">
        <h3>{intro_title}</h3>
        {body_paras}
      </div>'''

    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{html.escape(title)}</h2>
        {desc_html}
      </div>
      {intro_html}
      <div class="pdf-grid">{cards_html}</div>
    </section>'''


# ---------------------------------------------------------------------------
# Narrative renderer
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# LLM narrative renderer (status indicators + per-page summaries)
# ---------------------------------------------------------------------------
# Pulls outputs from the metadata table written by scripts/generate_narratives.py
# and renders them as visually-striking status badges (landing page) and
# tight per-page summary cards (top of each page). See METHODOLOGY.md §7.

# Color-coded by level. Pulled from prompts/synthesizer.md.
_STATUS_LEVELS = {
    "calm":     {"label": "Calm",     "color": "#10b981"},   # green
    "watchful": {"label": "Watchful", "color": "#f59e0b"},   # amber
    "strained": {"label": "Strained", "color": "#f97316"},   # orange
    "critical": {"label": "Critical", "color": "#ef4444"},   # red
}
# Display order — least to most concerning, used by the stepper-pill scale.
_STATUS_LEVEL_ORDER = ["calm", "watchful", "strained", "critical"]

# Map page prefix → display label for cross-page citations in the synthesizer's
# expandable_refs. Inverse of PAGE_ID_PREFIX.
_PAGE_PREFIX_TO_FILE = {
    "gs":      "global_shocks.html",
    "sg":      "singapore.html",
    "rg":      "regional.html",
    "home":    "index.html",
}


def _load_narrative(conn, key: str) -> dict | None:
    """Fetch a narrative payload from metadata. The orchestrator stores each
    output as JSON wrapped in `{"updated_at": ..., "payload": ...}` —
    return the unwrapped inner payload, or None when the key is missing /
    malformed."""
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = ?", (key,)
    ).fetchone()
    if not row or not row["value"]:
        return None
    try:
        wrapped = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(wrapped, dict) and "payload" in wrapped:
        return wrapped.get("payload")
    return wrapped if isinstance(wrapped, dict) else None


def _chart_id_anchor(chart_id: str, same_page: bool) -> str:
    """Build an anchor URL for a chart_id. When same_page is True (used by
    page-summary findings), produces just `#card-<id>`. When False (used by
    landing-page synthesizer refs), produces `<page_file>#card-<id>` so the
    link cross-navigates to the chart's owning page."""
    if same_page:
        return f"#card-{chart_id}"
    page_prefix = chart_id.split(".", 1)[0] if "." in chart_id else "home"
    return f"{_PAGE_PREFIX_TO_FILE.get(page_prefix, 'index.html')}#card-{chart_id}"


def _render_chart_id_badge(chart_id: str, same_page: bool) -> str:
    """Inline monospace badge linking to a chart anchor. Used in page-summary
    finding bullets and in synthesizer expandable_refs."""
    return (f'<a class="chart-ref-badge" href="{_chart_id_anchor(chart_id, same_page)}">'
            f'⌗ {html.escape(chart_id)}</a>')


def render_status_indicators(section: dict, conn) -> str:
    """Render the two big colored status badges on the landing page.
    Reads `narrative_synthesizer` from metadata; falls back to a placeholder
    when the narrative pipeline hasn't been run yet."""
    payload = _load_narrative(conn, "narrative_synthesizer")
    if not payload:
        return f'''
        <section class="status-indicators status-indicators--placeholder">
          <p class="muted">Status indicators will appear here once the LLM narrative
          pipeline has been run (<code>scripts/generate_narratives.py</code>).</p>
        </section>'''

    questions = [
        ("energy_supply",     "Energy supply"),
        ("financial_markets", "Financial markets"),
    ]

    cards_html = ""
    for q_key, q_label in questions:
        block = payload.get(q_key) or {}
        level = (block.get("level") or "").lower()
        meta = _STATUS_LEVELS.get(level, {"label": level.title() or "—",
                                           "color": "#6b7280"})
        narrative = block.get("narrative") or ""
        drivers   = block.get("drivers")   or []

        # Drivers — each is `{text, chart_ids}`. Render as a bullet with the
        # text and inline chart-id badges that cross-navigate to the chart's
        # owning page (same UX as per-page summary findings, just cross-page
        # rather than same-page anchors).
        drivers_html = ""
        for d in drivers:
            # Tolerate the older-shape schema (string-only drivers) so we
            # don't crash if an old narrative payload is still in the DB —
            # just render the string with no chart citations.
            if isinstance(d, str):
                drivers_html += f'<li class="status-driver"><p class="status-driver-text">{html.escape(d)}</p></li>'
                continue
            text       = html.escape(d.get("text", "") or "")
            chart_ids  = d.get("chart_ids", []) or []
            badges = "".join(
                _render_chart_id_badge(cid, same_page=False) for cid in chart_ids
            )
            drivers_html += (
                f'<li class="status-driver">'
                f'<p class="status-driver-text">{text}</p>'
                + (f'<div class="status-driver-refs">{badges}</div>' if badges else '')
                + '</li>'
            )
        # Collapsible — closed by default to keep the landing-page status
        # card compact. Click to expand the driver list.
        drivers_block = (
            f'<details class="collapsible-section">'
            f'<summary class="collapsible-title">Key Drivers <span class="collapsible-count">({len(drivers)})</span></summary>'
            f'<ul class="status-drivers">{drivers_html}</ul>'
            f'</details>'
        ) if drivers else ""

        # Stepper pills: render all 4 levels in order, with the current one
        # highlighted. Lets the viewer see where the current level sits
        # within the full scale (Calm → Watchful → Strained → Critical).
        steps_html = ""
        for i, lvl_key in enumerate(_STATUS_LEVEL_ORDER):
            lvl_meta = _STATUS_LEVELS[lvl_key]
            is_active = (lvl_key == level)
            cls = f"scale-step scale-step--{lvl_key}"
            if is_active:
                cls += " scale-step--active"
            steps_html += (
                f'<div class="{cls}" style="--step-color: {lvl_meta["color"]};">'
                f'{html.escape(lvl_meta["label"])}</div>'
            )
            # Subtle chevron between steps (skip after the last)
            if i < len(_STATUS_LEVEL_ORDER) - 1:
                steps_html += '<span class="scale-chevron" aria-hidden="true">›</span>'

        cards_html += f'''
        <div class="status-card status-card--{level}" style="--status-color: {meta['color']};">
          <div class="status-header">
            <span class="status-question">{html.escape(q_label)}</span>
            <span class="status-level">{html.escape(meta['label'])}</span>
          </div>
          <div class="status-scale" role="meter" aria-label="{html.escape(q_label)} level"
               aria-valuemin="1" aria-valuemax="{len(_STATUS_LEVEL_ORDER)}"
               aria-valuenow="{_STATUS_LEVEL_ORDER.index(level) + 1 if level in _STATUS_LEVEL_ORDER else 0}">
            {steps_html}
          </div>
          <div class="status-section-title">Overview</div>
          <p class="status-narrative">{html.escape(narrative)}</p>
          {drivers_block}
        </div>'''

    as_of = payload.get("as_of_date") or ""
    meta_line = f'Snapshot as of {html.escape(as_of)}' if as_of else ''

    return f'''
    <section class="status-indicators">
      <div class="status-grid">
        {cards_html}
      </div>
      <p class="status-meta">{meta_line}</p>
    </section>'''


def render_page_summary(section: dict, conn, page_slug: str) -> str:
    """Render the LLM-generated per-page summary card at the top of each page.
    Tight 2-3 sentence summary + bullet list of key_findings, each finding
    with inline chart_id badges linking to its anchors on the same page."""
    payload = _load_narrative(conn, f"narrative_{page_slug}")
    if not payload:
        return ""   # silent skip when narrative not generated yet

    questions = [
        ("energy_supply",     "Energy supply"),
        ("financial_markets", "Financial markets"),
    ]

    blocks_html = ""
    for q_key, q_label in questions:
        block = payload.get(q_key)
        if not block:
            continue   # this question doesn't apply on this page
        summary = block.get("summary") or ""
        findings = block.get("key_findings") or []
        gaps     = block.get("data_gaps")    or []
        # `concern_score` is intentionally not rendered — kept as an internal
        # signal that feeds the synthesizer's threshold rules. Showing it
        # per-page would compete with the synthesized landing-page level
        # (Calm/Watchful/Strained/Critical) and confuse viewers since a
        # page-level score doesn't always map to the landing-page level.

        # Key-finding bullets — each finding text + inline chart-id badges
        findings_html = ""
        for f in findings:
            text = html.escape(f.get("finding", "") or "")
            chart_ids = f.get("chart_ids", []) or []
            badges = "".join(
                _render_chart_id_badge(cid, same_page=True) for cid in chart_ids
            )
            findings_html += f'''
              <li class="ps-finding">
                <p class="ps-finding-text">{text}</p>
                {f'<div class="ps-finding-refs">{badges}</div>' if badges else ''}
              </li>'''

        # Data gaps as expandable footer — same styling as Key Drivers for visual symmetry.
        gaps_html = ""
        if gaps:
            gap_items = "".join(
                f'<li>{html.escape(g)}</li>' for g in gaps
            )
            gaps_html = f'''
              <details class="collapsible-section ps-gaps">
                <summary class="collapsible-title">Data Gaps <span class="collapsible-count">({len(gaps)})</span></summary>
                <ul class="ps-gaps-list">{gap_items}</ul>
              </details>'''

        blocks_html += f'''
          <div class="ps-block">
            <div class="ps-header">
              <h2>{html.escape(q_label)}</h2>
            </div>
            <div class="ps-section-title">Overview</div>
            <p class="ps-summary">{html.escape(summary)}</p>
            <details class="collapsible-section">
              <summary class="collapsible-title">Key Drivers <span class="collapsible-count">({len(findings)})</span></summary>
              <ul class="ps-findings">{findings_html}</ul>
            </details>
            {gaps_html}
          </div>'''

    if not blocks_html:
        return ""

    return f'''
    <section class="page-summary">
      <div class="ps-grid">
        {blocks_html}
      </div>
    </section>'''


def render_ai_methodology(section: dict) -> str:
    """Render the AI-disclosure + methodology footer on the landing page.
    Collapsible (closed by default) so viewers see a tight one-line
    disclosure but can expand for the full methodology if interested."""
    return '''
    <section class="ai-methodology">
      <details class="ai-method-details">
        <summary class="ai-method-summary">
          <span class="ai-method-icon">✦</span>
          <span class="ai-method-title">The analysis above is AI-generated.</span>
          <span class="ai-method-cta">Click to find out how <span class="ai-method-arrow">→</span></span>
        </summary>
        <div class="ai-method-body">
          <p>
            The dashboard pipeline uses Anthropic's Claude Sonnet 4.6 in a
            structured, deterministic flow. There are four AI calls per
            refresh, all run at temperature zero so the same inputs
            produce the same reads run-to-run.
          </p>

          <h4 class="ai-method-step-title">1 · Pre-compute summary statistics</h4>
          <p>
            Before any AI is called, a deterministic step walks every
            chart on every page and extracts a fixed set of statistics —
            current value versus the pre-war baseline, 4-week and 12-week
            momentum, the war-period range, where in that range the latest
            print sits, staleness flags, and shipping nowcast actual-vs-
            counterfactual gaps. This guarantees the AI only sees
            structured numbers and never has to "read" a chart.
          </p>

          <h4 class="ai-method-step-title">2 · Per-page reads</h4>
          <p>
            Three independent AI calls — one each for Global Shocks,
            Singapore, and Regional — receive only their page's summary
            statistics plus a strict prompt. Each produces a structured
            output: a 2-3 sentence overview and 3-5 key drivers per
            question (energy supply, financial markets), where every
            finding cites the specific charts that support it. Those
            citations become the clickable badges in the Key Drivers
            sections.
          </p>

          <h4 class="ai-method-step-title">3 · Synthesizer</h4>
          <p>
            A fourth AI call takes the three page outputs (not the raw
            data) and produces the landing-page status badges and
            narratives. The 4-level scale (Calm / Watchful / Strained /
            Critical) is a judgement call by the AI based on the full
            pattern of page-level findings, anchored against worked
            calibration examples baked into the prompt for each level.
            The narrative and drivers are the AI's synthesis, written
            for an MAS audience.
          </p>

          <h4 class="ai-method-step-title">4 · Guardrails</h4>
          <p>
            Prompts forbid policy speculation and historical comparisons
            not visible in the data. Every claim must cite a chart on
            the dashboard, and stale series must be named as such. The
            chart citations are the audit trail — click any of them to
            jump directly to the underlying chart and verify.
          </p>

          <p class="ai-method-caveat">
            AI can still be wrong. Treat the narratives as a structured
            first read, not a final word — verify the key drivers via
            the chart citations, especially before they leave the
            building.
          </p>
        </div>
      </details>
    </section>'''


def render_narrative(page_def: dict, conn) -> str:
    src = page_def.get("narrative_source", "placeholder")
    placeholder_text = page_def.get("narrative_placeholder", "Key takeaways will appear here.")

    text_html = ""
    label = "Key Takeaways"
    badge = "<span class=\"narrative-badge placeholder\">Placeholder</span>"

    if src == "metadata.llm_narrative":
        r = conn.execute("SELECT value FROM metadata WHERE key = 'llm_narrative'").fetchone()
        gen_at_row = conn.execute("SELECT value FROM metadata WHERE key = 'narrative_generated_at'").fetchone()
        if r and r["value"]:
            paragraphs = r["value"].split("\n\n")
            # Escape DB-derived prose to prevent any HTML/script injection from the narrative pipeline.
            text_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())
            gen_at = gen_at_row["value"] if gen_at_row else None
            timestamp_html = f'<p class="narrative-timestamp">Generated {html.escape(gen_at[:10])}</p>' if gen_at else ""
            badge = '<span class="narrative-badge live">From narrative pipeline</span>'
            return f'''
            <section class="narrative-card">
              <div class="narrative-header">
                <h2>{label}</h2>
                {badge}
              </div>
              <div class="narrative-body">{text_html}</div>
              {timestamp_html}
            </section>'''

    # Placeholder fallback
    return f'''
    <section class="narrative-card">
      <div class="narrative-header">
        <h2>{label}</h2>
        {badge}
      </div>
      <div class="narrative-body">
        <p class="muted">{placeholder_text}</p>
      </div>
    </section>'''


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------
def render_nav(active_slug: str) -> str:
    items = []
    for nav in PAGE_NAV:
        cls = "nav-link active" if nav["slug"] == active_slug else "nav-link"
        items.append(f'<a class="{cls}" href="{nav["file"]}">{nav["label"]}</a>')
    return f'<nav class="topnav">{"".join(items)}</nav>'


def render_page(slug: str, page_def: dict, conn) -> tuple[str, dict]:
    """Render one page. Returns (html, data_sources_state) — the second is the
    chart manifest used by compute_summary_stats.py to feed the LLM narrative
    pipeline. data_sources_state is keyed by chart_id with title / description /
    series / tab_slug / page_prefix per chart."""
    chart_state: dict = {}
    data_sources_state: dict = {}
    sections_html = []
    # Resolve the page-level chart-ID prefix (e.g. "sg" for singapore) so all
    # chart IDs on this page begin with it. Falls back to "x" for unknown
    # slugs (kept defensive — every page should be in PAGE_ID_PREFIX).
    page_prefix = PAGE_ID_PREFIX.get(slug, "x")

    # Insert the page-wide date-range bar (zoom toggle) into the sections
    # list rather than the chrome, so it can sit AFTER the LLM page_summary
    # but BEFORE the first chart-bearing section. Determine up front whether
    # the page actually has charts (presence of chart_grid or tab_group in
    # the layout); only then is the bar useful.
    section_types  = [s.get("type") for s in page_def["sections"]]
    has_charts     = any(t in ("chart_grid", "tab_group") for t in section_types)
    bar_inserted   = False

    def _ensure_date_range_bar():
        nonlocal bar_inserted
        if has_charts and not bar_inserted:
            sections_html.append(render_date_range_bar())
            bar_inserted = True

    for section in page_def["sections"]:
        t = section["type"]
        if t == "landing_cards":
            sections_html.append(render_landing_cards())
        elif t == "status_indicators":
            sections_html.append(render_status_indicators(section, conn))
        elif t == "ai_methodology":
            sections_html.append(render_ai_methodology(section))
        elif t == "page_summary":
            sections_html.append(render_page_summary(section, conn, slug))
            _ensure_date_range_bar()    # zoom toggle goes right after the LLM summary
        elif t == "chart_grid":
            _ensure_date_range_bar()    # safety net if no page_summary above
            sections_html.append(render_chart_grid(section, conn, chart_state, data_sources_state,
                                                    page_prefix=page_prefix))
        elif t == "tab_group":
            _ensure_date_range_bar()
            sections_html.append(render_tab_group(section, conn, chart_state, data_sources_state,
                                                   page_prefix=page_prefix, page_slug=slug))
        elif t == "shipping_iframe":
            sections_html.append(render_shipping_iframe(section))
        elif t == "placeholder":
            sections_html.append(render_placeholder(section))
        elif t == "pdf_cards":
            sections_html.append(render_pdf_cards(section))

    nav_html = render_nav(slug)
    # The legacy "Key takeaways" placeholder block is now redundant — the
    # `status_indicators` section on the landing page and the `page_summary`
    # section at the top of each content page do this work via the LLM
    # narrative pipeline. Set to empty so the BASE_TEMPLATE {narrative}
    # slot collapses; render_narrative() is kept as dead code for now in
    # case we want to revive a placeholder for new pages later.
    narrative_html = ""
    chart_init_js = json.dumps(chart_state)
    # Surface the set of chart IDs that own their own zoom (per-chart Zoom
    # In/Out button) — applyDateRange skips them so the page-level "war"
    # default doesn't override the user's per-chart state.
    no_default_zoom_ids = sorted([
        cid for cid, info in data_sources_state.items()
        if isinstance(info, dict) and info.get("_no_default_zoom")
    ])
    no_default_zoom_js = json.dumps(no_default_zoom_ids)
    title = page_def["title"]
    subtitle = page_def.get("subtitle", "")

    # date_range_bar is now inserted into the sections list above (after
    # page_summary if present, else just before the first chart section).
    # The BASE_TEMPLATE {date_range_bar} placeholder is unused — kept blank
    # for backward-compat with any older template references.
    date_range_bar_html = ""

    # Collapsible Data sources table at the bottom (only on pages with charts).
    data_sources_html = render_data_sources_section(data_sources_state) if data_sources_state else ""

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    rendered_html = BASE_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        nav=nav_html,
        narrative=narrative_html,
        date_range_bar=date_range_bar_html,
        sections="\n".join(sections_html),
        data_sources=data_sources_html,
        chart_configs=chart_init_js,
        no_default_zoom_ids=no_default_zoom_js,
        built_at=built_at,
    )
    return rendered_html, data_sources_state


def render_data_sources_section(data_sources_state: dict) -> str:
    """Single collapsible <details> at the page bottom listing every series in
    every chart on the page, with full attribution metadata in a table.
    Rows tagged with their owning tab so the JS can filter to match the active
    tab; rows without a tab tag are always visible (charts not inside a
    tab_group)."""
    if not data_sources_state:
        return ""

    rows = []
    for chart_id, info in data_sources_state.items():
        # Skip parent entries for multi-subchart cards (those carry
        # `subchart_meta`). Their constituent subchart entries are already
        # listed below — listing the parent too would duplicate every
        # underlying series. Parent entries exist only so the LLM
        # narrative pipeline can cite the umbrella card_id.
        if info.get("subchart_meta"):
            continue
        chart_title = html.escape(info["title"])
        tab_slug = info.get("tab_slug") or ""
        tab_attr = f' data-tab="{html.escape(tab_slug)}"' if tab_slug else ''
        for s in info["series"]:
            src_raw = s.get("source", "")
            chip_cls = source_chip_class(src_raw)
            src_label = html.escape(source_display_name(src_raw))
            sid = html.escape(s.get("series_id", ""))
            name = html.escape(s.get("name", ""))
            freq = html.escape((s.get("frequency", "") or ""))
            unit = html.escape((s.get("unit", "") or ""))
            last = ""
            if s.get("data"):
                last = html.escape(_format_through(s["data"][-1][0]))
            rows.append(f'''
              <tr{tab_attr}>
                <td class="ds-chart">{chart_title}</td>
                <td class="ds-series">{name}</td>
                <td><span class="source-chip {chip_cls}">{src_label}</span></td>
                <td class="ds-id">{sid}</td>
                <td>{freq}</td>
                <td>{unit}</td>
                <td>{last}</td>
              </tr>''')

    return f'''
    <details class="data-sources-section">
      <summary>
        <span class="ds-summary-label">Data sources &amp; series attribution</span>
        <span class="ds-summary-count" id="dsSummaryCount">—</span>
      </summary>
      <div class="ds-table-wrap">
        <table class="ds-table">
          <thead>
            <tr>
              <th>Chart</th>
              <th>Series (legend)</th>
              <th>Source</th>
              <th>Series ID</th>
              <th>Frequency</th>
              <th>Unit</th>
              <th>Latest</th>
            </tr>
          </thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
    </details>'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _icon(name: str) -> str:
    icons = {
        "globe": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
        "compass": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><polygon points="16 8 12 14 8 16 12 10"/></svg>',
        "map": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="3 6 9 4 15 6 21 4 21 18 15 20 9 18 3 20 3 6"/><line x1="9" y1="4" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="20"/></svg>',
    }
    return icons.get(name, "")


def _format_value(v) -> str:
    if v is None:
        return "—"
    av = abs(v)
    if av >= 1000:
        return f"{v:,.0f}"
    if av >= 100:
        return f"{v:.1f}"
    if av >= 10:
        return f"{v:.2f}"
    if av >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _format_date_pretty(d: str) -> str:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return dt.strftime("%-d %b %Y")
    except Exception:
        return d


def _url_escape(url: str) -> str:
    # URL-encode spaces (the SharePoint URLs have spaces in path segments)
    return url.replace(" ", "%20")


# ---------------------------------------------------------------------------
# Base template (chrome + CSS + Chart.js init)
# ---------------------------------------------------------------------------
BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — Iran Monitor</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/luxon@3.4.4/build/global/luxon.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@1.3.1/dist/chartjs-adapter-luxon.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <style>
    /* ── Theme ── */
    :root {{
      --bg-base: #0a1623;
      --bg-card: rgba(20, 35, 53, 0.55);
      --bg-card-hover: rgba(20, 35, 53, 0.75);
      --border: rgba(194, 154, 81, 0.2);
      --border-strong: rgba(194, 154, 81, 0.45);
      --text: #e0e6ef;
      --text-muted: rgba(224, 230, 239, 0.55);
      --text-dim: rgba(224, 230, 239, 0.35);
      --accent: #f0d08a;
      --accent-soft: rgba(240, 208, 138, 0.15);
      --kpi-up: #f87171;
      --kpi-down: #34d399;
    }}

    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0; padding: 0;
      background: var(--bg-base);
      background-image:
        radial-gradient(circle at 20% 0%, rgba(120, 60, 30, 0.08), transparent 50%),
        radial-gradient(circle at 80% 100%, rgba(40, 80, 120, 0.08), transparent 50%);
      background-attachment: fixed;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      min-height: 100vh;
    }}

    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* ── Top nav ── */
    .topnav {{
      display: flex; gap: 0.4rem;
      padding: 0.85rem 2rem;
      border-bottom: 1px solid var(--border);
      background: rgba(10, 22, 35, 0.85);
      backdrop-filter: blur(8px);
      position: sticky; top: 0; z-index: 50;
    }}
    .nav-link {{
      padding: 0.4rem 0.95rem;
      border-radius: 6px;
      color: var(--text-muted);
      font-size: 0.88rem; font-weight: 500;
    }}
    .nav-link:hover {{ color: var(--text); background: rgba(255,255,255,0.04); text-decoration: none; }}
    .nav-link.active {{ color: var(--accent); background: var(--accent-soft); }}

    /* ── Page header ── */
    .page-header {{
      max-width: 1280px; margin: 0 auto; padding: 2.5rem 2rem 1rem;
    }}
    .page-header h1 {{
      font-size: 2rem; font-weight: 700; margin: 0 0 0.4rem; color: var(--text);
      letter-spacing: -0.02em;
    }}
    .page-header .subtitle {{ color: var(--text-muted); margin: 0; font-size: 1rem; }}

    /* ── Container ── */
    main {{ max-width: 1280px; margin: 0 auto; padding: 0 2rem 4rem; }}

    /* ── Narrative card ── */
    .narrative-card {{
      background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
      padding: 1.5rem 1.75rem; margin: 1.5rem 0 2rem;
      backdrop-filter: blur(8px);
    }}
    .narrative-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }}
    .narrative-header h2 {{ margin: 0; font-size: 1.1rem; color: var(--accent); }}
    .narrative-badge {{
      font-size: 0.7rem; padding: 0.2rem 0.55rem;
      border-radius: 4px; letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600;
    }}
    .narrative-badge.placeholder {{ background: rgba(194, 154, 81, 0.15); color: rgba(240, 208, 138, 0.75); }}
    .narrative-badge.live {{ background: rgba(52, 211, 153, 0.15); color: #34d399; }}
    .narrative-body p {{ margin: 0 0 0.75rem; line-height: 1.65; color: var(--text); }}
    .narrative-body p:last-child {{ margin-bottom: 0; }}
    .narrative-timestamp {{ margin: 0.75rem 0 0; font-size: 0.78rem; color: var(--text-dim); }}

    /* ── Section ── */
    .page-section {{ margin: 0 0 2.5rem; }}
    .section-header h2 {{
      font-size: 1.25rem; margin: 0 0 0.4rem; color: var(--text);
      font-weight: 600; letter-spacing: -0.01em;
    }}
    .section-header .section-desc {{
      margin: 0 0 1.25rem; color: var(--text-muted); font-size: 0.92rem;
      line-height: 1.55;
    }}

    /* ── Chart grid ── */
    .chart-grid {{
      display: grid; gap: 1.25rem;
      grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    }}
    .chart-card {{
      background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
      padding: 1.25rem; backdrop-filter: blur(6px);
      transition: border-color 0.2s;
    }}
    .chart-card:hover {{ border-color: var(--border-strong); }}
    .card-header {{ margin-bottom: 0.75rem; }}
    .card-header h3 {{ margin: 0 0 0.25rem; font-size: 0.98rem; color: var(--accent); font-weight: 600; }}
    .card-desc {{ margin: 0; font-size: 0.83rem; color: var(--text-muted); line-height: 1.5; max-width: 64ch; }}

    /* Visible chart-ID badge — surfaces the deterministic chart ID (e.g.
       ⌗ sg.activity.petroleum_refining) so the LLM narrative system can
       cite charts and the reader can match the citation. Lives in a
       footer at the bottom of each card — quiet by default, click-to-copy
       the URL fragment. */
    .chart-id-footer {{
      margin-top: 0.6rem;
      text-align: right;
      line-height: 1;
    }}
    .chart-id-badge {{
      display: inline-block;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.66rem;
      color: rgba(224, 230, 239, 0.28);
      background: transparent;
      border: 1px solid rgba(224, 230, 239, 0.05);
      border-radius: 4px;
      padding: 0.08rem 0.4rem;
      text-decoration: none;
      letter-spacing: 0.02em;
      transition: color 0.15s, background 0.15s, border-color 0.15s;
    }}
    .chart-card:hover .chart-id-badge {{
      color: rgba(224, 230, 239, 0.5);
      border-color: rgba(224, 230, 239, 0.12);
    }}
    .chart-id-badge:hover {{
      color: var(--accent) !important;
      background: rgba(240, 208, 138, 0.08);
      border-color: rgba(240, 208, 138, 0.25) !important;
    }}
    .chart-id-badge.copied {{
      color: #10b981 !important;
      background: rgba(16, 185, 129, 0.1);
      border-color: rgba(16, 185, 129, 0.35) !important;
    }}

    /* Briefly highlight a chart card when its anchor is targeted via URL
       fragment (LLM narrative citations + click-to-copy badge link). */
    .chart-card.target-flash {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(240, 208, 138, 0.3);
    }}

    /* ════════════════════════════════════════════════════════════════════
       LLM narrative system — landing-page status indicators + per-page
       summary cards. See METHODOLOGY.md §7.
       ════════════════════════════════════════════════════════════════════ */

    /* Landing-page status indicators. Two big colored badges side-by-side. */
    .status-indicators {{
      margin: 1.5rem 0 2.5rem;
    }}
    .status-indicators--placeholder {{
      padding: 1rem 1.25rem;
      background: rgba(224,230,239,0.04);
      border: 1px dashed rgba(224,230,239,0.15);
      border-radius: 10px;
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1.25rem;
    }}
    @media (max-width: 800px) {{
      .status-grid {{ grid-template-columns: 1fr; }}
    }}
    .status-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-left: 6px solid var(--status-color, var(--accent));
      border-radius: 10px;
      padding: 1.25rem 1.4rem;
    }}
    .status-header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 1rem;
      margin-bottom: 0.7rem;
    }}
    .status-question {{
      font-size: 0.85rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
    }}
    .status-level {{
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--status-color, var(--text));
      letter-spacing: 0.01em;
    }}
    .status-narrative {{
      margin: 0.4rem 0 0.9rem;
      color: var(--text);
      line-height: 1.55;
      font-size: 0.93rem;
      text-align: justify;
      hyphens: auto;
    }}

    /* Stepper-pill scale showing all 4 levels with the current one
       highlighted. Lives between the status-header and the narrative
       so viewers see where the level sits within the full scale. */
    .status-scale {{
      display: flex;
      align-items: center;
      gap: 0.35rem;
      margin: 0.5rem 0 1rem;
      flex-wrap: wrap;
    }}
    .scale-step {{
      font-size: 0.74rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      padding: 0.28rem 0.65rem;
      border-radius: 4px;
      border: 1px solid var(--step-color);
      color: var(--step-color);
      background: transparent;
      opacity: 0.32;
      transition: opacity 0.2s, transform 0.2s;
    }}
    .scale-step--active {{
      opacity: 1;
      color: #fff;
      background: var(--step-color);
      border-color: var(--step-color);
      transform: scale(1.08);
      box-shadow: 0 0 0 3px var(--step-color)22,
                  0 0 14px -2px var(--step-color);
      font-weight: 700;
      letter-spacing: 0.05em;
    }}
    .scale-chevron {{
      color: rgba(224, 230, 239, 0.18);
      font-size: 0.95rem;
      line-height: 1;
      user-select: none;
    }}
    /* Subtitle above each section ("Overview") — small, muted, uppercase
       to delineate without competing with the level word. */
    .status-section-title {{
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 600;
      margin: 0.9rem 0 0.35rem;
    }}
    .status-section-title:first-of-type {{ margin-top: 0.2rem; }}

    /* Collapsible "Key Drivers" section. Same uppercase-muted-subtitle
       style as the static section titles, but with a rotating chevron and
       click-to-expand behaviour. Closed by default. Used both on the
       landing-page status cards and the per-page summary cards for
       visual consistency. */
    .collapsible-section {{
      margin-top: 0.7rem;
    }}
    .collapsible-section > summary {{
      list-style: none;     /* hide default browser triangle */
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      user-select: none;
      padding: 0.25rem 0.45rem;
      margin: 0 -0.45rem;     /* let hover tint extend slightly past text edge */
      border-radius: 4px;
      transition: background 0.15s ease;
    }}
    .collapsible-section > summary:hover {{
      background: rgba(240,208,138,0.06);
    }}
    .collapsible-section > summary::-webkit-details-marker {{
      display: none;        /* Safari fallback */
    }}
    .collapsible-section > summary::before {{
      content: "▸";
      display: inline-block;
      color: var(--accent);
      font-size: 0.85rem;
      transition: transform 0.15s ease;
      transform-origin: 50% 50%;
    }}
    .collapsible-section[open] > summary::before {{
      transform: rotate(90deg);
    }}
    .collapsible-title {{
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 600;
    }}
    .collapsible-section > summary:hover .collapsible-title,
    .collapsible-section[open] > summary .collapsible-title {{
      color: var(--accent);
    }}
    .collapsible-count {{
      font-weight: 500;
      color: rgba(224, 230, 239, 0.4);
      letter-spacing: 0.04em;
    }}
    .collapsible-section[open] > .status-drivers,
    .collapsible-section[open] > .ps-findings,
    .collapsible-section[open] > .ps-gaps-list {{
      margin-top: 0.6rem;
    }}
    .status-drivers {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    .status-driver {{
      padding: 0.55rem 0.7rem;
      background: rgba(224,230,239,0.03);
      border-radius: 6px;
      border-left: 2px solid rgba(224,230,239,0.1);
    }}
    .status-driver-text {{
      margin: 0;
      font-size: 0.86rem;
      color: var(--text);
      line-height: 1.5;
    }}
    .status-driver-refs {{
      margin-top: 0.4rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
    }}
    .status-meta {{
      margin: 0.9rem 0 0;
      font-size: 0.78rem;
      color: var(--text-muted);
      text-align: right;
    }}

    /* Per-page summary card. Lives at the top of each page. Tight summary
       per question + bullet list of key_findings with inline chart-id
       badges that link to the chart's anchor on the same page. */
    .page-summary {{
      margin: 1rem 0 2rem;
    }}
    .ps-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 1.25rem;
    }}
    .ps-block {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.1rem 1.3rem;
    }}
    .ps-header {{
      margin-bottom: 0.5rem;
    }}
    .ps-header h2 {{
      margin: 0;
      font-size: 1.05rem;
      color: var(--accent);
      font-weight: 600;
    }}
    /* Section subtitles ("Take" / "Key findings") inside the per-page
       summary card — match the landing-page status-section-title styling
       for consistency. */
    .ps-section-title {{
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 600;
      margin: 0.7rem 0 0.3rem;
    }}
    .ps-section-title:first-of-type {{ margin-top: 0.2rem; }}
    .ps-summary {{
      margin: 0.2rem 0 0.5rem;
      font-size: 0.92rem;
      color: var(--text);
      line-height: 1.55;
      font-style: italic;
      text-align: justify;
      hyphens: auto;
    }}
    .ps-findings {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.7rem;
    }}
    .ps-finding {{
      padding: 0.55rem 0.7rem;
      background: rgba(224,230,239,0.03);
      border-radius: 6px;
      border-left: 2px solid rgba(224,230,239,0.1);
    }}
    .ps-finding-text {{
      margin: 0;
      font-size: 0.86rem;
      color: var(--text);
      line-height: 1.5;
    }}
    .ps-finding-refs {{
      margin-top: 0.4rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
    }}
    .chart-ref-badge {{
      display: inline-block;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.7rem;
      color: rgba(224,230,239,0.45);
      background: transparent;
      border: 1px solid rgba(224,230,239,0.1);
      border-radius: 4px;
      padding: 0.08rem 0.4rem;
      text-decoration: none;
      letter-spacing: 0.02em;
      transition: color 0.15s, background 0.15s, border-color 0.15s;
    }}
    .chart-ref-badge:hover {{
      color: var(--accent);
      background: rgba(240,208,138,0.08);
      border-color: rgba(240,208,138,0.25);
    }}
    /* Data Gaps reuses .collapsible-section; only override is a top divider
       and slightly more breathing room since it follows the Key Drivers list. */
    .ps-gaps {{
      margin-top: 0.6rem;
      border-top: 1px solid rgba(224,230,239,0.06);
      padding-top: 0.5rem;
    }}
    .ps-gaps-list {{
      margin: 0.6rem 0 0;
      padding-left: 1.2rem;
      font-size: 0.8rem;
      color: var(--text-muted);
      line-height: 1.5;
    }}
    .ps-gaps-list li {{ margin: 0.25rem 0; }}

    /* AI-disclosure + methodology footer (landing page only). Tight,
       single-line summary by default; expands to a short methodology
       brief. Visually muted so it sits below the status indicators
       without competing with them. */
    .ai-methodology {{
      margin: 1.4rem 0 0.5rem;
    }}
    .ai-method-details {{
      background: rgba(224,230,239,0.025);
      border: 1px solid rgba(224,230,239,0.06);
      border-radius: 8px;
      padding: 0.65rem 1rem;
      transition: background 0.15s ease, border-color 0.15s ease;
    }}
    .ai-method-details:hover {{
      background: rgba(240,208,138,0.04);
      border-color: rgba(240,208,138,0.18);
    }}
    .ai-method-details[open] {{
      background: rgba(224,230,239,0.04);
      border-color: rgba(224,230,239,0.1);
      padding-bottom: 0.4rem;
    }}
    .ai-method-summary {{
      list-style: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 0.84rem;
      color: var(--text-muted);
      user-select: none;
    }}
    .ai-method-summary::-webkit-details-marker {{ display: none; }}
    .ai-method-icon {{
      color: var(--accent);
      font-size: 0.95rem;
      line-height: 1;
    }}
    .ai-method-title {{
      flex: 1;
      color: var(--text);
    }}
    .ai-method-cta {{
      color: var(--accent);
      font-weight: 600;
      font-size: 0.8rem;
    }}
    .ai-method-arrow {{
      display: inline-block;
      transition: transform 0.15s ease;
      transform-origin: 50% 50%;
    }}
    .ai-method-details[open] .ai-method-arrow {{
      transform: rotate(90deg);
    }}
    .ai-method-body {{
      margin-top: 0.9rem;
      padding-top: 0.7rem;
      border-top: 1px solid rgba(224,230,239,0.07);
      font-size: 0.86rem;
      color: var(--text);
      line-height: 1.6;
    }}
    .ai-method-body p {{
      margin: 0.5rem 0 0.9rem;
      text-align: justify;
      hyphens: auto;
    }}
    .ai-method-body p:last-child {{ margin-bottom: 0.2rem; }}
    .ai-method-step-title {{
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 600;
      margin: 1rem 0 0.2rem;
    }}
    .ai-method-step-title:first-of-type {{ margin-top: 0.3rem; }}
    .ai-method-body code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.78rem;
      background: rgba(224,230,239,0.06);
      padding: 0.1rem 0.35rem;
      border-radius: 3px;
      color: var(--text);
    }}
    .ai-method-caveat {{
      color: var(--text-muted);
      font-style: italic;
      border-left: 2px solid rgba(240,208,138,0.3);
      padding-left: 0.7rem;
      margin-top: 1rem !important;
    }}

    .chart-container {{ position: relative; height: 240px; margin-top: 0.5rem; }}
    .chart-empty {{ padding: 2rem 0; text-align: center; }}
    .muted {{ color: var(--text-muted); }}

    /* Country-panel selector — used by the Regional Shipping tab to swap
       the same shipping-nowcast cards across the 9 regional countries.
       Same styling reused by .view-selector-* (Regional Trade product
       picker). */
    .country-selector-wrap, .view-selector-wrap {{
      display: flex; align-items: center; gap: 0.6rem;
      margin: 0.5rem 0 1.25rem;
    }}
    .country-selector-label, .view-selector-label {{
      font-size: 0.85rem; color: var(--text-muted); font-weight: 500;
    }}
    .country-selector, .view-selector {{
      background: var(--bg-card); color: var(--text);
      border: 1px solid var(--border); border-radius: 6px;
      padding: 0.35rem 0.6rem; font-size: 0.9rem;
      cursor: pointer;
    }}
    .country-selector:focus, .view-selector:focus {{
      outline: none; border-color: var(--accent);
    }}
    .country-panel {{ /* one per country; show/hide via inline display style */ }}
    .view-panel {{ /* one per view; show/hide via inline display style */ }}

    /* Per-chart action row (zoom in/out etc.). Mirrors the original
       shipping-nowcast dashboard's button styling. */
    .chart-actions {{
      display: flex; gap: 0.5rem; justify-content: flex-end;
      margin-top: 0.5rem;
    }}
    .zoom-toggle-btn {{
      background: transparent;
      color: #9ca3af;
      border: 1px solid #374151;
      border-radius: 4px;
      padding: 0.18rem 0.55rem;
      font-size: 0.72rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .zoom-toggle-btn:hover {{
      color: #e5e7eb; border-color: #6b7280; background: #1f2937;
    }}
    .zoom-toggle-btn.active {{
      color: var(--accent); border-color: var(--accent);
    }}

    /* Multi-subchart cards: a card containing multiple side-by-side plots
       (used by the Singapore Trade Exposure tab where each SITC has annual
       shares + monthly levels in one wide card). */
    .chart-card-multi {{ /* card itself uses the same .chart-card style */ }}
    /* Single shared legend across all subcharts in a card. Used when
       single_legend=True is passed; per-subchart Chart.js legends are
       suppressed in that case. */
    .card-legend {{
      display: flex; flex-wrap: wrap; gap: 0.4rem 1rem;
      margin: 0.25rem 0 0.5rem; padding: 0.5rem 0;
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
    }}
    .card-legend-item {{
      display: inline-flex; align-items: center; gap: 0.4rem;
      font-size: 0.78rem; color: var(--text-muted);
    }}
    .card-legend-swatch {{
      display: inline-block; width: 14px; height: 14px;
      border-radius: 3px; flex-shrink: 0;
    }}
    /* Override the per-card description max-width so it spans the full card
       on multi-subchart cards (default 64ch is for single-column readability;
       wide multi-cards have ~2× that width available). Same override applies
       when a card is alone on its row (columns=1 grid). */
    .chart-card-multi .card-desc,
    .chart-grid-single .card-desc {{ max-width: none; }}
    .subchart-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1.25rem;
      margin-top: 0.5rem;
    }}
    .subchart {{ min-width: 0; }}
    .subchart-title {{
      margin: 0 0 0.4rem 0;
      font-size: 0.78rem;
      color: var(--text-muted);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    @media (max-width: 800px) {{
      .subchart-grid {{ grid-template-columns: 1fr; }}
    }}

    /* ── Source chip palette (used in the Data sources table) ── */
    .source-chip {{
      display: inline-block;
      padding: 0.13rem 0.55rem;
      border-radius: 999px;
      font-size: 0.66rem; font-weight: 700;
      letter-spacing: 0.04em; text-transform: uppercase;
      white-space: nowrap;
    }}
    .source-chip.ceic      {{ background: rgba(96,165,250,0.20);  color: #60a5fa; }}
    .source-chip.bloomberg {{ background: rgba(52,211,153,0.20);  color: #34d399; }}
    .source-chip.singstat  {{ background: rgba(240,208,138,0.20); color: #f0d08a; }}
    .source-chip.motorist  {{ background: rgba(248,113,113,0.20); color: #f87171; }}
    .source-chip.yfinance  {{ background: rgba(34,211,238,0.20);  color: #22d3ee; }}
    .source-chip.adb       {{ background: rgba(167,139,250,0.20); color: #a78bfa; }}
    .source-chip.investing {{ background: rgba(251,146,60,0.20);  color: #fb923c; }}
    .source-chip.other     {{ background: rgba(224,230,239,0.12); color: rgba(224,230,239,0.7); }}

    /* ── Data sources expansion (collapsible section at page bottom) ── */
    .data-sources-section {{
      margin-top: 2.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }}
    .data-sources-section summary {{
      cursor: pointer;
      display: flex; align-items: center; gap: 0.75rem;
      padding: 0.7rem 0.95rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg-card);
      list-style: none;
      user-select: none;
      transition: all 0.18s;
    }}
    .data-sources-section summary::-webkit-details-marker {{ display: none; }}
    .data-sources-section summary::before {{
      content: "▶";
      color: var(--text-muted);
      font-size: 0.65rem;
      transition: transform 0.2s;
      display: inline-block;
    }}
    .data-sources-section[open] summary::before {{
      transform: rotate(90deg);
    }}
    .data-sources-section summary:hover {{
      background: var(--bg-card-hover);
      border-color: var(--border-strong);
    }}
    .ds-summary-label {{ color: var(--accent); font-weight: 600; font-size: 0.95rem; flex: 1; }}
    .ds-summary-count {{ color: var(--text-muted); font-size: 0.78rem; }}

    .ds-table-wrap {{
      margin-top: 1rem;
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    .ds-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
      color: var(--text);
    }}
    .ds-table th, .ds-table td {{
      text-align: left;
      padding: 0.6rem 0.85rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      vertical-align: top;
    }}
    .ds-table th {{
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.70rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: rgba(0,0,0,0.18);
      position: sticky; top: 0;
    }}
    .ds-table tbody tr:last-child td {{ border-bottom: none; }}
    .ds-table tbody tr:hover td {{ background: rgba(255,255,255,0.025); }}
    .ds-table tbody tr.ds-row-hidden {{ display: none; }}
    .ds-table .ds-chart  {{ color: var(--accent); font-weight: 500; white-space: nowrap; }}
    .ds-table .ds-series {{ color: rgba(224,230,239,0.85); }}
    .ds-table .ds-id {{
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.74rem;
      color: rgba(224,230,239,0.55);
    }}

    /* ── Date-range bar (zoom selector) ── */
    .date-range-bar {{
      display: flex; align-items: center; gap: 0.4rem;
      margin: 0 0 1.25rem;
    }}
    .date-range-bar .dr-label {{
      font-size: 0.72rem; color: rgba(224,230,239,0.4);
      margin-right: 0.2rem; font-weight: 600;
      letter-spacing: 0.05em; text-transform: uppercase;
    }}
    .dr-btn {{
      padding: 0.28rem 0.75rem;
      border-radius: 999px;
      border: 1px solid rgba(194,154,81,0.25);
      background: rgba(194,154,81,0.06);
      color: rgba(224,230,239,0.6);
      font-size: 0.74rem; font-weight: 600;
      cursor: pointer; transition: all 0.18s ease;
      font-family: inherit;
    }}
    .dr-btn:hover {{
      border-color: rgba(194,154,81,0.5);
      color: var(--text);
      background: rgba(194,154,81,0.12);
    }}
    .dr-btn.dr-active {{
      border-color: var(--accent);
      background: rgba(194,154,81,0.22);
      color: var(--accent);
    }}
    .chart-stale-label {{
      font-size: 0.72rem; color: rgba(248,113,113,0.78);
      font-style: italic;
      margin: 0 0 0.4rem 0.1rem;
    }}

    /* ── Tabs ── */
    .tab-nav {{
      display: flex; gap: 0.4rem; border-bottom: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }}
    .tab-btn {{
      background: transparent; border: 0; padding: 0.65rem 1.25rem;
      color: var(--text-muted); cursor: pointer; font-size: 0.92rem; font-weight: 500;
      border-bottom: 2px solid transparent; margin-bottom: -1px;
      font-family: inherit;
    }}
    .tab-btn:hover {{ color: var(--text); }}
    .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}

    /* ── Iframe section ── */
    .iframe-section .iframe-link {{ font-size: 0.88rem; margin-top: 0.5rem; }}
    .iframe-wrap {{
      margin-top: 1rem; height: 80vh; min-height: 600px;
      background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
      overflow: hidden;
    }}
    .iframe-wrap iframe {{ width: 100%; height: 100%; border: 0; display: block; }}

    /* ── Placeholder card ── */
    .placeholder-card {{
      background: var(--bg-card); border: 1px dashed var(--border); border-radius: 10px;
      padding: 1.5rem 1.75rem;
    }}
    .placeholder-badge {{
      display: inline-block; padding: 0.25rem 0.65rem;
      background: rgba(194, 154, 81, 0.18); color: var(--accent);
      border-radius: 4px; font-size: 0.7rem; font-weight: 600;
      letter-spacing: 0.05em; text-transform: uppercase;
      margin-bottom: 0.75rem;
    }}
    .placeholder-card h2 {{ margin: 0 0 0.5rem; font-size: 1.15rem; color: var(--text); }}
    .placeholder-intro {{ margin: 0 0 0.5rem; color: var(--text-muted); font-size: 0.9rem; }}
    .planned-content {{ margin: 0; padding-left: 1.4rem; color: var(--text-muted); line-height: 1.6; font-size: 0.9rem; }}

    /* ── Landing nav cards ── */
    .nav-cards-grid {{
      display: grid; gap: 1.25rem;
      grid-template-columns: repeat(3, 1fr);
      margin-top: 1.5rem;
    }}
    .nav-card {{
      background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
      color: var(--text); text-decoration: none;
      transition: all 0.2s;
      display: flex; flex-direction: column;
      overflow: hidden;
    }}
    .nav-card:hover {{ background: var(--bg-card-hover); border-color: var(--border-strong); transform: translateY(-2px); text-decoration: none; }}
    .nav-card-hero {{
      width: 100%; height: 160px;
      background: rgba(0,0,0,0.18);
      border-bottom: 1px solid var(--border);
      overflow: hidden;
    }}
    .nav-card-hero svg {{ display: block; width: 100%; height: 100%; }}
    .nav-card-body {{ padding: 1.4rem 1.6rem 1.6rem; flex: 1; }}
    .nav-card h3 {{ margin: 0 0 0.4rem; font-size: 1.15rem; color: var(--accent); font-weight: 600; }}
    .nav-card p {{ margin: 0; color: var(--text-muted); font-size: 0.92rem; line-height: 1.55; }}

    @media (max-width: 900px) {{
      .nav-cards-grid {{ grid-template-columns: 1fr; }}
    }}

    /* ── Report series intro (above PDF cards) ── */
    .report-series-intro {{
      margin: 0 0 1.5rem;
      padding: 1.1rem 1.4rem 1.2rem;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: 8px;
    }}
    .report-series-intro h3 {{
      margin: 0 0 0.6rem; font-size: 1.05rem;
      color: var(--accent); font-weight: 600;
    }}
    .report-series-intro p {{
      margin: 0 0 0.6rem; color: var(--text);
      font-size: 0.92rem; line-height: 1.6;
    }}
    .report-series-intro p:last-child {{ margin-bottom: 0; }}

    /* ── PDF cards ── */
    .pdf-grid {{
      display: grid; gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    .pdf-card {{
      display: flex; gap: 1rem; align-items: center;
      background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
      padding: 1rem; text-decoration: none; color: var(--text);
      transition: all 0.2s; position: relative;
    }}
    .pdf-card:hover {{ background: var(--bg-card-hover); border-color: var(--border-strong); text-decoration: none; }}
    .pdf-flag {{
      width: 56px; height: 38px; flex-shrink: 0;
      border-radius: 4px; overflow: hidden;
      background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
    }}
    .pdf-meta {{ flex: 1; min-width: 0; }}
    .pdf-meta h4 {{ margin: 0 0 0.2rem; font-size: 0.95rem; color: var(--text); font-weight: 600; line-height: 1.3; }}
    .pdf-date {{ margin: 0; font-size: 0.8rem; color: var(--text-muted); }}
    .pdf-country {{ margin: 0.15rem 0 0; font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }}
    .pdf-arrow {{ font-size: 1rem; color: var(--accent); opacity: 0.6; }}
    .pdf-card:hover .pdf-arrow {{ opacity: 1; }}
    .pdf-card.pdf-loading {{ opacity: 0.6; pointer-events: none; }}

    /* ── Access-warning modal (shown when a PDF card preflight fails) ── */
    .modal-overlay {{
      display: none;
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.7);
      backdrop-filter: blur(4px);
      z-index: 1000;
      align-items: center; justify-content: center;
      padding: 1rem;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal-content {{
      background: var(--bg-base);
      border: 1px solid var(--border-strong);
      border-radius: 12px;
      padding: 1.75rem 2rem 1.5rem;
      max-width: 520px; width: 100%;
      box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    }}
    .modal-content h3 {{
      margin: 0 0 0.85rem;
      color: var(--accent);
      font-size: 1.15rem; font-weight: 600;
    }}
    .modal-content p {{
      margin: 0 0 0.85rem;
      color: var(--text);
      font-size: 0.93rem; line-height: 1.55;
    }}
    .modal-content p:last-of-type {{ margin-bottom: 1.25rem; }}
    .modal-content code {{
      background: rgba(255,255,255,0.05);
      padding: 0.12rem 0.4rem;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 0.85rem; color: var(--accent);
    }}
    .modal-link {{
      color: var(--accent); font-weight: 500; text-decoration: none;
      border-bottom: 1px dashed rgba(240,208,138,0.4);
    }}
    .modal-link:hover {{ border-bottom-style: solid; text-decoration: none; }}
    .modal-actions {{ display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 1rem; }}
    .modal-btn {{
      padding: 0.5rem 1.2rem;
      border-radius: 6px;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.88rem; font-weight: 600;
      border: 1px solid var(--border);
      transition: all 0.18s;
    }}
    .modal-btn.modal-btn-primary {{
      background: rgba(194,154,81,0.22);
      color: var(--accent);
      border-color: rgba(194,154,81,0.5);
    }}
    .modal-btn.modal-btn-primary:hover {{ background: rgba(194,154,81,0.32); }}
    .modal-btn.modal-btn-secondary {{
      background: transparent;
      color: var(--text-muted);
    }}
    .modal-btn.modal-btn-secondary:hover {{ color: var(--text); background: rgba(255,255,255,0.04); }}

    /* ── Footer ── */
    footer {{
      max-width: 1280px; margin: 2rem auto 0; padding: 1.5rem 2rem;
      border-top: 1px solid var(--border);
      font-size: 0.78rem; color: var(--text-dim);
      display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem;
    }}

    @media (max-width: 720px) {{
      .page-header {{ padding: 1.5rem 1rem 0.5rem; }}
      .page-header h1 {{ font-size: 1.5rem; }}
      main {{ padding: 0 1rem 3rem; }}
      .topnav {{ padding: 0.65rem 1rem; overflow-x: auto; }}
      .chart-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  {nav}

  <header class="page-header">
    <h1>{title}</h1>
    <p class="subtitle">{subtitle}</p>
  </header>

  <main>
    {narrative}
    {date_range_bar}
    {sections}
    {data_sources}
  </main>

  <!-- Access-warning modal (used when a PDF card link can't be reached) -->
  <div id="access-warning-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="access-warning-title">
    <div class="modal-content">
      <h3 id="access-warning-title">MAS network access required</h3>
      <p>This report is hosted on the MAS team SharePoint site (<code>team.dms.mas.gov.sg</code>) and requires you to be connected to the MAS network or VPN to open.</p>
      <p>If you're already on the network and still seeing this, the link may have moved — you can try opening it directly:</p>
      <p><a id="access-warning-link" href="#" target="_blank" rel="noopener" class="modal-link">Try opening anyway &rarr;</a></p>
      <div class="modal-actions">
        <button class="modal-btn modal-btn-secondary" onclick="closeAccessWarning()">Close</button>
      </div>
    </div>
  </div>

  <footer>
    <span>Iran Monitor &middot; built {built_at} by MAS-EPG-EconTech</span>
    <span>Data: CEIC, SingStat, Motorist, DataGov, Bloomberg/GSheets, Yahoo Finance, ADB AsianBondsOnline, Investing.com, IMF PortWatch</span>
  </footer>

  <script>
    // ── PDF card click → preflight then either open or show access modal ──
    function pdfCardClick(event, url) {{
      event.preventDefault();
      const card = event.currentTarget;
      card.classList.add('pdf-loading');

      const timeoutMs = 3000;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      // no-cors HEAD: opaque response on success, network/timeout error if the
      // host is unreachable. Doesn't tell us about HTTP status (we can't read
      // opaque responses), but does tell us if the host can be reached at all.
      fetch(url, {{ mode: 'no-cors', method: 'HEAD', signal: controller.signal }})
        .then(() => {{
          clearTimeout(timeoutId);
          card.classList.remove('pdf-loading');
          window.open(url, '_blank', 'noopener');
        }})
        .catch(() => {{
          clearTimeout(timeoutId);
          card.classList.remove('pdf-loading');
          showAccessWarning(url);
        }});
    }}

    function showAccessWarning(url) {{
      const modal = document.getElementById('access-warning-modal');
      const link = document.getElementById('access-warning-link');
      if (link) link.href = url;
      if (modal) modal.classList.add('open');
    }}

    function closeAccessWarning() {{
      const modal = document.getElementById('access-warning-modal');
      if (modal) modal.classList.remove('open');
    }}

    // ESC key + click-on-overlay to close modal
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') closeAccessWarning();
    }});
    document.addEventListener('click', (e) => {{
      const modal = document.getElementById('access-warning-modal');
      if (modal && e.target === modal) closeAccessWarning();
    }});

    // ── Tab switching ──
    function switchTab(btn, slug) {{
      const group = btn.closest('.page-section');
      group.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
      group.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + slug));
      filterDataSourcesByTab(slug);
      applyDateRangeBarVisibility(btn);
    }}

    // ── Hide the page-wide "War period / 1Y / All time" selector when the
    // active tab is marked data-hide-date-range (e.g. Trade tabs whose
    // content is all bar charts on a category x-axis — zoom is irrelevant).
    function applyDateRangeBarVisibility(activeBtn) {{
      const bar = document.querySelector('.date-range-bar');
      if (!bar) return;
      const hide = activeBtn && activeBtn.dataset.hideDateRange === "true";
      bar.style.display = hide ? "none" : "";
    }}

    // ── Data sources table — filter rows by active tab ──
    function filterDataSourcesByTab(activeTab) {{
      const rows = document.querySelectorAll('.ds-table tbody tr');
      let visibleRows = 0;
      const visibleCharts = new Set();
      rows.forEach(tr => {{
        const tabAttr = tr.dataset.tab;
        // Rows with no data-tab (charts not inside a tab_group) always show.
        const visible = !tabAttr || tabAttr === activeTab;
        tr.classList.toggle('ds-row-hidden', !visible);
        if (visible) {{
          visibleRows += 1;
          const chartCell = tr.querySelector('.ds-chart');
          if (chartCell) visibleCharts.add(chartCell.textContent.trim());
        }}
      }});
      const countEl = document.getElementById('dsSummaryCount');
      if (countEl) {{
        countEl.textContent = visibleRows + ' series across ' + visibleCharts.size + ' charts';
      }}
      // Hide the entire collapsible expansion when the active tab has no
      // charts (e.g. Trade / Shipping / MAS EPG reports tabs that are pure
      // placeholders or PDF cards). Avoids showing "0 series across 0 charts".
      const section = document.querySelector('.data-sources-section');
      if (section) {{
        section.style.display = (visibleRows === 0) ? 'none' : '';
      }}
    }}

    // ── Date-range / war-period zoom ──
    // Mirrors the original Middle East Energy Dashboard's behavior exactly:
    //  - "All time" shows full data
    //  - "1Y" shows the last 365 days
    //  - "War period" zooms to [2026-01-01, today] with a stale label fallback
    //    for series whose data ends before the war start (2026-02-28).
    const WAR_START      = "2026-02-28";
    const WAR_ZOOM_START = "2026-01-01";
    let currentDateRange = "war";  // default

    function setDateRange(range) {{
      currentDateRange = range;
      document.querySelectorAll(".dr-btn").forEach(btn => {{
        btn.classList.toggle("dr-active", btn.dataset.range === range);
      }});
      applyDateRange(range);
    }}

    function applyDateRange(range) {{
      const now = new Date().toISOString().slice(0, 10);
      const oneYearAgo = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
      const instances = window._chartInstances || {{}};

      // Remove any previous stale labels before re-applying
      document.querySelectorAll(".chart-stale-label").forEach(el => el.remove());

      Object.entries(instances).forEach(([id, chart]) => {{
        if (!chart) return;

        // Skip charts that own their zoom via a per-chart Zoom In/Out button
        // (e.g. shipping nowcast cards). Otherwise the page-level default
        // would clobber the user's per-chart state.
        if (NO_DEFAULT_ZOOM.has(id)) return;

        // Skip non-time-axis charts (e.g. bar charts with category x-axis).
        // The page-wide date-range selector only makes sense for time series;
        // category-axis charts have a fixed set of discrete labels.
        const xType = chart.options && chart.options.scales && chart.options.scales.x && chart.options.scales.x.type;
        if (xType && xType !== "time") return;

        // Find the earliest and latest dates across this chart's datasets.
        let latestDate = "";
        let earliestDate = "";
        chart.data.datasets.forEach(ds => {{
          ds.data.forEach(pt => {{
            const x = typeof pt === "object" ? pt.x : null;
            if (!x) return;
            if (x > latestDate) latestDate = x;
            if (!earliestDate || x < earliestDate) earliestDate = x;
          }});
        }});

        let xMin, xMax;
        if (range === "all") {{
          xMin = null; xMax = null;
        }} else if (range === "1y") {{
          xMin = oneYearAgo; xMax = now;
        }} else if (range === "war") {{
          // Unified war-zoom logic for ALL charts:
          //   xMax is always `now` (so the WAR_START annotation + any
          //   post-war gap remain visible).
          //   xMin defaults to WAR_ZOOM_START, but walks backward through
          //   the data when there are fewer than MIN_WAR_POINTS distinct
          //   timestamps in the window — so low-frequency charts AND
          //   stale-data charts both render with consistent x-axis width
          //   relative to sibling charts (data on the left, empty gap on
          //   the right for stale series).
          xMax = now;
          xMin = WAR_ZOOM_START;

          // Count DISTINCT timestamps (not total points) — a 4-series
          // monthly chart with 3 dates × 4 lines = 12 points is still
          // visually 3 columns of dots, so we walk back if too few dates.
          const MIN_WAR_POINTS = 8;
          const inWindow = new Set();
          const allDates = new Set();
          chart.data.datasets.forEach(ds => {{
            ds.data.forEach(pt => {{
              const x = typeof pt === "object" ? pt.x : null;
              if (!x) return;
              allDates.add(x);
              if (x >= WAR_ZOOM_START) inWindow.add(x);
            }});
          }});
          if (inWindow.size < MIN_WAR_POINTS && allDates.size > 0) {{
            const sorted = Array.from(allDates).sort();
            const idx = Math.max(0, sorted.length - MIN_WAR_POINTS);
            xMin = sorted[idx];
          }}

          // Stale-data label, two flavours:
          //   (a) data ENDS before the war (whole series is pre-war stale)
          //   (b) data STARTS after the war begins (no pre-war context)
          // Only one shows per chart; (a) takes precedence since a series
          // can't simultaneously end before and start after WAR_START.
          if (!latestDate || latestDate < WAR_START) {{
            const canvas = document.getElementById(id);
            const container = canvas && canvas.parentElement;
            if (container && !container.parentElement.querySelector(".chart-stale-label")) {{
              const lastFmt = latestDate
                ? new Date(latestDate).toLocaleDateString("en-US", {{ month: "short", year: "numeric" }})
                : "unknown";
              const label = document.createElement("div");
              label.className = "chart-stale-label";
              label.textContent = "Data ends " + lastFmt + " \u2014 no war-period coverage";
              container.parentElement.insertBefore(label, container);
            }}
          }} else if (earliestDate && earliestDate >= WAR_START) {{
            // Series only starts on/after the war began \u2014 no pre-war context.
            // Common for new ingest sources (e.g. day-by-day investing.com
            // commodity scrapes that started in March 2026).
            const canvas = document.getElementById(id);
            const container = canvas && canvas.parentElement;
            if (container && !container.parentElement.querySelector(".chart-stale-label")) {{
              const startFmt = new Date(earliestDate)
                .toLocaleDateString("en-US", {{ month: "short", year: "numeric" }});
              const label = document.createElement("div");
              label.className = "chart-stale-label";
              label.textContent = "Data starts " + startFmt + " \u2014 no pre-war context";
              container.parentElement.insertBefore(label, container);
            }}
          }}
        }}

        // Use delete for null to fully clear the constraint (Chart.js doesn't
        // always treat undefined / null assignments as "no bound").
        if (xMin === null) {{ delete chart.options.scales.x.min; }} else {{ chart.options.scales.x.min = xMin; }}
        if (xMax === null) {{ delete chart.options.scales.x.max; }} else {{ chart.options.scales.x.max = xMax; }}
        chart.update();
      }});
    }}

    // ── Country-panel selector (Regional Shipping tab) ──
    // The country_panels section emits N <div class="country-panel"
    // data-country="<iso2>"> blocks, only one of which is visible at a time.
    // The dropdown's onchange fires this handler to swap visibility.
    // ── View selector (Regional Trade product picker, etc.) ──
    // Same pattern as switchCountryPanel: hides all sibling .view-panel
    // divs in the same <section>, then shows the one with matching
    // data-view, and triggers chart resize on the now-visible canvases.
    function switchView(selectEl) {{
      const key = selectEl.value;
      const wrap = selectEl.closest("section");
      if (!wrap) return;
      wrap.querySelectorAll(".view-panel").forEach(p => {{
        p.style.display = (p.dataset.view === key) ? "" : "none";
      }});
      const active = wrap.querySelector('.view-panel[data-view="' + key + '"]');
      if (active && window._chartInstances) {{
        active.querySelectorAll(".chart-card canvas[id]").forEach(canvas => {{
          const inst = window._chartInstances[canvas.id];
          if (inst) inst.resize();
        }});
      }}
    }}
    window.switchView = switchView;

    function switchCountryPanel(selectEl) {{
      const iso2 = selectEl.value;
      // Find the parent .country-panels container so we only switch within
      // this section (not other selectors on the page).
      const wrap = selectEl.closest("section");
      if (!wrap) return;
      const panels = wrap.querySelectorAll(".country-panel");
      panels.forEach(p => {{
        const match = (p.dataset.country === iso2);
        p.style.display = match ? "" : "none";
      }});
      // Charts inside a hidden panel don't lay out properly until the panel
      // is shown. Trigger a Chart.js resize on every chart in the now-active
      // panel and re-apply the current page-level date range so axes are
      // correct.
      const activePanel = wrap.querySelector('.country-panel[data-country="' + iso2 + '"]');
      if (activePanel && window._chartInstances) {{
        activePanel.querySelectorAll(".chart-card canvas[id]").forEach(canvas => {{
          const inst = window._chartInstances[canvas.id];
          if (inst) {{
            inst.resize();
            // Respect any per-chart zoom state (don't clobber Zoom In).
            if (!window._chartZoomState || !window._chartZoomState[canvas.id]) {{
              if (typeof applyDateRange === "function" &&
                  typeof currentDateRange !== "undefined") {{
                // Date range will be re-applied to all charts on next user
                // click; but we also force a refresh now via the chart itself.
                inst.update("none");
              }}
            }}
          }}
        }});
      }}
    }}
    window.switchCountryPanel = switchCountryPanel;

    // ── Per-chart Zoom In / Zoom Out toggle ──
    // Mirrors the original shipping-nowcast dash. Overrides the page-level
    // date-range bar for a single chart: zoomed-in view spans ~3 months
    // pre-war + post-war (so the war annotation + recent detail are
    // maximally legible); zoomed-out view restores the page's currently-
    // selected range (war / 1y / all).
    window._chartZoomState = window._chartZoomState || {{}};   // chartId -> bool
    function toggleChartZoom(btn) {{
      const targetId = btn.dataset.target;
      if (!targetId) return;
      const chart = window._chartInstances[targetId];
      if (!chart) return;
      const zoomedIn = !window._chartZoomState[targetId];
      window._chartZoomState[targetId] = zoomedIn;

      if (zoomedIn) {{
        // ~3 months pre-war + everything from war start onward
        const warDate = new Date(WAR_START);
        warDate.setDate(warDate.getDate() - 91);
        const xMin = warDate.toISOString().slice(0, 10);
        const xMax = new Date().toISOString().slice(0, 10);
        chart.options.scales.x.min = xMin;
        chart.options.scales.x.max = xMax;
        chart.update();
        btn.textContent = "Zoom Out";
        btn.title = "Restore the page-level date range";
        btn.classList.add("active");
      }} else {{
        // Hand control back to the page-level date-range bar.
        delete chart.options.scales.x.min;
        delete chart.options.scales.x.max;
        chart.update();
        // Re-apply whatever the date-range bar currently has selected, so
        // un-zooming doesn't leave us stuck on whatever the chart showed
        // before the user pressed "Zoom In".
        if (typeof applyDateRange === "function" && typeof currentDateRange !== "undefined") {{
          applyDateRange(currentDateRange);
        }}
        btn.textContent = "Zoom In";
        btn.title = "Zoom in to ~3 months pre-war + war period";
        btn.classList.remove("active");
      }}
    }}
    window.toggleChartZoom = toggleChartZoom;

    // ── Chart.js initialization ──
    const CHART_CONFIGS = {chart_configs};
    // Charts that own their zoom (per-chart Zoom In/Out button). applyDateRange
    // skips these so the page-level "war" default doesn't override.
    const NO_DEFAULT_ZOOM = new Set({no_default_zoom_ids});
    document.addEventListener('DOMContentLoaded', () => {{
      window._chartInstances = {{}};
      // Buttons that ship with `data-default-zoomed-in="true"` mean the
      // chart was rendered with a zoomed-in x-axis baked in. Seed the
      // chartZoomState so the FIRST click on the toggle correctly flips
      // to "Zoom Out" (otherwise the toggle inverts the meaning).
      document.querySelectorAll(
        '.zoom-toggle-btn[data-default-zoomed-in="true"]'
      ).forEach(btn => {{
        const tid = btn.dataset.target;
        if (tid) window._chartZoomState[tid] = true;
      }});
      Object.entries(CHART_CONFIGS).forEach(([id, cfg]) => {{
        const el = document.getElementById(id);
        if (!el) return;
        try {{
          window._chartInstances[id] = new Chart(el, cfg);
        }} catch (e) {{
          console.error('Chart init failed for', id, e);
        }}
      }});
      // Apply default zoom (war period)
      if (Object.keys(CHART_CONFIGS).length > 0) {{
        applyDateRange(currentDateRange);
      }}
      // Filter data-sources table + apply date-range-bar visibility for the
      // initially-active tab (in case it's flagged hide_date_range).
      const activeTabBtn = document.querySelector('.tab-btn.active');
      if (activeTabBtn && activeTabBtn.dataset.tab) {{
        filterDataSourcesByTab(activeTabBtn.dataset.tab);
        applyDateRangeBarVisibility(activeTabBtn);
      }} else {{
        // No tabs on this page — show all rows and total count
        filterDataSourcesByTab(null);
      }}

      // ── Chart-ID badge: click to copy URL fragment to clipboard ──
      // Each card surfaces its deterministic ID (e.g. ⌗ sg.activity.petroleum_refining)
      // as an anchor. Clicking copies the absolute URL with #<id> fragment so the
      // viewer can paste it into chat / docs and land directly on the chart.
      document.addEventListener('click', function(ev) {{
        const badge = ev.target.closest('.chart-id-badge');
        if (!badge) return;
        ev.preventDefault();
        const cid = badge.dataset.chartId;
        if (!cid) return;
        const url = window.location.origin + window.location.pathname + '#' + cid;
        const done = () => {{
          badge.classList.add('copied');
          setTimeout(() => badge.classList.remove('copied'), 900);
          // Update the URL fragment so #-targeted highlight kicks in immediately.
          history.replaceState(null, '', '#' + cid);
          highlightTargetedChart();
        }};
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(url).then(done, done);
        }} else {{
          done();
        }}
      }});

      // ── URL-fragment-targeted chart highlight ──
      // When the page loads (or hash changes) with #<chart_id>, briefly outline
      // the matching .chart-card so the viewer sees the LLM citation target.
      // If the target lives inside a hidden tab panel, country panel, or view
      // panel, activate the right one first — otherwise scrollIntoView is a
      // no-op on display:none elements.
      function highlightTargetedChart() {{
        document.querySelectorAll('.chart-card.target-flash').forEach(el =>
          el.classList.remove('target-flash')
        );
        const hash = window.location.hash;
        if (!hash || hash.length <= 1) return;
        const raw = hash.slice(1);
        // Resolve the card. Hashes can take three forms:
        //   #card-<chart_id>   — already the card wrapper id (most common from LLM badges)
        //   #<chart_id>        — bare chart id, needs 'card-' prepended
        //   #<canvas_id>       — direct canvas id (legacy chart-id-footer badges)
        // Use getElementById throughout to avoid CSS-selector escaping issues
        // with the dot-separated chart id format.
        let card = null;
        if (raw.startsWith('card-')) {{
          card = document.getElementById(raw);
        }}
        if (!card) card = document.getElementById('card-' + raw);
        if (!card) {{
          const canvas = document.getElementById(raw);
          card = canvas ? canvas.closest('.chart-card') : null;
        }}
        if (!card) return;

        // Walk every ancestor of `card` and collect the panels that need
        // activating. Three flavours exist:
        //   .tab-panel       — switched by .tab-btn click (no inline display style;
        //                      uses 'active' class)
        //   .country-panel   — switched by <select> + switchCountryPanel();
        //                      hidden via inline style="display: none"
        //   .view-panel      — switched by <select> + switchView();
        //                      hidden via inline style="display: none"
        // Activating from innermost outward isn't required (each switcher
        // is independent), but processing them all in one pass — instead of
        // jumping outward via .closest() — is what fixes the nested case
        // (country-panel inside tab-panel: jumping past the tab-panel via
        // .parentElement.closest() loses sight of the inner country-panel).
        const panelsToActivate = [];
        for (let n = card.parentElement; n; n = n.parentElement) {{
          if (!n.classList) continue;
          if (n.classList.contains('tab-panel') && !n.classList.contains('active')) {{
            panelsToActivate.push({{ kind: 'tab', el: n }});
          }} else if (n.classList.contains('country-panel') && n.style.display === 'none') {{
            panelsToActivate.push({{ kind: 'country', el: n }});
          }} else if (n.classList.contains('view-panel') && n.style.display === 'none') {{
            panelsToActivate.push({{ kind: 'view', el: n }});
          }}
        }}
        for (const p of panelsToActivate) {{
          if (p.kind === 'tab') {{
            const slug = p.el.id.replace(/^tab-/, '');
            const btn = document.querySelector('.tab-btn[data-tab="' + CSS.escape(slug) + '"]');
            if (btn) {{
              switchTab(btn, slug);
            }} else {{
              const group = p.el.closest('.page-section');
              if (group) {{
                group.querySelectorAll('.tab-panel').forEach(x =>
                  x.classList.toggle('active', x === p.el)
                );
              }}
            }}
          }} else if (p.kind === 'country') {{
            const iso2 = p.el.dataset.country;
            const sect = p.el.closest('section');
            const sel  = sect ? sect.querySelector('select') : null;
            if (sel && iso2) {{
              sel.value = iso2;
              if (typeof switchCountryPanel === 'function') {{
                switchCountryPanel(sel);
              }} else {{
                sect.querySelectorAll('.country-panel').forEach(x => {{
                  x.style.display = (x.dataset.country === iso2) ? '' : 'none';
                }});
              }}
            }}
          }} else if (p.kind === 'view') {{
            const view = p.el.dataset.view;
            const sect = p.el.closest('section');
            const sel  = sect ? sect.querySelector('select') : null;
            if (sel && view) {{
              sel.value = view;
              if (typeof switchView === 'function') {{
                switchView(sel);
              }} else {{
                sect.querySelectorAll('.view-panel').forEach(x => {{
                  x.style.display = (x.dataset.view === view) ? '' : 'none';
                }});
              }}
            }}
          }}
        }}

        // Activating a country/view panel triggers Chart.js resizes + a
        // date-range re-application, which can take a few frames to settle.
        // Wait long enough for the layout to stabilise before scrolling, and
        // use block:'start' so multi-row cards land at the top of the
        // viewport unambiguously (block:'center' can put a tall card's
        // mid-section at the viewport centre, making the bottom half look
        // like it IS the card).
        const scrollAndFlash = () => {{
          card.classList.add('target-flash');
          card.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          setTimeout(() => card.classList.remove('target-flash'), 2200);
        }};
        // Two-stage wait: rAF lets one paint happen, setTimeout(120) gives
        // Chart.js resize callbacks time to complete before we measure.
        requestAnimationFrame(() => setTimeout(scrollAndFlash, 120));
      }}
      window.addEventListener('hashchange', highlightTargetedChart);
      // Run once at load — handles both bookmark links and freshly-shared URLs.
      setTimeout(highlightTargetedChart, 50);
    }});
  </script>
</body>
</html>'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Build Iran Monitor static HTML pages.",
    )
    p.add_argument(
        "--airbase",
        metavar="AIRBASE_PUBLIC_DIR",
        help="If set, ALSO emit a CSP-compliant variant of each page into "
             "the given directory (typically /opt/airbase-iran/public/). "
             "Replaces inline <script>/onclick with external dashboard.js + "
             "data-* attributes, and points <script src=...> at vendor/ "
             "instead of CDN URLs. The regular GitHub-Pages-style HTML is "
             "always written to the repo root regardless of this flag.",
    )
    args = p.parse_args()

    airbase_dir = None
    if args.airbase:
        from pathlib import Path as _Path
        airbase_dir = _Path(args.airbase).resolve()
        airbase_dir.mkdir(parents=True, exist_ok=True)
        # Copy vendor JS files into airbase public/vendor/ so the CSP-
        # compliant HTML can reference them locally instead of via CDN.
        from shutil import copy2
        vendor_src = ROOT / "assets" / "vendor"
        vendor_dst = airbase_dir / "vendor"
        vendor_dst.mkdir(parents=True, exist_ok=True)
        for v in vendor_src.glob("*.js"):
            copy2(v, vendor_dst / v.name)
        print(f"Airbase mode: writing CSP-compliant variant + vendor/ to {airbase_dir}")

    # Lazy import — only needed in airbase mode.
    csp_transform_page = None
    if airbase_dir:
        sys.path.insert(0, str(ROOT / "scripts"))
        from csp_transform import csp_transform_page  # noqa: E402

    conn = get_connection()
    print(f"Building Iran Monitor pages → {OUTPUT_DIR}")
    # Aggregate chart manifest across all pages — fed to the summary-stats
    # extractor, which the LLM narrative system consumes. Each chart's
    # entry knows which page it came from so a single LLM page-call can
    # see only that page's charts.
    manifest: dict = {}
    dashboard_js_seen: str | None = None   # capture once, write once for airbase
    for slug, page_def in PAGES.items():
        html_str, data_sources_state = render_page(slug, page_def, conn)
        out_path = OUTPUT_DIR / f"{slug if slug != 'index' else 'index'}.html"
        out_path.write_text(html_str, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  {out_path.name}: {size_kb:.1f} KB")

        # Airbase variant: post-transform the same HTML into CSP-compliant
        # form and write to <airbase_dir>/<page>.html plus the per-page
        # chart-configs JS.
        if airbase_dir:
            transformed_html, dashboard_js, chart_configs_js = csp_transform_page(
                html_str, slug,
            )
            (airbase_dir / out_path.name).write_text(transformed_html, encoding="utf-8")
            (airbase_dir / f"chart-configs-{slug}.js").write_text(
                chart_configs_js, encoding="utf-8",
            )
            # dashboard.js content is identical for every page — capture
            # the first non-empty version and write it once at the end.
            if dashboard_js and not dashboard_js_seen:
                dashboard_js_seen = dashboard_js
        # Stash chart-level metadata for the manifest. We store only the
        # series_id list per chart (not the full series-data lists which
        # would make the manifest huge); the extractor re-queries the DB
        # for stats.
        for chart_id, info in data_sources_state.items():
            # Skip rows without a series list (e.g. the country_share_comparison
            # entries register synthetic series with friendly_name only).
            series_ids = [s.get("series_id") for s in info.get("series", []) if s.get("series_id")]
            if not series_ids:
                continue
            manifest_entry = {
                "page":           slug,
                "page_prefix":    info.get("page_prefix", ""),
                "tab_slug":       info.get("tab_slug") or "",
                "title":          info.get("title", ""),
                "description":    info.get("description", ""),
                "relevant_to":    info.get("relevant_to") or [],
                "parent_chart_id": info.get("parent_chart_id"),
                "series_ids":     series_ids,
            }
            # Multi-subchart parent cards carry per-subchart metadata so the
            # summary-stats extractor can compute pair-aware signals
            # (e.g. nowcast actual-vs-counterfactual gaps).
            if info.get("subchart_meta"):
                manifest_entry["subchart_meta"] = info["subchart_meta"]
            manifest[chart_id] = manifest_entry
    conn.close()

    # Write the manifest. The summary-stats extractor reads this back instead
    # of re-walking the layout config (which would risk drift in chart-ID
    # generation between the build and the extractor).
    manifest_path = ROOT / "data" / "chart_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  chart_manifest.json: {len(manifest)} charts → {manifest_path.name}")

    # Airbase: write the shared dashboard.js once (its content is identical
    # for every page; we captured it from the first transformed page above).
    if airbase_dir and dashboard_js_seen:
        (airbase_dir / "dashboard.js").write_text(dashboard_js_seen, encoding="utf-8")
        airbase_size_kb = sum(
            f.stat().st_size for f in airbase_dir.rglob("*") if f.is_file()
        ) / 1024
        print(f"  Airbase variant complete in {airbase_dir} ({airbase_size_kb:.0f} KB total)")

    print("Done.")


if __name__ == "__main__":
    main()
