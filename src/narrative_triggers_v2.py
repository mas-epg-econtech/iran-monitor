"""
Iran Monitor — narrative-trigger evaluation.

Decides whether a fresh AI narrative is warranted given:
  - the latest summary statistics (`data/summary_stats.json`)
  - the snapshot saved at the last successful narrative run
    (DB metadata key `narrative_trigger_snapshot`)
  - the σ-based per-series thresholds (`data/trigger_thresholds.json`,
    produced by `scripts/compute_trigger_thresholds.py`)

A refresh fires if ANY of:
  - any trigger series has moved more than its `n_sigma` threshold since
    the last snapshot (in matching units — % for level series, pp for
    pp series like CPI YoY / yields / vol / IIP YoY)
  - any trigger series has just entered or exited its `at_war_high` /
    `at_war_low` flag state (catches new extremes that don't show up
    as a fast move)
  - the last narrative is older than `MAX_AGE_DAYS` (sanity floor — even
    if nothing's moved we want fresh prose at least weekly)
  - no previous snapshot exists (fresh DB / first-ever run)

Usage from inside the orchestrator:

    from src.narrative_triggers_v2 import (
        evaluate_triggers, save_snapshot, load_snapshot,
    )

    decision = evaluate_triggers(
        current_stats=...,    # dict from data/summary_stats.json
        last_snapshot=...,    # dict from DB metadata, or None
        last_narrative_at=..., # ISO 8601 string, or None
        thresholds=...,       # dict from data/trigger_thresholds.json
    )
    if decision.refresh:
        # ... call generate_narratives ...
        save_snapshot(conn, current_stats, thresholds)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

THRESHOLDS_PATH = ROOT / "data" / "trigger_thresholds.json"

# Sanity floor — refresh narratives at least this often regardless of
# whether any trigger series moved. Keeps the dashboard from feeling
# stale during quiet periods.
MAX_AGE_DAYS = 7

# DB metadata key for the snapshot.
SNAPSHOT_KEY = "narrative_trigger_snapshot"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class TriggerDecision:
    refresh: bool
    reasons: list[str] = field(default_factory=list)
    n_series_checked: int = 0
    n_series_fired: int = 0
    age_days: float | None = None    # None when no previous snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_thresholds() -> dict:
    """Load `data/trigger_thresholds.json`. Raises if missing — the
    orchestrator should run `compute_trigger_thresholds.py` first."""
    if not THRESHOLDS_PATH.exists():
        raise FileNotFoundError(
            f"Trigger thresholds not found: {THRESHOLDS_PATH}. "
            f"Run scripts/compute_trigger_thresholds.py first."
        )
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def _flatten_series_stats(stats: dict) -> dict[str, dict]:
    """Walk summary_stats.json and return {series_id: series_stat_dict}."""
    out: dict[str, dict] = {}
    for page_key in ("global_shocks", "singapore", "regional"):
        page = stats.get(page_key) or {}
        for chart in (page.get("charts") or {}).values():
            for sd in chart.get("series", []):
                sid = sd.get("series_id")
                if sid and sid not in out:
                    out[sid] = sd
    return out


def _series_snapshot_value(stat: dict) -> dict:
    """Extract the small set of fields we need to detect movement.
    The snapshot is intentionally minimal — value, delta_vs_baseline_pct,
    and the at-war flags. That's enough to detect both fast moves and
    new extremes without bloating the DB metadata blob."""
    cur = stat.get("current") or {}
    delta = stat.get("delta_vs_baseline") or {}
    war = stat.get("war_period_range") or {}
    return {
        "value":                  cur.get("value"),
        "date":                   cur.get("date"),
        "delta_vs_baseline_abs":  delta.get("abs"),
        "delta_vs_baseline_pct":  delta.get("pct"),
        "at_war_high":            bool(war.get("at_war_high")),
        "at_war_low":             bool(war.get("at_war_low")),
    }


def _movement_exceeds_threshold(prev: dict, cur: dict, kind: str, threshold: float) -> tuple[bool, float]:
    """Return (fired, magnitude). `prev` and `cur` are series-snapshot
    dicts. `kind` is 'pct' or 'pp' from the threshold config.

    For 'pct' series: compare current value vs previous value as %
    change; fire if abs change >= threshold (which is in percent).
    For 'pp' series: compare current value vs previous value as pp
    difference; fire if abs change >= threshold (in pp)."""
    pv = prev.get("value")
    cv = cur.get("value")
    if pv is None or cv is None:
        return False, 0.0
    if kind == "pct":
        if pv == 0:
            return False, 0.0
        magnitude = abs(cv / pv - 1.0) * 100.0
    else:
        magnitude = abs(cv - pv)
    return magnitude >= threshold, magnitude


def _flag_transition(prev: dict, cur: dict) -> str | None:
    """Return a description of any war-period-extreme flag transition,
    or None if the flags are unchanged."""
    transitions = []
    for flag in ("at_war_high", "at_war_low"):
        if prev.get(flag) != cur.get(flag):
            transitions.append(f"{flag}: {prev.get(flag)} → {cur.get(flag)}")
    return ", ".join(transitions) or None


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Accept 'Z' suffix.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate_triggers(
    current_stats: dict,
    last_snapshot: dict | None,
    thresholds: dict,
) -> TriggerDecision:
    """Compare current stats to the last snapshot using σ-based thresholds.
    Returns a TriggerDecision with `refresh` True/False and human-readable
    `reasons` listing the firing series + magnitudes.

    `last_snapshot` is the dict previously written by `save_snapshot()`
    (or None if no snapshot exists yet)."""
    decision = TriggerDecision(refresh=False)
    cfg_series = thresholds.get("series") or {}
    decision.n_series_checked = len(cfg_series)

    # 1. No previous snapshot → first-run, refresh.
    if not last_snapshot:
        decision.refresh = True
        decision.reasons.append("No previous narrative snapshot — first run.")
        return decision

    # 2. Sanity floor — refresh if narrative is older than MAX_AGE_DAYS.
    last_at = _parse_iso(last_snapshot.get("narrative_generated_at"))
    if last_at:
        age = (datetime.now(timezone.utc) - last_at).total_seconds() / 86400.0
        decision.age_days = round(age, 2)
        if age >= MAX_AGE_DAYS:
            decision.refresh = True
            decision.reasons.append(
                f"Last narrative is {age:.1f} days old (≥ {MAX_AGE_DAYS}-day floor)."
            )
            # Don't return yet — still report any series-level triggers
            # so the user sees what else moved.

    cur_flat = _flatten_series_stats(current_stats)
    prev_series = (last_snapshot.get("series") or {})

    # 3. Per-series checks.
    for sid, spec in cfg_series.items():
        cur_stat = cur_flat.get(sid)
        prev_stat = prev_series.get(sid)
        if cur_stat is None or prev_stat is None:
            continue
        cur_snap = _series_snapshot_value(cur_stat)

        fired, magnitude = _movement_exceeds_threshold(
            prev_stat, cur_snap,
            kind=spec["kind"], threshold=spec["threshold"],
        )
        unit = "%" if spec["kind"] == "pct" else "pp"
        if fired:
            decision.refresh = True
            decision.n_series_fired += 1
            decision.reasons.append(
                f"{spec['label']}: shifted {magnitude:.2f}{unit} "
                f"(threshold {spec['threshold']:.2f}{unit} = {thresholds['_meta']['n_sigma']}σ)"
            )

        flag_change = _flag_transition(prev_stat, cur_snap)
        if flag_change:
            decision.refresh = True
            decision.n_series_fired += 1
            decision.reasons.append(
                f"{spec['label']}: war-period flag changed ({flag_change})"
            )

    if not decision.refresh:
        decision.reasons.append(
            f"All {decision.n_series_checked} trigger series within "
            f"{thresholds['_meta']['n_sigma']}σ bands; "
            f"last narrative {decision.age_days} days ago (under "
            f"{MAX_AGE_DAYS}-day floor)."
        )

    return decision


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------
def build_snapshot(current_stats: dict, thresholds: dict, narrative_generated_at: str) -> dict:
    """Build the snapshot dict to save after a successful narrative run.
    Only stores the series listed in thresholds (small, focused)."""
    cur_flat = _flatten_series_stats(current_stats)
    series_out: dict[str, dict] = {}
    for sid in thresholds.get("series", {}).keys():
        stat = cur_flat.get(sid)
        if stat is None:
            continue
        series_out[sid] = _series_snapshot_value(stat)

    return {
        "saved_at":                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "narrative_generated_at":  narrative_generated_at,
        "as_of_date":              ((current_stats.get("_meta") or {}).get("as_of_date")),
        "series":                  series_out,
    }


def save_snapshot(conn, current_stats: dict, thresholds: dict, narrative_generated_at: str | None = None) -> dict:
    """Persist a fresh trigger snapshot to DB metadata. Returns the
    snapshot dict so the caller can also write it to disk if desired."""
    if narrative_generated_at is None:
        narrative_generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot = build_snapshot(current_stats, thresholds, narrative_generated_at)
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (SNAPSHOT_KEY, json.dumps(snapshot, ensure_ascii=False)),
    )
    conn.commit()
    return snapshot


def load_snapshot(conn) -> dict | None:
    """Load the last trigger snapshot from DB metadata (or None)."""
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (SNAPSHOT_KEY,),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None
