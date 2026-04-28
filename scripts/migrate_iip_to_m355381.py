#!/usr/bin/env python3
"""
One-off migration: switch the 4 datagov-sourced IIP series to the newer
SingStat M355381 table (cluster breakdown, 2025=100 base).

Background:
  - DataGov mirrors SingStat table M355301 (2019=100) which appears to have
    been frozen at Dec 2025 because SingStat rebased the IIP series.
  - SingStat table M355381 is the rebased successor (2025=100), with data
    current through Mar 2026.
  - This affects ipi_petroleum, ipi_petrochemicals, ipi_chemicals_cluster,
    ipi_semiconductors. (singstat_ipi_specialty_chemicals already uses M355381.)
  - We also rename labels from "IPI: ..." to "IIP: ..." since the official
    name is "Index of Industrial Production".

Steps:
  1. Fetch each of the 4 series from M355381 directly via SingStat REST API.
  2. Wipe the old rows for those 4 series_ids from iran_monitor.db (via /tmp
     scratch since FUSE mount can't handle SQLite writes directly).
  3. Insert the fresh M355381 data with the new "IIP: ..." labels and
     unit "Index (2025=100)".
  4. Copy the patched DB back to its mounted location.
  5. Update specialty_chemicals label too (consistency: "IPI:" → "IIP:").

Run from Iran Monitor root:
  python3 scripts/migrate_iip_to_m355381.py
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB_LIVE = ROOT / "data" / "iran_monitor.db"
DB_SCRATCH = Path("/tmp") / "iran_monitor_iip_migration.db"

# Series to switch from DataGov (M355301, 2019=100) to SingStat (M355381, 2025=100).
# source_key follows the existing pattern: "<tableId>:<seriesNo>".
TARGETS = {
    "ipi_petroleum":          {"label": "IIP: Petroleum",         "key": "M355381:1.2.1"},
    "ipi_petrochemicals":     {"label": "IIP: Petrochemicals",    "key": "M355381:1.2.2"},
    "ipi_chemicals_cluster":  {"label": "IIP: Chemicals Cluster", "key": "M355381:1.2"},
    "ipi_semiconductors":     {"label": "IIP: Semiconductors",    "key": "M355381:1.1.1"},
}

# Specialty chemicals — already on M355381, just rename label
SPECIALTY_RENAME = ("singstat_ipi_specialty_chemicals", "IIP: Specialty Chemicals")

NEW_UNIT = "Index (2025=100)"
FREQUENCY = "Monthly"
SOURCE = "singstat"
TODAY = datetime.utcnow().isoformat()

SINGSTAT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
META_URL = "https://tablebuilder.singstat.gov.sg/api/doswebcontent/1/StatisticTableFileUpload/StatisticTable/{table_id}"
ROW_URL = "https://tablebuilder.singstat.gov.sg/rowdata/{guid}_{table_id}_{series_no}.json"


def get_guid(table_id: str) -> str | None:
    """Resolve the SingStat title GUID for a given table ID."""
    resp = requests.get(META_URL.format(table_id=table_id), headers=SINGSTAT_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"  metadata HTTP {resp.status_code}: {resp.text[:120]}")
        return None
    data = resp.json().get("Data") or {}
    return data.get("id") or data.get("titleId")


_PERIOD_RE = re.compile(r"^(\d{4})\s+([A-Za-z]{3})$")
_MONTH_TO_NUM = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def parse_period(key: str) -> str | None:
    """Convert SingStat 'YYYY Mon' (e.g. '2026 Mar') → 'YYYY-MM-01'."""
    m = _PERIOD_RE.match(key.strip())
    if not m:
        return None
    year, mon = m.group(1), m.group(2).title()
    if mon not in _MONTH_TO_NUM:
        return None
    return f"{year}-{_MONTH_TO_NUM[mon]:02d}-01"


def fetch_series(table_id: str, series_no: str, guid: str) -> list[tuple[str, float]]:
    """Fetch one SingStat row → list of (date, value)."""
    url = ROW_URL.format(guid=guid, table_id=table_id, series_no=series_no)
    resp = requests.get(url, headers=SINGSTAT_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"    row HTTP {resp.status_code}")
        return []
    payload = resp.json()
    if not isinstance(payload, list):
        print(f"    unexpected payload shape: {type(payload).__name__}")
        return []
    out = []
    for row in payload:
        date = parse_period(str(row.get("Key", "")))
        try:
            value = float(str(row.get("Value", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if date is None:
            continue
        out.append((date, value))
    return out


def main() -> None:
    if not DB_LIVE.exists():
        sys.exit(f"DB not found: {DB_LIVE}")

    # ── Step 1: Fetch all 4 target series from SingStat ──────────────────
    print("[1/4] Fetching from SingStat M355381")
    guid = get_guid("M355381")
    if not guid:
        sys.exit("Failed to resolve SingStat M355381 GUID")
    print(f"      M355381 GUID = {guid}")

    fresh: dict[str, tuple[dict, list[tuple[str, float]]]] = {}
    for series_id, info in TARGETS.items():
        table_id, series_no = info["key"].split(":", 1)
        rows = fetch_series(table_id, series_no, guid)
        if not rows:
            print(f"      ✗ {series_id}: no data fetched (key {info['key']})")
            continue
        latest = rows[-1][0]
        print(f"      ✓ {series_id} ({info['key']}): {len(rows)} rows, latest {latest}")
        fresh[series_id] = (info, rows)
        time.sleep(0.4)  # courtesy

    if len(fresh) != len(TARGETS):
        sys.exit("Some series failed to fetch — aborting before any DB writes")

    # ── Step 2: Stage scratch copy of DB ─────────────────────────────────
    print(f"\n[2/4] Staging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    # ── Step 3: Wipe old + insert new + relabel ──────────────────────────
    print(f"\n[3/4] Updating {DB_SCRATCH.name}")
    conn = sqlite3.connect(DB_SCRATCH)

    # Delete old rows for the 4 series
    target_ids = list(TARGETS.keys())
    placeholders = ",".join("?" * len(target_ids))
    n_deleted = conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({placeholders})",
        target_ids,
    ).rowcount
    conn.commit()
    print(f"      Deleted {n_deleted} old rows for {target_ids}")

    # Insert fresh data
    for series_id, (info, rows) in fresh.items():
        for date, value in rows:
            conn.execute(
                "INSERT OR REPLACE INTO time_series "
                "(date, value, series_id, series_name, source, unit, frequency, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (date, value, series_id, info["label"], SOURCE, NEW_UNIT, FREQUENCY),
            )
    conn.commit()
    print(f"      Inserted {sum(len(r) for _, r in fresh.values()):,} new rows")

    # Rename the existing specialty_chemicals label too (already on M355381)
    spec_id, spec_label = SPECIALTY_RENAME
    n_renamed = conn.execute(
        "UPDATE time_series SET series_name = ? WHERE series_id = ?",
        (spec_label, spec_id),
    ).rowcount
    conn.commit()
    print(f"      Relabeled {n_renamed} rows for {spec_id} → '{spec_label}'")

    # Verify new state
    print()
    for sid in target_ids + [spec_id]:
        r = conn.execute(
            "SELECT series_name, unit, MAX(date), COUNT(*) FROM time_series WHERE series_id = ?",
            (sid,),
        ).fetchone()
        if r:
            print(f"      {sid:<35} | {r[0]:<30} | {r[1]:<18} | latest {r[2]} ({r[3]} rows)")

    conn.close()

    # ── Step 4: Copy scratch back to live ────────────────────────────────
    print(f"\n[4/4] Copying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print(f"\nMigration complete. Run `python3 scripts/build_iran_monitor.py` to re-render.")


if __name__ == "__main__":
    main()
