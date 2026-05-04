#!/usr/bin/env python3
"""
Iran Monitor — narrative-trigger threshold computation.

Computes σ-based trigger thresholds for the curated set of series that
gate AI narrative regeneration. For each series, pulls pre-war (2025)
history from `data/iran_monitor.db`, computes the standard deviation of
period-over-period changes (weekly for daily/weekly series, monthly for
monthly series), and writes the resulting thresholds to
`data/trigger_thresholds.json`.

The trigger system uses these thresholds to decide whether a fresh
narrative is warranted. A series whose current state has shifted by
more than `n_sigma * sigma` from the last narrative's snapshot is
considered to have moved "meaningfully" and triggers a refresh.

Run from the Iran Monitor root:
    python3 scripts/compute_trigger_thresholds.py

Output is committed to git so triggers are stable across runs without
re-querying the DB each time.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_connection  # type: ignore  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WINDOW_START = "2025-01-01"
WINDOW_END   = "2025-12-31"
N_SIGMA      = 2

OUT_PATH = ROOT / "data" / "trigger_thresholds.json"

# The curated trigger-series list. Each entry binds a series_id to:
#   - page:    which page's narrative cares about this series
#   - question: which question (energy_supply / financial_markets) it bears on
#   - kind:    'pct' for level series (compute % change vs last snapshot),
#              'pp'  for series already in pp units (CPI YoY, IIP YoY, yields, vol level)
#   - horizon: 'weekly' (daily/weekly source data) or 'monthly' (monthly source data)
#   - label:   human-readable name for trigger-state output
TRIGGER_SERIES = [
    # ── Energy supply ────────────────────────────────────────────────────
    {"series_id": "global_crude_oil",                       "page": "global_shocks", "question": "energy_supply",     "kind": "pct", "horizon": "weekly",  "label": "Brent crude"},
    {"series_id": "gsheets_naphtha_singapore_fob_cargoes",  "page": "global_shocks", "question": "energy_supply",     "kind": "pct", "horizon": "weekly",  "label": "Naphtha Singapore FOB"},
    {"series_id": "gsheets_jet_fuel_nwe_fob_barges",        "page": "global_shocks", "question": "energy_supply",     "kind": "pct", "horizon": "weekly",  "label": "Jet fuel NWE"},
    {"series_id": "ipi_petroleum",                          "page": "singapore",     "question": "energy_supply",     "kind": "pp",  "horizon": "monthly", "label": "Petroleum refining IIP YoY"},
    {"series_id": "ipi_petrochemicals",                     "page": "singapore",     "question": "energy_supply",     "kind": "pp",  "horizon": "monthly", "label": "Petrochemicals IIP YoY"},
    {"series_id": "regional_cpi_headline_ph",               "page": "regional",      "question": "energy_supply",     "kind": "pp",  "horizon": "monthly", "label": "Philippines CPI headline YoY"},
    {"series_id": "JKM_LNG",                                "page": "regional",      "question": "energy_supply",     "kind": "pct", "horizon": "weekly",  "label": "JKM LNG futures"},
    # ── Financial markets ────────────────────────────────────────────────
    {"series_id": "gsheets_us_dollar_singapore_dollar",     "page": "singapore",     "question": "financial_markets", "kind": "pct", "horizon": "weekly",  "label": "USD/SGD"},
    {"series_id": "gsheets_nominal_effec_rt",               "page": "singapore",     "question": "financial_markets", "kind": "pct", "horizon": "weekly",  "label": "SGD NEER"},
    {"series_id": "gsheets_sgd_singapore_govt_bval_10y",    "page": "singapore",     "question": "financial_markets", "kind": "pp",  "horizon": "weekly",  "label": "SGS 10Y yield"},
    {"series_id": "gsheets_usd_sgd_opt_vol_1m",             "page": "singapore",     "question": "financial_markets", "kind": "pp",  "horizon": "weekly",  "label": "USD/SGD 1M implied vol"},
    {"series_id": "financial_sora_3m",                      "page": "singapore",     "question": "financial_markets", "kind": "pp",  "horizon": "weekly",  "label": "SORA 3M compounded"},
    {"series_id": "PH_10Y",                                 "page": "regional",      "question": "financial_markets", "kind": "pp",  "horizon": "weekly",  "label": "Philippines 10Y yield"},
    {"series_id": "ID_10Y",                                 "page": "regional",      "question": "financial_markets", "kind": "pp",  "horizon": "weekly",  "label": "Indonesia 10Y yield"},
    {"series_id": "GOLD",                                   "page": "regional",      "question": "financial_markets", "kind": "pct", "horizon": "weekly",  "label": "Gold"},
]


# ---------------------------------------------------------------------------
# σ computation
# ---------------------------------------------------------------------------
def compute_sigma(conn: sqlite3.Connection, series_id: str, kind: str, horizon: str) -> tuple[float | None, int]:
    """Return (sigma, n_samples) of period-over-period changes in the
    pre-war window. `kind='pct'` returns σ in percent; `kind='pp'`
    returns σ in the same units as the series (pp)."""
    df = pd.read_sql_query(
        "SELECT date, value FROM time_series WHERE series_id = ? "
        "AND date BETWEEN ? AND ? ORDER BY date",
        conn, params=(series_id, WINDOW_START, WINDOW_END), parse_dates=["date"],
    )
    if df.empty:
        return None, 0
    df = df.set_index("date").sort_index()

    # Resample to the trigger horizon. 'W-FRI' means week ending Friday;
    # 'ME' means month-end. Take last observation in each bucket.
    rule = "W-FRI" if horizon == "weekly" else "ME"
    df = df.resample(rule).last().dropna()
    if len(df) < 4:
        return None, len(df)

    # Period-over-period change: % for level series, absolute (in pp) for
    # series already in pp.
    chg = (df["value"].pct_change() * 100) if kind == "pct" else df["value"].diff()
    chg = chg.dropna()
    if len(chg) < 3:
        return None, len(chg)
    return float(chg.std(ddof=1)), len(chg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    conn = get_connection()
    print(f"Computing trigger thresholds from {WINDOW_START} to {WINDOW_END} (n_sigma = {N_SIGMA})")
    print()

    out: dict = {
        "_meta": {
            "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window":      f"{WINDOW_START} to {WINDOW_END}",
            "n_sigma":     N_SIGMA,
            "method":      "σ of period-over-period changes (weekly Δ for weekly horizon, monthly Δ for monthly), threshold = n_sigma × σ.",
        },
        "series": {},
    }

    print(f"{'Series':38} {'σ':>10} {'threshold':>12} {'n':>4}")
    print("-" * 70)
    for spec in TRIGGER_SERIES:
        sid = spec["series_id"]
        sigma, n = compute_sigma(conn, sid, spec["kind"], spec["horizon"])
        if sigma is None:
            print(f"{spec['label'][:36]:38} {'(no data)':>10} {'-':>12} {n:>4}")
            continue
        threshold = N_SIGMA * sigma
        unit = "%" if spec["kind"] == "pct" else "pp"
        print(f"{spec['label'][:36]:38} {sigma:>9.3f}{unit} {threshold:>11.3f}{unit} {n:>4}")
        out["series"][sid] = {
            "label":      spec["label"],
            "page":       spec["page"],
            "question":   spec["question"],
            "kind":       spec["kind"],
            "horizon":    spec["horizon"],
            "sigma":      round(sigma, 4),
            "threshold":  round(threshold, 4),
            "n_samples":  n,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}  ({len(out['series'])} series)")


if __name__ == "__main__":
    main()
