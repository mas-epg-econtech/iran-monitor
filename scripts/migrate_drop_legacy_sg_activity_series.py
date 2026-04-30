#!/usr/bin/env python3
"""
One-off cleanup: drop rows for series_ids that are no longer referenced by
the Iran Monitor dashboard after the 2026-04-30 SG-Activity feedback pass.

Background:
  - Wholesale: replaced quarterly SingStat singstat_wti_* with monthly CEIC
    fwti_* (Foreign Wholesale Trade Index, 2017=100).
  - Chemicals IIP: replaced ipi_chemicals_cluster + singstat_ipi_specialty_chemicals
    with CEIC ipi_specialty_chemicals + ipi_other_chemicals.
  - F&B: replaced single food_and_beverage_sales (2025=100) with the 6-segment
    chained-volume F&B Services Index (fb_overall + 5 segments, 2017=100).
  - Petroleum trade card: dropped (legacy SingStat SITC-33-aggregate, replaced
    by SITC 333/334 partner breakouts on the Trade Exposure tab).
  - Construction: dropped ready-mix concrete (price + demand) per feedback.
  - IIP semiconductors: never wired into Iran Monitor; dropping for hygiene.

This script wipes the time_series rows for all dead series_ids. It does NOT
touch the indicators table — rows there are harmless and will be ignored by
the build (which iterates series from SERIES_REGISTRY).

Run from Iran Monitor root:
  python3 scripts/migrate_drop_legacy_sg_activity_series.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_LIVE = ROOT / "data" / "iran_monitor.db"
DB_SCRATCH = Path("/tmp") / "iran_monitor_drop_legacy.db"

DEAD_SERIES_IDS = [
    # Wholesale (quarterly SingStat → replaced by monthly CEIC fwti_* series)
    "singstat_wti_bunkering",
    "singstat_wti_ex_petroleum",
    # Chemicals IIP (replaced by CEIC Specialty + Other split)
    "ipi_chemicals_cluster",
    "singstat_ipi_specialty_chemicals",
    "ipi_semiconductors",
    # F&B (single 2025=100 series replaced by 6-segment chained-volume index)
    "food_and_beverage_sales",
    # Petroleum trade card (dropped — covered by Trade Exposure SITC 333/334)
    "singstat_imports_petroleum",
    "singstat_exports_petroleum",
    # Construction ready-mixed concrete (dropped per feedback)
    "ceic_constr_price_concrete",
    "ceic_constr_demand_concrete",
]


def main() -> None:
    if not DB_LIVE.exists():
        sys.exit(f"DB not found: {DB_LIVE}")

    print(f"[1/3] Staging DB at {DB_SCRATCH}")
    if DB_SCRATCH.exists():
        DB_SCRATCH.unlink()
    journal = DB_SCRATCH.with_suffix(DB_SCRATCH.suffix + "-journal")
    if journal.exists():
        journal.unlink()
    shutil.copy(DB_LIVE, DB_SCRATCH)

    print(f"\n[2/3] Wiping {len(DEAD_SERIES_IDS)} dead series from {DB_SCRATCH.name}")
    conn = sqlite3.connect(DB_SCRATCH)
    placeholders = ",".join("?" * len(DEAD_SERIES_IDS))
    pre_counts = dict(conn.execute(
        f"SELECT series_id, COUNT(*) FROM time_series "
        f"WHERE series_id IN ({placeholders}) GROUP BY series_id",
        DEAD_SERIES_IDS,
    ).fetchall())

    n_deleted = conn.execute(
        f"DELETE FROM time_series WHERE series_id IN ({placeholders})",
        DEAD_SERIES_IDS,
    ).rowcount
    conn.commit()
    print(f"      Deleted {n_deleted} rows total")
    for sid in DEAD_SERIES_IDS:
        print(f"      - {sid:<40} ({pre_counts.get(sid, 0)} rows wiped)")

    # Optional: also wipe their indicators rows for cleanliness
    n_ind = conn.execute(
        f"DELETE FROM indicators WHERE series_id IN ({placeholders})",
        DEAD_SERIES_IDS,
    ).rowcount
    conn.commit()
    print(f"      Deleted {n_ind} indicators rows")

    conn.close()

    print(f"\n[3/3] Copying {DB_SCRATCH.name} → {DB_LIVE}")
    shutil.copy(DB_SCRATCH, DB_LIVE)
    print("\nMigration complete. Rebuild with:")
    print("  python3 scripts/build_iran_monitor.py")


if __name__ == "__main__":
    main()
