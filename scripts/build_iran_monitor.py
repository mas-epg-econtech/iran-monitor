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
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path so we can import from src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection
from src.dependency_config import DEPENDENCY_NODES
from src.page_layouts import PAGES, PAGE_NAV, LANDING_CARDS
from src.flag_svgs import get_flag
from src.illustrations import get_hero
from src.series_descriptions import lookup as series_lookup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SINCE_DATE = "2021-01-01"   # Filter charts to data from this date onwards
CRISIS_DATE = "2026-02-28"  # Hormuz crisis onset (a.k.a. WAR_START); used for annotation
WAR_ZOOM_START = "2026-01-01"  # War-period view zoom start (~2 months pre-war for context)
OUTPUT_DIR = ROOT


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


def resolve_node_to_series_ids(conn, node_id: str) -> list[str]:
    """Resolve a dependency_config node to a concrete list of series_ids in the DB."""
    node = DEPENDENCY_NODES.get(node_id)
    if not node:
        return []
    series_ids = list(node.get("series_ids", []))

    # Resolve google_sheet_series via prefix matching against gsheets_* series_ids.
    # The DB stores them as gsheets_daily_<exact label>, gsheets_weekly_<...>, etc.
    for partial_label in node.get("google_sheet_series", []):
        # Use the first 35 chars of the label as a robust prefix match (avoids
        # being defeated by long labels that may have been truncated at write time).
        prefix = partial_label[:35].replace("'", "''")
        matches = conn.execute(
            "SELECT DISTINCT series_id FROM time_series WHERE series_id LIKE ?",
            (f"gsheets_%_{prefix}%",),
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


def build_chart_config(title: str, series_list: list[dict]) -> dict:
    """Build a Chart.js config dict for a multi-series line chart with a
    war-start vertical annotation. The initial x-axis range is set to the war
    period for series that have war-period data, so charts render at the right
    zoom on first paint (not after a JS update). Stale series (no data past
    WAR_START) initialize with no min so they show all available data — the JS
    applyDateRange function adds the "no war-period coverage" label for those.
    """
    datasets = []
    for i, s in enumerate(series_list):
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        data_points = [{"x": d, "y": v} for d, v in s["data"]]
        # Prefer the friendly name in the legend so long Bloomberg labels don't crowd the chart.
        label = s.get("friendly_name") or s["name"]
        if s.get("unit"):
            label = f"{label} ({s['unit']})"
        datasets.append({
            "label": label,
            "data": data_points,
            "borderColor": color,
            "backgroundColor": color + "20",  # 12.5% alpha
            "borderWidth": 1.6,
            "pointRadius": 0,
            "tension": 0.18,
            "spanGaps": True,
        })

    # Determine if any series in this chart has data past the war start.
    # If so, initialize the chart at war-period zoom; if not, leave full range.
    has_war_data = any(
        s["data"] and s["data"][-1][0] >= CRISIS_DATE
        for s in series_list
    )

    x_scale = {
        "type": "time",
        "time": {"unit": "month", "tooltipFormat": "MMM d, yyyy"},
        "ticks": {"color": "rgba(224, 230, 239, 0.5)", "font": {"size": 10}, "maxTicksLimit": 8},
        "grid": {"color": "rgba(224, 230, 239, 0.06)"},
    }
    if has_war_data:
        x_scale["min"] = WAR_ZOOM_START

    return {
        "type": "line",
        "data": {"datasets": datasets},
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
                # War-start vertical line (chartjs-plugin-annotation)
                "annotation": {
                    "annotations": {
                        "warLine": {
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
                    }
                },
            },
            "scales": {
                "x": x_scale,
                "y": {
                    "ticks": {"color": "rgba(224, 230, 239, 0.6)", "font": {"size": 10}},
                    "grid": {"color": "rgba(224, 230, 239, 0.06)"},
                },
            },
        },
    }


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


def render_chart_grid(section: dict, conn, chart_state: dict, data_sources_state: dict, tab_slug: str | None = None) -> str:
    """Render a chart_grid section.

    Two ways to specify the charts in this grid (can be combined in one section):
      - `nodes`: an ordered list whose items are either:
            * a string  → resolves to a dependency_config node
            * a dict    → custom series group: {"label": "...", "description": "...",
                                                "series": ["series_id", ...]}
        The order is preserved, allowing custom groups to be interleaved with nodes.
      - `series_groups`: a list of (label, [series_ids]) tuples — kept for backward
        compatibility with the Regional Financial Markets section.

    Auto-split: when a single node/group resolves to series with >1 distinct unit,
    the renderer emits one chart card per unit (titled "{label} — {unit}") so that
    incompatible scales aren't squashed onto the same y-axis.

    `tab_slug` is forwarded to each chart card so the page-bottom Data Sources
    table can filter its rows by active tab.
    """
    title = section.get("title", "")
    desc = section.get("description", "")

    cards = []

    def _emit(label: str, description: str, series_ids: list[str], base_prefix: str):
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
        series_list = _resolve_series_list(conn, series_ids)
        if not series_list:
            cards.append(_render_chart_card_for_series(
                label, description, [],
                chart_state, base_prefix, data_sources_state, tab_slug))
            return
        for unit, sublist in _split_by_unit(series_list):
            # Decide title + description + prefix based on group composition
            single_friendly = (
                len(sublist) == 1 and sublist[0].get("friendly_name") and sublist[0].get("friendly_desc")
            )
            if single_friendly:
                fname = sublist[0]["friendly_name"]
                # If the section label already contains the friendly name (or vice versa),
                # don't double up — e.g., "Brent crude oil — Brent (ICE)" is awkward.
                _fname_l = fname.lower()
                _label_l = label.lower()
                if _fname_l == _label_l or _fname_l in _label_l or _label_l in _fname_l:
                    chart_title = label
                else:
                    chart_title = f"{label} — {fname}"
                chart_desc = sublist[0]["friendly_desc"]
                chart_prefix = f"{base_prefix}_{_unit_slug(fname)}"
            elif unit is None:
                # Single-unit group, no split, no friendly override
                chart_title = label
                chart_desc = description
                chart_prefix = base_prefix
            else:
                chart_title = f"{label} — {unit}"
                chart_desc = description
                chart_prefix = f"{base_prefix}_{_unit_slug(unit)}"
            cards.append(_render_chart_card_for_series(
                chart_title, chart_desc, sublist,
                chart_state, chart_prefix, data_sources_state, tab_slug))

    # Mode 1: ordered `nodes` list (mix of node refs and custom groups)
    for item in section.get("nodes", []):
        if isinstance(item, str):
            node = DEPENDENCY_NODES.get(item)
            if not node:
                continue
            sids = resolve_node_to_series_ids(conn, item)
            _emit(node["label"], node.get("description", ""), sids, base_prefix=item)
        elif isinstance(item, dict):
            base = item.get("slug") or item["label"].lower().replace(" ", "_").replace("(", "").replace(")", "")
            _emit(item["label"], item.get("description", ""), item["series"], base_prefix=base)

    # Mode 2: explicit series_groups tuples (kept for Regional Financial Markets)
    for group_label, sids in section.get("series_groups", []):
        _emit(group_label, "", sids, base_prefix=group_label.replace(" ", "_"))

    inner = "\n".join(cards)
    desc_html = f'<p class="section-desc">{desc}</p>' if desc else ""
    return f'''
    <section class="page-section">
      <div class="section-header">
        <h2>{title}</h2>
        {desc_html}
      </div>
      <div class="chart-grid">
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
                                   tab_slug: str | None = None) -> str:
    """Render one chart card from a pre-resolved series_list (no DB I/O inside)."""
    if not series_list:
        return f'''
        <div class="chart-card">
          <div class="chart-empty">
            <h3>{html.escape(title)}</h3>
            <p class="muted">No data available for this series.</p>
          </div>
        </div>'''

    chart_id = f"chart_{prefix}_{len(chart_state)}"
    chart_state[chart_id] = build_chart_config(title, series_list)

    title_safe = html.escape(title)
    desc_html = f'<p class="card-desc">{html.escape(description)}</p>' if description else ""

    # Record series metadata for the page-level Data Sources table.
    data_sources_state[chart_id] = {
        "title": title,
        "series": series_list,
        "tab_slug": tab_slug,
    }

    return f'''
    <div class="chart-card">
      <div class="card-header">
        <h3>{title_safe}</h3>
        {desc_html}
      </div>
      <div class="chart-container"><canvas id="{chart_id}"></canvas></div>
    </div>'''


def render_tab_group(section: dict, conn, chart_state: dict, data_sources_state: dict) -> str:
    tabs = section["tabs"]
    nav_html = ""
    panels_html = ""
    for i, tab in enumerate(tabs):
        active_cls = " active" if i == 0 else ""
        nav_html += f'<button class="tab-btn{active_cls}" data-tab="{tab["slug"]}" onclick="switchTab(this, \'{tab["slug"]}\')">{tab["label"]}</button>'
        sub_inner = ""
        for sub in tab.get("subsections", []):
            t = sub["type"]
            if t == "chart_grid":
                sub_inner += render_chart_grid(sub, conn, chart_state, data_sources_state, tab_slug=tab["slug"])
            elif t == "shipping_iframe":
                sub_inner += render_shipping_iframe(sub)
            elif t == "placeholder":
                sub_inner += render_placeholder(sub)
            elif t == "pdf_cards":
                sub_inner += render_pdf_cards(sub)
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


def render_page(slug: str, page_def: dict, conn) -> str:
    chart_state: dict = {}
    data_sources_state: dict = {}
    sections_html = []
    for section in page_def["sections"]:
        t = section["type"]
        if t == "landing_cards":
            sections_html.append(render_landing_cards())
        elif t == "chart_grid":
            sections_html.append(render_chart_grid(section, conn, chart_state, data_sources_state))
        elif t == "tab_group":
            sections_html.append(render_tab_group(section, conn, chart_state, data_sources_state))
        elif t == "shipping_iframe":
            sections_html.append(render_shipping_iframe(section))
        elif t == "placeholder":
            sections_html.append(render_placeholder(section))
        elif t == "pdf_cards":
            sections_html.append(render_pdf_cards(section))

    nav_html = render_nav(slug)
    narrative_html = render_narrative(page_def, conn)
    chart_init_js = json.dumps(chart_state)
    title = page_def["title"]
    subtitle = page_def.get("subtitle", "")

    # Show the date-range bar only on pages that actually have charts.
    date_range_bar_html = render_date_range_bar() if chart_state else ""

    # Collapsible Data sources table at the bottom (only on pages with charts).
    data_sources_html = render_data_sources_section(data_sources_state) if data_sources_state else ""

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return BASE_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        nav=nav_html,
        narrative=narrative_html,
        date_range_bar=date_range_bar_html,
        sections="\n".join(sections_html),
        data_sources=data_sources_html,
        chart_configs=chart_init_js,
        built_at=built_at,
    )


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
    .chart-container {{ position: relative; height: 240px; margin-top: 0.5rem; }}
    .chart-empty {{ padding: 2rem 0; text-align: center; }}
    .muted {{ color: var(--text-muted); }}

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

        // Find the latest date across this chart's datasets
        let latestDate = "";
        chart.data.datasets.forEach(ds => {{
          ds.data.forEach(pt => {{
            const x = typeof pt === "object" ? pt.x : null;
            if (x && x > latestDate) latestDate = x;
          }});
        }});

        let xMin, xMax;
        if (range === "all") {{
          xMin = null; xMax = null;
        }} else if (range === "1y") {{
          xMin = oneYearAgo; xMax = now;
        }} else if (range === "war") {{
          if (latestDate && latestDate >= WAR_START) {{
            xMin = WAR_ZOOM_START; xMax = now;
          }} else {{
            // No war-period coverage — show all time + add stale label
            xMin = null; xMax = null;
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
          }}
        }}

        // Use delete for null to fully clear the constraint (Chart.js doesn't
        // always treat undefined / null assignments as "no bound").
        if (xMin === null) {{ delete chart.options.scales.x.min; }} else {{ chart.options.scales.x.min = xMin; }}
        if (xMax === null) {{ delete chart.options.scales.x.max; }} else {{ chart.options.scales.x.max = xMax; }}
        chart.update();
      }});
    }}

    // ── Chart.js initialization ──
    const CHART_CONFIGS = {chart_configs};
    document.addEventListener('DOMContentLoaded', () => {{
      window._chartInstances = {{}};
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
      // Filter data-sources table to the initially-active tab
      const activeTabBtn = document.querySelector('.tab-btn.active');
      if (activeTabBtn && activeTabBtn.dataset.tab) {{
        filterDataSourcesByTab(activeTabBtn.dataset.tab);
      }} else {{
        // No tabs on this page — show all rows and total count
        filterDataSourcesByTab(null);
      }}
    }});
  </script>
</body>
</html>'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    conn = get_connection()
    print(f"Building Iran Monitor pages → {OUTPUT_DIR}")
    for slug, page_def in PAGES.items():
        html = render_page(slug, page_def, conn)
        out_path = OUTPUT_DIR / f"{slug if slug != 'index' else 'index'}.html"
        # Write to /tmp first then copy across because of FUSE mount semantics
        # (HTML files are write-only ASCII so this isn't strictly necessary, but
        # it matches the pattern we use for SQLite).
        out_path.write_text(html, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  {out_path.name}: {size_kb:.1f} KB")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
