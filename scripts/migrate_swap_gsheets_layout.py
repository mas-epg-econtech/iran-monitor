#!/usr/bin/env python3
"""
One-off migration: clean out old `gsheets_daily/weekly/monthly_*` series_ids
left behind by the previous Google Sheets layout. The new ingestion writes
under `gsheets_<slug>` (no tab prefix), so the old rows are orphans — they
won't be touched by future update_data.py runs.

Pattern (same as other migrations):
  1. Stage scratch DB at /tmp.
  2. Count + delete rows whose series_id matches the legacy patterns.
  3. Verify, copy back.

Run from the Iran Monitor root:
  python3.11 scripts/migrate_swap_gsheets_layout.py

After this runs, do a full ingestion to repopulate under the new IDs:
  python3.11 scripts/energy/update_data.py
  python3.11 scripts/build_iran_monitor.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_LIVE = ROOT / "data" / "iran_monitor.db"
DB_SCRATCH = Path("/tmp") / "iran_monitor_swap_gsheets_layout.db"

# Anything matching these LIKE patterns is from the old layout.
LEGACY_PATTERNS = [
    "gsheets_daily_%",
    "gsheets_weekly_%",
    "gsheets_monthly_%",
]


def main() -> None:
    if not DB_LIVE.exists():
        sys.exit(f"DB not found: {DB_LIVE}")

    # Stage scratch DB
    print(f"Staging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    conn = sqlite3.connect(DB_SCRATCH)
    conn.row_factory = sqlite3.Row

    # Pre-count: how many rows + distinct series_ids match each pattern?
    print("\n=== Pre-cleanup audit ===")
    total_rows = 0
    total_sids = set()
    for pat in LEGACY_PATTERNS:
        rows = conn.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT series_id) AS sids "
            "FROM time_series WHERE series_id LIKE ?",
            (pat,),
        ).fetchone()
        n, sids = rows["n"], rows["sids"]
        print(f"  {pat:<28s} | {n:>7,d} rows | {sids:>4d} distinct series_ids")
        total_rows += n
        # Sample 3 ids per pattern for sanity
        sample = conn.execute(
            "SELECT DISTINCT series_id FROM time_series WHERE series_id LIKE ? LIMIT 3",
            (pat,),
        ).fetchall()
        for s in sample:
            total_sids.add(s["series_id"])
            print(f"      e.g. {s['series_id']}")

    if total_rows == 0:
        print("\nNothing to clean up — no legacy rows found. Exiting.")
        conn.close()
        return

    # Delete
    print("\n=== Deleting ===")
    deleted = 0
    for pat in LEGACY_PATTERNS:
        n = conn.execute(
            "DELETE FROM time_series WHERE series_id LIKE ?",
            (pat,),
        ).rowcount
        print(f"  {pat:<28s} | deleted {n:>7,d} rows")
        deleted += n
    conn.commit()
    print(f"  Total deleted: {deleted:,} rows")

    # Verify nothing remains
    print("\n=== Post-cleanup verification ===")
    for pat in LEGACY_PATTERNS:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM time_series WHERE series_id LIKE ?",
            (pat,),
        ).fetchone()
        print(f"  {pat:<28s} | {r['n']} rows remaining (expect 0)")

    # Show what gsheets_* series_ids remain — should be empty before next ingest,
    # or already populated under the new pattern if you ran update_data.py first.
    remaining = conn.execute(
        "SELECT COUNT(DISTINCT series_id) AS sids, COUNT(*) AS rows "
        "FROM time_series WHERE series_id LIKE 'gsheets_%'"
    ).fetchone()
    print(f"\n  All-pattern leftovers under gsheets_*: "
          f"{remaining['sids']} distinct ids, {remaining['rows']} rows.")

    conn.close()

    # Copy back
    print(f"\nCopying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print("\nDone. Next:")
    print("  python3.11 scripts/energy/update_data.py    # repopulate under new IDs")
    print("  python3.11 scripts/build_iran_monitor.py")


if __name__ == "__main__":
    main()
