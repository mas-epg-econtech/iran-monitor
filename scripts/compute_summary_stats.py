#!/usr/bin/env python3
"""
Iran Monitor — summary statistics extractor.

Reads `data/chart_manifest.json` (produced as a side-effect of
`build_iran_monitor.py`) and queries `data/iran_monitor.db` to compute
per-series summary statistics that the LLM narrative system consumes:

    - current value + date
    - pre-war baseline value + period (default: avg of Nov + Dec 2025)
    - delta vs baseline (% and absolute)
    - short-term trend (~4 weeks and ~12 weeks)
    - staleness flag (days since the latest data point, vs a frequency-aware
      threshold so a quarterly series isn't considered stale at 60 days)

The output is `data/summary_stats.json`, structured per page:

    {
      "global_shocks": {
        "page": "Global Shocks",
        "charts": {
          "gs.energy.crude_oil": {
            "title": "Crude Oil",
            "description": "...",
            "tab_slug": "energy",
            "series": [
              {
                "series_id": "global_crude_oil",
                "name": "Brent",
                "unit": "USD/barrel",
                "frequency": "Daily",
                "current": {"value": 72.3, "date": "2026-04-29"},
                "baseline": {"value": 64.8, "period": "2025-11/2025-12"},
                "delta_vs_baseline": {"abs": 7.5, "pct": 11.6},
                "trend_4w_pct":  3.2,
                "trend_12w_pct": 11.4,
                "data_age_days": 1,
                "stale": false
              },
              ...
            ]
          },
          ...
        }
      },
      "singapore":   {...},
      "regional":    {...}
    }

The extractor is deliberately faithful: it only emits stats it can compute
from observable data. Where a baseline window has no points, the baseline
is null (and dependent fields are null too) — the LLM prompt explicitly
instructs the model to flag rather than infer in those cases.

Run from the Iran Monitor root after a build:
    python3 scripts/compute_summary_stats.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection  # type: ignore  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MANIFEST_PATH = ROOT / "data" / "chart_manifest.json"
OUT_PATH      = ROOT / "data" / "summary_stats.json"

# Pre-war baseline window — the two months immediately before CRISIS_DATE
# (war starts 2026-02-28; baseline is the calm tail of 2025).
BASELINE_START = "2025-11-01"
BASELINE_END   = "2025-12-31"
BASELINE_LABEL = "2025-11/2025-12"

# As-of date used for "current" / staleness — defaults to today.
AS_OF_DATE = datetime.utcnow().strftime("%Y-%m-%d")

# Frequency-aware staleness thresholds (days). A monthly series is fine
# at 45 days old (one cycle slip); quarterly tolerates 100; daily expects
# updates within a week.
STALENESS_DAYS = {
    "daily":     7,
    "weekly":    14,
    "monthly":   45,
    "quarterly": 100,
    "annual":    400,
}

PAGE_DISPLAY = {
    "global_shocks": "Global Shocks",
    "singapore":     "Singapore",
    "regional":      "Regional",
}

# War-onset date — used as the lower bound for "war-period" gap aggregations
# in nowcast pair stats below.
CRISIS_DATE = "2026-02-28"

TAB_DISPLAY = {
    # Per-page tab slug → human label, used in the output to make the LLM's
    # life easier (it doesn't have to slug-decode tab names).
    # Falls back to the slug Title-cased if not listed here.
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fetch_series_meta(conn, sid: str) -> dict:
    r = conn.execute(
        "SELECT series_name, unit, frequency, source FROM indicators WHERE series_id = ?",
        (sid,),
    ).fetchone()
    if r:
        return {"name": r["series_name"], "unit": r["unit"] or "",
                "frequency": r["frequency"] or "", "source": r["source"] or ""}
    r = conn.execute(
        "SELECT series_name, unit, frequency, source FROM time_series "
        "WHERE series_id = ? LIMIT 1", (sid,),
    ).fetchone()
    if r:
        return {"name": r["series_name"] or sid, "unit": r["unit"] or "",
                "frequency": r["frequency"] or "", "source": r["source"] or ""}
    return {"name": sid, "unit": "", "frequency": "", "source": ""}


def _fetch_series_points(conn, sid: str) -> list[tuple[str, float]]:
    """All (date, value) points for a series, sorted ascending. Drops null values."""
    rows = conn.execute(
        "SELECT date, value FROM time_series WHERE series_id = ? "
        "AND value IS NOT NULL ORDER BY date",
        (sid,),
    ).fetchall()
    return [(r["date"], float(r["value"])) for r in rows]


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _pct_change(curr: float | None, ref: float | None) -> float | None:
    if curr is None or ref is None or ref == 0:
        return None
    return (curr - ref) / ref * 100.0


def _abs_change(curr: float | None, ref: float | None) -> float | None:
    if curr is None or ref is None:
        return None
    return curr - ref


def _values_in_window(points: list[tuple[str, float]], start: str, end: str) -> list[float]:
    return [v for d, v in points if start <= d <= end]


def _value_at_or_before(points: list[tuple[str, float]], target_date: str) -> float | None:
    """Return the most recent value with date <= target_date, or None if none."""
    last = None
    for d, v in points:
        if d <= target_date:
            last = v
        else:
            break
    return last


def _staleness_threshold_days(frequency: str) -> int:
    return STALENESS_DAYS.get((frequency or "").strip().lower(), 60)


def _trend_pct(points: list[tuple[str, float]], current_value: float, current_date: str,
               weeks_back: int) -> float | None:
    """% change from the most recent observation `weeks_back` weeks before
    `current_date` to `current_value`. Returns None if no observation exists
    in the lookback window."""
    if current_value is None or not current_date:
        return None
    try:
        cd = datetime.strptime(current_date, "%Y-%m-%d")
    except ValueError:
        return None
    target = (cd - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")
    ref = _value_at_or_before(points, target)
    return _pct_change(current_value, ref)


def _round(x: float | None, ndigits: int = 4) -> float | None:
    if x is None:
        return None
    return round(x, ndigits)


def _compute_war_period_range(points: list[tuple[str, float]],
                               current_value: float | None) -> dict | None:
    """Min and max value during the war window (since CRISIS_DATE) plus dates,
    n_points, and `current_pct_through_range` (where the current value sits
    on the [min, max] axis, as a percentage; null when min == max).

    Lets the LLM see whether the current value is at a war-period extreme
    or in the middle of the range — a different read from "delta vs
    baseline" alone, especially for volatile series that whip back and
    forth (FX, vol, equity).

    Returns None when no points fall inside the war window — the LLM
    prompt should treat the absence of this field as "no war-period
    observations to compare against."
    """
    in_window = [(d, v) for d, v in points if d >= CRISIS_DATE]
    if not in_window:
        return None
    min_d, min_v = min(in_window, key=lambda dv: dv[1])
    max_d, max_v = max(in_window, key=lambda dv: dv[1])
    if max_v == min_v or current_value is None:
        through = None
    else:
        through = (current_value - min_v) / (max_v - min_v) * 100.0
    # Convenience flags so the LLM doesn't have to compute thresholds —
    # current value is "at the high" / "at the low" of the war-period
    # range when within 10% of either end. Only applies when there are
    # at least 5 war-period points (otherwise the range is too thin to
    # meaningfully say "at extreme").
    at_war_high = (through is not None and through >= 90 and len(in_window) >= 5)
    at_war_low  = (through is not None and through <= 10 and len(in_window) >= 5)
    return {
        "min":      {"value": _round(min_v), "date": min_d},
        "max":      {"value": _round(max_v), "date": max_d},
        "n_points": len(in_window),
        "current_pct_through_range": _round(through, 2),
        "at_war_high": at_war_high,
        "at_war_low":  at_war_low,
    }


def _is_percentage_unit(unit: str) -> bool:
    """True if the series's unit is itself a percentage / rate, in which case
    the right way to express change is in percentage points (the absolute
    delta) rather than as a % change of a %.

    Examples that return True: '% YoY', '% MoM', '% pa', '% share', 'bp',
    'basis points', '%'.
    Examples that return False: 'USD/Barrel', 'Index (2025=100)', 'TEU th'.
    """
    u = (unit or "").strip().lower()
    if not u:
        return False
    if u.startswith("%") or u.startswith("percent"):
        return True
    if u in {"bp", "bps", "basis points"}:
        return True
    return False


# ---------------------------------------------------------------------------
# Per-series stats
# ---------------------------------------------------------------------------
def compute_series_stats(conn, sid: str) -> dict:
    meta = _fetch_series_meta(conn, sid)
    points = _fetch_series_points(conn, sid)
    if not points:
        return {
            "series_id":   sid,
            "name":        meta["name"],
            "unit":        meta["unit"],
            "frequency":   meta["frequency"],
            "source":      meta["source"],
            "current":     None,
            "baseline":    None,
            "delta_vs_baseline": None,
            "trend_4w":  None,
            "trend_12w": None,
            "war_period_range": None,
            "data_age_days": None,
            "stale":         True,
            "n_points":      0,
        }

    last_date, last_value = points[-1]
    baseline_values = _values_in_window(points, BASELINE_START, BASELINE_END)
    baseline_value  = _avg(baseline_values)

    delta_abs = _abs_change(last_value, baseline_value)
    # For series whose unit is itself a percentage / yield / share, expressing
    # change as a "percent of a percent" is misleading — e.g. CPI 0.75% YoY
    # rising to 1.0% should be read as +0.25 pp, not "+33%". Suppress the
    # pct field for such series so the LLM cites the absolute (pp) change.
    is_pct_unit = _is_percentage_unit(meta["unit"])
    delta_pct = None if is_pct_unit else _pct_change(last_value, baseline_value)
    # Trends: same logic. For pp-denominated series we want absolute pp moves
    # over the lookback window, not pct-of-pct.
    if is_pct_unit:
        trend_4w  = (_abs_change(last_value, _value_at_or_before(
                       points, (datetime.strptime(last_date, "%Y-%m-%d")
                                - timedelta(weeks=4)).strftime("%Y-%m-%d")))
                     if last_date else None)
        trend_12w = (_abs_change(last_value, _value_at_or_before(
                       points, (datetime.strptime(last_date, "%Y-%m-%d")
                                - timedelta(weeks=12)).strftime("%Y-%m-%d")))
                     if last_date else None)
    else:
        trend_4w  = _trend_pct(points, last_value, last_date, 4)
        trend_12w = _trend_pct(points, last_value, last_date, 12)

    try:
        age_days = (datetime.strptime(AS_OF_DATE, "%Y-%m-%d")
                    - datetime.strptime(last_date, "%Y-%m-%d")).days
    except ValueError:
        age_days = None

    stale = (age_days is not None
             and age_days > _staleness_threshold_days(meta["frequency"]))

    # Tell the LLM how to phrase changes for this series — "pp" means the
    # delta_abs / trend fields are in percentage points (the unit is itself
    # a percentage); "pct" means delta_pct is the right thing to cite.
    delta_kind = "pp" if is_pct_unit else "pct"
    trend_unit = "pp" if is_pct_unit else "pct"
    war_range  = _compute_war_period_range(points, last_value)
    return {
        "series_id":   sid,
        "name":        meta["name"],
        "unit":        meta["unit"],
        "frequency":   meta["frequency"],
        "source":      meta["source"],
        "current":     {"value": _round(last_value), "date": last_date},
        "baseline":    (
            {"value": _round(baseline_value), "period": BASELINE_LABEL,
             "n_points": len(baseline_values)}
            if baseline_value is not None else None
        ),
        "delta_vs_baseline": (
            {"abs": _round(delta_abs), "pct": _round(delta_pct), "kind": delta_kind}
            if baseline_value is not None else None
        ),
        "trend_4w":  {"value": _round(trend_4w), "unit": trend_unit},
        "trend_12w": {"value": _round(trend_12w), "unit": trend_unit},
        "war_period_range": war_range,
        "data_age_days": age_days,
        "stale":         bool(stale),
        "n_points":      len(points),
    }


# ---------------------------------------------------------------------------
# Shipping nowcast pair stats (option C)
# ---------------------------------------------------------------------------
# PortWatch nowcast charts pair an `*_actual` series with an `*_cf`
# (counterfactual) series — the right comparison for the war-effect story
# is actual-vs-cf, NOT actual-vs-Nov-Dec-baseline (which conflates
# seasonality). For each shipping chart we also emit a per-pair `nowcast`
# block giving the latest gap, 4-week trailing gap, and the deepest
# war-period gap.

def _detect_actual_cf_pairs(series_ids: list[str]) -> list[tuple[str, str, str]]:
    """Find (label_stem, actual_id, cf_id) triples in a series_id list.
    Pairs are detected by the `*_actual` / `*_cf` suffix convention used
    by the PortWatch nowcast pipeline. Returns an empty list if no pairs
    are found (i.e. the chart isn't a nowcast chart)."""
    actuals = {sid[:-len("_actual")]: sid for sid in series_ids if sid.endswith("_actual")}
    cfs     = {sid[:-len("_cf")]:     sid for sid in series_ids if sid.endswith("_cf")}
    common  = sorted(set(actuals.keys()) & set(cfs.keys()))
    return [(stem, actuals[stem], cfs[stem]) for stem in common]


def _compute_nowcast_pair(conn, label: str, actual_id: str, cf_id: str) -> dict:
    """For a paired (actual, cf) nowcast series, compute the war-effect signals
    that the LLM should cite for the shipping question. Skips dates where
    only one of the two has data."""
    a = dict(_fetch_series_points(conn, actual_id))
    c = dict(_fetch_series_points(conn, cf_id))
    common_dates = sorted(set(a.keys()) & set(c.keys()))
    if not common_dates:
        return {
            "label":         label,
            "actual_id":     actual_id,
            "cf_id":         cf_id,
            "latest_week":   None,
            "actual_value":  None,
            "cf_value":      None,
            "gap_pct":       None,
            "gap_4w_avg_pct": None,
            "war_max_gap_pct": None,
            "war_max_gap_week": None,
        }

    # Latest week with both observations
    latest = common_dates[-1]
    a_latest, c_latest = a[latest], c[latest]
    gap_latest = _pct_change(a_latest, c_latest)

    # 4-week trailing average gap, on the dates where both series exist.
    # Walks backward from `latest` capturing up to 4 prior observations.
    last4 = common_dates[-4:]
    gaps_4w = [_pct_change(a[d], c[d]) for d in last4]
    gaps_4w = [g for g in gaps_4w if g is not None]
    gap_4w_avg = _avg(gaps_4w) if gaps_4w else None

    # War-period maximum |gap|: of all dates >= CRISIS_DATE, the one with
    # the most extreme percentage gap (whichever sign).
    war_dates = [d for d in common_dates if d >= CRISIS_DATE]
    war_max_gap_pct: float | None = None
    war_max_gap_week: str | None  = None
    for d in war_dates:
        g = _pct_change(a[d], c[d])
        if g is None:
            continue
        if war_max_gap_pct is None or abs(g) > abs(war_max_gap_pct):
            war_max_gap_pct  = g
            war_max_gap_week = d

    return {
        "label":           label,
        "actual_id":       actual_id,
        "cf_id":           cf_id,
        "latest_week":     latest,
        "actual_value":    _round(a_latest),
        "cf_value":        _round(c_latest),
        "gap_pct":         _round(gap_latest),
        "gap_4w_avg_pct":  _round(gap_4w_avg),
        "war_max_gap_pct": _round(war_max_gap_pct),
        "war_max_gap_week": war_max_gap_week,
    }


def compute_nowcast_pairs(conn, manifest_entry: dict) -> list[dict]:
    """Return a list of paired `nowcast` blocks for one chart, or [] if the
    chart has no actual/cf pairs.

    Two cases:
      1. Multi-subchart cards (Tankers, Containers, Total port calls per
         country) — `subchart_meta` lists the per-subchart series. We pair
         within each subchart and label with the subchart's subtitle.
      2. Flat single-chart nowcast cards (Malacca Strait, country total
         port calls) — pair directly within the chart's own series_ids
         and label with the chart's title.
    """
    pairs_out: list[dict] = []
    if manifest_entry.get("subchart_meta"):
        for sm in manifest_entry["subchart_meta"]:
            for stem, a_id, c_id in _detect_actual_cf_pairs(sm.get("series_ids") or []):
                pairs_out.append(_compute_nowcast_pair(conn, sm.get("subtitle", stem), a_id, c_id))
    else:
        for stem, a_id, c_id in _detect_actual_cf_pairs(manifest_entry.get("series_ids") or []):
            pairs_out.append(_compute_nowcast_pair(conn, manifest_entry.get("title", stem), a_id, c_id))
    return pairs_out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _tab_label(tab_slug: str) -> str:
    if tab_slug in TAB_DISPLAY:
        return TAB_DISPLAY[tab_slug]
    # Auto: replace underscores with spaces, title case
    return tab_slug.replace("_", " ").strip().title() if tab_slug else "(no tab)"


def main() -> None:
    if not MANIFEST_PATH.exists():
        sys.exit(f"Manifest not found: {MANIFEST_PATH}\n"
                 f"Run scripts/build_iran_monitor.py first.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    conn = get_connection()

    # Output structure: page → {page label, charts: {chart_id → {...stats...}}}
    out: dict = {
        page_slug: {
            "page": PAGE_DISPLAY.get(page_slug, page_slug.title()),
            "charts": {},
        }
        for page_slug in PAGE_DISPLAY
    }

    n_charts = 0
    n_series = 0
    for chart_id, info in manifest.items():
        page = info["page"]
        if page not in out:
            out[page] = {"page": PAGE_DISPLAY.get(page, page.title()), "charts": {}}
        # Skip subcharts in the per-chart output (their parent card is what
        # the LLM cites). We still compute stats for their series via the
        # parent's series_ids list.
        if info.get("parent_chart_id"):
            continue
        series_stats = [compute_series_stats(conn, sid) for sid in info["series_ids"]]
        chart_payload: dict = {
            "title":        info["title"],
            "description":  info["description"],
            "tab_slug":     info["tab_slug"],
            "tab_label":    _tab_label(info["tab_slug"]),
            "relevant_to":  info.get("relevant_to") or [],
            "series":       series_stats,
        }
        # Add pair-aware nowcast stats for shipping charts. Empty list (no
        # actual/cf pairs detected) → field is omitted from the output so
        # the LLM doesn't have to deal with noise on non-shipping charts.
        nowcast_pairs = compute_nowcast_pairs(conn, info)
        if nowcast_pairs:
            chart_payload["nowcast_pairs"] = nowcast_pairs
        out[page]["charts"][chart_id] = chart_payload
        n_charts += 1
        n_series += len(series_stats)

    conn.close()

    # Build a relevance index — chart IDs grouped by their `relevant_to`
    # tag and by page. Lets the page-level prompt enumerate "all charts
    # tagged X on this page" in one place rather than scanning the whole
    # tree. Order within each list is layout order (insertion order of
    # `out[page]['charts']`).
    charts_by_relevance: dict[str, dict[str, list[str]]] = {
        "energy_supply":     {},
        "financial_markets": {},
    }
    for page_slug, payload in out.items():
        if page_slug.startswith("_"):
            continue
        for chart_id, c in payload["charts"].items():
            for tag in (c.get("relevant_to") or []):
                charts_by_relevance.setdefault(tag, {}) \
                                   .setdefault(page_slug, []) \
                                   .append(chart_id)

    # Add an "as_of" header so the LLM knows when the snapshot was taken
    # and the baseline window for context.
    out["_meta"] = {
        "as_of_date":   AS_OF_DATE,
        "baseline":     {"start": BASELINE_START, "end": BASELINE_END,
                         "label": BASELINE_LABEL},
        "n_charts":     n_charts,
        "n_series":     n_series,
        "subcharts_excluded": True,
        "charts_by_relevance": charts_by_relevance,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {OUT_PATH}")
    print(f"  charts: {n_charts}, series: {n_series}, "
          f"as_of: {AS_OF_DATE}, baseline: {BASELINE_LABEL}")
    # Per-page breakdown
    for slug, payload in out.items():
        if slug.startswith("_"):
            continue
        n_p_charts = len(payload["charts"])
        n_p_series = sum(len(c["series"]) for c in payload["charts"].values())
        print(f"  {slug}: {n_p_charts} charts, {n_p_series} series")


if __name__ == "__main__":
    main()
